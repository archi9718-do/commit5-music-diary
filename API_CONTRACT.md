# MoodWave API 협의 초안 — 건호 ↔ 상현 ↔ 프론트엔드

> **확정 아님**: 진행 매뉴얼은 'API 4개'만 지정하며 정확한 경로는 미확정입니다. 아래 주소는 건호의 구현 제안입니다. `main`에 합치기 전에 팀에서 합의하세요.

## 로컬 개발 주소

- Backend `http://127.0.0.1:8000`
- Swagger `http://127.0.0.1:8000/docs`
- React(Vite) `http://localhost:5173` (개발용 CORS 허용)

## 업무 경계

- **상현**: 감정 모델 추론 / 감정 JSON 생성 / 에이전트
- **건호**: 기록 ID 발급 / 감정 JSON 수신·저장 / 사용자 확정 감정에 따른 추천 / 추천 결과 저장
- **프론트엔드**: 사용자 기록·감정 확인 버튼 / API 연동 / 오늘의 판 표시

## 요청 순서와 JSON

1. 프론트엔드 → `POST /api/records` (새 기록 생성)

```json
{ "text": "오늘 좀 지쳤어" }
```

응답 (201):

```json
{ "record_id": 1, "text": "오늘 좀 지쳤어" }
```

2. 상현 감정 결과 → `POST /api/emotions` (해당 record_id 사용)

```json
{
  "record_id": 1,
  "text": "오늘 좀 지쳤어",
  "probs": {"좋음": 0.10, "무난함": 0.15, "가라앉음": 0.62, "예민함": 0.13},
  "emotion": "가라앉음",
  "confidence": "중간"
}
```

응답 (200):

```json
{ "record_id": 1, "predicted_emotion": "가라앉음", "saved": true }
```

3. 사용자가 감정을 확인한 후 프론트엔드 → `POST /api/recommendations`

```json
{ "record_id": 1, "confirmed_emotion": "가라앉음" }
```

응답 (200): **상현이 요청한 추천 결과 최상위 구조(`songs`)를 유지**

```json
{
  "songs": [
    {"song_id":"mock_sad_01","brightness":0.20,"energy":0.30,"step":"맞추기"},
    {"song_id":"mock_sad_02","brightness":0.45,"energy":0.32,"step":"조금 밝게"},
    {"song_id":"mock_sad_03","brightness":0.70,"energy":0.35,"step":"더 밝게"}
  ]
}
```

**중요**: 위 `mock_*` 곡과 값은 API 테스트를 위한 가상 값이며 DEAM/PMEmo의 실제 곡 ID나 레이블이 아닙니다.

4. 프론트엔드 → `GET /api/records/1/lp` (오늘의 임시 판 조회)

응답: `record_id`, `text`, `confirmed_emotion`, `songs` 배열과 설명 문구 `note`.

5. 상태 점검용 추가 주소: `GET /health` (`{"status":"ok","service":"moodwave-backend"}`)

## 오늘의 완료 기준

- `POST /api/records`가 새로운 `record_id`를 반환
- 상현 JSON을 `POST /api/emotions`가 200 응답으로 수신
- `POST /api/recommendations`가 정확히 **3곡** 반환
- 서버 재시작 후 `GET /api/records/{record_id}/lp`에서 테스트 결과 조회 가능
- GitHub PR에 `.db`, `.env`, 데이터셋, 음원, 모델 파일 없음

## 이후 개발 시 다시 합의할 점

- 좋아요/건너뛰기, 완청, 감상 후 반응 수집 엔드포인트
- 좋음/무난함과 가라앉음/예민함의 서로 다른 '판에 새기기' 규칙
- 인증/계정, 실제 DB 선택(MySQL 후보), 음원 재생 권한, 배포 방식
- `record_id`가 기록 생성 이후 상현에게 전달되는 구체적 흐름
