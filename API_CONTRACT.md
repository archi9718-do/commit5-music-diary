# MoodWave API 연동 명세서 — 건호 ↔ 상현 ↔ 프론트엔드

- **작성 기준:** 2026-11-17 (PR #10 DB v5 및 합의된 확신도 0.7 기준 반영)
- **근거:** `archi9718-do/commit5-music-diary` 저장소 `main` 브랜치의 `backend/app/main.py`, `backend/app/schemas.py`, `backend/app/recommender.py`, `backend/app/db.py` 확인
- **상태:** 3.1~3.6은 현재 구현된 *MVP 개발용 API*, **3.7은 미구현·팀 검토용 설계안**입니다. 팀의 최종 연동 설계·배포 주소는 **확인 필요**
- **주의:** 기존 `API_CONTRACT.md`의 `mock_*` 예시는 오래된 정보입니다. 현재 추천 서버는 별도 CSV에 저장된 DEAM·PMEmo **점수**를 이용합니다.

> **추가 설계안 (2026-11-17):** 3.7은 PR #10 통합 이후 코드를 전제로 한 미구현·팀 검토용 초안입니다. 기존 구현 설명과 구분해서 읽어 주세요.

## 1. 전체 흐름과 화면 호출 순서

### 1.1. 기본 흐름 (프론트엔드 기준)

```
[기록 화면] 글 입력
   │  POST /api/records/analyze  {"text": "..."}
   ▼
[감정 확인 화면] 응답의 confidence로 화면 모양 선택
   │  높음: 확인 버튼 1개 (emotion)       + "다른 감정이에요" → 4개 버튼
   │  중간: 버튼 2개 (probs 상위 2개)     + "다른 감정이에요" → 4개 버튼
   │  낮음: 버튼 4개 (좋음·무난함·가라앉음·예민함)
   │  사용자가 버튼을 눌러야 다음으로 넘어감
   │  POST /api/recommendations  {"record_id": ..., "confirmed_emotion": "사용자가 누른 감정"}
   ▼
[추천 화면] songs 3곡을 받은 순서대로 표시 (step 순서에 의미 있음)
   │  GET /api/records/{record_id}/lp
   ▼
[오늘의 판 화면]
```

1. 프론트엔드가 **`POST /api/records/analyze`**를 한 번 호출합니다. 서버 안에서 `기록 생성 → 감정 분석 → 감정 결과 저장`이 끝나고, `record_id`와 감정 결과가 함께 돌아옵니다.
2. 프론트엔드는 `confidence`에 맞는 **감정 확인 화면**을 보여 줍니다. 예측값을 자동 확정하지 않습니다. 높음·중간 화면의 "다른 감정이에요"(4개 버튼으로 이동)는 AI가 틀렸을 때 사용자가 고칠 수 있게 하는 **제안**이며 팀 확인이 필요합니다.
3. 사용자가 누른 감정을 `confirmed_emotion`으로 **`POST /api/recommendations`**를 호출합니다. 추천은 예측 감정(`emotion`)이 아니라 이 값으로 합니다.
4. **`GET /api/records/{record_id}/lp`**로 기록과 3곡을 조회합니다.

### 1.2. 감정 분석을 쓸 수 없을 때 (대체 흐름)

`POST /api/records/analyze`가 **`503`**을 돌려주면:

1. **`POST /api/records`**로 글만 저장하고 `record_id`를 받습니다.
2. 감정 확인 화면을 **버튼 4개(낮음과 같은 화면)**로 보여 줍니다.
3. 이후는 기본 흐름 3~4번과 같습니다.

`422`(빈 글, 2,000자 초과)는 대체 흐름으로 가지 않고 글을 다시 입력받습니다.

### 1.3. 개발·시험용 흐름

감정 결과를 서버 밖에서 만들어 넣을 때(상현의 `ai/emotion/send_to_server.py` 등)는 `POST /api/records` → **`POST /api/emotions`** 순서로 호출합니다. 프론트엔드는 이 흐름을 쓰지 않습니다.

**업무 구분**
- 상현: 감정 모델 추론, `probs`, `emotion`, `confidence` 산출, `POST /api/records/analyze`의 감정 분석 부분, 추천 이유 생성·에이전트 흐름(후속 통합)
- 건호: `record_id` 발급, 감정 결과 저장, 사용자 확정 감정으로 3곡 추천, DB 저장·조회
- 프론트엔드: 기록 입력, 감정 확인 화면, API 호출, LP 화면 표시

## 2. 서버 기본 정보

| 구분 | 값 | 비고 |
|---|---|---|
| 개발 서버 | `http://127.0.0.1:8000` | 서버를 실행하는 **본인 컴퓨터** 기준 |
| Swagger | `http://127.0.0.1:8000/docs` | API 직접 시험 |
| 헬스체크 | `GET /health` | `{"status":"ok","service":"moodwave-backend"}` |
| 데이터 저장 | SQLite | 기본 위치 `backend/moodwave.db`, GitHub 제외 |
| 콘텐츠 유형 | `application/json` | 요청 본문이 있는 POST·PATCH 기준 |
| 프론트 로컬 CORS | `http://localhost:5173`, `http://127.0.0.1:5173`, `http://localhost:3000` | 현재 코드 기준 |

**네트워크 주의:** `127.0.0.1`은 해당 PC 자기 자신입니다. 상현의 PC에서 건호의 PC에 직접 접속하려면 공용 서버/접근 가능한 주소 및 접근 정책을 별도 정해야 합니다.

## 3. 구현된 API

| 순서 | Method | 경로 | 정상 상태 코드 | 역할 | 주 사용처 |
|---|---|---|---|---|---|
| 1 | `POST` | `/api/records/analyze` | `201` | 기록 생성 + 감정 분석 + 저장 (3.5) | 프론트엔드 기본 흐름 |
| 2 | `POST` | `/api/records` | `201` | 기록 생성, ID 발급 | 대체 흐름·개발용 |
| 3 | `POST` | `/api/emotions` | `200` | 감정 분석 결과 저장 | 개발·시험용 |
| 4 | `POST` | `/api/recommendations` | `200` | 최종 감정 기반 3곡 추천·저장 | 프론트엔드 |
| 5 | `GET` | `/api/records/{record_id}/lp` | `200` | LP 기록·추천곡·반응 조회 | 프론트엔드 |
| 6 | `PATCH` | `/api/records/{record_id}/songs/{recommend_order}` | `200` | 좋아요·건너뛰기·완청 저장 (3.6.1) | 프론트엔드 |
| 7 | `POST` | `/api/records/{record_id}/engrave` | `200` | 좋아요 곡만 LP에 새기기 (3.6.2) | 프론트엔드 |

### 3.1. 기록 생성 — `POST /api/records`

**요청 예시**
```json
{"text":"오늘 좀 지쳤어"}
```

**응답 예시 · 201**
```json
{"record_id":123,"text":"오늘 좀 지쳤어"}
```

- `text`: 문자열, 최대 2,000자. 기본값은 빈 문자열입니다.
- 반환된 `record_id`는 이후 요청에 동일하게 사용합니다. 123은 예시이며 실제로는 서버가 발급합니다.
- 한국 날짜 기준 회원당 하루 1건입니다. 같은 날 재기록하면 **같은 ID**를 반환하고 글·예측 감정·확신도·확률을 새 값으로 바꿉니다. 확정 감정·추천곡·반응·`flow_ended_at`은 초기화하고 `mood_asked_at`, `mood_after`는 보존합니다. 이 규칙은 `POST /api/records/analyze`에도 적용됩니다.

### 3.2. 감정 인식 결과 — `POST /api/emotions`

**상현이 전달할 요청 JSON**
```json
{
  "record_id":123,
  "text":"오늘 좀 지쳤어",
  "probs":{"좋음":0.05,"무난함":0.10,"가라앉음":0.72,"예민함":0.13},
  "emotion":"가라앉음",
  "confidence":"높음"
}
```

**응답 예시 · 200**
```json
{"record_id":123,"predicted_emotion":"가라앉음","saved":true}
```

**필드 및 검증 규칙 (현재 `schemas.py`)**

| 필드 | 타입 | 조건 |
|---|---|---|
| `record_id` | 정수 | 0보다 크고, 이미 생성된 ID여야 함 |
| `text` | 문자열 | 최대 2,000자 |
| `probs` | 문자열 → 실수 객체 | `좋음`, `무난함`, `가라앉음`, `예민함` 네 키가 **정확히** 있어야 함 |
| `probs` 각 값 | 실수 | 0~1 |
| `probs` 합계 | 실수 | 1과의 차이가 **0.02 이하** |
| `emotion` | 문자열 | 위 네 감정 중 하나 |
| `confidence` | 문자열 | `높음` / `중간` / `낮음` |

이 응답의 `predicted_emotion`은 **AI 예측 결과**이며, 확정 감정은 아닙니다.

**확신도 산출 기준 (2026-11-16 팀 합의, `ai/emotion/emotion_mapper.py`)**

| 4종 감정 중 최대 확률 | `confidence` | 기본 확인 버튼 |
|---|---|---|
| `0.7 이상` | `높음` | 예측 감정 1개 |
| `0.4 이상, 0.7 미만` | `중간` | 확률 상위 2개 |
| `0.4 미만` | `낮음` | 감정 4개 |

3.2와 3.5의 `높음` 예시는 최대 확률을 `0.72`로 맞췄고 확률 합은 1입니다. `0.62`라면 `중간`입니다. 이 기준은 감정 모델의 산출 규칙이며, 현재 `POST /api/emotions`의 스키마 검증이 확률로 `confidence`를 다시 계산하거나 그 일치 여부를 검사하는 것은 아닙니다.


### 3.3. 3곡 추천 — `POST /api/recommendations`

**요청 JSON**
```json
{"record_id":123,"confirmed_emotion":"가라앉음"}
```

**응답 예시 · 200**

다음 예시는 기존 통합 테스트에서 확인한 형태입니다. 실제 선정 곡은 점수표·추천 정책에 따라 바뀔 수 있습니다.

```json
{
  "songs":[
    {"song_id":"deam_1146","brightness":0.2,"energy":0.3,"step":"맞추기"},
    {"song_id":"deam_1147","brightness":0.45,"energy":0.325,"step":"조금 밝게"},
    {"song_id":"deam_1355","brightness":0.6625,"energy":0.35,"step":"더 밝게"}
  ]
}
```

- `confirmed_emotion`: **사용자가 최종 확인한** `좋음` / `무난함` / `가라앉음` / `예민함`.
- `songs`: **정확히 3개**.
- 각 곡: `song_id` (문자열), `brightness` (0~1), `energy` (0~1), `step` (추천 단계 문자열).
- 같은 `record_id`로 다시 호출하면 이전 3곡 추천·반응은 **새 결과로 교체**되고 `flow_ended_at`이 초기화됩니다. `mood_asked_at`, `mood_after`는 보존합니다. 같은 날 다른 감정을 시험할 때는 같은 ID로 다시 추천합니다.
- 현재 점수 간 유클리드 거리로 후보를 선택하며, 목표 좌표는 **1차 구현값(검증된 최적값 아님)**입니다.
- 추천 단계:
  - `좋음`·`무난함`: `비슷한 분위기 1` → `비슷한 분위기 2` → `비슷한 분위기 3`
  - `가라앉음`: `맞추기` → `조금 밝게` → `더 밝게`
  - `예민함`: `맞추기` → `에너지 낮추기` → `차분하고 조금 밝게`

### 3.4. LP 기록·추천곡·반응 조회 — `GET /api/records/{record_id}/lp`

예시 경로: `GET /api/records/123/lp`

**응답 예시 · 200**
```json
{
  "record_id": 123,
  "text": "오늘 좀 지쳤어",
  "confirmed_emotion": "가라앉음",
  "songs": [
    {
      "song_id": "deam_1146",
      "brightness": 0.2,
      "energy": 0.3,
      "step": "맞추기",
      "recommend_order": 1,
      "title": null,
      "artist": null,
      "is_liked": true,
      "is_skipped": false,
      "is_completed": true,
      "is_engraved": false
    },
    {
      "song_id": "deam_1147",
      "brightness": 0.45,
      "energy": 0.325,
      "step": "조금 밝게",
      "recommend_order": 2,
      "title": null,
      "artist": null,
      "is_liked": false,
      "is_skipped": false,
      "is_completed": true,
      "is_engraved": false
    },
    {
      "song_id": "deam_1355",
      "brightness": 0.6625,
      "energy": 0.35,
      "step": "더 밝게",
      "recommend_order": 3,
      "title": null,
      "artist": null,
      "is_liked": false,
      "is_skipped": true,
      "is_completed": false,
      "is_engraved": false
    }
  ],
  "note": "LP 새김은 POST /api/records/{record_id}/engrave 로 합니다(좋아요 곡만)."
}
```

곡별 `recommend_order`는 1~3, 반응 필드는 JSON 불리언입니다. `title`, `artist`는 메타데이터 입력 전에는 `null`입니다. 추천 전에는 `confirmed_emotion=null`, `songs=[]`일 수 있으며, 기록이 없으면 `404`입니다.

좋아요·건너뛰기·완청 저장 및 좋아요 곡 LP 새김 API는 구현되어 있습니다(3.6). 위 예시는 반응 저장 후 새기기 전 상태입니다. 음악 플레이어와 3.7의 감상 후 API는 미구현입니다.

### 3.5. 글 감정 분석 + 기록 생성 — `POST /api/records/analyze` (추가 경로, 상현)

화면이 이 경로를 **한 번만** 부르면 `기록 생성 → 감정 분석 → 감정 결과 저장`이 서버 안에서 끝납니다. 같은 날 재기록 시 3.1의 덮어쓰기 규칙이 적용됩니다.

**요청 JSON** (`POST /api/records`와 같음)
```json
{"text":"오늘 좀 지쳤어"}
```

**응답 예시 · 201** (`POST /api/emotions` 요청과 같은 감정 결과 양식)
```json
{
  "record_id":124,
  "text":"오늘 좀 지쳤어",
  "probs":{"좋음":0.02,"무난함":0.03,"가라앉음":0.23,"예민함":0.72},
  "emotion":"예민함",
  "confidence":"높음"
}
```

- `emotion`은 **AI 예측**입니다. 화면은 `confidence`에 따라 확인 버튼을 보여 주고(높음: 1개 / 중간: 상위 2개 / 낮음: 4개), 사용자가 고른 감정을 `POST /api/recommendations`의 `confirmed_emotion`으로 보냅니다.
- 저장 위치는 `/api/emotions`와 같습니다(DB v5 `tb_record`의 `emotion_pred`, `confidence_level`, `emotion_probs`).
- **실패 처리:** 감정 분석이 성공했을 때만 기록과 감정을 **한 번에** 저장합니다. 실패하면 아무것도 저장하지 않습니다.

| 상태 코드 | 원인 | 화면 처리 제안 |
|---|---|---|
| `422` | 빈 글, 2,000자 초과 (모델이 없어도 먼저 검사) | 글 다시 입력 |
| `503` | 감정 모델·AI 패키지 없음, 모델 실행 오류 | `POST /api/records`로 기록 후 감정 버튼 4개로 진행 |
| `500` | 모델 결과가 감정 결과 양식과 다름 | 서버 로그 확인 (저장 안 됨) |

**실행 조건**
- 파이썬 **3.11 이상**이 필요합니다(팀 기준). 실제로 확인한 버전은 3.14.7입니다(상현 GPU 컴퓨터).
- 감정 분석까지 쓰려면 `torch`·`transformers`가 설치된 가상환경에서 서버를 실행해야 합니다. 설치 방법은 `ai/requirements.txt` 맨 위 설명을 따릅니다.
- 모델 폴더는 환경 변수 `MOODWAVE_MODEL_DIR`로 지정합니다. 없으면 `C:\work\moodwave_data\models\klue-bert-base-sentiment`를 씁니다.
- 모델은 서버가 켜질 때 한 번만 불러옵니다(약 2초). 이후 글 한 줄 분석은 수 ms입니다(상현 GPU 컴퓨터 기준).
- 패키지나 모델이 없어도 서버와 감정 분석 이외의 API, pytest는 정상 동작합니다. 이때 서버 터미널에 `감정 분석 꺼짐: ...` 경고가 한 줄 나옵니다.

### 3.5.1. 녹음 감정 분석 + 기록 생성 — `POST /api/records/voice` (추가 경로, 상현)

녹음 파일을 보내면 `받아쓰기 → 글 감정 분석 → 기록·감정 저장`이 서버 안에서 끝납니다. 응답, 저장 위치, 같은 날 덮어쓰기 규칙은 3.5와 **같습니다**(서버 안에서 같은 함수를 씀). `text`에는 받아쓴 글이 들어갑니다.

**요청:** 녹음 파일을 요청 본문에 **그대로**(raw body) 보냅니다. multipart(`FormData`)가 아닙니다.
```js
// MediaRecorder로 모은 Blob을 그대로 보냄
fetch(`${base}/api/records/voice`, {method: "POST", headers: {"Content-Type": blob.type}, body: blob});
```
- 형식: webm(opus), wav, m4a 등 ffmpeg가 읽는 형식이면 됩니다. `Content-Type`은 참고용이고 서버가 내용으로 판단합니다.
- 크기: **3MB 이하** (10초 wav 48kHz 스테레오 약 1.9MB). 길이는 앞 **10초**만 받아씁니다.
- 녹음 원본은 메모리에서만 처리하고 **디스크에 쓰지 않습니다.** 응답 후 남지 않습니다(multipart 임시 파일도 없음).

**응답 · 201:** 3.5와 같은 감정 결과 양식.

| 상태 코드 | 원인 | 화면 처리 제안 |
|---|---|---|
| `400` | 빈 본문, 읽을 수 없는 녹음 파일 | 다시 녹음 |
| `413` | 3MB 초과 | 다시 녹음 (10초 제한 확인) |
| `422` | 말소리 없음(무음·고른 잡음), 받아쓴 글이 빔 | 다시 녹음 또는 글로 기록 |
| `503` | 받아쓰기·감정 모델·AI 패키지 없음, 모델 실행 오류 | 글로 기록(3.5) 또는 `POST /api/records` 후 감정 버튼 4개 |
| `500` | 모델 결과가 감정 결과 양식과 다름 | 서버 로그 확인 |

어떤 실패에서도 기록을 저장하지 않습니다(오늘 기록도 덮어쓰지 않음).

**무음 처리:** Whisper는 무음·잡음에서 글을 지어냅니다(11/19 확인: 무음 → "한글자막 제공 및 …", 잡음 → "감사합니다."). 두 겹으로 막습니다. (1) 30ms 조각별 소리 크기의 "큰 쪽 ÷ 조용한 쪽" 비율이 2 미만이면 말소리 없음(데이터셋 말소리 1,000개 중 잘못 막은 것 0개) (2) 자주 지어내는 문구(`자막`, `시청해 주셔서`, 단독 `감사합니다`)면 빈 글. 실제 크롬 녹음으로 기준을 다시 맞출 예정입니다.

**실행 조건**
- 파이썬 **3.12 이상**(`av` 19.0.2 조건), `ai/requirements.txt`의 `av`. ffmpeg는 `av` 안에 들어 있어 따로 설치하지 않습니다.
- 모델: GPU면 `large-v3-turbo`, 없으면 `base`. 환경 변수 `MOODWAVE_STT_MODEL`로 바꿉니다. 모델 파일은 `C:\work\moodwave_data\hf_cache\hub`(환경 변수 `MOODWAVE_HF_CACHE`)에 받습니다.
- 서버가 켜질 때 받아쓰기 모델도 미리 불러옵니다(GPU 약 3~9초). 실패하면 이 경로만 503이고 서버 터미널에 `받아쓰기 꺼짐: ...`이 나옵니다.

**측정 (11/19)**
- 장비: Intel i7-12700, RAM 16GB, NVIDIA RTX 5060 Ti / Python 3.14.7, torch 2.15.0+cu132, transformers 5.22.2, av 19.0.2
- GPU `large-v3-turbo` fp16, 미리 불러온 뒤, 6.4초 webm 녹음 1개: 요청 → 응답 **0.25초** (본문 읽기 + 해독 + 받아쓰기 + 글 감정 + DB 저장. 네트워크 전송 제외, 같은 컴퓨터 안 시험 클라이언트)
- CPU `base` fp32: 받아쓰기만 평균 1.64초 (S3, 녹음 30개 평균 7.1초, 준비 실행 1회 뒤, 파일 해독·글 감정 제외)

### 3.6. 추천곡 반응·LP 새김 및 UI 연동 — DB v5 기준

PR #10으로 main에 통합된 `backend/app/main.py`, `backend/app/schemas.py`, `backend/app/schema.sql` 기준입니다.

#### 3.6.1. 추천곡 반응 저장 — `PATCH /api/records/{record_id}/songs/{recommend_order}`

**요청 예시** (1번 곡에 좋아요)

```json
{"is_liked":true}
```

**응답 예시 · 200**

```json
{"record_id":123,"recommend_order":1,"song_id":"deam_1146","is_liked":true,"is_skipped":false,"is_completed":false,"is_engraved":false}
```

- `record_id`는 양의 정수, `recommend_order`는 추천 순서 1~3입니다.
- `is_liked`, `is_skipped`, `is_completed` 중 하나 이상을 보냅니다. 보낸 필드만 바꾸고, 생략하거나 `null`인 필드는 기존 값을 유지합니다. 유효한 값이 하나도 없으면 `422`입니다. `false`는 값을 끄는 요청입니다.
- 좋아요와 건너뛰기, 건너뛰기와 완청은 동시에 참일 수 없습니다(`409`, 변경 없음). SQLite CHECK 제약도 같은 조합을 막습니다.
- 좋아요를 취소하면 `is_engraved`도 `false`가 됩니다. 좋아요를 켜는 것만으로 새겨지지는 않습니다. `is_engraved`는 이 PATCH의 수정 필드가 아니며 새기기 API로 설정합니다.

| 상태 | 원인 |
|---|---|
| `404` | 해당 기록·추천 순서의 곡이 없음 |
| `409` | 기존 상태와 합친 결과에 좋아요+건너뛰기 또는 건너뛰기+완청이 동시에 참 |
| `422` | 잘못된 ID·순서·필드 타입 또는 유효한 반응 필드가 없음 |

#### 3.6.2. 좋아요 곡 LP 새김 — `POST /api/records/{record_id}/engrave`

요청 본문을 생략하면 좋아요 곡을 모두 새깁니다. `{"recommend_orders":[1,3]}`을 보내면 선택한 추천 순서 중 좋아요한 곡만 새깁니다. 프론트의 ‘기록만 저장하기’는 빈 배열을 보내 새김을 모두 해제합니다. 같은 선택과 반응 상태에서 반복 호출하면 결과가 같습니다.

**응답 예시 · 200** (좋아요한 곡은 1번뿐인 상태)

```json
[
  {"record_id":123,"recommend_order":1,"song_id":"deam_1146","is_liked":true,"is_skipped":false,"is_completed":true,"is_engraved":true},
  {"record_id":123,"recommend_order":2,"song_id":"deam_1147","is_liked":false,"is_skipped":false,"is_completed":true,"is_engraved":false},
  {"record_id":123,"recommend_order":3,"song_id":"deam_1355","is_liked":false,"is_skipped":true,"is_completed":false,"is_engraved":false}
]
```

응답은 추천 순서로 정렬한 3.6.1 형식의 배열입니다. 기록은 있지만 추천 전이면 빈 배열 `[]`, 기록이 없으면 `404`, 양의 정수가 아닌 ID면 `422`입니다. 감상 종료·질문 표시·기분 저장은 자동 실행하지 않습니다.

#### 3.6.3. UI 연동 원칙

**MVP 완청 판정:** 플레이어의 `onEnded`에서 완청으로 처리합니다.

| 경계 사례 | 프론트엔드 처리 | 저장 결과 |
|---|---|---|
| 이전에 건너뛴 곡을 다시 끝까지 재생 (`onEnded`) | 같은 PATCH 본문에 `{"is_skipped":false,"is_completed":true}`를 함께 전송합니다. `{"is_completed":true}`만 보내면 기존 건너뛰기 값이 남아 `409`입니다. | `is_skipped=false`, `is_completed=true` |
| 좋아요한 곡에서 건너뛰기 (2026-11-19 확정: 한쪽을 누르면 다른 쪽이 풀림) | 같은 PATCH 본문에 `{"is_liked":false,"is_skipped":true}`를 함께 전송합니다. `{"is_skipped":true}`만 보내면 기존 좋아요가 남아 `409`입니다. 이미 완청한 곡이면 아래 행이 우선이라 보내지 않습니다. | `is_liked=false`, `is_skipped=true`, `is_engraved=false` |
| 건너뛴 곡에서 좋아요 (2026-11-19 확정) | 같은 PATCH 본문에 `{"is_liked":true,"is_skipped":false}`를 함께 전송합니다. | `is_liked=true`, `is_skipped=false` |
| 이미 완청한 곡을 다시 재생하다가 건너뛰기 | 프론트는 해당 곡의 건너뛰기 PATCH를 전송하지 않습니다. 완청을 취소하는 PATCH도 보내지 않습니다. | 기존 `is_completed=true`, `is_skipped=false` 유지 |

**409 응답 처리:** 이 PATCH에서 `409`를 받으면 일반 오류 화면이나 오류 팝업을 띄우지 않고 넘어갑니다. 실패한 변경은 성공으로 반영하지 않고 기존 상태를 유지하며, LP를 다시 조회하여 화면 상태를 서버와 맞춥니다.

**후속 개선안 (MVP 미적용):** 재생바를 끝으로 옮겨 `onEnded`가 발생하는 경우에 대비해, 실제 누적 재생시간이 곡 길이의 90% 이상일 때만 완청으로 인정하는 검증을 검토합니다.

### 3.7. 감상 종료·감상 후 기분 — 미구현 설계안

**상태: 2026-11-17 작성 초안. 아래 경로·응답·정책은 아직 구현되지 않았으며 팀 검토 후 구현합니다. 현재 Swagger에서는 호출할 수 없습니다.** DB v5의 `flow_ended_at`, `mood_asked_at`, `mood_after`를 사용하고 새 테이블은 만들지 않는 안입니다.

**적용 전제:** PR #10이 통합된 최신 main과 DB v5 기준입니다. 로컬 코드가 이전 버전이면 먼저 최신 코드와 작업 브랜치를 맞춘 뒤 구현합니다. 이 절 추가만으로 아래 기능이 생기는 것은 아닙니다.

#### 3.7.1. 호출 순서와 공통 규칙

1. 기존 API로 기록·사용자 확정 감정·추천 3곡을 준비합니다.
2. 곡별 완청·건너뛰기는 DB v5 곡별 반응 PATCH로 저장하고 응답을 기다립니다.
3. 세 번째 곡의 재생 종료·건너뛰기·재생 실패로 3곡 흐름이 끝나면 `POST /api/records/{record_id}/flow/end`를 호출합니다. 이 요청 자체는 곡별 반응을 변경하지 않습니다.
4. 응답의 `should_ask_mood`가 `true`이면 질문 표시 직전에 `POST /api/records/{record_id}/mood-question`을 호출합니다. 이 요청에서 표시를 허용받은 경우에만 질문을 띄웁니다.
5. 사용자가 답하거나 명시적으로 질문을 건너뛰면 `PATCH /api/records/{record_id}/mood-after`로 저장합니다. 새로고침·재접속 시 `GET /api/records/{record_id}/post-listening`으로 상태만 조회합니다.

| Method | 경로 | 정상 상태 | 역할 |
|---|---|---|---|
| `GET` | `/api/records/{record_id}/post-listening` | `200` | 현재 종료·질문·응답 상태 조회, DB 변경 없음 |
| `POST` | `/api/records/{record_id}/flow/end` | `200` | 흐름 종료 기록, 질문 대상 여부 반환 |
| `POST` | `/api/records/{record_id}/mood-question` | `200` | 하루 한 번 질문 표시 권한 확보 및 시각 기록 |
| `PATCH` | `/api/records/{record_id}/mood-after` | `200` | 감상 후 응답 또는 명시적 무응답 저장 |

- `record_id`는 0보다 큰 정수입니다. 로그인 전에는 기존 시연용 회원의 기록을 사용하는 개발용 API이며, 운영용 접근 제어는 별도 구현 대상입니다.
- GET과 두 POST에는 요청 본문이 없습니다. PATCH에는 아래 JSON만 보냅니다.
- 시각은 클라이언트가 보내지 않고 서버가 정합니다. 응답은 UTC ISO 8601 문자열(`2026-11-17T03:00:00Z`), 미설정은 `null`입니다. 하루 구분은 기존 `record_date`의 한국 날짜를 따릅니다.
- 완료한 서로 다른 `song_id` 수를 `completed_song_count`로 계산합니다. 같은 곡의 반복 재생·PATCH 재시도는 중복으로 세지 않으며 좋아요·건너뛰기·재생 실패를 완청으로 추정하지 않습니다.
- 질문 대상은 **사용자 확정 감정이 `가라앉음` 또는 `예민함`이고, 흐름 종료 시각이 있으며, 현재 추천곡 중 2곡 이상 완청했고, 질문 표시 기록과 응답이 모두 없는 경우**입니다. AI 예측 감정으로 판정하지 않습니다.
- `should_ask_mood`는 위 조건의 계산 결과이며, 조회·종료 응답의 `true`만으로 질문을 표시하지 않습니다. 실제 표시 권한은 `mood-question`에서 원자적으로 확보합니다.

#### 3.7.2. 상태 조회와 흐름 종료

**GET 응답 예시 · 200** (흐름 종료 전, 완청 2곡)

```json
{
  "record_id": 123,
  "flow_ended_at": null,
  "completed_song_count": 2,
  "should_ask_mood": false,
  "mood_asked_at": null,
  "mood_after": null
}
```

`POST /api/records/123/flow/end`도 같은 여섯 필드를 반환합니다. 종료 후에는 `flow_ended_at`이 채워지고 질문 조건을 만족하면 `should_ask_mood`가 `true`입니다.

- 확정 감정과 추천 3곡이 준비되지 않았으면 종료 요청은 `409`입니다. 준비됐으면 완청 0~1곡인 경우에도 흐름은 종료하며 질문은 생략합니다.
- 처음 요청만 `flow_ended_at`을 기록합니다. 반복 요청은 최초 시각을 유지하고 현재 상태를 반환합니다. 질문 표시·응답·LP 새김을 자동 실행하지 않습니다.
- 조회 시 완청 수나 질문 대상 여부는 별도 저장값이 아니라 현재 추천곡 상태로 계산합니다. 종료 후 반응 수정으로 조건이 달라져도 이미 기록된 질문·응답은 취소하지 않습니다.
- 종료 요청은 플레이어가 보낸 종료 이벤트를 신뢰하는 MVP입니다. 재생 실패와 건너뛰기를 구분한 종료 사유 저장·실제 재생시간 검증은 후속 범위입니다.

#### 3.7.3. 질문 표시 — `POST /api/records/{record_id}/mood-question`

**응답 예시 · 200** (최초로 표시 권한을 얻은 요청)

```json
{
  "record_id": 123,
  "show_question": true,
  "mood_asked_at": "2026-11-17T03:00:00Z",
  "mood_after": null
}
```

- 질문 대상 조건을 서버에서 다시 검사하고, 조건 확인과 `mood_asked_at` 최초 저장을 같은 트랜잭션으로 처리합니다. 동시 요청 중 하나만 `show_question=true`를 받습니다.
- 질문이 이미 기록돼 있으면 `200`, `show_question=false`와 기존 시각·응답을 반환합니다. 재시도는 시각을 바꾸거나 질문을 다시 열지 않습니다. 이 경우 현재 완청 수·감정이 바뀌었더라도 중복 요청으로 처리합니다.
- 아직 질문 기록이 없고 대상 조건을 만족하지 않으면 `409`이며 아무것도 저장하지 않습니다.
- 화면 문구는 **“음악을 듣고 난 지금 기분은 어떤가요?”**, 선택지는 아래 세 응답과 별도의 “건너뛰기”를 제안합니다.
- 이 안의 `mood_asked_at`은 실제 화면 렌더링 완료가 아닌 **서버의 최초 표시 허용 시각**으로 사용합니다. 응답 유실·화면 종료로 질문이 실제로 보이지 않아도 자동 재표시하지 않는 MVP 정책입니다. 서버 기록만으로 실제 노출을 보장할 수 없으며, 이 의미와 복구 정책은 팀 검토 대상입니다.

#### 3.7.4. 기분 저장 — `PATCH /api/records/{record_id}/mood-after`

**요청 예시**

```json
{"mood_after":"조금 나아졌어요"}
```

**응답 예시 · 200**

```json
{
  "record_id": 123,
  "mood_asked_at": "2026-11-17T03:00:00Z",
  "mood_after": "조금 나아졌어요"
}
```

| 입력값 | 의미 |
|---|---|
| `조금 나아졌어요` | 사용자가 직접 선택한 응답 |
| `그대로예요` | 사용자가 직접 선택한 응답 |
| `더 무거워졌어요` | 사용자가 직접 선택한 응답 |
| `무응답` | 사용자가 명시적으로 “건너뛰기”를 선택함 |

- `mood_after`는 필수이며 위 네 문자열만 허용합니다. 빈 본문·누락·`null`·그 외 문자열은 `422`입니다. 시간·감정·임의의 추가 필드는 받지 않습니다(`422`).
- `mood_asked_at`이 없으면 `409`입니다. 서버가 질문을 자동 기록하거나 사용자 응답을 추정하지 않습니다.
- 최초 응답만 저장합니다. 같은 값 재전송은 `200`으로 기존 결과를 반환하고, 이미 저장된 값과 다른 값으로 변경하려 하면 `409`입니다. 이 확인과 저장도 하나의 트랜잭션으로 처리합니다.
- 질문을 닫거나 연결이 끊긴 사실만으로 `무응답`을 저장하지 않습니다. 명시적 선택 없이 종료됐다면 `mood_after=null`로 남습니다. 답변이 없는 상태로 다시 접속해도 질문은 자동 재표시하지 않습니다.
- 같은 날 재기록·재추천 이후에도 표시 기록이 있고 응답이 `null`이면 기존 질문에 대한 응답을 받을 수 있습니다. 이때 현재 감정·완청 조건을 다시 요구하지 않습니다. 이미 답변했다면 기존 응답을 보존합니다.

#### 3.7.5. 예외·동일 날짜 재시작·검증 기준

| 상태 | 적용 범위와 원인 | 처리 |
|---|---|---|
| `404` | 네 API 공통: 기록이 없음 | 기록부터 다시 확인 |
| `422` | 네 API 공통: 잘못된 ID. PATCH: 허용하지 않는 본문 | 입력 수정, DB 변경 없음 |
| `409` | 종료: 감정·추천곡 미준비. 질문: 최초 표시 조건 미충족. 응답: 질문 전 저장·기존 응답 변경 | 상태를 다시 조회, DB 변경 없음 |

오류 본문은 기존 API와 같이 `{"detail":"오류 설명"}` 형태이며 `422`는 FastAPI 검증 오류 배열입니다. **PR #10의 곡별 반응 PATCH에 대한 409 무표시 규칙은 해당 PATCH에 한정**합니다. 이 절의 409는 상태를 재조회해 질문을 생략하거나 이미 저장된 결과를 안내하며, 실패한 요청을 성공으로 표시하지 않습니다.

같은 날 재기록·재추천 시 기존 코드대로 `flow_ended_at`을 초기화하고 질문·응답은 보존합니다. 다음 날에는 다른 `record_id`가 생성돼 질문 상태가 새로 시작됩니다. 질문 횟수는 회원·기록 날짜당 최대 한 번의 **표시 허용**이며, 세션당 한 번이 아닙니다.

**MVP 제한:** 같은 기록을 재추천해도 `record_id`는 같고 흐름 버전이 없습니다. 화면은 이전 재생을 중지하고 곡별 PATCH·종료 요청이 끝난 뒤에만 재기록·재추천해야 합니다. 여러 탭·지연된 이전 요청을 서버에서 완전히 구별하려면 별도 흐름 ID 또는 버전 검증이 필요하며 후속 과제입니다.

**구현 후 완료 기준** (현재 테스트 결과가 아닌 신규 테스트 계획)

- 확정 감정 4종 × 완청 0·1·2·3곡 × 종료 전후의 질문 대상 경계 확인
- AI 예측과 확정 감정이 다를 때 확정 감정 기준 판정, 반복 완청은 중복 집계하지 않음
- 질문 대상이 아니어도 종료 가능, 추천 전 종료는 `409`, 종료 재시도 시 최초 시각 보존
- 조회만으로 DB가 바뀌지 않음, 질문 동시 요청·재시도 중 최초 하나만 표시 허용
- 질문 전 응답·다른 값 덮어쓰기 `409`, 같은 값 재시도 `200`, 잘못된 응답 `422`
- 명시적 건너뛰기만 `무응답` 저장, 단순 종료는 `null` 유지
- 동시 응답도 최초 하나만 저장, 실패한 요청은 DB 변경 없음
- 같은 날 재기록·재추천 후 질문·응답 보존, 다음 날 새 기록, 서버 재시작 후 상태 유지
- 기존 곡별 409·LP 새김·감정 분석 대체 흐름과 전체 pytest·Ruff 통과

## 4. 대표 오류 처리

| 상태 코드 | 뜻/대표 원인 | 조치 |
|---|---|---|
| `404` | 존재하지 않는 `record_id` | 먼저 기록 생성 후 발급된 ID 사용 |
| `422` | 잘못된 JSON / 필드 누락 / 잘못된 감정 또는 확률 | 요청 JSON·타입·확률 합계 확인 |
| `503` | CSV 점수표 환경변수 미설정, 파일 오류, 후보 부족 | 서버의 CSV 경로·데이터 상태 확인 |
| `500` | 기타 서버 내부 문제 | 서버 터미널 로그 확인 |

## 5. 로컬 서버 실행

Windows PowerShell 기준입니다. **서버용 터미널과 작업용 터미널을 나눠** 씁니다(VS Code 터미널의 `+`). 모든 명령은 저장소 최상위 폴더(예: `C:\work\commit5-music-diary`)를 기준으로 합니다.

### 5.1. 공통 준비: 점수표 위치

- `song_scores.csv` 및 원본 음원은 **GitHub 저장소에 포함되어 있지 않습니다**. 점수표를 팀에 전달할 수 있는 라이선스/배포 조건을 확인하거나 각자 자료를 추출해야 합니다.
- 점수표가 없으면 시험용 점수표 `backend\tests\fixtures\sample_song_scores.csv`(인공 점수 13곡)로 흐름만 확인할 수 있습니다.
- `MOODWAVE_RECOMMEND_SCOPE=DEAM`: 기본 시연·추천 후보 범위. `ALL`: DEAM + PMEmo 내부 테스트 후보 범위.

### 5.2. 방법 A — 서버만 실행 (감정 분석 없이)

AI 패키지가 필요 없습니다. 이때 `POST /api/records/analyze`만 `503`이고, 나머지 API는 정상입니다.

```powershell
cd backend
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt

$env:MOODWAVE_SCORES_CSV="C:\work\moodwave_data\processed\song_scores.csv"
$env:MOODWAVE_RECOMMEND_SCOPE="DEAM"

python -m uvicorn app.main:app --reload
```

- `MOODWAVE_SCORES_CSV`는 **해당 컴퓨터에서 실제 CSV가 있는 경로**로 변경해야 합니다.
- 서버 시작 로그에 `감정 분석 꺼짐: ...` 경고가 한 줄 나오는 것은 정상입니다.

### 5.3. 방법 B — 감정 분석까지 실행

**필요한 것:** 파이썬 3.11 이상(확인한 버전 3.14.7), `torch`·`transformers`, 감정 모델 폴더. 서버 패키지와 AI 패키지를 **같은 가상환경**에 설치해야 합니다.

**B-1. 이미 준비된 가상환경을 쓰는 경우 (상현 컴퓨터)**

`C:\work\moodwave_data\.venv`에 서버 패키지·AI 패키지·GPU용 torch가 모두 설치되어 있습니다.

```powershell
cd backend
$env:MOODWAVE_SCORES_CSV="C:\work\moodwave_data\processed\song_scores.csv"
$env:MOODWAVE_RECOMMEND_SCOPE="DEAM"
$env:MOODWAVE_MODEL_DIR="C:\work\moodwave_data\models\klue-bert-base-sentiment"
C:\work\moodwave_data\.venv\Scripts\python.exe -m uvicorn app.main:app --reload
```

**B-2. 새로 준비하는 경우**

방법 A의 가상환경을 켠 상태에서, `backend` 폴더에서 **아래 순서대로** 실행합니다.

```powershell
# 1) GPU가 있으면 GPU용 torch를 먼저 설치 (CUDA 버전에 맞는 주소 사용. 아래는 상현 컴퓨터 예시)
#    GPU가 없으면 이 줄은 건너뜀 → 2)에서 일반(CPU) torch가 설치됨
python -m pip install torch==2.15.0 --index-url https://download.pytorch.org/whl/cu132

# 2) AI 패키지 설치
python -m pip install -r ..\ai\requirements.txt

# 3) 감정 모델 내려받기 (처음 한 번만, 인터넷 필요)
python ..\ai\emotion\download_model.py

# 4) 환경 변수 지정 후 실행
$env:MOODWAVE_SCORES_CSV="C:\work\moodwave_data\processed\song_scores.csv"
$env:MOODWAVE_RECOMMEND_SCOPE="DEAM"
$env:MOODWAVE_MODEL_DIR="C:\work\moodwave_data\models\klue-bert-base-sentiment"
python -m uvicorn app.main:app --reload
```

- 1)과 2)의 순서가 바뀌면 GPU용 대신 일반 torch가 먼저 설치될 수 있습니다.
- `download_model.py`는 모델을 `C:\work\moodwave_data\models\klue-bert-base-sentiment`에 저장합니다. 다른 위치에 두었다면 `MOODWAVE_MODEL_DIR`를 그 위치로 바꿉니다.
- 환경 변수(`$env:...`)는 **그 터미널 창에서만** 유지됩니다. 창을 새로 열면 다시 지정합니다.

