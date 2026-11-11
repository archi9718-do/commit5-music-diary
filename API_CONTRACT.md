# MoodWave API 연동 명세서 — 건호 ↔ 상현 ↔ 프론트엔드

- **작성 기준:** 2026-11-11
- **근거:** `archi9718-do/commit5-music-diary` 저장소 `main` 브랜치의 `backend/app/main.py`, `backend/app/schemas.py`, `backend/app/recommender.py`, `backend/app/db.py` 확인
- **상태:** 현재 구현된 *MVP 개발용 API*. 팀의 최종 연동 설계·배포 주소는 **확인 필요**
- **주의:** 기존 `API_CONTRACT.md`의 `mock_*` 예시는 오래된 정보입니다. 현재 추천 서버는 별도 CSV에 저장된 DEAM·PMEmo **점수**를 이용합니다.

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
| 콘텐츠 유형 | `application/json` | 요청 본문이 있는 POST 기준 |
| 프론트 로컬 CORS | `http://localhost:5173`, `http://127.0.0.1:5173`, `http://localhost:3000` | 현재 코드 기준 |

**네트워크 주의:** `127.0.0.1`은 해당 PC 자기 자신입니다. 상현의 PC에서 건호의 PC에 직접 접속하려면 공용 서버/접근 가능한 주소 및 접근 정책을 별도 정해야 합니다.

## 3. 구현된 API

| 순서 | Method | 경로 | 정상 상태 코드 | 역할 | 주 사용처 |
|---|---|---|---|---|---|
| 1 | `POST` | `/api/records/analyze` | `201` | 기록 생성 + 감정 분석 + 저장 (3.5) | 프론트엔드 기본 흐름 |
| 2 | `POST` | `/api/records` | `201` | 기록 생성, ID 발급 | 대체 흐름·개발용 |
| 3 | `POST` | `/api/emotions` | `200` | 감정 분석 결과 저장 | 개발·시험용 |
| 4 | `POST` | `/api/recommendations` | `200` | 최종 감정 기반 3곡 추천·저장 | 프론트엔드 |
| 5 | `GET` | `/api/records/{record_id}/lp` | `200` | 임시 LP 기록·추천곡 조회 | 프론트엔드 |

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

### 3.2. 감정 인식 결과 — `POST /api/emotions`

