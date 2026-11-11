# MoodWave API 연동 명세서 — 건호 ↔ 상현 ↔ 프론트엔드

- **작성 기준:** 2026-11-11
- **근거:** `archi9718-do/commit5-music-diary` 저장소 `main` 브랜치의 `backend/app/main.py`, `backend/app/schemas.py`, `backend/app/recommender.py`, `backend/app/db.py` 확인
- **상태:** 현재 구현된 *MVP 개발용 API*. 팀의 최종 연동 설계·배포 주소는 **확인 필요**
- **주의:** 기존 `API_CONTRACT.md`의 `mock_*` 예시는 오래된 정보입니다. 현재 추천 서버는 별도 CSV에 저장된 DEAM·PMEmo **점수**를 이용합니다.

## 1. 전체 흐름과 역할

1. 프론트엔드가 사용자 기록을 생성해 **`record_id`**를 받습니다.
2. 상현의 감정 분석 모델이 `record_id`와 감정별 확률을 포함한 JSON을 생성하여 건호의 **`POST /api/emotions`**로 전달합니다.
3. 프론트엔드에서 **사용자가 최종 감정을 확인**합니다. 예측값을 자동 확정하지 않습니다.
4. 프론트엔드가 **`POST /api/recommendations`**를 호출하면 건호의 서버가 점수 기반 3곡을 추천하고 DB에 저장합니다.
5. 프론트엔드가 **`GET /api/records/{record_id}/lp`**로 감정 기록 및 추천 결과를 조회합니다.

**업무 구분**
- 상현: 감정 모델 추론, `probs`, `emotion`, `confidence` 산출, 추천 이유 생성·에이전트 흐름(후속 통합)
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

## 3. 구현된 API 4개

| 순서 | Method | 경로 | 정상 상태 코드 | 역할 |
|---|---|---|---|---|
| 1 | `POST` | `/api/records` | `201` | 기록 생성, ID 발급 |
| 2 | `POST` | `/api/emotions` | `200` | 감정 분석 결과 저장 |
| 3 | `POST` | `/api/recommendations` | `200` | 최종 감정 기반 3곡 추천·저장 |
| 4 | `GET` | `/api/records/{record_id}/lp` | `200` | 임시 LP 기록·추천곡 조회 |

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

## 5. 상현 컴퓨터에서 로컬 서버 실행

저장소 최신 버전을 받은 뒤 **Windows PowerShell**에서 실행:

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
- `MOODWAVE_RECOMMEND_SCOPE=DEAM`: 기본 시연·추천 후보 범위. `ALL`: DEAM + PMEmo 내부 테스트 후보 범위.
- `song_scores.csv` 및 원본 음원은 **GitHub 저장소에 포함되어 있지 않습니다**. 점수표를 팀에 전달할 수 있는 라이선스/배포 조건을 확인하거나 각자 자료를 추출해야 합니다.
- 인증·외부 배포 및 파일/원본 녹음 삭제 정책은 아직 개발용입니다.

### AI 감정 인식 모델을 함께 실행하는 경우

기존 FastAPI 서버만 사용할 때는 AI 패키지가 없어도 됩니다.

실제 텍스트 감정 분석 기능을 사용하려면 Python 3.11 이상 환경에서
PyTorch(torch), Transformers 및 감정 모델 파일을 준비해야 합니다.

**1. AI 패키지 설치**

backend 폴더에서 실행:

```powershell
python -m pip install -r ..\ai\requirements.txt
```

GPU용 PyTorch는 사용 중인 GPU 및 CUDA 환경에 맞게 설치해야 합니다.

**2. 감정 모델 폴더 지정**

```powershell
$env:MOODWAVE_MODEL_DIR="C:\work\moodwave_data\models\klue-bert-base-sentiment"
```

모델 파일 경로는 실제 저장 위치에 맞게 변경합니다.

**3. FastAPI 실행**

```powershell
python -m uvicorn app.main:app --reload
```

**4. 실행 결과**

- 모델 정상 로딩: `POST /api/records/analyze` 사용 가능
- 모델 또는 AI 패키지 없음: 분석 API만 HTTP 503 반환
- 기존 기록·음악 추천·LP 조회 API는 계속 사용 가능

## 6. 통합 테스트 순서와 완료 기준

1. `POST /api/records` → 새 `record_id` 수신
2. `POST /api/emotions` → 동일한 ID로 상현 JSON 저장, `saved: true` 확인
3. 사용자 감정 확인 후 `POST /api/recommendations` → 서로 다른 실제 곡 3개 수신
4. `GET /api/records/{record_id}/lp` → 동일 ID·확정 감정·3곡 조회
5. 서버 재시작 후 4번을 반복해 기존 데이터 유지 여부 확인

**건호가 로컬에서 확인한 결과 (2026-11-10):** 감정 4종 추천 JSON, 실제 DEAM 점수 기반 추천, 전체 API 통합 흐름, 서버 재시작 후 조회, pytest `11 passed` (Starlette 관련 경고 1건). 상현의 **실제 감정 모델이 이 API에 자동 호출하는 통합**은 아직 검증하지 않았습니다.

## 7. 팀 협의가 남은 사항

- 상현의 감정 모델 결과가 건호 백엔드로 전달되는 실제 네트워크 경로 및 호출 주체
- 감정 확신도별 사용자 확인 화면 및 확정 시점
- 좋아요·건너뛰기·완청 및 감상 후 반응 API
- 실제 LP 새기기 규칙·주간 리캡
- 사용자 인증·개인정보 동의·음성 원본 삭제·배포 정책
- DEAM 원본 점수 1,802곡과 기존 기획 유효 1,744곡의 차이
- DEAM/PMEmo **음원**의 공개 재생/배포 권한 및 점수표 팀 공유 가능 범위

> 감정 추정은 의료 진단이 아닙니다. 사용자 기록에 없는 사건이나 감정을 만들어 저장하지 않습니다.