**B-3. 정상 실행 확인**

| 서버 시작 로그 | 뜻 |
|---|---|
| `Loading weights: 100%` 다음 `Application startup complete.` | 모델 정상 로딩. `POST /api/records/analyze` 사용 가능 |
| `감정 분석 꺼짐: 감정 분석 패키지를 불러오지 못했습니다 (...torch...)` | torch 없는 가상환경으로 실행함 → 방법 B의 가상환경으로 다시 실행 |
| `감정 분석 꺼짐: 감정 모델을 불러오지 못했습니다 (FileNotFoundError ...)` | 모델 폴더 경로 확인 (`MOODWAVE_MODEL_DIR`) |

어느 경우든 기존 기록·음악 추천·LP 조회 API는 계속 사용할 수 있습니다.

## 6. 통합 테스트 순서와 완료 기준

Swagger(`http://127.0.0.1:8000/docs`)에서 각 경로를 펼치고 `Try it out` → 입력 → `Execute` 순서로 시험합니다.

**6.1. 기본 흐름 (방법 B로 실행)**
1. `POST /api/records/analyze` `{"text":"오늘 좀 지쳤어"}` → `201`, 감정 결과 5개 키(`record_id`, `text`, `probs`, `emotion`, `confidence`) 확인. `record_id` 기록
2. `POST /api/recommendations` `{"record_id": 1번 ID, "confirmed_emotion": "가라앉음"}` → `200`, 서로 다른 곡 **3개**
3. `GET /api/records/{record_id}/lp` → 같은 글·확정 감정·3곡
4. 서버 재시작 후 3번을 반복해 데이터 유지 확인

