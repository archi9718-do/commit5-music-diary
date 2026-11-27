# 목소리 감정 보완 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** AI Hub 감정 음성(5차 2차 세트)으로 목소리 감정 분류기를 학습해 글 감정과 비교하고, 나아질 때만 녹음 경로에서 글 확률과 합친다.

**Architecture:** 고정 인코더(wav2vec2-base / HuBERT base) 평균 특징 → 선형 층 1개(768→4). 서비스는 `최종 = (1−w)·글 + w·목소리`. 데이터·특징·모델은 저장소 밖, 코드는 `ai/voice_emotion/`, 서버 연결은 `backend/app/main.py`의 기존 `_prepare` 패턴.

**Tech Stack:** Python 3.13 (`backend\.venv`), torch 2.15.0 CPU, transformers 5.22.2, numpy, av, pytest.

**Spec:** `docs/superpowers/specs/2026-11-26-voice-emotion-design.md`

## Global Constraints

- 새 의존성 없음. torch, transformers, numpy, av, 표준 라이브러리만.
- AI Hub 원본·문장·특징·분류기 파일은 저장소에 넣지 않는다. 시험에도 넣지 않는다 (가짜 값만).
- 경로: 원본 `C:\work\moodwave_data\raw`, 특징·나누기 표 `C:\work\moodwave_data\features`, 모델 `C:\work\moodwave_data\models\voice-emotion`, HF 캐시 `C:\work\moodwave_data\hf_cache` (`HF_HOME`).
- 4종 이름과 순서는 `EMOTIONS = ("좋음", "무난함", "가라앉음", "예민함")`. 대응: happiness→좋음, neutral→무난함, sadness→가라앉음, angry→예민함.
- 앞 10초만 쓴다 (`ai/stt/service.py` `MAX_SEC = 10`).
- 결과 형식 `{"record_id","text","probs","emotion","confidence"}`, probs 합 1, 소수 둘째 자리 (`fix_probs_sum`), `HIGH = 0.7`은 바꾸지 않는다.
- 녹음 원본은 디스크·로그에 남기지 않는다.
- 커밋·push는 상현이 요청할 때만 한다. 각 Task의 커밋 단계는 요청을 받은 경우에만 실행한다.
- 시험 실행: `cd backend; .\.venv\Scripts\python -m pytest -q`. 기존 247개가 계속 통과해야 한다. Ruff는 기존 경고 3개 외에 늘지 않는다.
- `ai/voice_emotion/`의 순수 모듈(`data.py`, `split.py`)은 torch를 import하지 않는다. torch가 필요한 시험은 `pytest.importorskip("torch")`.

## Review Focus

1. CSV에 4종 밖 라벨이나 빈 칸이 섞인 줄 → 예외 없이 제외 (Task 1 `test_blank_and_unknown_labels_dropped`).
2. 한 나이+성별 묶음이 너무 커서 평가 15%를 혼자 넘는 경우 → 나누기가 멈추지 않고 비율에서 벗어난 값을 보고 (Task 2 `test_split_reports_ratios`).
3. 10초보다 긴 wav, 1초 미만 wav → 앞 10초만 쓰고, 짧아도 특징 768차원 (Task 3 `test_features_truncate_and_short`).
4. 목소리 확률이 한 감정에 1.0으로 몰리거나 w=1.0 → 형식(합 1, 둘째 자리) 유지 (Task 5 `test_fuse_extremes`).
5. 목소리 모델 폴더는 있는데 메타의 `enabled`가 false → 서버는 지금과 똑같이 글만 (Task 7 `test_voice_disabled_meta_text_only`).

---

### Task 1: 라벨 읽기와 다수결 (`data.py`)

**Files:**
- Create: `ai/voice_emotion/__init__.py` (빈 파일), `ai/voice_emotion/data.py`
- Test: `backend/tests/test_voice_emotion_data.py`

