"""모든 시험 공통 설정."""

import pytest

from app import main


@pytest.fixture(autouse=True)
def no_real_stt(monkeypatch):
    """진짜 Whisper를 서버 시작마다 불러오면 시험마다 수 초가 걸려서 기본으로 꺼 둡니다.
    받아쓰기 시험(test_voice.py)은 가짜 함수를 다시 끼워 넣습니다."""
    monkeypatch.setattr(main, "stt_service", None)
