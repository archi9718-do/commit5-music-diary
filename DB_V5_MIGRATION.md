# DB v5 전환 안내 (`feature/db-v5`)

> 기준: 테이블 명세서 v5 (2026-11-13), 브랜치 `feature/db-v5` (출발점 `main` c148f38)
>
> 기존 `records`, `recommendations` 표를 v5 표(`tb_record`, `tb_record_song` 등)로 바꿨습니다.
> 기존 API 5개의 **요청·응답 양식은 그대로**이고, 추천곡 반응 API 2개를 새로 추가했습니다.

## 1. 바뀐 파일

| 파일 | 내용 |
|---|---|
| `backend/app/schema.sql` | **신규.** v5 표 7개 생성 SQL. 서버가 켜질 때 실행 |
| `backend/app/db.py` | `schema.sql` 실행, 시연용 회원 1명 준비, 하루 1건 덮어쓰기(`save_today_record`), 곡 등록(`ensure_song`) |
| `backend/app/main.py` | 기존 API 5개를 새 표로 연결, 반응 API 2개 추가, CORS에 `PATCH` 허용 |
| `backend/app/schemas.py` | `SongFeedbackUpdate`, `SongFeedback` 추가 |
| `backend/tests/test_analyze.py` | 기록 개수 세는 표 이름만 `tb_record`로 변경 |
| `backend/tests/test_feedback.py` | **신규.** 반응·LP 새김·같은 날 덮어쓰기 시험 4개 |

## 2. 표 이름·컬럼 대응표

### `records` → `tb_record`

| 기존 (`records`) | v5 (`tb_record`) | 비고 |
|---|---|---|
| `id` | `record_id` | |
| `text` | `record_text` | |
| `predicted_emotion` | `emotion_pred` | |
| `confirmed_emotion` | `emotion_final` | |
| `confidence` | `confidence_level` | |
| `probs_json` | `emotion_probs` | JSON 글자, `json_valid` 검사 |
| `created_at` | `created_at` | UTC |
| (없음) | `user_id` | 로그인 전까지 시연용 회원 `demo@moodwave.local` |
| (없음) | `record_date` | 한국 날짜 `YYYY-MM-DD`, 회원당 하루 1건 |
| (없음) | `flow_ended_at`, `mood_after`, `mood_asked_at`, `photo_path`, `additional_note`, `updated_at` | 감상 후 질문·사진용, 아직 API 없음 |

### `recommendations` → `tb_record_song`

| 기존 (`recommendations`) | v5 (`tb_record_song`) | 비고 |
|---|---|---|
| `record_id` | `record_id` | FK → `tb_record`, 기록 삭제 시 함께 삭제 |
| `position` | `recommend_order` | 1~3. **`(record_id, recommend_order)`로 곡 1개를 찾음** |
| `song_id` | `song_id` | FK → `tb_song` (추천 시 자동 등록) |
| `brightness` | `valence_at_rec` | API 응답 키는 `brightness` 그대로 |
| `energy` | `arousal_at_rec` | API 응답 키는 `energy` 그대로 |
| `step` | `step` | |
| (없음) | `is_liked`, `is_skipped`, `is_completed`, `is_engraved` | 0/1, 반응 API로 저장 |
| (없음) | `record_song_id`, `created_at` | |

### `song_feedback`(로컬 작업) → `tb_record_song`

별도 표 없이 `tb_record_song`의 같은 행에 반응을 저장합니다. 곡 1개 = `(record_id, recommend_order)` 한 행입니다.

| 반응 | 컬럼 | 규칙 |
|---|---|---|
| 좋아요 | `is_liked` | 취소하면 `is_engraved`도 0 |
| 건너뛰기 | `is_skipped` | `is_completed`와 동시에 1 불가 |
| 끝까지 들음 | `is_completed` | 재생 실패·건너뛰기는 0 |
| LP 새김 | `is_engraved` | 좋아요 곡만 1 가능 (DB CHECK) |

## 3. 새 API

### 3.1. 추천곡 반응 저장 — `PATCH /api/records/{record_id}/songs/{recommend_order}`

보낸 항목만 바꿉니다. 보내지 않은 항목은 그대로입니다.

```json
// 요청 예: 1번 곡에 좋아요
{"is_liked": true}

// 응답 200
{"record_id": 1, "recommend_order": 1, "song_id": "deam_2",
 "is_liked": true, "is_skipped": false, "is_completed": false, "is_engraved": false}
```

| 상태 | 언제 |
|---|---|
| `404` | 해당 기록·순서의 추천곡이 없음 |
| `409` | 건너뛰기와 완청이 동시에 1이 되는 요청 |
| `422` | 순서가 1~3이 아님, 세 항목 중 아무것도 안 보냄 |

### 3.2. 그날의 판에 새기기 — `POST /api/records/{record_id}/engrave`

좋아요 누른 곡만 `is_engraved = 1`, 나머지는 0으로 맞춥니다. 여러 번 불러도 결과가 같습니다. 응답은 3.1 형식의 배열입니다.

## 4. 기존 API에서 달라진 동작

| API | 달라진 점 |
|---|---|
| `POST /api/records`, `POST /api/records/analyze` | **같은 날 다시 부르면 새 ID 대신 오늘 기록을 덮어쓰고 같은 `record_id`를 돌려줍니다** (팀 결정 2). 이때 확정 감정·추천곡·반응은 지워지고, `mood_after`·`mood_asked_at`은 남습니다. 서로 다른 감정을 시험하려면 `/api/recommendations`를 같은 ID로 다시 부르면 됩니다(추천곡 교체). |
| `POST /api/recommendations` | 같은 ID로 다시 부르면 추천곡 3개와 반응이 새로 시작되고 `flow_ended_at`이 비워집니다. |
| `GET /api/records/{record_id}/lp` | 기존 키는 그대로이고, 곡마다 `recommend_order`, `title`, `artist`, `is_liked`, `is_skipped`, `is_completed`, `is_engraved`가 추가됐습니다. `title`, `artist`는 메타데이터를 넣기 전까지 `null`입니다. |

## 5. 로컬에서 확인하는 법

1. 기존 `backend/moodwave.db`가 있으면 **지우고** 서버를 켜세요. 이전 표(`records` 등)가 남아 있어도 서버는 동작하지만 새 표와 섞여 헷갈립니다.
2. `python -m pytest -q` → 24개 통과 (기존 20 + 신규 4)
3. `python -m ruff check --select BLE,PLR0402,I .` → 통과
4. Swagger(`/docs`)의 "추천곡 반응" 묶음에서 PATCH·engrave를 직접 눌러 볼 수 있습니다.

## 6. 남은 일

- 3곡 흐름 종료(`flow_ended_at`), 감상 후 질문(`mood_asked_at`, `mood_after`) API
- 곡 메타데이터(제목·아티스트)를 `tb_song`에 넣는 스크립트
- 감정별 판 기본곡(`tb_lp_base_song`) 데이터와 판 조회 API
- 로그인 구현 후 시연용 회원 대신 로그인 회원의 `user_id` 사용
- `API_CONTRACT.md`에 3장 내용 반영 (`feature/emotion-model`의 문서 수정이 `main`에 합쳐진 뒤)