**Interfaces:**
- Produces:
  - `RAW_DIR = Path(r"C:\work\moodwave_data\raw")`
  - `LABEL_MAP: dict[str, str]` (소문자 원 라벨 → 4종 이름)
  - `majority_label(votes: list[str]) -> str | None` — 소문자·공백 정리 후 같은 값이 3개 이상이면 그 값을 `LABEL_MAP`으로 바꿔 돌려줌. 4종 밖이거나 다수결이 없으면 `None`.
  - `load_rows(csv_path: Path, wav_dir: Path) -> list[dict]` — cp949 CSV를 읽어 `{"wav_path": str, "text": str, "label": str, "group": "나이|성별"}` 목록. 다수결 `None`인 줄, wav 파일이 없는 줄은 뺀다. 감정 열은 `"1번 감정"`~`"5번 감정"` (실제 열 이름은 Step 0에서 확인한 대로), 세기 열은 읽지 않는다.

- [ ] **Step 0: 실제 라벨 철자와 열 이름 확인**

Run: `backend\.venv\Scripts\python -I -c "import csv,collections;r=list(csv.DictReader(open(r'C:\work\moodwave_data\raw\5차년도_2차.csv',encoding='cp949')));print(list(r[0].keys()));print(collections.Counter(v for x in r for k,v in x.items() if '감정' in k and '세기' not in k))"`
Expected: 열 이름 목록과 라벨 철자별 개수. `LABEL_MAP` 키와 감정 열 이름을 이 출력에 맞춘다 (문장은 출력하지 않는다).

- [ ] **Step 1: 실패하는 시험 작성**

```python
def test_majority_needs_three_of_five():
    assert majority_label(["Happiness", "happiness", " HAPPINESS", "sadness", "angry"]) == "좋음"
    assert majority_label(["happiness", "happiness", "sadness", "sadness", "angry"]) is None

def test_blank_and_unknown_labels_dropped():
    assert majority_label(["fear", "fear", "fear", "sadness", ""]) is None
    assert majority_label(["", "", "", "neutral", "neutral"]) is None

def test_load_rows_reads_cp949_and_skips_missing_wav(tmp_path):
    # tmp_path에 cp949 CSV 3줄(다수결 됨 / 다수결 없음 / wav 없음)과 빈 wav 1개를 만든다
    rows = load_rows(csv_path, wav_dir)
    assert rows == [{"wav_path": str(wav_dir / "a.wav"), "text": "뭐야", "label": "예민함", "group": "20|남"}]
```

- [ ] **Step 2: 실패 확인** — Run: `cd backend; .\.venv\Scripts\python -m pytest tests/test_voice_emotion_data.py -v` / Expected: FAIL (ImportError)
- [ ] **Step 3: `data.py` 구현** — wav 찾기는 `wav_dir.rglob(f"{wav_id}.wav")` 대신 시작할 때 `{stem: path}` 사전을 한 번 만든다 (5차 하위 폴더 대응).
- [ ] **Step 4: 통과 확인** — 같은 명령 / Expected: PASS
- [ ] **Step 5: 커밋 (요청 시)** — `git add ai/voice_emotion/__init__.py ai/voice_emotion/data.py backend/tests/test_voice_emotion_data.py; git commit -m "feat: AI Hub 감정 음성 라벨 다수결 읽기"`

### Task 2: 화자·문장이 겹치지 않는 나누기 (`split.py`)

**Files:**
- Create: `ai/voice_emotion/split.py`
- Test: `backend/tests/test_voice_emotion_split.py`

