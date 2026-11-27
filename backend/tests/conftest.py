"""모든 시험 공통 설정."""

import pytest

from app import main


@pytest.fixture(autouse=True)
def no_real_stt(monkeypatch):
    """진짜 Whisper를 서버 시작마다 불러오면 시험마다 수 초가 걸려서 기본으로 꺼 둡니다.
    받아쓰기 시험(test_voice.py)은 가짜 함수를 다시 끼워 넣습니다."""
    monkeypatch.setattr(main, "stt_service", None)


@pytest.fixture(autouse=True)
def no_agent_warm_up(monkeypatch):
    """서버 시작마다 Claude API에 연결하지 않도록 꺼 둡니다 (키가 있는 컴퓨터에서도 시험은 네트워크를 안 씀)."""
    from app import reasons

    monkeypatch.setattr(reasons, "agent_warm_up", lambda: None)


@pytest.fixture(autouse=True)
def no_real_voice_emotion(monkeypatch):
    """진짜 목소리 인코더를 서버 시작마다 불러오지 않게 꺼 둡니다. 목소리 시험(test_voice.py)은 가짜를 끼워 넣습니다."""
    monkeypatch.setattr(main, "voice_service", None)
