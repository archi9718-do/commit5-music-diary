# features.py
# 고정한 음성 인코더(학습하지 않음)로 녹음마다 768차원 특징 하나를 뽑아 저장합니다.
# 특징 = 마지막 층 출력의 시간 평균. 서비스처럼 앞 10초만 씁니다.
# 결과는 저장소 밖 FEATURE_DIR/{인코더}.npz. 끊겨도 다시 실행하면 이어서 합니다.
import os

import numpy as np
import torch

if __package__:
    from .split import FEATURE_DIR, SPLIT_CSV
else:
    from split import FEATURE_DIR, SPLIT_CSV

HF_CACHE = r"C:\work\moodwave_data\hf_cache"
ENCODERS = {"wav2vec2": "facebook/wav2vec2-base", "hubert": "facebook/hubert-base-ls960"}
SR = 16000
MAX_SAMPLES = 10 * SR  # ai/stt/service.py MAX_SEC = 10과 같게
SAVE_EVERY = 500


def load_encoder(name: str):
    """(feature_extractor, model)을 캐시에서만 읽습니다. 인터넷에서 받지 않습니다."""
    os.environ.setdefault("HF_HOME", HF_CACHE)
    from transformers import AutoFeatureExtractor, AutoModel

    repo = ENCODERS[name]
    # 서버에서는 글·받아쓰기 모델이 transformers를 먼저 불러와 HF_HOME이 안 먹으므로 경로를 직접 넘김
    cache = os.environ.get("MOODWAVE_HF_CACHE", os.path.join(HF_CACHE, "hub"))  # ai/stt/service.py와 같은 변수
    extractor = AutoFeatureExtractor.from_pretrained(repo, cache_dir=cache, local_files_only=True)
    model = AutoModel.from_pretrained(repo, cache_dir=cache, local_files_only=True)
    model.eval()
    return extractor, model


def embed(audio_16k: np.ndarray, extractor, model) -> np.ndarray:
    """16kHz 소리 → (768,) float32."""
    inputs = extractor(audio_16k[:MAX_SAMPLES], sampling_rate=SR, return_tensors="pt")
    with torch.no_grad():
        hidden = model(inputs.input_values).last_hidden_state[0]
    return hidden.mean(0).numpy().astype(np.float32)


def _save(path, X, paths):
    tmp = path.with_suffix(".tmp.npz")
    np.savez(tmp, X=np.stack(X), wav_path=np.array(paths))
    os.replace(tmp, path)  # 저장 중에 끊겨도 이전 파일은 남음


def main() -> None:
    import argparse
    import csv
    import time

    from ai.stt.benchmark_whisper import load_wav_16k

    parser = argparse.ArgumentParser(description="나누기 표의 녹음마다 인코더 특징을 뽑아 저장")
    parser.add_argument("--encoder", choices=sorted(ENCODERS), required=True)
    args = parser.parse_args()

    with open(SPLIT_CSV, encoding="utf-8", newline="") as f:
        todo = [r["wav_path"] for r in csv.DictReader(f)]
    out = FEATURE_DIR / f"{args.encoder}.npz"
    X, paths = [], []
    if out.exists():
        old = np.load(out)
        X, paths = list(old["X"]), list(old["wav_path"])
    done = set(paths)
    todo = [p for p in todo if p not in done]
    print(f"{args.encoder}: 이미 {len(done)}개, 남은 {len(todo)}개 → {out}", flush=True)

    extractor, model = load_encoder(args.encoder)
    start = time.perf_counter()
    for i, path in enumerate(todo, start=1):
        X.append(embed(load_wav_16k(path), extractor, model))
        paths.append(path)
        if i % SAVE_EVERY == 0 or i == len(todo):
            _save(out, X, paths)
            rate = (time.perf_counter() - start) / i
            print(f"  {i}/{len(todo)} ({rate:.2f}초/개, 남은 약 {rate * (len(todo) - i) / 60:.0f}분)", flush=True)
    print(f"끝: {len(paths)}개, {(time.perf_counter() - start) / 60:.1f}분", flush=True)


if __name__ == "__main__":
    main()
