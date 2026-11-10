"""DEAM/PMEmo 정규화 점수를 이용한 초기 3곡 추천 규칙.

이 모듈은 점수 CSV 읽기와 추천 계산만 담당합니다. API와 DB 저장은 main.py가 담당합니다.
"""

import csv
import math
import os
from dataclasses import dataclass
from pathlib import Path

from .schemas import Emotion, Song


class ScoreDataError(Exception):
    """추천에 필요한 점수 파일이 없거나 유효한 후보를 만들 수 없을 때 발생합니다."""


@dataclass(frozen=True)
class ScoredSong:
    song_id: str
    dataset: str
    valence: float
    arousal: float


# 구현 제안: 목표 좌표는 기존 가상 추천곡의 값을 출발점으로 사용합니다.
# 실제 추천 적합도는 사용자 평가 후 조정해야 하며, 검증된 최적값은 아닙니다.
TARGETS: dict[str, tuple[tuple[float, float, str], ...]] = {
    "좋음": (
        (0.80, 0.70, "비슷한 분위기 1"),
        (0.78, 0.72, "비슷한 분위기 2"),
        (0.82, 0.68, "비슷한 분위기 3"),
    ),
    "무난함": (
        (0.50, 0.40, "비슷한 분위기 1"),
        (0.55, 0.45, "비슷한 분위기 2"),
        (0.52, 0.42, "비슷한 분위기 3"),
    ),
    "가라앉음": (
        (0.20, 0.30, "맞추기"),
        (0.45, 0.32, "조금 밝게"),
        (0.70, 0.35, "더 밝게"),
    ),
    "예민함": (
        (0.25, 0.85, "맞추기"),
        (0.30, 0.50, "에너지 낮추기"),
        (0.55, 0.30, "차분하고 조금 밝게"),
    ),
}


def load_song_scores(csv_path: Path) -> list[ScoredSong]:
    """원본 CSV를 수정하지 않고 정규화 점수만 읽습니다.

    헤더·결측치·범위·중복을 검사해 잘못된 곡이 추천에 섞이는 것을 방지합니다.
    """
    if not csv_path.is_file():
        raise ScoreDataError("음악 점수 CSV 파일을 찾을 수 없습니다.")

    songs: list[ScoredSong] = []
    seen_ids: set[str] = set()
    required = {"song_id", "dataset", "valence", "arousal"}

    try:
        with csv_path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle, skipinitialspace=True)
            reader.fieldnames = [(name or "").strip() for name in (reader.fieldnames or [])]
            if not required.issubset(reader.fieldnames or []):
                raise ScoreDataError("CSV에 song_id, dataset, valence, arousal 열이 필요합니다.")

            for line_num, row in enumerate(reader, start=2):
                try:
                    song_id = (row["song_id"] or "").strip()
                    dataset = (row["dataset"] or "").strip()
                    valence = float(row["valence"])
                    arousal = float(row["arousal"])
                except (TypeError, ValueError, KeyError) as exc:
                    raise ScoreDataError(f"CSV {line_num}행에 잘못된 점수가 있습니다.") from exc

                if not song_id or dataset not in {"DEAM", "PMEmo"}:
                    raise ScoreDataError(f"CSV {line_num}행에 곡 ID 또는 데이터셋 오류가 있습니다.")
                if song_id in seen_ids:
                    raise ScoreDataError(f"CSV {line_num}행에 중복된 곡 ID가 있습니다.")
                if not (
                    math.isfinite(valence)
                    and math.isfinite(arousal)
                    and 0.0 <= valence <= 1.0
                    and 0.0 <= arousal <= 1.0
                ):
                    raise ScoreDataError(f"CSV {line_num}행 점수가 0~1 범위를 벗어났습니다.")
                seen_ids.add(song_id)
                songs.append(ScoredSong(song_id, dataset, valence, arousal))
    except OSError as exc:
        raise ScoreDataError("음악 점수 CSV를 읽지 못했습니다.") from exc

    if not songs:
        raise ScoreDataError("점수 CSV에 추천 가능한 곡이 없습니다.")
    return songs


def recommend_three(emotion: Emotion) -> list[Song]:
    """사용자가 확정한 감정에 맞춰 중복 없는 3곡을 추천합니다.

    환경변수로 점수 파일 위치와 사용 데이터셋 범위를 지정합니다.
    결과는 상현과 협의한 Song JSON 형식을 그대로 유지합니다.
    """
    file_name = os.environ.get("MOODWAVE_SCORES_CSV")
    if not file_name:
        raise ScoreDataError("MOODWAVE_SCORES_CSV 환경변수가 설정되지 않았습니다.")

    # 공개 시연은 DEAM만 허용하는 규칙을 기본값으로 둡니다.
    scope = os.environ.get("MOODWAVE_RECOMMEND_SCOPE", "DEAM").upper()
    if scope not in {"DEAM", "ALL"}:
        raise ScoreDataError("MOODWAVE_RECOMMEND_SCOPE는 DEAM 또는 ALL이어야 합니다.")

    catalog = load_song_scores(Path(file_name))
    candidates = [song for song in catalog if scope == "ALL" or song.dataset == "DEAM"]
    if len(candidates) < 3:
        raise ScoreDataError("선택한 데이터셋에 추천 가능한 곡이 3개 미만입니다.")

    selected: list[ScoredSong] = []
    results: list[Song] = []

    for target_v, target_a, step in TARGETS[emotion]:
        used = {song.song_id for song in selected}
        eligible = [song for song in candidates if song.song_id not in used]

        if selected and emotion == "가라앉음":
            # 슬픈 날에는 실제 곡 점수가 이전 곡보다 밝아지도록 보장합니다.
            eligible = [song for song in eligible if song.valence > selected[-1].valence]
        elif selected and emotion == "예민함":
            # 예민한 날에는 에너지를 단계적으로 낮춥니다.
            eligible = [song for song in eligible if song.arousal < selected[-1].arousal]
            if len(selected) == 2:
                # 마지막 곡은 한 단계 차분하면서 조금 더 밝게 마무리합니다.
                eligible = [song for song in eligible if song.valence > selected[-1].valence]

        if not eligible:
            raise ScoreDataError("감정별 3곡 흐름을 만족하는 후보가 부족합니다.")

        # 두 점수의 단위가 0~1이므로 유클리드 거리 제곱으로 간단히 비교합니다.
        # 동점일 때는 song_id 순으로 선택해 동일 입력의 결과를 재현할 수 있게 합니다.
        chosen = min(
            eligible,
            key=lambda song: (
                (song.valence - target_v) ** 2 + (song.arousal - target_a) ** 2,
                song.song_id,
            ),
        )
        selected.append(chosen)
        results.append(
            Song(
                song_id=chosen.song_id,
                brightness=chosen.valence,
                energy=chosen.arousal,
                step=step,
            )
        )
    return results
