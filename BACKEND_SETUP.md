# MoodWave — FastAPI 협업 스타터 (2026-11-09)

**목적**: 감정 모델 없이도 `기록 → 상현 감정 JSON 수신 → 사용자 감정 확인 → 임시 3곡 추천 → LP 조회`가 한 번 연결되는 최소 데모.

> 서버·경로·SQLite는 **시작용 제안**입니다. 최종 DB, API 명세, 권한·안전 정책은 팀 합의가 필요합니다. 이 스타터에는 **실제 DEAM/PMEmo 음원/곡 데이터가 들어 있지 않습니다**.

## 1. 설치 (Windows PowerShell / Python 3.10+)

이 폴더가 GitHub 저장소 루트라면:

```powershell
cd backend
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

PowerShell에서 가상환경 활성화 제한 오류가 나면, 가상환경을 활성화하지 않고 아래처럼 바로 실행할 수 있습니다:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload
```

## 2. 실행 및 Swagger

```powershell
python -m uvicorn app.main:app --reload
```

- 주소: <http://127.0.0.1:8000/health>
- Swagger: <http://127.0.0.1:8000/docs>

## 3. API 체험 순서

**Swagger**에서 아래 순서로 `Try it out → Execute`를 누르세요.

1. `POST /api/records` — `{"text":"오늘 좀 지쳤어"}` → `record_id` 기억
2. `POST /api/emotions` — `API_CONTRACT.md` 감정 JSON의 `record_id`를 1번 결과로 변경
3. `POST /api/recommendations` — `{"record_id":1,"confirmed_emotion":"가라앉음"}` (여기 1은 실제 발급받은 ID로 변경)
4. `GET /api/records/{record_id}/lp` — 기록과 임시 추천 3곡 확인

## 4. 테스트

```powershell
python -m pytest -q
```

## 5. GitHub 협업 (원격 저장소가 이미 있는 경우)

```powershell
# 저장소 루트에서 진행
# 원격 저장소를 아직 내려받지 않았다면:
# git clone https://github.com/OWNER/REPO.git
# cd REPO

git switch main
git pull origin main
git switch -c feature/backend-api
# 이 스타터 파일을 저장소에 복사 및 작업 후
git status
git add backend API_CONTRACT.md .gitignore README.md
git commit -m "feat(backend): add FastAPI MVP and API contract"
git push -u origin feature/backend-api
```

이후 GitHub 웹에서 `feature/backend-api` → `main`으로 Pull Request를 열고 상현에게 리뷰를 요청합니다. 저장소에 이미 `README.md`나 `.gitignore`가 있으면 파일 전체를 덮어쓰지 말고 변경 내용만 합치세요.

> 팀이 `develop` 통합 브랜치를 쓰기로 정했다면, `main` 대신 그 브랜치를 기준으로 합의하고 작업하세요.

## 6. 파일 구조

```text
MoodWave/
├── .gitignore
├── README.md
├── API_CONTRACT.md
└── backend/
    ├── requirements.txt
    ├── app/
    │   ├── __init__.py
    │   ├── main.py          # 4개 업무 API + health
    │   ├── schemas.py       # 상현/건호 JSON 구조
    │   ├── db.py            # 시작용 SQLite 기록 DB
    │   └── recommender.py   # 가상 음악 3곡 응답
    └── tests/
        └── test_api.py
```

## 보안/저작권

- `.venv`, `.env`, 데이터베이스, 원본 데이터셋, 음원, 모델 파일을 GitHub에 넣지 않습니다.
- 원본 데이터는 예: `C:\work\moodwave_data` 처럼 원드라이브와 Git 저장소 바깥에 둡니다.
- 공개 데모에 DEAM을 쓰는 방향이라도 **라이선스 및 공개 재생/전송 허가를 별도로 확인**하세요. 허가 전에는 현재처럼 가상 곡·모의 재생만 사용합니다.
- 프로젝트는 테스트 전용이며 인증, 운영용 데이터베이스, 사용자 데이터 삭제 정책, 실제 재생 기능은 구현되지 않았습니다.