**6.2. 오류·대체 흐름**
1. `POST /api/records/analyze` `{"text":"   "}` → `422` (모델이 없어도 422)
2. 방법 A로 실행 후 `POST /api/records/analyze` → `503`, 이어서 `POST /api/records` → `201`이고 이후 6.1의 2~3번 정상

**6.3. 자동 시험**
```powershell
cd backend
python -m pytest -q
```
PR #10 통합 후 기존 테스트는 `25 passed`가 기준입니다(2026-11-17 확인). 3.7 구현 시 신규 테스트로 개수가 늘어납니다. `test_analyze.py`는 가짜 감정 함수를 쓰므로 모델이 없는 컴퓨터에서도 통과합니다.

**확인 결과 (2026-11-11)**
- 건호: 모델 없는 환경에서 서버 정상 실행과 `503` 확인, pytest `20 passed`, Ruff 통과, 실제 DEAM 점수표로 `기록 → 감정 저장 → 3곡 추천 → LP 조회` 성공
- 상현: 실제 감정 모델(GPU)로 6.1 흐름 성공(시험용 점수표 사용). 모델 불러오기 약 2초(서버 시작 때 한 번), 글 한 줄 분석 약 5ms

## 7. 팀 협의 사항

**정해진 것 (2026-11-11)**
- 감정 결과 전달 경로: 건호 서버가 상현의 `ai.emotion.service.analyze_text()`를 직접 호출 (`POST /api/records/analyze`). 감정 전용 서버는 따로 두지 않음
- 감정 분석 실패 시: 아무것도 저장하지 않고 `503`. 화면은 대체 흐름(1.2)
- 감정 확신도별 확인 화면: 높음 1개 / 중간 2개 / 낮음 4개 버튼. 기준값은 높음 0.7 / 중간 0.4 (2026-11-16, 짧은 구어체 80문장 검증으로 높음 0.6 → 0.7)