**Interfaces:**
- Consumes: Task 1 `load_rows`, `RAW_DIR`
- Produces:
  - `FEATURE_DIR = Path(r"C:\work\moodwave_data\features")`
  - `split_rows(rows: list[dict], seed: int = 42, ratios=(0.70, 0.15, 0.15)) -> tuple[list[dict], dict]` — 각 줄에 `"split": "train"|"val"|"test"`를 붙인 목록과 `{"train": 비율, "val": 비율, "test": 비율}`. 묶음(`group`)을 seed로 섞은 뒤 test, val 순서로 목표 비율에 닿을 때까지 묶음을 채운다. 그다음 test 문장(`text`)과 같은 문장을 가진 val·train 줄, val 문장과 같은 train 줄을 지운다.
  - `python -m ai.voice_emotion.split` → `FEATURE_DIR / "split_set2.csv"` (utf-8, 열 `wav_path,text,label,group,split`)를 쓰고 비율과 감정별 개수를 출력.

- [ ] **Step 1: 실패하는 시험 작성**

```python
def test_groups_do_not_cross_splits():
    out, _ = split_rows(fake_rows(groups=36, per_group=20))
    by = {s: {r["group"] for r in out if r["split"] == s} for s in ("train", "val", "test")}
    assert not (by["train"] & by["val"]) and not (by["train"] & by["test"]) and not (by["val"] & by["test"])

def test_sentences_do_not_leak():
    out, _ = split_rows(fake_rows(groups=36, per_group=20, repeat_text_every=3))
    test_t = {r["text"] for r in out if r["split"] == "test"}
    val_t = {r["text"] for r in out if r["split"] == "val"}
    train_t = {r["text"] for r in out if r["split"] == "train"}
    assert not (test_t & (val_t | train_t)) and not (val_t & train_t)

def test_split_is_deterministic():
    assert split_rows(fake_rows(36, 20), seed=1)[0] == split_rows(fake_rows(36, 20), seed=1)[0]

def test_split_reports_ratios():
    _, ratios = split_rows(fake_rows(groups=3, per_group=[100, 5, 5]))  # 큰 묶음 하나
    assert set(ratios) == {"train", "val", "test"} and abs(sum(ratios.values()) - 1) < 1e-9
```

- [ ] **Step 2: 실패 확인** — `.\.venv\Scripts\python -m pytest tests/test_voice_emotion_split.py -v` / FAIL
- [ ] **Step 3: `split.py` 구현**
- [ ] **Step 4: 통과 확인** — PASS
- [ ] **Step 5: 실제 나누기 표 만들기** — Run (저장소 최상위): `backend\.venv\Scripts\python -m ai.voice_emotion.split` / Expected: 줄 수가 11,686 이하(문장 제외 반영), 세 비율이 각각 목표 ±5%p 안, 평가 세트에 4종이 모두 있음. 벗어나면 seed만 바꿔 다시 실행하고 쓴 seed를 기록한다.
- [ ] **Step 6: 커밋 (요청 시)**

### Task 3: 특징 추출 (`features.py`)

**Files:**
- Create: `ai/voice_emotion/features.py`
- Test: `backend/tests/test_voice_emotion_features.py`

**Interfaces:**
- Consumes: Task 2 `split_set2.csv`, `FEATURE_DIR`; `ai/stt/benchmark_whisper.py` `load_wav_16k(path) -> np.ndarray`
- Produces:
  - `ENCODERS = {"wav2vec2": "facebook/wav2vec2-base", "hubert": "facebook/hubert-base-ls960"}`
  - `MAX_SAMPLES = 10 * 16000`
  - `load_encoder(name: str) -> tuple[feature_extractor, model]` — `HF_HOME`이 없으면 `C:\work\moodwave_data\hf_cache`로 둔 뒤 `AutoFeatureExtractor`, `AutoModel`을 `local_files_only=True`로 읽고 `model.eval()`.
  - `embed(audio_16k: np.ndarray, extractor, model) -> np.ndarray` — 앞 `MAX_SAMPLES`만, `torch.no_grad()`, 마지막 층 `last_hidden_state[0].mean(0)` → `float32 (768,)`.
  - `python -m ai.voice_emotion.features --encoder wav2vec2|hubert` → `FEATURE_DIR / f"{name}.npz"` (`X: (N,768) float32`, `wav_path: (N,)`). 이미 있는 파일의 `wav_path`는 건너뛰고 500개마다 저장해 중간에 끊겨도 이어서 한다.

