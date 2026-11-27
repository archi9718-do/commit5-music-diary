# 로그인 설계 (11/30까지)

작성 11/27 상현. 11/27 건호 검토 의견 반영. 상태: 서버(건호)·화면(yenaduck0920-bit) 구현 전 합의안.

## 1. 왜

MoodWave는 "그 사람에게 맞춘 플레이리스트"가 방향이다. 지금은 시연 기기에서 참여자 코드(`X-Participant`, 4자리)로 사람을 나눈다. 이 방식은 그날 한 번 쓰고 끝나서, 다음에 다시 와도 이어지지 않는다. 그래서 계정으로 로그인하고, 기록·취향 유형이 계정에 남아 다음에 써도 이어지게 한다.

12/7 평가(약 25명)도 로그인으로 한다. 게스트(로그인 없이 쓰기)는 없다. 참여자는 화면에서 직접 가입한다.

## 2. 목표 / 목표 아님

**목표 (11/30까지)**
- 화면에서 아이디·비밀번호로 가입, 로그인, 로그아웃
- 로그인한 사람의 기록·추천곡·반응·취향 유형이 서버에 계정별로 남는다
- 로그아웃 뒤 다시 로그인하면, 다른 기기에서도 내역·나의 LP·취향 유형이 그대로 보인다
- 다른 사람의 기록은 볼 수도 고칠 수도 없다

**목표 아님**
- 소셜 로그인(카카오·Google), 비밀번호 찾기, 이메일 인증, 회원 탈퇴 화면
- 짧은/긴 토큰 두 장 방식(refresh token). 계정당 토큰 한 장으로 한다
- 게스트 사용, 참여자 코드를 로그인과 함께 유지하기

**실패로 볼 것 (돌아가도 안 되는 것)**
- 로그아웃하면 서버 데이터가 지워진다
- 공용 평가 PC에서 앞사람 기록·취향·임시 LP가 다음 사람에게 보인다
- 비밀번호가 평문이나 되돌릴 수 있는 형태로 DB에 남는다
- 기존 계정·기록이 사라지거나 새 계정에 섞인다

## 3. 지금 구조 (바뀌는 곳)

- 서버는 이미 사용자별로 저장한다. `db.get_user_id(con, participant)`가 헤더로 회원을 찾거나 만들고, 기록 id 경로는 `owner.owned_record`가 주인을 확인한다 (남의 기록이면 404).
- `tb_user`: `email TEXT NOT NULL UNIQUE -- 로그인 ID`, `password_hash TEXT NOT NULL`. 지금은 시연 회원(`demo@moodwave.local`)과 `participant-XXXX@moodwave.local` 회원만 있고 비밀번호 값은 `login-not-implemented`이다.
- 화면은 `api.js`의 `request()` 한 곳에서 `participantHeader()`로 헤더를 붙인다.
- 기록은 감정 분석 단계(`/api/records/analyze`, `/api/records/voice`)에서 `tb_record` 행이 먼저 생긴다. 중간에 나가도 행이 남는다. `flow_ended_at`은 "감상 마치기" 시각이라 저장 완료 표시로 못 쓴다.
- 화면의 "기록만 저장하기"와 "LP판에 새기기"는 둘 다 `persist()` → `POST /api/records/{id}/engrave`를 부른다 ("기록만 저장하기"는 빈 목록).
- **빈 곳**: 내역, 월간 분석, 나의 LP, 취향 유형은 서버가 아니라 브라우저 localStorage(`moodwave.mvp.records.v1`, `moodwave.mvp.taste.v1`)에서 읽는다. 서버에 "내 기록 목록" API가 없다. 로그인만 넣으면 다른 기기나 다시 로그인했을 때 화면이 빈다.

## 4. 방법 비교

