# 음악 취향 유형 검사 + 참여자 코드 — 구현 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 12문항 취향 유형 검사 결과로 추천 3곡을 바꾸고, 시연 기기 한 대를 돌려 쓰는 12/7 평가에서 참여자별로 기록이 나뉘게 한다.

**Architecture:** 참여자는 화면이 만든 4자리 코드를 `X-Participant` 헤더로 보내고, 서버는 코드마다 `tb_user`를 찾거나 만든다. 유형 결과는 `localStorage`에 두고, 추천 요청에 선택 항목 `taste_side`를 실어 보내면 서버가 "감정 × 쪽" 8개 표 중 하나로 계산하고 `tb_record.taste_side`에 남긴다.

**Tech Stack:** FastAPI + pydantic v2 + SQLite (`backend/.venv`, pytest), React 18 + Vite (`node --test`)

**Spec:** `docs/superpowers/specs/2026-11-23-music-taste-type-design.md` (승인 2026-11-24). 각 작업은 스펙의 절 번호를 적는다. 실행하는 사람은 스펙도 함께 읽는다.

## Global Constraints

- 감정 4종 그대로: `좋음`, `무난함`, `가라앉음`, `예민함`
- 쪽 8개: 가라앉음 `위로`/`머무름`, 예민함 `진정`/`발산`, 좋음 `유지`/`증폭`, 무난함 `잔잔`/`전환`. 앞쪽이 기본 쪽(지금 방식)
- 공개 시연은 DEAM만 (`MOODWAVE_RECOMMEND_SCOPE=DEAM`). 시연 모드(`draft.demo`)는 추천·권유를 바꾸지 않음
- 새 의존성 없음
- 참여자 코드 형식 `^[A-Z0-9]{4}$`, 이메일 `participant-<코드>@moodwave.local`
- `localStorage` 키는 모두 `moodwave.mvp.` 로 시작: `moodwave.mvp.participant.v1`, `moodwave.mvp.taste.v1`, `moodwave.mvp.taste.offered.v1`
- 화면 문구·주석·커밋 메시지는 한국어. 커밋 끝에 `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`
- main에서 바로 커밋하지 않는다. 작업 브랜치: `feature/taste-type` (main에서 새로 만듦). push·PR은 상현이 요청할 때만
- 백엔드 시험: `cd backend; .\.venv\Scripts\python.exe -m pytest -q` (지금 68개 통과). 프론트: `cd frontend; npm test` (지금 14개 통과)

## 시작 조건 (게이트)

- **작업 1~2 (참여자 코드)**: 건호에게 "서버 쪽 참여자 코드를 우리가 만든다"고 알리고 동의를 받은 뒤 시작
- **작업 3~6 (유형 검사)**: 실제 DEAM 점수표로 스펙 9절 구역별 곡 수를 센 뒤 시작. 30곡 미만인 쪽이 있으면 멈추고 상현에게 보고

## Review Focus

1. 브라우저가 보내는 `X-Participant` 헤더를 CORS가 막아 모든 요청이 실패 → 작업 1에 사전 요청(OPTIONS) 시험
2. 소문자·5자리 등 형식이 틀린 코드 → 저장 없이 422 → 작업 1 시험
3. 앞 참여자의 `moodwave.mvp.pending-lp.v1`(감상 후 복구 정보)가 남아 다음 참여자에게 복구 화면이 뜸 → 작업 2 시험 (접두어로 모두 지우는지, 다른 앱 키는 남는지)
4. 옛 버전이 저장했거나 손상된 유형 값(`answers` 11개, 감정 하나 빠짐, 다른 감정의 쪽) → 화면이 멈추지 않고 그 감정은 `taste_side`를 안 보냄 → 작업 5 시험
5. Day Type에서 다시 검사(`draft.mood` 없음)한 결과 화면 → [확인]이 Day Type으로 돌아가고 추천을 부르지 않음 → 작업 6 손 확인