- [ ] **Step 1: 실패하는 시험 작성** (`pytest.importorskip("torch")`, 가짜 extractor·model 사용)

```python
def test_features_truncate_and_short():
    model = FakeModel()  # 입력 길이를 기록하고 last_hidden_state (1, T//320, 768) 반환
    assert embed(np.zeros(16000 * 15, np.float32), FakeExtractor(), model).shape == (768,)
    assert model.seen_len == 16000 * 10
    assert embed(np.zeros(8000, np.float32), FakeExtractor(), model).shape == (768,)
```

- [ ] **Step 2: 실패 확인** — FAIL
- [ ] **Step 3: `features.py` 구현**
- [ ] **Step 4: 통과 확인** — PASS
- [ ] **Step 5: 실제 추출 (오래 걸림, 백그라운드)** — 상현에게 "인코더당 약 1~1.5시간, CPU를 계속 씀"을 알린 뒤 실행: `backend\.venv\Scripts\python -m ai.voice_emotion.features --encoder wav2vec2`, 끝나면 `--encoder hubert`. Expected: 각 npz의 N이 `split_set2.csv` 줄 수와 같음. 실제 걸린 시간을 기록한다.
- [ ] **Step 6: 커밋 (요청 시)**

### Task 4: 분류기 학습 (`train.py`)

**Files:**
- Create: `ai/voice_emotion/train.py`
- Test: `backend/tests/test_voice_emotion_train.py`

**Interfaces:**
- Consumes: Task 3 npz, Task 2 `split_set2.csv`, `EMOTIONS`
- Produces:
  - `macro_f1(golds: list[str], preds: list[str]) -> float` — `ai/emotion/evaluate_f1.py`의 `f1_report(golds, preds)["macro_f1"]`를 그대로 쓴다.
  - `train_head(X_train, y_train, X_val, y_val, seed=42) -> torch.nn.Linear` — `y`는 `EMOTIONS` 순서 번호. 클래스 가중치 = `N / (4 * 개수)`, Adam, 검증 macro-F1이 10 에폭 동안 오르지 않으면 멈추고 가장 좋았던 가중치를 돌려줌. 학습률·배치는 구현자가 정한다.
  - `predict_head(head, X) -> np.ndarray` — `(N, 4)` softmax 확률, 열 순서 `EMOTIONS`.
  - `python -m ai.voice_emotion.train` → 두 인코더를 같은 seed로 학습해 검증 macro-F1을 출력하고, 높은 쪽의 `head.pt`(`state_dict`)와 `train.json`(`{"encoder", "val_macro_f1": {"wav2vec2", "hubert"}, "seed"}`)을 `C:\work\moodwave_data\models\voice-emotion\`에 저장.

- [ ] **Step 1: 실패하는 시험 작성** (`importorskip("torch")`)

```python
def test_train_head_learns_separable_data():
    X, y = separable_blobs(n=400, dim=768, classes=4, seed=0)  # 클래스마다 다른 평균
    head = train_head(X[:300], y[:300], X[300:], y[300:])
    probs = predict_head(head, X[300:])
    assert probs.shape == (100, 4) and np.allclose(probs.sum(1), 1, atol=1e-5)
    assert macro_f1([EMOTIONS[i] for i in y[300:]], [EMOTIONS[i] for i in probs.argmax(1)]) > 0.9
