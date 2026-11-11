"""상현 감정 결과를 건호 서버로 보내는 연결 시험 코드"""
import json
import sys
import urllib.error
import urllib.request

from emotion_mapper import predict_emotion  # 같은 폴더의 내 감정 함수 (합 보정 포함)

SERVER = "http://127.0.0.1:8000"            # 건호 서버 로컬 주소

TEST_TEXTS = [
    "오늘 정말 기분 좋았어",
    "오늘 좀 지쳤어",
    "그냥 그래 ㅋㅋ",
]


def post_json(path, data):
    """서버에 JSON을 보내고 응답 JSON을 돌려받는다."""
    body = json.dumps(data, ensure_ascii=False).encode("utf-8")  # 한글이 깨지지 않게
    req = urllib.request.Request(
        SERVER + path,
        data=body,
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as res:
            return json.loads(res.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        # 서버가 양식이 틀렸다고 거절한 경우: 이유를 그대로 보여 준다
        print(f"[서버 거절] {path} 상태코드 {e.code}")
        print(e.read().decode("utf-8"))
        sys.exit(1)
    except urllib.error.URLError as e:
        print(f"[연결 실패] 서버가 켜져 있는지 확인하세요: {e.reason}")
        sys.exit(1)


def main():
    for text in TEST_TEXTS:
        # 1) 기록 만들기 → record_id 받기
        record = post_json("/api/records", {"text": text})
        record_id = record["record_id"]

        # 2) 감정 예측 (결과 양식 dict, 확률 합은 이미 1로 보정됨)
        result = predict_emotion(text, record_id)

        # 3) 서버로 보내기
        saved = post_json("/api/emotions", result)

        total = sum(result["probs"].values())
        ok = "성공" if saved.get("saved") is True else "실패"
        print(f"[{ok}] id={record_id} '{text}' → {result['emotion']}"
              f"({result['confidence']}), 확률합={total:.4f}")
        print("   서버 응답:", saved)


if __name__ == "__main__":
    main()