기록 id로 부르는 경로(`/lp`, 반응, 새김, 감상 후 기분)는 바꾸지 않는다. 화면은 자기가 받은 `record_id`만 쓰고 목록 조회 API가 없어서, 평소 사용으로는 다른 참여자의 기록이 보이지 않는다. 참여자 코드는 인증이 아니다(헤더를 바꿀 수 있음). 최근 7일 추천곡 제외는 이미 `target.user_id` 기준이고 `test_recommendations_use_only_same_users_previous_week`가 다른 사용자 경우를 시험한다.

---

### 작업 1: 서버 — 참여자 코드 (스펙 12절)

**Files:**
- Modify: `backend/app/db.py` (`get_demo_user_id` 아래)
- Modify: `backend/app/main.py:14` import, `:106-111` CORS, `:119-131` `create_record`, `:134-146` `analyze_record`, `:164-199` `_analyze_and_save`, `:202-252` `analyze_voice`·`_voice_to_result`
- Create: `backend/tests/test_participant.py`

**Interfaces:**
- Produces: `db.PARTICIPANT_PATTERN = r"^[A-Z0-9]{4}$"`, `db.get_user_id(con: sqlite3.Connection, participant: str | None) -> int`
- Produces: 헤더 `X-Participant` (없으면 시연 사용자). 프론트(작업 2)가 이 이름을 쓴다

- [ ] **Step 1: 실패하는 시험 작성** — `backend/tests/test_participant.py`. DB는 `tmp_path`로 분리(`test_voice.py`의 `isolated_env`처럼). 기록의 사용자 이메일은 `tb_record JOIN tb_user`로 확인

```python
def test_no_header_uses_demo_user(client):
    rid = client.post("/api/records", json={"text": "a"}).json()["record_id"]
    assert email_of(rid) == "demo@moodwave.local"

def test_two_participants_same_day_keep_both_records(client):
    a = client.post("/api/records", json={"text": "a"}, headers={"X-Participant": "AAAA"}).json()["record_id"]
    b = client.post("/api/records", json={"text": "b"}, headers={"X-Participant": "BBBB"}).json()["record_id"]
    assert a != b
    assert email_of(a) == "participant-AAAA@moodwave.local"
    assert email_of(b) == "participant-BBBB@moodwave.local"
    # 같은 참여자가 다시 기록하면 같은 날 덮어쓰기 규칙 그대로
    again = client.post("/api/records", json={"text": "c"}, headers={"X-Participant": "AAAA"}).json()["record_id"]
    assert again == a

@pytest.mark.parametrize("code", ["k7qm", "ABCDE", "AB-1"])
def test_bad_participant_code_is_422_and_saves_nothing(client, code):
    r = client.post("/api/records", json={"text": "a"}, headers={"X-Participant": code})
    assert r.status_code == 422
    assert count_records() == 0

def test_analyze_and_voice_use_participant(client, monkeypatch):
    # FakeEmotionService·FakeSttService는 test_analyze.py·test_voice.py의 것을 가져다 씀
    ...  # /api/records/analyze, /api/records/voice 각각 X-Participant: CCCC → email_of == participant-CCCC@...

def test_cors_preflight_allows_participant_header(client):
    r = client.options("/api/records", headers={
        "Origin": "http://localhost:5173",
        "Access-Control-Request-Method": "POST",
        "Access-Control-Request-Headers": "content-type,x-participant",
    })
    assert r.status_code == 200
    assert "x-participant" in r.headers["access-control-allow-headers"].lower()
```

- [ ] **Step 2: 실패 확인** — `.\.venv\Scripts\python.exe -m pytest tests/test_participant.py -q` → 헤더 무시로 이메일 단언 실패, CORS 단언 실패
- [ ] **Step 3: 구현**
  - `get_user_id`: `participant`가 `None`이면 `get_demo_user_id(con)`. 아니면 `INSERT OR IGNORE INTO tb_user (email, password_hash)` (`DEMO_PASSWORD_HASH` 사용) 뒤 `SELECT user_id`
  - `main.py`: `Participant = Annotated[str | None, Header(alias="X-Participant", pattern=PARTICIPANT_PATTERN)]`를 세 경로의 인자로 받는다 (FastAPI가 형식 오류를 422로 돌려줌). `_analyze_and_save(text, participant)`, `_voice_to_result(audio, participant)`로 넘기고, `get_demo_user_id(con)` 두 곳을 `get_user_id(con, participant)`로 바꾼다
  - CORS `allow_headers=["Content-Type", "X-Participant"]`