| 방법 | 장점 | 단점 |
|---|---|---|
| **A. 서버 토큰 + DB 저장 (선택)** | 표준 라이브러리만 씀, 로그아웃하면 바로 무효, 지금 헤더 구조와 같아 바뀌는 곳이 적음 | 화면에 XSS가 생기면 토큰이 새어 나감 (지금은 React 기본 출력만 써서 낮음, 토큰은 메모리에만 둠) |
| B. JWT | 서버가 토큰을 저장하지 않음 | `PyJWT` 의존성 추가, 로그아웃해도 만료 전까지 유효, 서버 하나라 얻는 게 없음 |
| C. HttpOnly 쿠키 세션 | 스크립트가 토큰을 못 읽어 가장 안전 | 화면·서버 주소가 달라 CORS credentials·SameSite·ngrok을 맞춰야 함. 3일 안에 위험 |

A로 한다 (11/27 상현 결정, 건호 동의). 상용 음악 앱(Spotify 등)도 "서버에 계정별 저장 + 기기에는 사본만 + 로그아웃하면 기기 사본만 지움" 구조이고, A는 그것을 토큰 한 장으로 줄인 형태다.

## 5. 설계

### 5.1 서버 (건호)

**계정 저장 (DB 마이그레이션 없음)**
- 새 로그인 아이디는 `tb_user.email` 칸에 그대로 넣는다. 이 칸은 이미 `NOT NULL UNIQUE`이고 주석도 "로그인 ID"다. 스키마 주석에 "이메일 또는 로그인 아이디"라고 적는다.
- 기존 값은 모두 `@`가 들어간 이메일이고, 새 아이디는 `@`를 허용하지 않으므로 겹치지 않는다. 기존 계정·기록은 그대로 두고, 새 계정은 새 `user_id`로 시작한다.
- 이유: SQLite는 `ALTER`로 `NOT NULL`을 풀 수 없어 표를 새로 만들어 옮겨야 하고, `tb_record` 등이 `tb_user`를 참조해 옮길 때 위험하다. (건호 제안은 새 칸 + 마이그레이션이었고, 상현 제안으로 바꿈. 칸 이름이 어색한 것이 단점)
- 새 표 `tb_session(token_hash TEXT PRIMARY KEY, user_id INTEGER NOT NULL UNIQUE, expires_at TEXT NOT NULL, created_at TEXT)`. `user_id UNIQUE`로 계정당 한 장.
- 취향 유형: `tb_user`에 `taste_answers TEXT`(JSON), `taste_taken_at TEXT`를 `ALTER TABLE ... ADD COLUMN`으로 더한다 (`taste_side`와 같은 방식).
- 저장 완료: `tb_record`에 `saved_at TEXT`를 더한다. `POST /api/records/{id}/engrave`가 처음 불릴 때 채운다 (빈 목록이어도). 같은 날 다시 기록하면 `emotion_final`·`taste_side`처럼 `saved_at`도 비운다.

**비밀번호·토큰**
- 비밀번호: `hashlib.scrypt(..., maxmem=256 * 1024 * 1024)` + 사용자마다 `secrets.token_bytes(16)` 소금. 이 PC에서 기본 `maxmem`으로는 실패하고, 256 MiB면 약 0.32초 (11/27 건호 확인). 저장 형식 예: `scrypt$n$r$p$salt_hex$hash_hex`. 비교는 `hmac.compare_digest`.
- 토큰: `secrets.token_urlsafe(32)`. DB에는 `sha256(token)`만 저장한다. 만료 30일.
- **계정당 토큰 한 장**: 로그인(가입 포함)하면 그 계정의 이전 `tb_session` 행을 지우고 새로 만든다. 이전 기기의 토큰은 곧바로 401이 된다.
- 로그아웃: 그 요청의 토큰 행만 지운다. 데이터는 지우지 않는다.
- 아이디: 영문 소문자·숫자 4~20자 (`eval01` 같은 평가용 아이디 포함). 비밀번호: 8~64자. 형식이 틀리면 422.
- 로그인 실패 메시지는 "아이디나 비밀번호가 맞지 않아요" 하나로 (아이디가 있는지 알려 주지 않음).
- 같은 아이디로 5번 연속 실패하면 5분 동안 로그인을 막는다 (서버 ngrok 공개 대비). 서버 메모리에 둬도 된다 (서버 하나, 재시작하면 풀림).