```

- [ ] **Step 2: 실패 확인** — FAIL
- [ ] **Step 3: `train.py` 구현**
- [ ] **Step 4: 통과 확인** — PASS
- [ ] **Step 5: 실제 학습** — `backend\.venv\Scripts\python -m ai.voice_emotion.train` / Expected: 두 검증 macro-F1 출력, `head.pt`·`train.json` 생성. 평가(test) 세트는 이 단계에서 읽지 않는다.
- [ ] **Step 6: 커밋 (요청 시)**

### Task 5: 글·목소리 합치기 (`fuse.py`)

**Files:**
- Create: `ai/voice_emotion/fuse.py`
- Test: `backend/tests/test_voice_emotion_fuse.py`

**Interfaces:**
- Consumes: `ai/emotion/emotion_mapper.py` `EMOTIONS`, `fix_probs_sum(probs, top)`, `get_confidence(top_prob)`
- Produces: `fuse(result: dict, voice_probs: dict, w: float) -> dict` — `analyze_text` 결과와 같은 키. `probs = (1−w)·result["probs"] + w·voice_probs`, `emotion`은 반올림 전 최댓값, `probs`는 `fix_probs_sum`, `confidence`는 `get_confidence(반올림한 probs[emotion])`. `record_id`, `text`는 그대로. 입력 dict는 바꾸지 않는다.

- [ ] **Step 1: 실패하는 시험 작성** (`importorskip("torch")`)

```python
TEXT = {"record_id": None, "text": "뭐야", "probs": {"좋음": 0.1, "무난함": 0.5, "가라앉음": 0.1, "예민함": 0.3}, "emotion": "무난함", "confidence": "중간"}

def test_fuse_w0_keeps_text():
    assert fuse(TEXT, {"좋음": 0.0, "무난함": 0.0, "가라앉음": 0.0, "예민함": 1.0}, 0.0) == TEXT

def test_fuse_changes_emotion_and_confidence():
    out = fuse(TEXT, {"좋음": 0.0, "무난함": 0.0, "가라앉음": 0.0, "예민함": 1.0}, 0.6)
    assert out["emotion"] == "예민함" and out["probs"]["예민함"] == 0.72 and out["confidence"] == "높음"

def test_fuse_extremes():
    for w in (0.3, 1.0):
        out = fuse(TEXT, {"좋음": 1.0, "무난함": 0.0, "가라앉음": 0.0, "예민함": 0.0}, w)
        assert set(out["probs"]) == set(EMOTIONS) and round(sum(out["probs"].values()), 10) == 1.0
        assert all(v == round(v, 2) for v in out["probs"].values())
```

- [ ] **Step 2: 실패 확인** — FAIL
- [ ] **Step 3: `fuse.py` 구현**
- [ ] **Step 4: 통과 확인** — PASS
- [ ] **Step 5: 커밋 (요청 시)**

### Task 6: 평가와 켜기 판정 (`evaluate.py`) + README

**Files:**
- Create: `ai/voice_emotion/evaluate.py`
- Modify: `README.md` (감정 인식 결과 절에 비교표 추가)
- Test: `backend/tests/test_voice_emotion_evaluate.py`

**Interfaces:**
- Consumes: Task 4 `predict_head`, `macro_f1`, `head.pt`, `train.json`; Task 5 `fuse`; `ai/emotion/service.py` `analyze_text`; `f1_report`
- Produces:
  - `SHORT_LEN = 10`, `W_GRID = [round(i / 10, 1) for i in range(11)]`
  - `choose_w(text_results: list[dict], voice_probs: list[dict], golds: list[str]) -> float` — `W_GRID`에서 macro-F1이 가장 높은 w, 같으면 작은 w.
  - `bootstrap_lower(golds, preds_a, preds_b, n=1000, seed=42) -> float` — 같은 인덱스로 다시 뽑아 `macro_f1(b) − macro_f1(a)`의 2.5% 분위수.
  - `decide_enable(w: float, full_gain: float, full_lower: float, short_gain: float) -> bool` — `w > 0 and full_gain >= 0.01 and full_lower > 0 and short_gain >= 0`.
  - `python -m ai.voice_emotion.evaluate` → 검증 세트로 `w`(전체)와 `w_short`·`w_long`(10자 이하/초과 따로 `choose_w`)을 고르고, 평가 세트에서 글만/목소리만/합침(w)/합침(w_short,w_long) × 전체/짧은 말의 macro-F1·정확도, 감정별 F1, 확신도 표("높음" 비율·"높음"일 때 정확도, 글만 vs 합침(w))를 출력하고 `C:\work\moodwave_data\results\voice_emotion\{YYYYMMDD-HHMM}.json`에 저장. `meta.json`(`{"encoder", "w", "w_short", "w_long", "enabled", "metrics", "classes": EMOTIONS}`)을 모델 폴더에 쓴다. 글 확률은 각 줄의 `text`로 `analyze_text`를 불러 구한다.

- [ ] **Step 1: 실패하는 시험 작성** (`importorskip("torch")`; 순수 함수만, 모델 없이)

```python
def test_choose_w_prefers_smaller_on_tie():
    # 글이 이미 다 맞으면 w=0.0
    assert choose_w(all_correct_text, any_voice, golds) == 0.0