**정해진 것 (2026-11-18 멘토링 · 11/19 팀 답장)**
- 감정 범위: **4종 유지**(좋음·무난함·가라앉음·예민함). 멘토 조언("기본 감정까지만, 조합·세분화는 하지 않음")에 따라 감정 조합·세분화는 하지 않습니다. 결과 양식·API 변경 없음
- 음악 재생: 서버에 저장한 음원을 직접 재생합니다. 외부 재생 연동은 음원이 많아질 때 검토
- 감정 분류 평가: 정밀도·재현율·F1 (`ai/emotion/evaluate_f1.py`). 첫 모델 60~70% 수준도 가능하다는 전제
- 추천 적합도·기분 변화 평가: 반 친구 약 25명 사용자 평가. 결과가 나빠도 원인 분석과 "무엇을 발견해 어떻게 고쳤는지"를 발표에 포함
- 짧은 말투 오류: 목소리 감정(필수 기능)으로 보완을 우선하고, 시간이 부족하면 감정 사전 보완. 한 단어 대답("뭐야")은 분석이 어렵다는 한계로 명시
- 감상 후 응답 문구: DB `mood_after` 규격(`조금 나아졌어요` / `그대로예요` / `더 무거워졌어요` / 건너뛰기 = `무응답`)에 화면을 맞춤
- 감상 후 질문 조건: 확정 감정이 `가라앉음`·`예민함`이고 2곡 이상 완청한 경우만 (3.7과 같음)
- 좋아요·건너뛰기: 한쪽을 누르면 다른 쪽이 풀림 (3.6.3)
- 녹음 길이: 최대 10초 (받아쓰기 측정 범위 5~10초와 같음)
- 화면: 프로필 나누기 없음. 처음 들어가면 바로 쓰기. 사용자별 첫 화면 순서 맞춤 예시 2~3개(기록~추천은 순서 고정, "오늘의 판"은 앞에 둘 수 있음)
- 멘토 의견이 없어 팀 결정을 유지하는 것: 확신도 0.7, "다른 감정이에요" 버튼, 기능을 빼는 순서

