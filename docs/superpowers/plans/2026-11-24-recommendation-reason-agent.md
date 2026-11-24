# 추천 이유 에이전트 — 구현 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 추천 3곡마다 도구 결과에 근거한 이유 한 줄을 보여 주고, 검사에 걸리거나 실패하면 템플릿 문장을 보여 준다.

**Architecture:** `ai/agent/`에 규칙(검사기·템플릿·위험 표현)과 에이전트(도구 3개, 최대 4번 반복)를 두고, 서버는 새 라우터 `backend/app/reasons.py`의 `POST /api/records/{record_id}/reasons`에서 DB 사실을 모아 넘긴다. 화면은 추천 화면을 먼저 보여 준 뒤 이 경로를 기다리지 않고 불러 이유 칸만 바꾼다.

**Tech Stack:** Python 3.13, FastAPI, `anthropic` 공식 SDK (Claude API, `claude-opus-5-5`), React 18, `node --test`

**Spec:** `docs/superpowers/specs/2026-11-24-recommendation-reason-agent-design.md` (승인 2026-11-24)

## Global Constraints

- 모델 `claude-opus-5-5`, `output_config.effort="low"`, `betas=["server-side-fallback-2026-07-01"]`, `fallbacks="default"` (거절되면 서버가 다른 모델로 다시 시도)
- 키는 환경 변수 `ANTHROPIC_API_KEY`. 코드·저장소·로그에 키를 쓰지 않는다
- 일기 원문(`record_text`)은 위험 표현 검사에만 쓰고 LLM에 보내지 않는다
- 서버가 기다리는 시간은 전체 10초 (반복 전체 합), 반복 최대 4번
- `anthropic`은 `ai/requirements.txt`에 버전 고정. 없거나 키가 없어도 서버는 켜지고 이 경로는 `template` (스펙 3절의 `backend/requirements.txt` 대신 — 기존 모델 패키지와 같은 관리 방식)
- DB 구조는 바꾸지 않는다
- 시험은 실제 API를 부르지 않는다 (가짜 클라이언트). 실제 호출은 작업 5의 평가 스크립트만
- 화면 문구·주석·커밋 메시지는 한국어, 커밋 끝에 `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`
- 브랜치: `docs/reason-agent-design`에서 `feature/reason-agent`를 만들어 작업. push·PR은 상현이 요청할 때만
- 시험 명령: `cd backend; .\.venv\Scripts\python.exe -m pytest -q` / `cd frontend; npm test`

**스펙과 다른 점 (계획에서 정함)**
- 응답 `reasons[]`에 `song_id`를 넣는다. 같은 기록으로 다시 추천받아 곡이 바뀌었으면 화면이 옛 이유를 버릴 수 있게 하기 위해서다
- 평가 입력은 감정 4종 × 최근 7일 3가지 = 12경우 × 10번 = 120회. 취향 쪽(`taste_side`)은 아직 구현 전이라 뺀다. 취향 유형 작업 4가 병합되면 `get_today`에 `taste_side`를 넣고 새 단계 이름 템플릿을 더한다 (그 계획의 작업 3·4에 함께 반영)

## Review Focus

1. 모델이 같은 순서를 두 번 쓰거나(`[1,1,3]`) 2줄만 돌려줌 → 3줄 모두 템플릿 → 작업 1 시험
2. 문장 앞뒤 공백·줄바꿈, 중간 줄바꿈 → 앞뒤는 다듬고 중간 줄바꿈은 탈락 → 작업 1 시험
3. 사진만 기록해 `record_text`가 `NULL`·빈 글 → 위험 아님, 오류 없음 → 작업 1·3 시험
4. 이유를 기다리는 사이 같은 기록으로 다시 추천받아 곡이 바뀜, 또는 같은 날 다시 기록 → 옛 이유를 버림 → 작업 4 시험
5. 키는 있지만 시연장 인터넷이 끊김 → 10초 안에 `template` → 작업 2 시험 (가짜 클라이언트가 예외)

---

### Task 1: 규칙 — 위험 표현·템플릿·검사기 (스펙 7.3~7.5절)

