"""목소리 특징 추출 시험. 진짜 인코더 대신 가짜를 써서 모델 파일 없이 돌아갑니다."""

import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

torch = pytest.importorskip("torch")

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from ai.voice_emotion.features import MAX_SAMPLES, embed


class FakeExtractor:
    def __call__(self, audio, sampling_rate, return_tensors):
        assert sampling_rate == 16000 and return_tensors == "pt"
        return SimpleNamespace(input_values=torch.from_numpy(np.asarray(audio, np.float32))[None])


class FakeModel:
    seen_len = None

    def __call__(self, input_values):
        self.seen_len = input_values.shape[1]
        frames = input_values.shape[1] // 320 + 1
        hidden = torch.arange(frames, dtype=torch.float32)[None, :, None].repeat(1, 1, 768)
        return SimpleNamespace(last_hidden_state=hidden)


def test_features_truncate_and_short():
    model = FakeModel()
    out = embed(np.zeros(16000 * 15, np.float32), FakeExtractor(), model)
    assert out.shape == (768,) and out.dtype == np.float32
    assert model.seen_len == MAX_SAMPLES == 16000 * 10
    assert embed(np.zeros(8000, np.float32), FakeExtractor(), model).shape == (768,)


def test_embed_is_time_mean():
    model = FakeModel()
    out = embed(np.zeros(320 * 3, np.float32), FakeExtractor(), model)  # 프레임 0,1,2,3 → 평균 1.5
    assert np.allclose(out, 1.5)


def test_load_encoder_passes_cache_dir(monkeypatch):
    """서버에서는 글·받아쓰기 모델이 transformers를 먼저 불러와 HF_HOME이 안 먹음 → cache_dir를 직접 넘겨야 함 (11/26)."""
    transformers = pytest.importorskip("transformers")
    from ai.voice_emotion import features

    seen = []

    def fake(repo, **kw):
        seen.append(kw)
        return SimpleNamespace(eval=lambda: None)

    monkeypatch.setattr(transformers.AutoFeatureExtractor, "from_pretrained", fake)
    monkeypatch.setattr(transformers.AutoModel, "from_pretrained", fake)
    features.load_encoder("hubert")
    assert [Path(kw["cache_dir"]) for kw in seen] == [Path(features.HF_CACHE) / "hub"] * 2
    assert all(kw["local_files_only"] for kw in seen)
