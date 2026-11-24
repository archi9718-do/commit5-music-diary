"""받아쓰기 무음·잡음 거름 시험. 모델을 불러오지 않고 판단 함수만 봅니다.

11/24 실제 크롬 녹음 9개로 다시 맞춘 값: 무음 비율 2.8, TV 소리 5.9, 작게 말하기 11.5.
"""

import sys
from pathlib import Path

import numpy as np
import pytest

pytest.importorskip("av")  # 받아쓰기 패키지가 없는 컴퓨터에서는 건너뜀

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from ai.stt.service import TARGET_SR, has_speech, is_hallucination, is_uncertain


def burst_signal(ratio: float) -> np.ndarray:
    """조용한 바탕에 큰 조각이 섞인 3초 신호. 큰 쪽 ÷ 조용한 쪽 RMS가 정확히 ratio.

    잡음은 조각마다 RMS가 흔들려 비율이 어긋나므로, 30ms 조각에 딱 맞는 400Hz 사인파를 씁니다.
    """
    t = np.arange(TARGET_SR * 3) / TARGET_SR
    amplitude = np.full(t.size, 0.001)
    amplitude[TARGET_SR : TARGET_SR + TARGET_SR // 2] *= ratio
    return (amplitude * np.sin(2 * np.pi * 400 * t)).astype(np.float32)


@pytest.mark.parametrize("ratio", [2.8, 5.9])
def test_chrome_silence_and_tv_ratios_are_not_speech(ratio):
    assert not has_speech(burst_signal(ratio))


def test_quiet_speech_ratio_is_speech():
    assert has_speech(burst_signal(11.5))


# 건호 리뷰(#28): 문구가 "들어 있기만" 해도 막으면 정상 일기도 막힘 → 실제로 관찰된 문장 전체만 막음
@pytest.mark.parametrize("text", [
    "구독과 좋아요 부탁드립니다.", "구독과 좋아요 부탁드립니다", "시청해 주셔서 감사합니다", "시청해주셔서 감사합니다!",
    "한글자막 제공 및 자막 편집",
])
def test_known_whisper_inventions_are_dropped(text):
    assert is_hallucination(text)


@pytest.mark.parametrize("text", [
    "피곤해",  # 짧은 정상 발화
    "오늘은 좋은 일이 생겨서 기분이 좋았다",
    "친구가 좋아요 부탁한다고 해서 웃었어요",  # 막는 문구가 들어간 정상 발화
    "영화 자막이 틀려서 웃겼어",
    "유튜브에서 구독과 좋아요 부탁드립니다 소리를 백 번 들었어",
    "친구가 고마워요 라고 해서 기뻤어", "오늘 다들 수고하셨습니다 하고 퇴근했어",
    "고마워요.", "감사합니다", "수고하셨습니다.",  # 한 마디 인사말은 막지 않음 (아래 is_uncertain으로 감정을 직접 고르게 함)
])
def test_real_diary_text_is_kept(text):
    assert not is_hallucination(text)


@pytest.mark.parametrize(("text", "uncertain"), [
    ("고마워요.", True), ("감사합니다", True), ("수고하셨습니다!", True),
    ("피곤해", False), ("친구가 고마워요 라고 해서 기뻤어", False), ("오늘은 좋은 일이 생겨서 기분이 좋았다", False),
])
def test_greeting_only_is_uncertain(text, uncertain):
    # 잡음에서 지어낸 글인지 실제 한 마디인지 글로는 구분할 수 없음 → 확신도를 낮춰 사용자가 감정을 고르게 함
    assert is_uncertain(text) is uncertain