**Files:**
- Create: `ai/agent/__init__.py` (빈 파일), `ai/agent/rules.py`
- Create: `backend/tests/fixtures/risk_sentences.json`
- Create: `backend/tests/test_agent_rules.py`
- Modify: `frontend/tests/domain.test.js` (위험 문장 묶음 시험 추가)

**Interfaces:**
- Produces:
  - `is_risk(text: str | None) -> bool` — NFC 정규화·앞뒤 공백 제거 뒤 `RISK_PATTERNS` 중 하나라도 맞으면 `True`
  - `template_reasons(emotion: str, steps: list[str]) -> list[str]` — 길이는 `steps`와 같음
  - `check_reasons(reasons: list[dict], emotion: str, has_recent: bool) -> tuple[list[str], list[str]]` — `(다듬은 문장 3개 순서대로 또는 [], 문제 코드 목록)`. 문제가 없으면 문제 목록이 `[]`
  - 문제 코드: `"format"`, `"forbidden:<단어>"`, `"emotion:<단어>"`, `"song:<단어>"`, `"recent:<단어>"`

`rules.py`의 값 (스펙 12절에서 Claude 초안으로 둔 것, 이 값 그대로):

- `RISK_PATTERNS`: `frontend/src/domain.js`의 `SIGNALS` 7개와 같은 정규식
- 형식: 다듬은 `text`가 `^[가-힣 .,!?·]+$`에 맞고, 15~45자, `요\.?$`로 끝남. `recommend_order`가 정확히 {1,2,3}
- `FORBIDDEN`: `우울증, 공황, 장애, 치료, 진단, 증상, 상담, 괜찮아질, 나아질, 반드시, 분명히, 틀림없이, 힘내, 해야, 하세요, 친구, 가족, 회사, 학교, 시험`
- `EMOTION_WORDS` (확정 감정이 아닌 감정의 단어가 나오면 탈락): 좋음 `신나, 기쁜, 기뻐, 행복, 들뜬, 설레` / 무난함 `평범, 무난` / 가라앉음 `슬픈, 슬퍼, 우울, 외로, 눈물` / 예민함 `화나, 짜증, 불안, 초조`
- `SONG_WORDS`: `피아노, 기타, 드럼, 신스, 보컬, 가사, 장르, 재즈, 힙합, 발라드, 아티스트, 가수, 제목`
- `RECENT_WORDS` (`has_recent`가 거짓일 때 나오면 탈락): `요즘, 며칠, 이번 주, 최근`
- `TEMPLATES` (`(감정, 단계)` → 문장)과 `GENERIC_TEMPLATE = "오늘 고른 기분에 맞춰 고른 곡이에요."`:

| 감정 | 단계 | 문장 |
|---|---|---|
| 좋음 | 비슷한 분위기 1 / 2 / 3 | 지금의 밝은 기분과 닮은 곡으로 시작해요. / 비슷한 밝기로 좋은 기분을 이어가요. / 같은 분위기로 편안하게 마무리해요. |
| 무난함 | 비슷한 분위기 1 / 2 / 3 | 지금처럼 고른 분위기의 곡으로 시작해요. / 비슷한 흐름으로 편하게 이어가요. / 잔잔한 분위기로 하루를 마무리해요. |
| 가라앉음 | 맞추기 / 조금 밝게 / 더 밝게 | 지금 마음처럼 낮고 잔잔한 곡으로 시작해요. / 밝기를 조금 올려 천천히 이어가요. / 한결 밝은 곡으로 오늘을 마무리해요. |
| 예민함 | 맞추기 / 에너지 낮추기 / 차분하고 조금 밝게 | 지금의 높은 긴장과 닮은 곡으로 시작해요. / 에너지를 낮춘 곡으로 숨을 고르게 해요. / 차분하고 조금 밝은 곡으로 마무리해요. |