- [ ] **Step 4: 통과 확인** — `.\.venv\Scripts\python.exe -m pytest -q` → 전체 통과 (68 + 새 시험)
- [ ] **Step 5: 커밋** — `feat: 참여자 코드 헤더로 참여자별 기록 저장`

### 작업 2: 화면 — 다음 참여자로 시작 (스펙 12절)

**Files:**
- Create: `frontend/src/participant.js`
- Modify: `frontend/src/api.js:5-17` (`request` 헤더)
- Modify: `frontend/src/App.jsx:490` (마이 화면)
- Create: `frontend/tests/participant.test.js`

**Interfaces:**
- Consumes: 헤더 이름 `X-Participant`, 형식 `^[A-Z0-9]{4}$` (작업 1)
- Produces: `PARTICIPANT_KEY = "moodwave.mvp.participant.v1"`, `newParticipantCode(random = Math.random) -> string`, `participantHeader(storage = globalThis.localStorage) -> {} | {"X-Participant": string}`, `startNextParticipant(storage = globalThis.localStorage, random = Math.random) -> string`, `readParticipant(storage) -> string | null`
- 저장 형식은 `App.jsx`의 `write()`와 같은 JSON 문자열 (`"\"K7QM\""`)

- [ ] **Step 1: 실패하는 시험 작성** — `frontend/tests/participant.test.js`. `getItem/setItem/removeItem/key/length`를 가진 가짜 저장소를 시험 파일 안에 만든다

```js
test("코드는 영문 대문자·숫자 4자리",()=>{
  for(let i=0;i<50;i++)assert.match(newParticipantCode(),/^[A-Z0-9]{4}$/);
});
test("다음 참여자로 시작은 moodwave.mvp. 키만 모두 지우고 새 코드를 저장한다",()=>{
  const s=fakeStorage({"moodwave.mvp.records.v1":"[1]","moodwave.mvp.pending-lp.v1":"{}","moodwave.mvp.taste.v1":"{}","moodwave.mvp.taste.offered.v1":"true","other.app":"x"});
  const code=startNextParticipant(s);
  assert.deepEqual(s.keys().sort(),["moodwave.mvp.participant.v1","other.app"]);
  assert.equal(readParticipant(s),code);
});
test("코드가 없거나 형식이 틀리면 헤더를 보내지 않는다",()=>{
  assert.deepEqual(participantHeader(fakeStorage({})),{});
  assert.deepEqual(participantHeader(fakeStorage({"moodwave.mvp.participant.v1":"\"k7qm\""})),{});
  assert.deepEqual(participantHeader(fakeStorage({"moodwave.mvp.participant.v1":"깨진값"})),{});
  assert.deepEqual(participantHeader(fakeStorage({"moodwave.mvp.participant.v1":"\"K7QM\""})),{"X-Participant":"K7QM"});
});
```

- [ ] **Step 2: 실패 확인** — `npm test` → `participant.js` 없음
- [ ] **Step 3: 구현**
  - `participant.js`: 지울 키 목록을 먼저 모은 뒤 지운다 (지우면서 `key(i)` 순서가 바뀌므로). `localStorage`를 쓸 수 없으면 `participantHeader`는 `{}`
  - `api.js` `request`: 세 경우(본문 없음·Blob·JSON) 모두 `headers`에 `...participantHeader()`를 합친다
  - `App.jsx` 마이 화면에 "평가 참여자" 칸: 코드가 있으면 크게 보여 줌. [다음 참여자로 시작] → `window.confirm("지금 기록이 이 기기에서 지워져요. 다음 참여자로 시작할까요?")` → `startNextParticipant()` → `location.hash="#/me"; location.reload()` (화면 상태를 저장소에서 새로 읽기 위함)