**API**
| 경로 | 설명 |
|---|---|
| `POST /api/auth/signup` `{login_id, password}` | 가입하고 바로 로그인. `{token, login_id}`. 아이디 중복이면 409 |
| `POST /api/auth/login` `{login_id, password}` | `{token, login_id}`. 이전 토큰 무효. 틀리면 401, 잠금이면 429 |
| `POST /api/auth/logout` | 그 토큰의 행만 삭제. 데이터는 지우지 않음 |
| `GET /api/me` | `{login_id}`. 토큰 확인용 |
| `GET /api/me/records` | `saved_at`이 있는 내 기록만 (최근순). 기록마다 `record_id, record_date, record_text, emotion_final, taste_side, mood_after, saved_at`와 추천곡 3개(`/lp` 응답의 곡 정보 + 좋아요·새김 상태) |
| `GET /api/me/taste` / `PUT /api/me/taste` `{answers}` | 취향 유형. 서버는 `answers`로 쪽을 다시 계산해 저장한다 (화면 값을 믿지 않음, `schemas.py` `SIDES`와 같은 규칙). 검사 전이면 `null` |

세부 요청·응답 형식은 11/28에 건호·화면 담당이 맞추고 `API_CONTRACT.md`에 적는다.

**인증 연결**
- `owner.py`의 `Participant` 헤더 대신 `Authorization: Bearer <token>`에서 회원을 찾는 의존성(예: `current_user`)을 만든다. 토큰이 없거나, 틀리거나, 만료되거나, 다른 기기 로그인으로 무효가 되면 401.
- `get_user_id(con, participant)`를 쓰는 곳과 `owned_record`가 이 회원 id를 쓰게 바꾼다. 기록·추천·7일 제외 로직은 그대로.
- 로그인이 필요 없는 경로: `/health`, `/api/auth/signup`, `/api/auth/login`, 음원 파일(`/api/audio*`).
- CORS `allow_headers`에 `Authorization`을 더하고 `X-Participant`는 뺀다.
- `X-Participant`, `PARTICIPANT_PATTERN`, `participant-XXXX` 회원 생성은 지운다. DB에 이미 있는 회원 행은 그대로 둔다.

### 5.2 화면 (yenaduck0920-bit)

- 로그인 안 했으면 첫 화면에서 로그인/가입 화면을 보여 준다. 시연 메뉴 시나리오(`draft.demo`)는 서버를 안 부르므로 그대로 둔다.
- **토큰은 메모리(React 상태)에만 둔다** (건호 제안, 공용 평가 PC 대비). 새로고침하면 다시 로그인해야 한다. `request()`가 `participantHeader()` 대신 `Authorization` 헤더를 붙인다. 401을 받으면 메모리 토큰을 버리고 로그인 화면으로.
- **사본의 주인 표시**: localStorage `moodwave.mvp.owner.v1`에 사본 주인의 `login_id`를 둔다. 로그인했을 때
  - 주인이 다르거나 없으면: `moodwave.mvp.*`를 모두 지우고(지금 `startNextParticipant`의 지우는 코드 재사용) 주인을 새로 적은 뒤 서버에서 받는다.
  - 같은 사람이면: 사본을 남긴다. 새로고침 뒤 임시 LP 복구(`moodwave.mvp.pending-lp.v1`)가 그대로 된다.
  - 이유: 토큰이 메모리에만 있어서, A가 새로고침하고 자리를 뜨면 로그인 화면은 나와도 A의 사본이 localStorage에 남는다.