- [ ] **Step 1: 위험 문장 묶음 작성** — `risk_sentences.json`: `[{"text": "...", "risk": true|false}, ...]`. 위험 14개(정규식 7개마다 2개씩, 띄어쓰기 변형 포함: "죽고싶다", "죽고 싶어" 등) + 위험 아님 8개("죽을 만큼 웃겼어", "자살 예방 캠페인을 봤어", "목숨 걸고 뛰었어" 등 — 지금 정규식 결과에 맞춰 `risk` 값을 적는다)
- [ ] **Step 2: 실패하는 시험 작성** — `backend/tests/test_agent_rules.py` (`sys.path`에 저장소 최상위 추가, `main.py`처럼)

```python
def test_risk_sentences_match_fixture():
    for case in json.loads(RISK_FIXTURE.read_text(encoding="utf-8")):
        assert is_risk(case["text"]) is case["risk"], case["text"]

def test_empty_text_is_not_risk():
    assert is_risk(None) is False and is_risk("") is False and is_risk("   ") is False

@pytest.mark.parametrize(("emotion", "steps"), [
    ("좋음", ["비슷한 분위기 1", "비슷한 분위기 2", "비슷한 분위기 3"]),
    ("무난함", ["비슷한 분위기 1", "비슷한 분위기 2", "비슷한 분위기 3"]),
    ("가라앉음", ["맞추기", "조금 밝게", "더 밝게"]),
    ("예민함", ["맞추기", "에너지 낮추기", "차분하고 조금 밝게"]),
])
def test_templates_pass_checker(emotion, steps):
    texts = template_reasons(emotion, steps)
    reasons = [{"recommend_order": i, "text": t} for i, t in enumerate(texts, 1)]
    assert check_reasons(reasons, emotion, has_recent=False) == (texts, [])

def test_unknown_step_uses_generic_template():
    assert template_reasons("좋음", ["없는 단계"]) == [GENERIC_TEMPLATE]

GOOD = ["지금 마음처럼 낮고 잔잔한 곡으로 시작해요.", "밝기를 조금 올려 천천히 이어가요.", "한결 밝은 곡으로 오늘을 마무리해요."]
def lines(*texts, orders=(1, 2, 3)): return [{"recommend_order": o, "text": t} for o, t in zip(orders, texts)]

def test_strips_outer_whitespace():
    texts, problems = check_reasons(lines(*[f"  {t}\n" for t in GOOD]), "가라앉음", False)
    assert problems == [] and texts == GOOD

@pytest.mark.parametrize(("reasons", "code"), [
    (lines(*GOOD, orders=(1, 1, 3)), "format"),
    (lines(*GOOD[:2]), "format"),
    (lines("너무 짧아요.", *GOOD[1:]), "format"),
    (lines("지금 마음처럼 낮고\n잔잔한 곡으로 시작해요.", *GOOD[1:]), "format"),
    (lines("밝기 0.45인 곡으로 조금 밝게 이어가요.", *GOOD[1:]), "format"),
    (lines("힘내라는 마음으로 밝은 곡을 골랐어요.", *GOOD[1:]), "forbidden:힘내"),
    (lines("신나는 리듬으로 기분을 바꿔 보아요.", *GOOD[1:]), "emotion:신나"),
    (lines("잔잔한 피아노 소리로 마음을 달래요.", *GOOD[1:]), "song:피아노"),
    (lines("요즘 무거웠던 마음을 천천히 풀어요.", *GOOD[1:]), "recent:요즘"),
])
def test_checker_rejects(reasons, code):
    texts, problems = check_reasons(reasons, "가라앉음", has_recent=False)
    assert texts == [] and code in problems

def test_recent_word_ok_when_history_exists():
    reasons = lines("요즘 무거웠던 마음을 천천히 풀어요.", *GOOD[1:])
    assert check_reasons(reasons, "가라앉음", has_recent=True)[1] == []
```