- [ ] **Step 4: 통과 확인** — `npm test` 전체 통과, `npm run build` 성공
- [ ] **Step 5: 손 확인** — 서버·화면을 켜고 마이 → 다음 참여자로 시작 → 코드 표시, 기록 → 추천 → 개발자 도구 네트워크에서 `X-Participant` 헤더와 200 확인. 다시 누르면 내역이 비어 있음
- [ ] **Step 6: 커밋** — `feat: 다음 참여자로 시작 버튼과 참여자 코드 헤더`

### 작업 3: 추천 — 감정 × 쪽 8개 표 (스펙 8절)

**Files:**
- Modify: `backend/app/schemas.py` (`Emotion` 아래)
- Modify: `backend/app/recommender.py:30-53` `TARGETS`, `:128-189` `recommend_three`·`_can_follow`
- Test: `backend/tests/test_recommender.py`

**Interfaces:**
- Produces (`schemas.py`): `TasteSide = Literal["위로","머무름","진정","발산","유지","증폭","잔잔","전환"]`, `SIDES: dict[str, tuple[str, str]] = {"가라앉음": ("위로","머무름"), "예민함": ("진정","발산"), "좋음": ("유지","증폭"), "무난함": ("잔잔","전환")}` (앞이 기본 쪽)
- Produces (`recommender.py`): `TARGETS: dict[TasteSide, tuple[tuple[float, float, str], ...]]` (쪽 이름이 키), `ORDERED_SIDES = {"위로", "진정"}`, `recommend_three(emotion, recent_song_ids=frozenset(), *, side: TasteSide | None = None, candidates=None) -> list[Song]`. `side`가 `SIDES[emotion]`에 없으면 `ValueError`

새 표 값 (밝기, 에너지, 단계 이름) — 스펙 8절 그대로:

| 쪽 | 1 | 2 | 3 |
|---|---|---|---|
| 머무름 | 0.20, 0.30, `맞추기` | 0.22, 0.25, `곁에 머물기` | 0.28, 0.22, `잔잔하게 마무리` |
| 발산 | 0.25, 0.85, `맞추기` | 0.22, 0.88, `쏟아내기` | 0.30, 0.80, `끝까지 쏟아내기` |
| 증폭 | 0.80, 0.70, `맞추기` | 0.83, 0.80, `더 신나게` | 0.85, 0.88, `끌어올리기` |
| 전환 | 0.50, 0.40, `맞추기` | 0.65, 0.55, `조금 밝게` | 0.78, 0.65, `활기차게` |

기존 4개 표는 숫자·단계 이름 그대로 `위로`, `진정`, `유지`, `잔잔` 키로 옮긴다.

- [ ] **Step 1: 실패하는 시험 작성** — `test_recommender.py`에 추가

```python
NEW_STEPS = {
    ("가라앉음", "머무름"): ["맞추기", "곁에 머물기", "잔잔하게 마무리"],
    ("예민함", "발산"): ["맞추기", "쏟아내기", "끝까지 쏟아내기"],
    ("좋음", "증폭"): ["맞추기", "더 신나게", "끌어올리기"],
    ("무난함", "전환"): ["맞추기", "조금 밝게", "활기차게"],
}

@pytest.mark.parametrize(("emotion", "side"), NEW_STEPS)
def test_new_sides_return_three_songs_with_their_steps(monkeypatch, emotion, side):
    monkeypatch.setenv("MOODWAVE_SCORES_CSV", str(FIXTURE))
    songs = recommend_three(emotion, side=side)
    assert [s.step for s in songs] == NEW_STEPS[(emotion, side)]
    assert len({s.song_id for s in songs}) == 3

@pytest.mark.parametrize("emotion", ["좋음", "무난함", "가라앉음", "예민함"])
def test_default_side_equals_no_side(monkeypatch, emotion):
    monkeypatch.setenv("MOODWAVE_SCORES_CSV", str(FIXTURE))
    assert recommend_three(emotion) == recommend_three(emotion, side=SIDES[emotion][0])

def test_side_of_other_emotion_is_rejected(monkeypatch):
    monkeypatch.setenv("MOODWAVE_SCORES_CSV", str(FIXTURE))
    with pytest.raises(ValueError):
        recommend_three("가라앉음", side="발산")
```