**남은 것**
- 다음 멘토링에서 다시 물을 것: 추천 기준(지금의 DEAM 밝기·에너지 점수 vs 음악 예측 모델 학습), 모델 연동 방식(받아쓰기 + 목소리 감정 + 글 감정을 모두 연결하는 방식이 맞는지)
- 콘텐츠 확장(멘토 제안): 명상 소리·낭독처럼 한 분야 집중(캄 Calm 사례) 또는 운동·여행 등 유튜브 연동. 범위를 작게 유지하라는 조언과 함께 팀 결정 필요
- 저작권 질문 대비 답변 준비(멘토 예시: 문제를 알고 있고, 수익을 내면 계약이 필요하며, 이번은 교육용 프로젝트)
- 녹음 업로드: 서버 경로는 3.5.1로 구현(원본은 디스크에 쓰지 않음). 화면에서 녹음 Blob을 보내는 부분은 남음
- 받아쓰기 서버 컴퓨터: GPU면 `large-v3-turbo`(평균 0.20초), CPU만 있으면 `base`(평균 1.64초). 상현 PC(RTX 5060 Ti)의 서버 가상환경에서 CUDA 동작 확인(11/19). 시연 서버를 어느 PC로 할지 결정 필요
- 에이전트 호출 위치(추천 경로 뒤 또는 별도 경로)와 최근 7일 기록 조회 기능 (4주차 초)
- 감상 종료·감상 후 질문·응답 API (3.7 검토 후 구현). 좋아요·건너뛰기·완청 및 좋아요 곡 LP 새김 API는 PR #10으로 통합 완료
- 감정별 판 기본곡·판 조회 및 주간 리캡
- 사용자 인증·개인정보 동의·녹음 동의 기록·배포 정책
- DEAM 원본 점수 1,802곡과 기존 기획 유효 1,744곡의 차이
- DEAM/PMEmo **음원**의 공개 재생/배포 권한 및 점수표 팀 공유 가능 범위

> 감정 추정은 의료 진단이 아닙니다. 사용자 기록에 없는 사건이나 감정을 만들어 저장하지 않습니다.