- [ ] **Step 3: 실패 확인** — `pytest tests/test_agent_rules.py -q` → `ai.agent.rules` 없음
- [ ] **Step 4: 구현** — 위 값과 인터페이스대로 `rules.py`. 문제는 모두 모아 돌려준다(첫 문제에서 멈추지 않음, 평가 보고용). 문제가 하나라도 있으면 문장 목록은 `[]`
- [ ] **Step 5: 프론트 시험 추가** — `domain.test.js`에서 `../../backend/tests/fixtures/risk_sentences.json`을 `fs`로 읽어 모든 문장에 `classify(text).kind === "risk"`가 `case.risk`와 같은지 확인
- [ ] **Step 6: 통과 확인** — `pytest -q`, `npm test` 전체 통과. 프론트 시험이 실패하면 묶음의 `risk` 값이 아니라 어느 쪽 정규식이 다른지 본다
- [ ] **Step 7: 커밋** — `feat: 추천 이유 검사기·템플릿·위험 표현 규칙`

### Task 2: 에이전트 — 도구 반복과 호출 (스펙 7.1, 7.2, 7.6절)

**Files:**
- Create: `ai/agent/service.py`
- Modify: `ai/requirements.txt` (`anthropic==<설치된 버전>`, 한 줄 주석: 추천 이유 에이전트, 없으면 이 경로만 템플릿)
- Create: `backend/tests/test_agent_service.py`

**Interfaces:**
- Consumes: `check_reasons`, `is_risk`는 쓰지 않음 (위험 검사는 서버가 먼저 함)
- Produces:
  - `MODEL = "claude-opus-5-5"`, `MAX_TURNS = 4`, `DEADLINE_SECONDS = 10.0`
  - `ready() -> bool` — `anthropic`을 불러올 수 있고 `ANTHROPIC_API_KEY`가 있으면 `True`
  - `write_reasons(facts: dict, *, client=None) -> dict` — `facts = {"today": {"confirmed_emotion": str, "taste_side": str | None}, "songs": [{"recommend_order": int, "song_id": str, "step": str, "brightness": float, "energy": float}] * 3, "recent_moods": [{"date": "YYYY-MM-DD", "emotion": str}]}`. 돌려주는 값: `{"texts": list[str] | None, "problems": list[str], "tool_calls": list[str], "stop": str}`. `texts`는 검사 통과 시 3줄, 아니면 `None`. `stop`은 `"ok"`, `"checker"`, `"max_turns"`, `"refusal"`, `"error:<예외 이름>"`, `"timeout"`, `"bad_json"` 중 하나
  - `client`가 `None`이면 `anthropic.Anthropic(max_retries=1)`을 만든다 (`anthropic`은 이 함수 안에서 불러와서, SDK가 없어도 모듈 import와 시험은 됨)

- [ ] **Step 1: 설치·버전 고정** — `.\.venv\Scripts\python.exe -m pip install anthropic` → `pip show anthropic`의 버전을 `ai/requirements.txt`에 적는다
- [ ] **Step 2: 실패하는 시험 작성** — 가짜 클라이언트: `client.beta.messages.create(**kwargs)`가 정해 둔 응답을 차례로 돌려주고 받은 `kwargs`를 기록한다. 응답은 `SimpleNamespace(stop_reason=..., content=[SimpleNamespace(type="tool_use", id=..., name=..., input={}) | SimpleNamespace(type="text", text=...)])`