- [ ] **Step 2: 실패 확인** — `pytest tests/test_recommender.py -q` → `side` 인자 없음
- [ ] **Step 3: 구현** — `rank`·단계 이름은 `TARGETS[side]`로. `_can_follow(side, previous, song, stage)`는 `위로`·`진정`일 때만 지금 조건, 그 밖은 `True`. DP 분기 조건 `emotion in {"가라앉음","예민함"}`을 `side in ORDERED_SIDES`로 바꾼다
- [ ] **Step 4: 통과 확인** — `pytest -q` 전체 통과 (기존 순서 시험 포함)
- [ ] **Step 5: 커밋** — `feat: 추천표를 감정 × 쪽 8개로 나눔`

### 작업 4: API·DB — `taste_side` 받기·저장 (스펙 7.2, 7.3절)

**Files:**
- Modify: `backend/app/schemas.py:36-39` `RecommendationRequest`
- Modify: `backend/app/schema.sql:76-94` `tb_record`
- Modify: `backend/app/db.py` `init_db`, `save_today_record` (`ON CONFLICT ... DO UPDATE SET`)
- Modify: `backend/app/main.py:275-316` `create_recommendations`
- Create: `backend/tests/test_taste_side.py`

**Interfaces:**
- Consumes: `TasteSide`, `SIDES` (작업 3), `recommend_three(..., side=...)` (작업 3)
- Produces: 요청 `{"record_id", "confirmed_emotion", "taste_side"?: TasteSide | null}`, 열 `tb_record.taste_side`

- [ ] **Step 1: 실패하는 시험 작성** — `backend/tests/test_taste_side.py` (DB는 `tmp_path`)

```python
def test_without_taste_side_matches_default_and_stores_null(client): ...
    # taste_side 없이 가라앉음 → step == ["맞추기","조금 밝게","더 밝게"], DB taste_side IS NULL
def test_taste_side_changes_songs_and_is_stored(client): ...
    # 가라앉음 + 머무름 → step == ["맞추기","곁에 머물기","잔잔하게 마무리"], DB taste_side == "머무름"
def test_default_side_is_stored_not_null(client): ...
    # 가라앉음 + 위로 → DB taste_side == "위로" (검사 안 함과 구분)
@pytest.mark.parametrize("side", ["발산", "없는쪽"])
def test_side_not_matching_emotion_is_422(client, side): ...
    # 가라앉음 + side → 422, tb_record_song 0행
def test_rerecord_same_day_clears_taste_side(client): ...
    # 머무름으로 추천 → 같은 날 POST /api/records → DB taste_side IS NULL
def test_old_db_gets_column_on_startup(tmp_path, monkeypatch): ...
    # taste_side 열 없이 tb_record를 만든 DB 파일로 TestClient(app) 시작 → PRAGMA table_info에 taste_side 있음
```

- [ ] **Step 2: 실패 확인** — `pytest tests/test_taste_side.py -q`
- [ ] **Step 3: 구현**
  - `RecommendationRequest.taste_side: TasteSide | None = None` + `model_validator(mode="after")`: 값이 있고 `SIDES[confirmed_emotion]`에 없으면 `ValueError` (→ 422)
  - `schema.sql` `tb_record`에 `mood_asked_at` 다음 줄로 스펙 7.3절의 열 정의를 주석까지 그대로 넣는다
  - `init_db`: `executescript` 뒤 `PRAGMA table_info(tb_record)`에 `taste_side`가 없으면 `ALTER TABLE tb_record ADD COLUMN taste_side TEXT CHECK (...)` (같은 CHECK)
  - `save_today_record` 덮어쓰기에 `taste_side = NULL` 추가, 독스트링의 "새로 시작" 목록에도 추가
  - `create_recommendations`: `recommend_three(..., side=payload.taste_side, ...)`, `UPDATE tb_record SET emotion_final = ?, taste_side = ?, flow_ended_at = NULL`
- [ ] **Step 4: 통과 확인** — `pytest -q` 전체 통과
- [ ] **Step 5: 커밋** — `feat: 추천 요청에 taste_side를 받고 기록에 저장`

### 작업 5: 화면 — 유형 계산·저장 값 확인 (스펙 5, 6.3, 6.4, 7.1절)

