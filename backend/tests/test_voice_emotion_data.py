"""AI Hub 감정 음성 라벨 읽기(다수결) 시험. 진짜 AI Hub 데이터는 쓰지 않습니다."""

import csv
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from ai.voice_emotion.data import load_rows, majority_label, soft_label

HEADER = ["wav_id", "발화문", "상황", "1번 감정", "1번 감정세기", "2번 감정", "2번 감정세기",
          "3번 감정", "3번 감정세기", "4번 감정", "4번감정세기", "5번 감정", "5번 감정세기", "나이", "성별"]


def test_majority_needs_three_of_five():
    assert majority_label(["Happiness", "happiness", " HAPPINESS", "sadness", "angry"]) == "좋음"
    assert majority_label(["happiness", "happiness", "sadness", "sadness", "angry"]) is None


def test_majority_maps_four_emotions():
    assert majority_label(["Neutral"] * 3 + ["angry", "fear"]) == "무난함"
    assert majority_label(["Sadness"] * 5) == "가라앉음"
    assert majority_label(["Angry"] * 4 + ["sadness"]) == "예민함"


def test_blank_and_unknown_labels_dropped():
    assert majority_label(["fear", "fear", "fear", "sadness", ""]) is None
    assert majority_label(["", "", "", "neutral", "neutral"]) is None


def _row(wav_id, votes, text="뭐야", age="20", sex="남"):
    return [wav_id, text, "anger", votes[0], "1", votes[1], "1", votes[2], "1", votes[3], "1", votes[4], "1", age, sex]


def test_load_rows_reads_cp949_and_skips_missing_wav(tmp_path):
    wav_dir = tmp_path / "wav"
    (wav_dir / "sub").mkdir(parents=True)
    (wav_dir / "sub" / "a.wav").write_bytes(b"")  # 하위 폴더에 있어도 찾아야 함
    (wav_dir / "b.wav").write_bytes(b"")
    csv_path = tmp_path / "set.csv"
    with open(csv_path, "w", encoding="cp949", newline="") as f:
        w = csv.writer(f)
        w.writerow(HEADER)
        w.writerow(_row("a", ["angry", "Angry", "angry", "sadness", "fear"]))      # 다수결 됨
        w.writerow(_row("b", ["angry", "angry", "sadness", "sadness", "fear"]))    # 다수결 없음
        w.writerow(_row("c", ["angry", "angry", "angry", "angry", "angry"]))       # wav 없음

    rows = load_rows(csv_path, wav_dir)

    assert rows == [{"wav_path": str(wav_dir / "sub" / "a.wav"), "text": "뭐야", "label": "예민함", "group": "20|남"}]


def test_soft_label_counts_only_four_emotions():
    # EMOTIONS 순서: 좋음, 무난함, 가라앉음, 예민함. fear 표는 버리고 4표로 나눔
    assert soft_label(["Sadness", "sadness", "sadness", "neutral", "fear"]) == [0.0, 0.25, 0.75, 0.0]
    assert soft_label(["fear", "disgust", "", "surprise", "fear"]) is None