def test_choose_w_picks_voice_when_text_wrong():
    assert choose_w(text_all_wrong_flat, voice_all_right, golds) > 0.0

def test_bootstrap_lower_positive_when_b_always_better():
    assert bootstrap_lower(golds, wrong_preds, golds) > 0

def test_decide_enable_rules():
    assert decide_enable(0.3, 0.012, 0.001, 0.0)
    assert not decide_enable(0.0, 0.05, 0.02, 0.01)   # w=0
    assert not decide_enable(0.3, 0.009, 0.001, 0.0)  # 1%p 미만
    assert not decide_enable(0.3, 0.02, -0.001, 0.0)  # 구간이 0을 포함
    assert not decide_enable(0.3, 0.02, 0.01, -0.01)  # 짧은 말이 나빠짐
```

- [ ] **Step 2: 실패 확인** — FAIL
- [ ] **Step 3: `evaluate.py` 구현**
- [ ] **Step 4: 통과 확인** — PASS
- [ ] **Step 5: 실제 평가** — `backend\.venv\Scripts\python -m ai.voice_emotion.evaluate` / Expected: 비교표·확신도 표 출력, `meta.json`의 `enabled` 값 확인. 평가 세트를 본 뒤 w나 인코더를 다시 고르지 않는다.
- [ ] **Step 6: README 기록** — 비교표, 고른 인코더, w, 확신도 표, 켜기 판정을 README 감정 인식 절에 숫자로 적는다 (문장 예시는 넣지 않는다). `HIGH` 변경이 필요해 보이면 숫자만 적고 "상현·건호 결정 필요"로 남긴다.
- [ ] **Step 7: 상현에게 결과 보고** — `enabled`가 false면 여기서 끝 (Task 7 하지 않음).
- [ ] **Step 8: 커밋 (요청 시)**

### Task 7 (조건부: `enabled`가 true일 때만): 서버 녹음 경로 연결

**Files:**
- Create: `ai/voice_emotion/service.py`
- Modify: `backend/app/main.py` (import 블록 46–63, `_prepare` 호출 87–95, `lifespan` 99–104, `_analyze_and_save` 177, `_voice_to_result` 244–275)
- Modify: `backend/tests/conftest.py` (기본으로 목소리 끄는 fixture)
- Test: `backend/tests/test_voice.py` (시험 추가)

**Interfaces:**
- Consumes: Task 3 `load_encoder`, `embed`; Task 4 `predict_head`; Task 5 `fuse`; `ai/stt/service.py` `decode_audio(bytes) -> np.ndarray`
- Produces:
  - `ai/voice_emotion/service.py`: `get_model_dir() -> str` (`MOODWAVE_VOICE_MODEL_DIR`, 없으면 `C:\work\moodwave_data\models\voice-emotion`); `warm_up() -> None` (폴더·`meta.json`·`head.pt`가 없으면 `FileNotFoundError`, `enabled`가 false면 `RuntimeError("목소리 감정 꺼짐 판정")`, 아니면 인코더·분류기를 읽고 1초 무음으로 한 번 실행); `combine(result: dict, audio_bytes: bytes) -> dict` (`decode_audio` → `embed` → `predict_head` → `fuse(result, voice_probs, meta["w"])`).
  - `backend/app/main.py`: `voice_service`(import 실패 시 `None`), `VOICE_STATUS`, `prepare_voice_model()`(`_prepare(VOICE_STATUS, voice_service, _VOICE_IMPORT_ERROR, "목소리 감정")`, `lifespan`에서 `prepare_stt_model()` 다음에 호출), `_analyze_and_save(text: str, participant: str | None = None, audio: bytes | None = None)`. `analyze_text` 성공 뒤 `audio is not None and VOICE_STATUS["ready"]`이면 `voice_service.combine(result, audio)`, 예외는 `_log_model_failure("목소리 감정", exc)` 후 글 결과 유지. `_voice_to_result`의 마지막 줄을 `_analyze_and_save(text, participant, audio)`로.
  - 설계 문서 8절의 `voice_probs` 인자 대신 `audio`를 넘긴다 (디코딩을 서비스 안에 두어 main이 numpy를 몰라도 되게; 설계 10절 범위 안의 구현 선택).

- [ ] **Step 1: 실패하는 시험 작성** (`test_voice.py`, 가짜 목소리 서비스)

```python
class FakeVoiceService:
    def __init__(self, warm_up_error=None, combine_error=None): ...
    def warm_up(self): raise self.warm_up_error if set
    def combine(self, result, audio_bytes):
        if self.combine_error: raise self.combine_error
        return {**result, "probs": {"좋음": 0.9, "무난함": 0.05, "가라앉음": 0.03, "예민함": 0.02}, "emotion": "좋음", "confidence": "높음"}