**상현이 전달할 요청 JSON**
```json
{
  "record_id":123,
  "text":"오늘 좀 지쳤어",
  "probs":{"좋음":0.10,"무난함":0.15,"가라앉음":0.62,"예민함":0.13},
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
- 같은 `record_id`로 다시 호출하면 이전 3곡 추천 기록은 **새 결과로 교체**됩니다. 서로 다른 감정 테스트에는 새 ID를 발급받으세요.
- 현재 점수 간 유클리드 거리로 후보를 선택하며, 목표 좌표는 **1차 구현값(검증된 최적값 아님)**입니다.
- 추천 단계:
  - `좋음`·`무난함`: `비슷한 분위기 1` → `비슷한 분위기 2` → `비슷한 분위기 3`
  - `가라앉음`: `맞추기` → `조금 밝게` → `더 밝게`
  - `예민함`: `맞추기` → `에너지 낮추기` → `차분하고 조금 밝게`

### 3.4. 임시 LP 조회 — `GET /api/records/{record_id}/lp`

예시 경로: `GET /api/records/123/lp`

**응답 예시 · 200**
```json
{
  "record_id":123,
  "text":"오늘 좀 지쳤어",
  "confirmed_emotion":"가라앉음",
  "songs":[
    {"song_id":"deam_1146","brightness":0.2,"energy":0.3,"step":"맞추기"},
    {"song_id":"deam_1147","brightness":0.45,"energy":0.325,"step":"조금 밝게"},
    {"song_id":"deam_1355","brightness":0.6625,"energy":0.35,"step":"더 밝게"}
  ],
  "note":"개발용 임시 판: 좋아요·완청·감상 후 기분에 따른 실제 새기기 규칙은 미구현"
}
```

현재는 **임시 LP 데이터 조회**만 가능합니다. 음악 재생·완청·좋아요·실제 LP 새기기 규칙은 미구현입니다.

### 3.5. 글 감정 분석 + 기록 생성 — `POST /api/records/analyze` (추가 경로, 상현)

화면이 이 경로를 **한 번만** 부르면 `기록 생성 → 감정 분석 → 감정 결과 저장`이 서버 안에서 끝납니다. 기존 4개 API는 그대로입니다.

**요청 JSON** (`POST /api/records`와 같음)
```json
{"text":"오늘 좀 지쳤어"}
```

**응답 예시 · 201** (`POST /api/emotions` 요청과 같은 감정 결과 양식)
```json
{
  "record_id":124,
  "text":"오늘 좀 지쳤어",
  "probs":{"좋음":0.02,"무난함":0.03,"가라앉음":0.33,"예민함":0.62},
  "emotion":"예민함",
  "confidence":"높음"
}
```

- `emotion`은 **AI 예측**입니다. 화면은 `confidence`에 따라 확인 버튼을 보여 주고(높음: 1개 / 중간: 상위 2개 / 낮음: 4개), 사용자가 고른 감정을 `POST /api/recommendations`의 `confirmed_emotion`으로 보냅니다.
- 저장 위치는 `/api/emotions`와 같습니다(`records`의 `predicted_emotion`, `confidence`, `probs_json`).
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
- 패키지나 모델이 없어도 서버와 기존 4개 API, pytest는 정상 동작합니다. 이때 서버 터미널에 `감정 분석 꺼짐: ...` 경고가 한 줄 나옵니다.

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
`20 passed`가 기준입니다. `test_analyze.py`는 가짜 감정 함수를 쓰므로 모델이 없는 컴퓨터에서도 통과합니다.

**확인 결과 (2026-11-11)**
- 건호: 모델 없는 환경에서 서버 정상 실행과 `503` 확인, pytest `20 passed`, Ruff 통과, 실제 DEAM 점수표로 `기록 → 감정 저장 → 3곡 추천 → LP 조회` 성공
- 상현: 실제 감정 모델(GPU)로 6.1 흐름 성공(시험용 점수표 사용). 모델 불러오기 약 2초(서버 시작 때 한 번), 글 한 줄 분석 약 5ms

## 7. 팀 협의 사항

**정해진 것 (2026-11-11)**
- 감정 결과 전달 경로: 건호 서버가 상현의 `ai.emotion.service.analyze_text()`를 직접 호출 (`POST /api/records/analyze`). 감정 전용 서버는 따로 두지 않음
- 감정 분석 실패 시: 아무것도 저장하지 않고 `503`. 화면은 대체 흐름(1.2)
- 감정 확신도별 확인 화면: 높음 1개 / 중간 2개 / 낮음 4개 버튼. 기준값(0.6 / 0.4)은 모델 검증 결과에 따라 조정

**남은 것**
- 녹음 업로드 경로: 화면 → 서버 녹음 전송 → 받아쓰기 → 감정. 경로 담당과 녹음 원본 즉시 삭제 위치 (3주차 초)
- 에이전트 호출 위치(추천 경로 뒤 또는 별도 경로)와 최근 7일 기록 조회 기능 (4주차 초)
- 좋아요·건너뛰기·완청 및 감상 후 반응 API (건호 진행 예정)
- 실제 LP 새기기 규칙·주간 리캡
- 사용자 인증·개인정보 동의·녹음 동의 기록·배포 정책
- DEAM 원본 점수 1,802곡과 기존 기획 유효 1,744곡의 차이
- DEAM/PMEmo **음원**의 공개 재생/배포 권한 및 점수표 팀 공유 가능 범위

> 감정 추정은 의료 진단이 아닙니다. 사용자 기록에 없는 사건이나 감정을 만들어 저장하지 않습니다.
