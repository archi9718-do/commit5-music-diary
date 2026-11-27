"""POST /api/records/voice 시험.

진짜 Whisper·감정 모델 대신 가짜 함수를 끼워 넣어 torch가 없는 컴퓨터에서도 돌아갑니다.
"""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from test_analyze import FAKE_PROBS, FakeEmotionService, count_records

from app import main


class FakeSttService:
    """ai.stt.service와 같은 이름의 함수 2개만 흉내 냅니다."""

    def __init__(self, text="오늘 좀 지쳤어", error=None):
        self.text, self.error = text, error

    def warm_up(self):
        pass

    def transcribe(self, audio_bytes):
        if self.error:
            raise self.error
        return self.text

    def is_uncertain(self, text):  # 진짜 규칙은 test_stt_filters.py가 시험함
        return text == "고마워요."


@pytest.fixture(autouse=True)
def isolated_env(monkeypatch, tmp_path):
    monkeypatch.setenv("MOODWAVE_DB_PATH", str(tmp_path / "voice_test.db"))
    monkeypatch.setattr(main, "emotion_service", FakeEmotionService())


def post_voice(client, data=b"fake-webm-bytes"):
    return client.post("/api/records/voice", content=data, headers={"Content-Type": "audio/webm"})


def test_voice_returns_same_format_as_analyze(monkeypatch):
    monkeypatch.setattr(main, "stt_service", FakeSttService())
    with TestClient(main.app) as client:
        res = post_voice(client)
        assert res.status_code == 201
        body = res.json()
        assert set(body) == {"record_id", "text", "probs", "emotion", "confidence"}
        assert body["text"] == "오늘 좀 지쳤어"  # 받아쓴 글이 그대로 저장·응답됨
        assert body["probs"] == FAKE_PROBS
        # 같은 날 다시 녹음하면 같은 기록을 덮어씀 (analyze와 같은 규칙)
        assert post_voice(client).json()["record_id"] == body["record_id"]
        assert count_records() == 1


@pytest.mark.parametrize(("stt", "data", "code"), [
    (FakeSttService(error=ValueError("녹음 파일을 읽지 못했습니다")), b"x", 400),  # 잘못된 녹음
    (FakeSttService(), b"", 400),  # 빈 본문
    (FakeSttService(), b"0" * (main.MAX_AUDIO_BYTES + 1), 413),  # 3MB 초과
    (FakeSttService(text="  "), b"x", 422),  # 무음 → 빈 받아쓰기
    (FakeSttService(text="가" * (main.MAX_RECORD_TEXT_LENGTH + 1)), b"x", 422),
    (FakeSttService(error=RuntimeError("GPU 오류")), b"x", 503),  # 모델 실행 오류
    (None, b"x", 503),  # 받아쓰기 패키지 없음
])
def test_voice_errors_save_nothing(monkeypatch, stt, data, code):
    monkeypatch.setattr(main, "stt_service", stt)
    with TestClient(main.app) as client:
        assert post_voice(client, data).status_code == code
        assert count_records() == 0  # 실패하면 기록이 생기지 않아야 함


def test_voice_503_when_emotion_model_missing(monkeypatch):
    monkeypatch.setattr(main, "stt_service", FakeSttService())
    monkeypatch.setattr(main, "emotion_service", None)
    with TestClient(main.app) as client:
        assert post_voice(client).status_code == 503
        assert count_records() == 0


@pytest.mark.parametrize("value", ["-1", "invalid"])
def test_voice_bad_content_length_is_rejected(monkeypatch, value):
    monkeypatch.setattr(main, "stt_service", FakeSttService())
    with TestClient(main.app) as client:
        assert client.post("/api/records/voice", content=b"audio", headers={"Content-Length": value}).status_code == 400
        assert count_records() == 0


def test_voice_checks_body_size_independently_of_header(monkeypatch):
    monkeypatch.setattr(main, "stt_service", FakeSttService())
    with TestClient(main.app) as client:
        response = client.post(
            "/api/records/voice",
            content=iter([b"a" * main.MAX_AUDIO_BYTES, b"b"]),
            headers={"Content-Length": "1"},
        )
        assert response.status_code == 413
        assert count_records() == 0