def test_voice_fusion_saved_when_ready(...):      # 201, emotion == "좋음", DB에도 "좋음"
def test_voice_fusion_error_falls_back_to_text(...):  # combine_error=RuntimeError → 201, FAKE_PROBS 그대로
def test_voice_disabled_meta_text_only(...):      # warm_up_error=RuntimeError("목소리 감정 꺼짐 판정") → 201, FAKE_PROBS 그대로
def test_text_records_never_use_voice(...):       # POST /api/records/analyze는 combine을 부르지 않음
```

`conftest.py`에 `monkeypatch.setattr(main, "voice_service", None)` autouse fixture를 추가해 다른 시험이 진짜 인코더를 읽지 않게 한다.

- [ ] **Step 2: 실패 확인** — `.\.venv\Scripts\python -m pytest tests/test_voice.py -v` / FAIL
- [ ] **Step 3: `service.py`와 `main.py` 수정**
- [ ] **Step 4: 전체 시험** — `.\.venv\Scripts\python -m pytest -q` / Expected: 기존 247 + 새 시험 모두 PASS; `ruff check .` 기존 3개만
- [ ] **Step 5: 속도 재기** — 서버를 켜고 10초짜리 녹음 wav(직접 녹음, AI Hub 아님)로 `curl.exe -s -o NUL -w "%{time_total}" -H "Content-Type: audio/wav" --data-binary "@녹음.wav" http://127.0.0.1:8000/api/records/voice`를 5번 재서 평균. Expected: 5초 미만. 넘으면 `meta.json`의 `enabled`를 false로 두고 상현에게 보고.
- [ ] **Step 6: 커밋 (요청 시)**

### (선택) 2단계: 4·5차를 학습에 더한 비교

Task 6까지 끝나고 시간이 남을 때만. 상현에게 먼저 묻는다. 4·5차 줄은 `load_rows`로 읽고(4차 CSV·wav ID가 어긋나는 32개 제외), 학습 세트에만 더한다. 평가 세트는 `split_set2.csv`의 test 그대로. 결과는 README 비교표에 한 줄 추가.
