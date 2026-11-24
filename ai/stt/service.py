# service.py
# MoodWave 받아쓰기(STT)의 "입구" 파일입니다. 글 감정의 ai/emotion/service.py와 같은 모양입니다.
# 서버는 warm_up()과 transcribe()만 부릅니다.
# 녹음은 메모리(bytes)로만 받고 디스크에 쓰지 않습니다 → 처리 뒤 원본이 남지 않습니다.
import io
import os
import re
from itertools import chain

import av
import numpy as np
import torch
from huggingface_hub import snapshot_download
from transformers import pipeline

# 모델은 저장소 밖에 받기. 서버에서는 다른 모듈이 transformers를 먼저 불러
# HF_HOME 환경 변수가 안 먹으므로, 받는 폴더를 직접 지정합니다.
HF_CACHE = os.environ.get("MOODWAVE_HF_CACHE", r"C:\work\moodwave_data\hf_cache\hub")
TARGET_SR = 16000  # Whisper가 받는 소리 해상도
MAX_SEC = 10  # 기획 5~10초. 화면도 10초에서 멈춤(11/19 결정). 넘으면 앞 10초만 씀
GEN_KW = {"language": "korean", "task": "transcribe"}
# 무음·잡음이면 Whisper가 글을 지어냄(11/19 확인: 무음 → "한글자막 제공 및 ...", 잡음 → "감사합니다.")
# 두 겹으로 막음: (1) 소리 크기 (2) 자주 지어내는 문구
# 소리 크기만으로는 못 가름: 데이터셋에 크기 0.0006인 녹음도 CER 0%로 받아써짐.
# 대신 "큰 조각 ÷ 조용한 조각" 비율을 봄. 말은 쉼이 있어 크고, 고른 잡음은 1에 가까움.
# 11/19 측정: 말소리 200개 최소 3.3 / 하위 5% 17.1, 고른 잡음 1.1
# 11/24 실제 크롬 녹음: 무음 2.8, TV 소리 5.9, 작게 말하기 11.5 → 6.0 (크롬 잡음 억제로 조용한 쪽이 거의 0이 됨)
# 키보드 18.5, 선풍기 34.3은 비율로 못 가름(작게 말하기보다 큼) → 아래 문구 목록이 막음
MIN_SPEECH_RATIO = 6.0
# 지어낸 글은 실제로 관찰된 "문장 전체"만 막음 (띄어쓰기·문장부호는 무시). 문구가 들어 있기만 한 정상 일기는 통과
# (11/24 건호 리뷰: "친구가 좋아요 부탁한다고 해서 웃었어요"가 막히던 문제)
HALLUCINATION_SENTENCES = ("구독과좋아요부탁드립니다", "시청해주셔서감사합니다")
HALLUCINATION_PREFIXES = ("한글자막",)  # 무음에서 "한글자막 제공 및 ..."처럼 뒤가 바뀌며 나옴
# 인사말 한 마디: 잡음에서 지어낸 것인지 실제로 말한 것인지 글로는 구분할 수 없음 → 막지 않고 감정을 사용자가 고르게 함
GREETING_ONLY = ("감사합니다", "수고하셨습니다", "고마워요")

_asr = None


def get_model_name() -> str:
    """S3 측정 기준: GPU는 large-v3-turbo(0.2초, CER 1.7%), CPU는 base(1.6초, CER 7.0%)."""
    default = "large-v3-turbo" if torch.cuda.is_available() else "base"
    return os.environ.get("MOODWAVE_STT_MODEL", default)


def load_model():
    """모델을 한 번만 불러옵니다."""
    global _asr
    if _asr is None:
        gpu = torch.cuda.is_available()
        path = snapshot_download(f"openai/whisper-{get_model_name()}", cache_dir=HF_CACHE)  # 있으면 그대로 씀
        _asr = pipeline("automatic-speech-recognition", model=path,
                        device=0 if gpu else -1, dtype=torch.float16 if gpu else torch.float32)
    return _asr


def decode_audio(audio_bytes: bytes) -> np.ndarray:
    """wav·webm(opus)·m4a 등 무엇이든 16kHz 한 채널 float32로 바꿉니다. (av 안의 ffmpeg 사용)"""
    resampler = av.AudioResampler(format="flt", layout="mono", rate=TARGET_SR)
    chunks = []
    remaining = MAX_SEC * TARGET_SR
    with av.open(io.BytesIO(audio_bytes)) as container:
        if not container.streams.audio:
            raise ValueError("녹음에서 소리를 찾지 못했습니다.")
        # 10초를 채우면 디코더도 닫아 압축 파일의 나머지를 펼치지 않습니다.
        for frame in chain(container.decode(audio=0), (None,)):
            for converted in resampler.resample(frame):
                samples = converted.to_ndarray().reshape(-1)[:remaining]
                chunks.append(samples)
                remaining -= samples.size
                if not remaining:
                    return np.concatenate(chunks)
    if not chunks:
        raise ValueError("녹음에서 소리를 찾지 못했습니다.")
    return np.concatenate(chunks)


