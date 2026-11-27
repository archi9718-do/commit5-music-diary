# service.py
# 서버가 부르는 목소리 감정 진입점: warm_up()과 combine(). 녹음 → 인코더 → 분류기 → 글 결과와 섞기.
# 켤지 말지는 evaluate.py가 쓴 meta.json의 enabled로 정합니다.
import json
import os
from pathlib import Path

import numpy as np
import torch
from ai.emotion.emotion_mapper import EMOTIONS
from ai.stt.service import decode_audio

from .features import ENCODERS, SR, embed, load_encoder
from .fuse import fuse
from .train import MODEL_DIR, predict_head

_MODEL: dict = {}


def get_model_dir() -> str:
    return os.environ.get("MOODWAVE_VOICE_MODEL_DIR", MODEL_DIR)


def warm_up() -> None:
    """인코더·분류기를 한 번만 읽고 1초 무음으로 미리 돌려 둡니다."""
    folder = Path(get_model_dir())
    for name in ("meta.json", "head.pt"):
        if not (folder / name).is_file():
            raise FileNotFoundError(f"목소리 감정 모델 파일이 없습니다: {folder / name}")
    meta = json.loads((folder / "meta.json").read_text(encoding="utf-8"))
    if not meta.get("enabled"):
        raise RuntimeError("목소리 감정 꺼짐 판정")
    if meta["encoder"] not in ENCODERS or list(meta["classes"]) != list(EMOTIONS):
        raise RuntimeError("meta.json의 인코더·감정 순서가 코드와 다릅니다")

    extractor, model = load_encoder(meta["encoder"])
    head = torch.nn.Linear(model.config.hidden_size, len(EMOTIONS))
    head.load_state_dict(torch.load(folder / "head.pt"))
    head.eval()
    _MODEL.update(extractor=extractor, model=model, head=head, w=float(meta["w"]))
    _voice_probs(np.zeros(SR, dtype=np.float32))


def _voice_probs(audio_16k: np.ndarray) -> dict:
    x = embed(audio_16k, _MODEL["extractor"], _MODEL["model"])
    return dict(zip(EMOTIONS, map(float, predict_head(_MODEL["head"], x[None])[0])))


def combine(result: dict, audio_bytes: bytes) -> dict:
    """analyze_text 결과에 목소리 확률을 섞은 새 결과. warm_up 전이면 RuntimeError."""
    if not _MODEL:
        raise RuntimeError("목소리 감정 모델을 아직 불러오지 않았습니다")
    return fuse(result, _voice_probs(decode_audio(audio_bytes)), _MODEL["w"])