def test_decode_error_does_not_expose_internal_details(monkeypatch):
    monkeypatch.setattr(main, "stt_service", FakeSttService(error=ValueError("private decoder details")))
    with TestClient(main.app) as client:
        response = post_voice(client, b"invalid")
        assert response.status_code == 400
        assert "private decoder details" not in response.json()["detail"]



def test_uncertain_transcript_is_shown_first_and_saves_nothing(monkeypatch, tmp_path):
    # 건호 리뷰(#28): 잡음이 "고마워요."로 받아써지면 확인 전에 오늘 일기·추천곡이 덮어써지던 문제
    monkeypatch.setenv("MOODWAVE_SCORES_CSV", str(Path(__file__).parent / "fixtures" / "sample_song_scores.csv"))
    stt = FakeSttService(text="고마워요.")
    monkeypatch.setattr(main, "stt_service", stt)  # 서버가 켜질 때 받아쓰기가 준비돼 있어야 함
    with TestClient(main.app) as client:
        record_id = client.post("/api/records", json={"text": "오늘의 진짜 일기"}).json()["record_id"]
        assert client.post("/api/recommendations",
                           json={"record_id": record_id, "confirmed_emotion": "좋음"}).status_code == 200
        before = client.get(f"/api/records/{record_id}/lp").json()

        response = post_voice(client)
        assert response.status_code == 422
        detail = response.json()["detail"]
        assert detail["code"] == "uncertain_transcript" and detail["text"] == "고마워요."

        after = client.get(f"/api/records/{record_id}/lp").json()
    assert after["text"] == "오늘의 진짜 일기"
    assert [s["song_id"] for s in after["songs"]] == [s["song_id"] for s in before["songs"]]
    assert count_records() == 1


# --- 목소리 감정 합치기 (Task 7) -------------------------------------------
VOICE_PROBS = {"좋음": 0.9, "무난함": 0.05, "가라앉음": 0.03, "예민함": 0.02}


class FakeVoiceService:
    """ai.voice_emotion.service와 같은 이름의 함수 2개만 흉내 냅니다."""

    def __init__(self, warm_up_error=None, combine_error=None):
        self.warm_up_error, self.combine_error = warm_up_error, combine_error
        self.calls = 0

    def warm_up(self):
        if self.warm_up_error:
            raise self.warm_up_error

    def combine(self, result, audio_bytes):
        self.calls += 1
        if self.combine_error:
            raise self.combine_error
        return {**result, "probs": VOICE_PROBS, "emotion": "좋음", "confidence": "높음"}


def saved_emotion():
    from app.db import connect

    con = connect()
    try:
        return con.execute("SELECT emotion_pred FROM tb_record").fetchone()[0]
    finally:
        con.close()


def test_voice_fusion_saved_when_ready(monkeypatch):
    monkeypatch.setattr(main, "stt_service", FakeSttService())
    monkeypatch.setattr(main, "voice_service", FakeVoiceService())
    with TestClient(main.app) as client:
        res = post_voice(client)
        assert res.status_code == 201
        assert res.json()["emotion"] == "좋음" and res.json()["probs"] == VOICE_PROBS
        assert saved_emotion() == "좋음"


@pytest.mark.parametrize("voice", [
    FakeVoiceService(combine_error=RuntimeError("인코더 오류")),  # 합치기 중 오류 → 글 결과 유지
    FakeVoiceService(warm_up_error=RuntimeError("목소리 감정 꺼짐 판정")),  # meta.json enabled=false
    None,  # 패키지 없음
])
def test_voice_unavailable_keeps_text_result(monkeypatch, voice):
    monkeypatch.setattr(main, "stt_service", FakeSttService())
    monkeypatch.setattr(main, "voice_service", voice)
    with TestClient(main.app) as client:
        res = post_voice(client)
        assert res.status_code == 201
        assert res.json()["probs"] == FAKE_PROBS
        assert saved_emotion() == "예민함"


def test_text_records_never_use_voice(monkeypatch):
    voice = FakeVoiceService()
    monkeypatch.setattr(main, "voice_service", voice)
    with TestClient(main.app) as client:
        assert client.post("/api/records/analyze", json={"text": "오늘 좀 지쳤어"}).status_code == 201
    assert voice.calls == 0
