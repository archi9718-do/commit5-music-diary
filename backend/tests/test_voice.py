"""POST /api/records/voice 시험.

진짜 Whisper·감정 모델 대신 가짜 함수를 끼워 넣어 torch가 없는 컴퓨터에서도 돌아갑니다.
"""

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


def test_greeting_only_voice_asks_user_to_pick_emotion(monkeypatch):
    # 잡음에서 지어낸 "고마워요."일 수도 있어서 막지 않고 확신도를 "낮음"으로 → 화면이 감정 버튼 4개를 보여 줌
    monkeypatch.setattr(main, "stt_service", FakeSttService(text="고마워요."))
    with TestClient(main.app) as client:
        response = post_voice(client)
    assert response.status_code == 201
    assert response.json()["confidence"] == "낮음" and response.json()["text"] == "고마워요."
