"""POST /api/records/analyze 시험.

진짜 감정 모델 대신 가짜 감정 함수를 끼워 넣어서 시험합니다.
그래서 torch·모델 폴더가 없는 컴퓨터에서도 이 시험은 그대로 돌아갑니다.
"""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import main
from app.db import connect

FIXTURE = Path(__file__).parent / "fixtures" / "sample_song_scores.csv"

FAKE_PROBS = {"좋음": 0.02, "무난함": 0.03, "가라앉음": 0.33, "예민함": 0.62}


class FakeEmotionService:
    """ai.emotion.service와 같은 이름의 함수 2개만 흉내 냅니다."""

    def __init__(self, warm_up_error=None, analyze_error=None):
        self.warm_up_error = warm_up_error
        self.analyze_error = analyze_error

    def warm_up(self):
        if self.warm_up_error:
            raise self.warm_up_error

    def analyze_text(self, text, record_id=None):
        if self.analyze_error:
            raise self.analyze_error
        if not text.strip():
            raise ValueError("감정을 분석할 글이 비어 있습니다.")
        return {"record_id": record_id, "text": text, "probs": dict(FAKE_PROBS),
                "emotion": "예민함", "confidence": "높음"}


@pytest.fixture(autouse=True)
def isolated_env(monkeypatch, tmp_path):
    """시험마다 새 DB 파일과 시험용 점수표를 씁니다."""
    monkeypatch.setenv("MOODWAVE_DB_PATH", str(tmp_path / "analyze_test.db"))
    monkeypatch.setenv("MOODWAVE_SCORES_CSV", str(FIXTURE))
    monkeypatch.setenv("MOODWAVE_RECOMMEND_SCOPE", "DEAM")


def count_records():
    con = connect()
    try:
        return con.execute("SELECT COUNT(*) FROM tb_record").fetchone()[0]
    finally:
        con.close()


def test_analyze_then_recommend_then_lp(monkeypatch):
    """글 → 감정(자동) → 사용자 확인 감정으로 3곡 → 판 조회까지 한 번에 확인."""
    monkeypatch.setattr(main, "emotion_service", FakeEmotionService())
    with TestClient(main.app) as client:
        res = client.post("/api/records/analyze", json={"text": "오늘 좀 지쳤어"})
        assert res.status_code == 201
        body = res.json()
        # 감정 결과 양식 그대로인지 확인
        assert set(body) == {"record_id", "text", "probs", "emotion", "confidence"}
        assert body["record_id"] > 0
        assert body["text"] == "오늘 좀 지쳤어"
        assert body["probs"] == FAKE_PROBS
        assert body["emotion"] == "예민함"
        assert body["confidence"] == "높음"

        # 사용자가 예측과 다른 감정을 골랐다고 가정 → 확인된 감정으로 추천
        rec = client.post("/api/recommendations",
                          json={"record_id": body["record_id"], "confirmed_emotion": "가라앉음"})
        assert rec.status_code == 200
        assert len(rec.json()["songs"]) == 3

        lp = client.get(f"/api/records/{body['record_id']}/lp")
        assert lp.status_code == 200
        assert lp.json()["confirmed_emotion"] == "가라앉음"
        assert len(lp.json()["songs"]) == 3


def test_empty_text_returns_422_and_saves_nothing(monkeypatch):
    monkeypatch.setattr(main, "emotion_service", FakeEmotionService())
    with TestClient(main.app) as client:
        before = count_records()
        res = client.post("/api/records/analyze", json={"text": "   "})
        assert res.status_code == 422
        assert count_records() == before  # 기록이 생기지 않아야 함


def test_model_missing_returns_503_but_other_api_work(monkeypatch):
    """모델 폴더가 없는 컴퓨터: 서버는 켜지고, 분석 경로만 503."""
    monkeypatch.setattr(main, "emotion_service",
                        FakeEmotionService(warm_up_error=FileNotFoundError("모델 폴더 없음")))
    with TestClient(main.app) as client:
        assert client.get("/health").status_code == 200
        before = count_records()
        assert client.post("/api/records/analyze", json={"text": "테스트"}).status_code == 503
        assert count_records() == before
        assert client.post("/api/records", json={"text": "테스트"}).status_code == 201  # 기존 경로는 정상


def test_package_missing_returns_503(monkeypatch):
    """torch·AI 패키지가 아예 없는 컴퓨터."""
    monkeypatch.setattr(main, "emotion_service", None)
    with TestClient(main.app) as client:
        assert client.post("/api/records/analyze", json={"text": "테스트"}).status_code == 503


@pytest.mark.parametrize("text", ["", "   "])
def test_empty_text_returns_422_even_without_model(monkeypatch, text):
    """모델·패키지가 없어도 빈 글은 503이 아니라 422 (입력 검사가 먼저)."""
    monkeypatch.setattr(main, "emotion_service", None)
    with TestClient(main.app) as client:
        before = count_records()
        assert client.post("/api/records/analyze", json={"text": text}).status_code == 422
        assert count_records() == before


def test_too_long_text_returns_422_even_without_model(monkeypatch):
    """2,000자 초과도 모델 상태와 상관없이 422."""
    monkeypatch.setattr(main, "emotion_service", None)
    with TestClient(main.app) as client:
        assert client.post("/api/records/analyze", json={"text": "가" * 2001}).status_code == 422


def test_analyze_error_returns_503_and_saves_nothing(monkeypatch):
    """모델 실행 중 오류: 아무것도 저장하지 않음."""
    monkeypatch.setattr(main, "emotion_service",
                        FakeEmotionService(analyze_error=RuntimeError("GPU 오류")))
    with TestClient(main.app) as client:
        before = count_records()
        assert client.post("/api/records/analyze", json={"text": "테스트"}).status_code == 503
        assert count_records() == before


def test_bad_result_format_returns_500_and_saves_nothing(monkeypatch):
    """모델 결과 양식이 깨진 경우(예: 감정 이름 오타): 저장하지 않음."""
    class BrokenService(FakeEmotionService):
        def analyze_text(self, text, record_id=None):
            return {"record_id": None, "text": text, "probs": {"좋음": 1.0},
                    "emotion": "좋음", "confidence": "높음"}

    monkeypatch.setattr(main, "emotion_service", BrokenService())
    with TestClient(main.app) as client:
        before = count_records()
        assert client.post("/api/records/analyze", json={"text": "테스트"}).status_code == 500
        assert count_records() == before