**Files:**
- Create: `frontend/src/taste.js`
- Create: `frontend/tests/taste.test.js`

**Interfaces:**
- Produces:
  - `TASTE_KEY = "moodwave.mvp.taste.v1"`, `OFFERED_KEY = "moodwave.mvp.taste.offered.v1"`
  - `SIDES` (감정 라벨 → `[기본 쪽, 다른 쪽]`, 작업 3과 같은 값)
  - `QUESTIONS: {emotion, text, a, b}[12]` — 문항 번호 순, 문구는 스펙 6.3절 그대로 (`a`는 "가", `b`는 "나")
  - `QUESTION_ORDER = [0,3,6,9,1,4,7,10,2,5,8,11]` (보여 주는 순서, 축을 섞음)
  - `scoreTaste(answers: ("가"|"나")[]) -> {가라앉음, 예민함, 좋음, 무난함}` (축마다 많이 고른 쪽)
  - `parseTaste(value: unknown) -> {sides, answers, takenAt} | null` (`answers`가 "가"/"나" 12개가 아니면 `null`)
  - `tasteSideFor(taste, emotionLabel) -> string | undefined` (저장된 쪽이 그 감정의 두 쪽 중 하나일 때만)
  - `typeCode(sides) -> string` (예 `"위진유잔"`), `NICKNAMES: Record<code, string>` (스펙 6.4절 16개 그대로), `SIDE_COPY` (결과 카드의 감정별 한 줄, 스펙 6.4절 예시 문구 사용)

- [ ] **Step 1: 실패하는 시험 작성**

```js
test("문항 번호 순 답으로 축마다 많이 고른 쪽",()=>{
  const a=["나","나","가", "가","가","가", "가","나","나", "가","가","가"];
  assert.deepEqual(scoreTaste(a),{"가라앉음":"머무름","예민함":"진정","좋음":"증폭","무난함":"잔잔"});
  assert.equal(typeCode(scoreTaste(a)),"머진증잔");
  assert.equal(NICKNAMES["머진증잔"],"고요히 곁을 지키는 감상가");
});
test("보여 주는 순서는 축을 섞는다",()=>{
  assert.deepEqual(QUESTION_ORDER.slice(0,4).map(i=>QUESTIONS[i].emotion),["가라앉음","예민함","좋음","무난함"]);
  assert.deepEqual([...QUESTION_ORDER].sort((x,y)=>x-y),[0,1,2,3,4,5,6,7,8,9,10,11]);
});
test("깨진 저장 값은 결과 없음",()=>{
  for(const v of [null,"x",{},{answers:Array(11).fill("가")},{answers:Array(12).fill("다")}])assert.equal(parseTaste(v),null);
});
test("그 감정의 쪽이 아니면 taste_side를 보내지 않는다",()=>{
  const t={sides:{"가라앉음":"발산","예민함":"발산"},answers:Array(12).fill("가"),takenAt:"2026-11-30T10:00:00+09:00"};
  assert.equal(tasteSideFor(t,"가라앉음"),undefined);
  assert.equal(tasteSideFor(t,"예민함"),"발산");
  assert.equal(tasteSideFor(t,"좋음"),undefined);
  assert.equal(tasteSideFor(null,"좋음"),undefined);
});
```

- [ ] **Step 2: 실패 확인** — `npm test`
- [ ] **Step 3: 구현** — `parseTaste`는 `sides`를 저장값에서 믿지 않고 `answers`로 다시 계산해도 된다(더 짧으면 그렇게). 감정 라벨은 `domain.js`의 `MOODS[].label`과 같은 문자열
- [ ] **Step 4: 통과 확인** — `npm test` 전체 통과
- [ ] **Step 5: 커밋** — `feat: 취향 유형 문항과 계산`

### 작업 6: 화면 — 권유·검사·결과·Day Type·추천 요청 (스펙 6.1, 6.2, 6.5, 14절)

**Files:**
- Modify: `frontend/src/App.jsx` — `PAGES`(:7-16)에 `"taste-offer"`, `"taste-quiz"`, `"taste-result"` 추가, `accept`(:284-307), 화면 보호 규칙(:446), `daytype`(:496)
- 필요하면 `frontend/src/styles.css`(기존 클래스 `surface`, `actions`, `btn` 재사용이 우선)

