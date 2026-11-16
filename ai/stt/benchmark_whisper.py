# benchmark_whisper.py
# Whisper 모델 크기별로 5~10초 녹음의 받아쓰기 속도와 글자 오류율(CER)을 잽니다.
# 응답 5초 지표(녹음 끝 → 확인 화면)에 맞는 모델 크기를 고르기 위한 측정용입니다.
# 결과 파일은 저장소 밖(C:\work\moodwave_data\results\stt_benchmark)에 저장합니다.
import argparse
import csv
import os
import random
import re
import time
import wave

os.environ.setdefault("HF_HOME", r"C:\work\moodwave_data\hf_cache")  # 모델은 저장소 밖에 받기

import numpy as np
import torch
from transformers import pipeline

DATA_DIR = r"C:\work\moodwave_data\raw\감정 분류를 위한 대화 음성 데이터셋"
DEFAULT_OUT = r"C:\work\moodwave_data\results\stt_benchmark"
MODELS = ["tiny", "base", "small", "medium", "large-v3-turbo"]
TARGET_SR = 16000  # Whisper가 받는 소리 해상도


def load_wav_16k(path: str) -> np.ndarray:
    """wav를 읽어 16kHz float32로 바꿉니다. (scipy·ffmpeg 없이 numpy만 사용)"""
    with wave.open(path) as w:
        sr, width, ch = w.getframerate(), w.getsampwidth(), w.getnchannels()
        raw = w.readframes(w.getnframes())
    assert width == 2, f"16비트 wav만 지원합니다: {path}"
    x = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
    if ch > 1:
        x = x.reshape(-1, ch).mean(axis=1)  # 여러 채널이면 평균으로 하나로
    if sr == TARGET_SR:
        return x
    assert sr % TARGET_SR == 0, f"16kHz의 정수배만 지원합니다: {sr}"
    step = sr // TARGET_SR  # 48kHz면 3
    # 줄이기 전에 8kHz 위 소리를 걸러야 소리가 뭉개지지 않습니다(저역 통과 필터)
    n = np.arange(-48, 49)
    h = np.sinc(2 * (0.45 / step) * n) * np.hamming(len(n))
    x = np.convolve(x, h / h.sum(), mode="same")
    return x[::step].astype(np.float32)


def normalize(text: str) -> str:
    """띄어쓰기와 문장 부호를 빼고 비교합니다. (받아쓰기 띄어쓰기 차이는 감정에 영향이 적음)"""
    return re.sub(r"[^0-9A-Za-z가-힣]", "", text)


def cer(gold: str, pred: str) -> float:
    """글자 오류율 = 편집 거리 ÷ 정답 글자 수."""
    g, p = normalize(gold), normalize(pred)
    prev = list(range(len(p) + 1))
    for i, gc in enumerate(g, 1):
        cur = [i]
        for j, pc in enumerate(p, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (gc != pc)))
        prev = cur
    return prev[-1] / max(len(g), 1)


def pick_samples(n: int, seed: int, min_s: float, max_s: float) -> list[dict]:
    """세 CSV에서 무작위로 뽑되, 길이가 min_s~max_s초인 녹음만 씁니다."""
    rows = []
    for name in ("4차년도", "5차년도", "5차년도_2차"):
        with open(os.path.join(DATA_DIR, f"{name}.csv"), encoding="cp949") as f:
            for r in csv.DictReader(f):
                rows.append({"wav_id": r["wav_id"], "gold": r["발화문"],
                             "path": os.path.join(DATA_DIR, name, r["wav_id"] + ".wav")})
    random.Random(seed).shuffle(rows)  # seed 고정 → 매번 같은 문장
    picked = []
    for r in rows:
        if not os.path.exists(r["path"]):
            continue
        with wave.open(r["path"]) as w:
            sec = w.getnframes() / w.getframerate()
        if min_s <= sec <= max_s:
            picked.append({**r, "audio_sec": round(sec, 2)})
        if len(picked) == n:
            break
    return picked


def run(model: str, device: str, samples: list[dict]) -> list[dict]:
    gpu = device == "cuda"
    asr = pipeline("automatic-speech-recognition", model=f"openai/whisper-{model}",
                   device=0 if gpu else -1, dtype=torch.float16 if gpu else torch.float32)
    kw = {"language": "korean", "task": "transcribe"}
    asr({"raw": samples[0]["audio"], "sampling_rate": TARGET_SR}, generate_kwargs=kw)  # 준비 실행(시간에서 뺌)
    out = []
    for s in samples:
        t = time.perf_counter()
        pred = asr({"raw": s["audio"], "sampling_rate": TARGET_SR}, generate_kwargs=kw)["text"].strip()
        sec = time.perf_counter() - t
        out.append({"model": model, "device": device, "wav_id": s["wav_id"], "audio_sec": s["audio_sec"],
                    "sec": round(sec, 3), "cer": round(cer(s["gold"], pred), 4),
                    "gold": s["gold"], "pred": pred})
    del asr
    if gpu:
        torch.cuda.empty_cache()  # 다음 모델을 위해 GPU 메모리 비우기
    return out


def main():
    parser = argparse.ArgumentParser(description="Whisper 크기별 속도·CER 측정")
    parser.add_argument("--models", nargs="+", default=MODELS)
    parser.add_argument("--devices", nargs="+", default=["cuda", "cpu"])
    parser.add_argument("--n", type=int, default=30, help="측정할 녹음 수")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--out", default=DEFAULT_OUT, help="결과 폴더 (저장소 밖)")
    args = parser.parse_args()

    samples = pick_samples(args.n, args.seed, 5.0, 10.0)
    for s in samples:
        s["audio"] = load_wav_16k(s["path"])
    print(f"녹음 {len(samples)}개, 평균 길이 {np.mean([s['audio_sec'] for s in samples]):.1f}초")

    os.makedirs(args.out, exist_ok=True)
    rows, summary = [], []
    for device in args.devices:
        if device == "cuda" and not torch.cuda.is_available():
            print("GPU가 없어 cuda 측정은 건너뜁니다.")
            continue
        for model in args.models:
            res = run(model, device, samples)
            rows += res
            secs = [r["sec"] for r in res]
            line = {"model": model, "device": device, "mean_sec": round(float(np.mean(secs)), 3),
                    "max_sec": round(max(secs), 3), "cer": round(float(np.mean([r["cer"] for r in res])), 4)}
            summary.append(line)
            print(f"{device:4} {model:15} 평균 {line['mean_sec']:.3f}초  최대 {line['max_sec']:.3f}초  CER {line['cer']:.3f}")

    for name, data in (("summary.csv", summary), ("predictions.csv", rows)):
        with open(os.path.join(args.out, name), "w", encoding="utf-8-sig", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(data[0]))
            w.writeheader()
            w.writerows(data)
    print(f"결과 저장 위치: {args.out}")


if __name__ == "__main__":
    main()