```python
def test_tool_loop_then_valid_json_returns_texts():
    client = FakeClient([tool_use("get_today"), tool_use("get_songs"), final_json(GOOD)])
    result = write_reasons(FACTS, client=client)
    assert result["texts"] == GOOD and result["stop"] == "ok"
    assert result["tool_calls"] == ["get_today", "get_songs"]
    # 도구 결과에는 facts 값만 들어감, 일기 원문은 요청 어디에도 없음
    second = client.calls[1]["messages"][-1]["content"][0]
    assert json.loads(second["content"]) == FACTS["today"]
    assert "record_text" not in json.dumps(client.calls, ensure_ascii=False, default=str)

def test_request_settings():
    client = FakeClient([final_json(GOOD)])
    write_reasons(FACTS, client=client)
    kw = client.calls[0]
    assert kw["model"] == "claude-opus-5-5"
    assert kw["output_config"]["effort"] == "low"
    assert kw["output_config"]["format"]["type"] == "json_schema"
    assert kw["betas"] == ["server-side-fallback-2026-07-01"] and kw["fallbacks"] == "default"
    assert {t["name"] for t in kw["tools"]} == {"get_today", "get_songs", "get_recent_moods"}
    assert all(t["strict"] and t["input_schema"]["properties"] == {} for t in kw["tools"])

def test_system_prompt_is_fixed_across_calls():
    client = FakeClient([tool_use("get_songs"), final_json(GOOD)])
    write_reasons(FACTS, client=client)
    assert client.calls[0]["system"] == client.calls[1]["system"]

def test_too_many_turns_gives_none():
    client = FakeClient([tool_use("get_today")] * 5)
    result = write_reasons(FACTS, client=client)
    assert result["texts"] is None and result["stop"] == "max_turns" and len(client.calls) == 4

@pytest.mark.parametrize(("responses", "stop"), [
    ([SimpleNamespace(stop_reason="refusal", content=[])], "refusal"),
    ([final_text("not json")], "bad_json"),
    ([final_json(["신나는 리듬으로 기분을 바꿔 보아요.", *GOOD[1:]])], "checker"),
])
def test_failures_give_none(responses, stop):
    result = write_reasons(FACTS, client=FakeClient(responses))
    assert result["texts"] is None and result["stop"] == stop

def test_exception_gives_none():
    result = write_reasons(FACTS, client=FakeClient([ConnectionError("offline")]))
    assert result["texts"] is None and result["stop"] == "error:ConnectionError"

def test_unknown_tool_name_returns_error_result_not_crash(): ...
    # 모델이 없는 도구 이름을 부르면 is_error 결과를 돌려주고 계속 진행
```

`FACTS`는 가라앉음, 곡 3개(`맞추기`/`조금 밝게`/`더 밝게`), `recent_moods=[]`.

- [ ] **Step 3: 실패 확인** — `pytest tests/test_agent_service.py -q`
- [ ] **Step 4: 구현**
  - 수동 반복(`tool-use.md`의 Manual Agentic Loop 모양). 도구 결과는 `json.dumps(..., ensure_ascii=False)`
  - 첫 사용자 메시지는 고정 문장("오늘 추천된 3곡에 대해 곡마다 이유 한 줄을 써 주세요. 도구로 사실을 확인하세요.") — 사실은 도구로만 준다
  - 시스템 프롬프트: 스펙 7.3절 규칙을 문장으로 (한국어, 15~45자, "요"로 끝남, 숫자·곡 정보·다른 감정 단어·금지 표현 금지, 도구 결과에 없는 내용 금지). 날짜·id 없음
  - 시간: 시작할 때 `deadline = time.monotonic() + DEADLINE_SECONDS`, 매 호출에 `client.with_options(timeout=남은 시간)`을 쓴다 — 가짜 클라이언트도 `with_options`를 흉내 낸다. 남은 시간이 0 이하면 `"timeout"`
  - 마지막 답(`stop_reason == "end_turn"`)의 텍스트를 `json.loads` → `check_reasons(data["reasons"], emotion, has_recent=bool(facts["recent_moods"]))`
  - 모든 예외는 잡아서 `"error:<이름>"`, 로그에는 예외 이름만 (응답·키 내용 없음)
- [ ] **Step 5: 통과 확인** — `pytest -q`
- [ ] **Step 6: 커밋** — `feat: 추천 이유 에이전트 (도구 3개, 최대 4번)`

### Task 3: 서버 경로 (스펙 6절)

**Files:**
- Create: `backend/app/reasons.py` (라우터, `post_listening.py`와 같은 모양)
- Modify: `backend/app/main.py` (`app.include_router(reasons_router)` 한 줄, `post_listening_router` 옆)
- Modify: `backend/app/schemas.py` (`ReasonLine`, `ReasonsResponse`)
- Modify: `API_CONTRACT.md` (3절 표에 경로 추가 + 새 소절)
- Create: `backend/tests/test_reasons.py`

**Interfaces:**
- Consumes: `is_risk`, `template_reasons` (작업 1), `write_reasons`, `ready` (작업 2)
- Produces: `POST /api/records/{record_id}/reasons` → `ReasonsResponse = {"source": Literal["agent","template"], "risk": bool, "reasons": [{"recommend_order": int, "song_id": str, "text": str}] (3개)}`