- 로그인 직후 `GET /api/me/records`, `GET /api/me/taste`로 내역·LP·유형을 채운다. localStorage는 사본으로만 쓴다.
- 검사 결과를 저장할 때 `PUT /api/me/taste`도 부른다. 검사를 건너뛰면 기본 추천으로 간다 (지금과 같음).
- 로그아웃: `POST /api/auth/logout` 뒤 메모리 토큰을 버리고 `moodwave.mvp.*`를 모두 지운다 (기록·취향·임시 LP 포함). 서버 데이터는 남는다.
- 마이의 "평가 참여자 / 다음 참여자로 시작"은 "로그인: 아이디 / 로그아웃"으로 바꾼다.

### 5.3 평가 설문 연결

- 참여자 코드 대신 평가용 로그인 아이디를 쓴다. 진행자가 참여자마다 `eval01`~`eval25`를 정해 주고, 참여자는 화면에서 그 아이디와 자기 비밀번호로 직접 가입한다.
- 설문에 그 아이디를 적는다. 분석할 때 `tb_user.email = 'eval01'`로 기록을 찾는다.
- 설계 문서 `2026-11-23-music-taste-type-design.md` 11·12절의 "참여자 코드"는 이 아이디로 읽는다.

### 5.4 #40(취향 유형)과의 관계

#40은 11/27 머지됐다 (`eb92c49`). 로그인 브랜치는 최신 `main`에서 시작한다. #40의 `taste_side` 저장·추천표는 그대로 쓰고, 유형 저장 위치만 서버로 옮긴다. #40 화면 손 확인 중 1·3·4번(건너뛰기, Day Type 다시 검사, 시연·위험 표현에서 권유 안 나옴)은 아직 안 했다. 로그인 손 확인 때 main 기준으로 함께 본다.

## 6. 일정

- 11/27: 이 문서 합의
- 11/28: 건호·화면 담당이 API 요청·응답 형식부터 맞추고 병행. 서버 (계정·세션·`saved_at`·auth API·`current_user` 연결·`/api/me/*`, 시험)
- 11/29: 화면 (로그인·가입·로그아웃, 서버에서 내역 불러오기, 주인 표시)
- 11/30: 실제 평가 PC에서 함께 손 확인 (7절), `API_CONTRACT.md`·README 갱신

## 7. 시험

**서버 시험 (건호)**
- 가입 → 로그인 → 기록 → 추천 → 저장 → 로그아웃 → 다시 로그인 → `/api/me/records`·`/api/me/taste`가 그대로
- 두 계정: 서로의 `record_id`로 `/lp`, 반응, 새김을 부르면 404
- 토큰 없음·틀림·만료·로그아웃한 토큰 → 401
- 같은 계정으로 두 번 로그인 → 첫 토큰 401
- 감정 분석만 하고 저장 안 한 기록은 `/api/me/records`에 안 나옴. "기록만 저장"(빈 목록 `engrave`)한 기록은 나옴
- 아이디 중복 → 409. 형식 틀림(대문자, `@` 포함, 3자) → 422. 5번 실패 → 429, 5분 뒤 풀림
- DB `password_hash`가 `scrypt$`로 시작하고 비밀번호 원문이 없음
- 기존 시험(참여자 코드 시험 제외) 모두 통과

**11/30 평가 PC 손 확인 (함께)**
- A 가입 → 기록·취향 저장 → 로그아웃 → B 로그인 → A 기록 접근 차단 → A 재로그인 → 기록·취향 복원
- 다른 기기에서 A 로그인 → 평가 PC의 A 토큰 무효 (다음 요청에서 로그인 화면)
- 브라우저 네트워크 탭에서 요청에 `Authorization` 헤더 확인
- 새로고침 → 로그인 화면. 같은 사람이 다시 로그인하면 임시 LP 복구. 다른 사람이 로그인하면 앞사람 사본 없음
- 로그아웃 뒤 localStorage에 `moodwave.mvp.*`가 없음
- #40 남은 손 확인 1·3·4번