def warm_up() -> None:
    """서버가 켜질 때 한 번 불러, 모델을 미리 읽고 GPU를 데워 둡니다."""
    load_model()({"raw": np.zeros(TARGET_SR, dtype=np.float32), "sampling_rate": TARGET_SR},
                 generate_kwargs=GEN_KW)


def transcribe(audio_bytes: bytes) -> str:
    """녹음 파일 내용(bytes)을 받아 받아쓴 글을 돌려줍니다. 말소리가 없으면 빈 글("")."""
    if not audio_bytes:
        raise ValueError("녹음 파일이 비어 있습니다.")
    try:
        audio = decode_audio(audio_bytes)
    except av.error.FFmpegError as e:
        raise ValueError(f"녹음 파일을 읽지 못했습니다: {e}") from e
    if not has_speech(audio):
        return ""  # 말소리 없음: 모델을 돌리지 않음
    text = load_model()({"raw": audio, "sampling_rate": TARGET_SR}, generate_kwargs=GEN_KW)["text"].strip()
    return "" if is_hallucination(text) else text


def _compact(text: str) -> str:
    return re.sub(r"[\s.,!?~]", "", text)


def is_hallucination(text: str) -> bool:
    """무음·잡음에서 Whisper가 지어낸 것으로 확인된 문장 전체면 True."""
    # ponytail: 관찰된 문장만 막음(11/24 크롬 녹음). 새 문장이 또 나오면 음성 구간 검출(VAD)로 바꾸기
    compact = _compact(text)
    return compact in HALLUCINATION_SENTENCES or compact.startswith(HALLUCINATION_PREFIXES)


def is_uncertain(text: str) -> bool:
    """인사말 한 마디만 받아썼으면 True. 서버는 확신도를 "낮음"으로 낮춰 사용자가 감정을 고르게 합니다."""
    return _compact(text) in GREETING_ONLY


def has_speech(audio: np.ndarray) -> bool:
    """30ms 조각별 소리 크기에서 큰 쪽 5% ÷ 조용한 쪽 10% 비율로 말소리 여부를 봅니다."""
    # ponytail: 무음·고른 잡음만 가름(11/24 크롬 녹음으로 맞춤). 키보드·선풍기는 is_hallucination이 막음
    n = 480  # 16kHz에서 30ms
    if len(audio) < n:
        return False
    rms = np.sqrt((audio[: len(audio) // n * n].reshape(-1, n) ** 2).mean(axis=1))
    loud, quiet = np.percentile(rms, 95), np.percentile(rms, 10)
    return loud > 1e-5 and loud / max(quiet, 1e-7) >= MIN_SPEECH_RATIO  # 1e-5 미만은 완전 무음


if __name__ == "__main__":
    # 확인용: python ai/stt/service.py 녹음파일 [정답 문장]
    import sys
    import time

    # 말소리 판단 자체 점검: 무음·고른 잡음은 False
    rng = np.random.default_rng(0)
    assert not has_speech(np.zeros(TARGET_SR * 3, dtype=np.float32))
    assert not has_speech(rng.normal(0, 0.01, TARGET_SR * 3).astype(np.float32))

    path = sys.argv[1]
    with open(path, "rb") as f:
        data = f.read()
    assert has_speech(decode_audio(data)), "말소리가 없다고 판단했습니다"

    t = time.perf_counter()
    warm_up()
    print(f"모델 {get_model_name()} 미리 불러오기: {time.perf_counter() - t:.1f}초")

    t = time.perf_counter()
    text = transcribe(data)
    print(f"받아쓰기: {text}")
    print(f"처리 시간: {time.perf_counter() - t:.2f}초 (녹음 {len(decode_audio(data)) / TARGET_SR:.1f}초)")
    if len(sys.argv) > 2:
        from benchmark_whisper import cer  # 같은 폴더의 글자 오류율 함수 재사용

        err = cer(sys.argv[2], text)
        assert err < 0.2, f"글자 오류율이 너무 높습니다: {err:.1%}"
        print(f"정답 문장과 비교: CER {err:.1%} → 통과")

    try:
        transcribe(b"not audio")
    except ValueError as e:
        print(f"[잘못된 파일 거절 확인] {e}")
