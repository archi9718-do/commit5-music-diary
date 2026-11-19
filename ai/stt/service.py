# service.py
# MoodWave 받아쓰기(STT)의 "입구" 파일입니다. 글 감정의 ai/emotion/service.py와 같은 모양입니다.
# 서버는 warm_up()과 transcribe()만 부릅니다.
# 녹음은 메모리(bytes)로만 받고 디스크에 쓰지 않습니다 → 처리 뒤 원본이 남지 않습니다.
import io
import os

os.environ.setdefault("HF_HOME", r"C:\work\moodwave_data\hf_cache")  # 모델은 저장소 밖에 받기

import av
import numpy as np
import torch
from transformers import pipeline

TARGET_SR = 16000  # Whisper가 받는 소리 해상도
MAX_SEC = 10  # 기획 5~10초. 화면도 10초에서 멈춤(11/19 결정). 넘으면 앞 10초만 씀
GEN_KW = {"language": "korean", "task": "transcribe"}

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
        _asr = pipeline("automatic-speech-recognition", model=f"openai/whisper-{get_model_name()}",
                        device=0 if gpu else -1, dtype=torch.float16 if gpu else torch.float32)
    return _asr


def decode_audio(audio_bytes: bytes) -> np.ndarray:
    """wav·webm(opus)·m4a 등 무엇이든 16kHz 한 채널 float32로 바꿉니다. (av 안의 ffmpeg 사용)"""
    resampler = av.AudioResampler(format="flt", layout="mono", rate=TARGET_SR)
    chunks = []
    with av.open(io.BytesIO(audio_bytes)) as container:
        for frame in container.decode(audio=0):
            chunks += [f.to_ndarray().reshape(-1) for f in resampler.resample(frame)]
    chunks += [f.to_ndarray().reshape(-1) for f in resampler.resample(None)]  # 남은 소리 비우기
    if not chunks:
        raise ValueError("녹음에서 소리를 찾지 못했습니다.")
    return np.concatenate(chunks)[: MAX_SEC * TARGET_SR]


def warm_up() -> None:
    """서버가 켜질 때 한 번 불러, 모델을 미리 읽고 GPU를 데워 둡니다."""
    load_model()({"raw": np.zeros(TARGET_SR, dtype=np.float32), "sampling_rate": TARGET_SR},
                 generate_kwargs=GEN_KW)


def transcribe(audio_bytes: bytes) -> str:
    """녹음 파일 내용(bytes)을 받아 받아쓴 글을 돌려줍니다."""
    if not audio_bytes:
        raise ValueError("녹음 파일이 비어 있습니다.")
    try:
        audio = decode_audio(audio_bytes)
    except av.error.FFmpegError as e:
        raise ValueError(f"녹음 파일을 읽지 못했습니다: {e}") from e
    text = load_model()({"raw": audio, "sampling_rate": TARGET_SR}, generate_kwargs=GEN_KW)["text"]
    return text.strip()


if __name__ == "__main__":
    # 확인용: python ai/stt/service.py 녹음파일 [정답 문장]
    import sys
    import time

    path = sys.argv[1]
    with open(path, "rb") as f:
        data = f.read()

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