- [ ] **Step 1: 실패하는 시험 작성** — DB는 `tmp_path`. 에이전트는 `monkeypatch`로 `reasons.write_reasons`·`reasons.agent_ready`를 바꿔 끼운다

```python
def test_agent_success(client, recommended): ...
    # 가짜 write_reasons가 texts 3개 → source "agent", reasons[].text가 그 문장, song_id는 tb_record_song 순서대로
def test_agent_receives_facts_without_diary_text(client, recommended): ...
    # 가짜가 받은 facts: today.confirmed_emotion == "가라앉음", songs 3개 step 순서, recent_moods == [], "record_text" 키 없음
def test_agent_failure_gives_template(client, recommended): ...
    # 가짜가 texts None → source "template", text == template_reasons(...) 결과
def test_not_ready_gives_template_without_calling_agent(client, recommended): ...
def test_risk_text_skips_agent(client): ...
    # 위험 문장으로 기록·추천 → risk True, source "template", 가짜가 불리지 않음
def test_photo_only_record_is_not_risk(client): ...
    # record_text 빈 글로 기록·추천 → risk False
def test_before_recommendation_is_409(client): ...
def test_missing_record_is_404(client): ...
def test_recent_moods_only_same_user_previous_7_days(client): ...
    # 어제(같은 사용자, emotion_final 있음)·8일 전·다른 사용자(X-Participant 또는 직접 INSERT)·오늘 기록을 만든 뒤
    # facts["recent_moods"] == [{"date": 어제, "emotion": ...}]
def test_agent_exception_still_200_template(client, recommended): ...
```

- [ ] **Step 2: 실패 확인** — `pytest tests/test_reasons.py -q`
- [ ] **Step 3: 구현**
  - `ai.agent` import는 `main.py`의 감정 모델처럼 `try/except`로 감싼다. 실패하면 `agent_ready = lambda: False`
  - 한 연결에서: 기록(`user_id`, `record_date`, `record_text`, `emotion_final`) → 없으면 404, 곡 3행(`recommend_order`, `song_id`, `step`, `valence_at_rec`, `arousal_at_rec`) → 3행이 아니면 409, 최근 7일 (`user_id` 같고 `record_date >= date(?, '-7 days') AND record_date < ?`, `emotion_final IS NOT NULL`, 날짜순)
  - 연결을 닫은 뒤 에이전트를 부른다 (`run_in_threadpool`, DB 잠금을 오래 잡지 않게)
  - `write_reasons`가 예외를 던져도 `template` (두 번째 겹)
- [ ] **Step 4: 통과 확인** — `pytest -q`
- [ ] **Step 5: API_CONTRACT.md** — 스펙 6절의 요청·응답, 404·409, `source`·`risk` 뜻, "결과는 DB에 저장하지 않음", `song_id` 추가 이유
- [ ] **Step 6: 커밋** — `feat: POST /api/records/{id}/reasons 추천 이유 경로`

### Task 4: 화면 연결 (스펙 8절)

**Files:**
- Modify: `frontend/src/api.js` (`applyReasons` 추가)
- Modify: `frontend/src/App.jsx` `accept()` (지금 `:284-307`)
- Create: `frontend/tests/reasons.test.js`

**Interfaces:**
- Consumes: 응답 양식 (작업 3)
- Produces: `applyReasons(queue, sentRecordId, currentRecordId, data) -> queue | null` — `agent`·`template` 모두 서버 문장으로 바꾼다 (스펙 1절: 사용자는 검사 통과 문장이나 템플릿 문장만 봄). 버릴 때는 `null`. 큐 항목은 `lpTracks`가 만든 모양(`id: "server:<song_id>"`, `reason`)

- [ ] **Step 1: 실패하는 시험 작성**