**Interfaces:**
- Consumes: 작업 5의 전부, 요청 항목 `taste_side` (작업 4)

- [ ] **Step 1: 구현**
  - `accept(id)`: 위험 표현 검사·덮어쓰기 확인은 지금 그대로 먼저. 그다음 `!draft.demo && !parseTaste(read(TASTE_KEY,null)) && !read(OFFERED_KEY,false)`면 `write(OFFERED_KEY,true)`, `patch({mood:id})`, `go("taste-offer")`로 멈춤. 아니면 지금의 추천 부분(`run(async()=>...)`)을 실행 — 이 부분을 `recommendFor(id)`로 꺼내서 권유 [건너뛰기]와 결과 [추천 받으러 가기]도 같은 함수를 부른다
  - 추천 요청 본문: `{record_id, confirmed_emotion: label, ...(side ? {taste_side: side} : {})}`, `side = tasteSideFor(parseTaste(read(TASTE_KEY,null)), label)`
  - `taste-quiz`: 컴포넌트 상태로 현재 위치와 답(문항 번호 순 배열) 보관, `QUESTION_ORDER` 순으로 한 문항씩, 진행 표시 `3 / 12`. 마지막 답 뒤 `write(TASTE_KEY,{sides,answers,takenAt:new Date().toISOString()})` → `taste-result`
  - `taste-result`: 스펙 6.4절 카드. 추천 흐름에서 왔으면(`draft.mood` 있음) [추천 받으러 가기] → `recommendFor(draft.mood)`, Day Type에서 왔으면 [확인] → `go("daytype")`. 어디서 왔는지는 검사 시작 때 상태로 기억
  - 화면 보호(:446): `taste-offer`는 `draft.mood` 없으면 `record`로. `taste-quiz`·`taste-result`는 Day Type에서 시작한 경우가 아니면서 `draft.mood`가 없으면 `record`로 (스펙 14절)
  - `daytype`: 기존 문구 위에 유형 카드 + [다시 검사하기], 결과 없으면 [유형 검사하기]
- [ ] **Step 2: 확인** — `npm test` 전체 통과, `npm run build` 성공
- [ ] **Step 3: 손 확인** (서버 `MOODWAVE_SCORES_CSV` 설정, 마이 → 다음 참여자로 시작으로 깨끗한 상태)
  - 기록 → 감정 확인 → 권유 → 건너뛰기 → 3곡(기본 단계 이름). 같은 날 다시 기록 → 권유 안 나옴
  - 다음 참여자로 시작 → 기록 → 권유 → 검사 12문항 → 결과 → 추천 3곡의 `step`이 고른 쪽 이름. 네트워크에서 요청에 `taste_side` 확인
  - 마이 → Day Type → 다시 검사 → [확인] → Day Type으로 돌아옴(추천 요청 없음) → 다음 추천에 반영
  - 시연 메뉴 시나리오(시연 모드)·위험 표현 글 → 권유 안 나옴
- [ ] **Step 4: 커밋** — `feat: 취향 유형 권유·검사·결과 화면과 추천 반영`

### 작업 7: 문서 (스펙 16절 7)

**Files:**
- Modify: `API_CONTRACT.md` 3.3절(`POST /api/recommendations`)에 `taste_side`(선택, 422 조건), 2절(서버 기본 정보)에 `X-Participant` 헤더(선택, 형식, 422)
- Modify: `README.md` 진행 현황에 취향 유형 검사·참여자 코드, "빼는 순서"에 스펙 13절 문장
- Modify: 스펙 12절 "기록 id로 조회하는 경로…함께 바꾼다" 줄을 이 계획 Review Focus 아래 문단의 결론으로 바꿈

- [ ] **Step 1: 고치기**
- [ ] **Step 2: 커밋** — `docs: taste_side와 X-Participant를 API 문서·README에 반영`

12/7 설문 문항(스펙 11절)은 설문지 쪽 일이라 이 계획에 넣지 않는다. 평가 준비 때 상현이 넣는다.