```js
const queue=[{id:"server:deam_2",reason:"맞추기"},{id:"server:deam_3",reason:"조금 밝게"},{id:"server:deam_4",reason:"더 밝게"}];
const data=(source,ids=["deam_2","deam_3","deam_4"])=>({source,risk:false,reasons:ids.map((song_id,i)=>({recommend_order:i+1,song_id,text:`이유 ${i+1}이에요.`}))});
for(const source of ["agent","template"])test(`${source} 응답이면 곡마다 이유를 바꾼다`,()=>{
  assert.deepEqual(applyReasons(queue,7,7,data(source)).map(t=>t.reason),["이유 1이에요.","이유 2이에요.","이유 3이에요."]);
});
test("그사이 다른 기록이 되었으면 버린다",()=>assert.equal(applyReasons(queue,7,8,data("agent")),null));
test("그사이 곡이 바뀌었으면 버린다",()=>assert.equal(applyReasons(queue,7,7,data("agent",["deam_9","deam_3","deam_4"])),null));
```

- [ ] **Step 2: 실패 확인** — `npm test`
- [ ] **Step 3: 구현**
  - `applyReasons`: 큐의 곡 id 3개와 응답 `song_id` 3개가 순서까지 같을 때만 교체
  - `accept()`: `go("recommend")` 뒤에, `!draft.demo`일 때 `request(\`/records/${recordId}/reasons\`,"POST")`를 `await`하지 않고 부른다. `.then`: `risk`면 `go("risk")`, 아니면 `setDraft(old=>{const q=applyReasons(old.queue,recordId,old.recordId,data);return q?{...old,queue:q}:old;})`. `.catch(()=>{})` (템플릿 문장이 이미 보이므로 알리지 않음)
- [ ] **Step 4: 통과 확인** — `npm test`, `npm run build`
- [ ] **Step 5: 손 확인** — 서버(`MOODWAVE_SCORES_CSV` 설정, 키 있음)·화면을 켜고 기록 → 감정 확인 → 추천 화면이 단계 이름으로 바로 뜨고 몇 초 뒤 이유 문장으로 바뀜. 키 없이(`$env:ANTHROPIC_API_KEY=""`로 켠 서버) 다시 → 곧바로 템플릿 문장으로 바뀜. 네트워크 탭에서 `/reasons` 응답의 `source` 확인
- [ ] **Step 6: 커밋** — `feat: 추천 화면에 에이전트 이유 반영`

### Task 5: 평가 스크립트와 README (스펙 9절)

**Files:**
- Create: `ai/agent/eval.py`
- Modify: `README.md` 8절 표 (형식 준수율·환각·109 안내의 "현재" 칸), 진행 현황

**Interfaces:**
- Consumes: `write_reasons`, `is_risk`, `risk_sentences.json`

- [ ] **Step 1: 구현** — `python -m ai.agent.eval [--runs 10]` (저장소 최상위에서)
  - 경우 12개: 감정 4종(작업 1 표의 단계 이름, 밝기·에너지는 `backend/app/recommender.py`의 `TARGETS` 값) × 최근 7일 `[]` / 같은 감정 3일 / 감정 3종 섞임
  - 실행마다 한 줄을 CSV로: `case, run, stop, problems, tool_calls, text1, text2, text3, hallucination(빈 칸)` → `C:\work\moodwave_data\agent_eval\YYYYMMDD-HHMM.csv` (`MOODWAVE_AGENT_EVAL_DIR`로 바꿀 수 있음, 저장소 밖)
  - 끝에 출력: 형식 준수율(`"format"` 문제 없는 비율), 검사기 통과율, 문제 코드별 수, 도구 호출 평균, `is_risk` 위험 문장 일치율
  - 실행 전 "약 N회 호출, 예상 $X"를 출력하고 `--yes` 없이는 묻고 멈춘다 (비용 확인)
- [ ] **Step 2: 실행** — 상현의 승인 뒤 `--runs 10` (120회). 상현이 CSV의 `hallucination` 칸을 채움 (검사기 통과분만 읽으면 됨)
- [ ] **Step 3: README 8절 갱신** — 측정 날짜와 숫자. 사람 검토 개수 명시
- [ ] **Step 4: 커밋** — `feat: 추천 이유 에이전트 평가 스크립트와 결과`
