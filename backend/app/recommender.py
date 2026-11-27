"""DEAM/PMEmo 정규화 점수를 이용한 초기 3곡 추천 규칙.

이 모듈은 점수 CSV 읽기와 추천 계산만 담당합니다. API와 DB 저장은 main.py가 담당합니다.
"""

import csv
import math
import os
from collections.abc import Set
from dataclasses import dataclass
from pathlib import Path

from .schemas import SIDES, Emotion, Song, TasteSide


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

# 취향 유형의 쪽별 목표. 기본 쪽은 위 감정별 표 그대로, 다른 쪽 4개는 설계 문서 8절 값입니다.
SIDE_TARGETS: dict[str, tuple[tuple[float, float, str], ...]] = {
    **{default: TARGETS[emotion] for emotion, (default, _) in SIDES.items()},
    "머무름": ((0.20, 0.30, "맞추기"), (0.22, 0.25, "곁에 머물기"), (0.28, 0.22, "잔잔하게 마무리")),
    # DEAM에 밝기 < 0.45·에너지 ≥ 0.8인 곡이 1곡뿐이라 목표를 데이터 안(에너지 상위 약 4%)으로 낮춤 (11/27)
    "발산": ((0.30, 0.70, "맞추기"), (0.28, 0.74, "쏟아내기"), (0.30, 0.78, "끝까지 쏟아내기")),
    "증폭": ((0.80, 0.70, "맞추기"), (0.83, 0.80, "더 신나게"), (0.85, 0.88, "끌어올리기")),
    "전환": ((0.50, 0.40, "맞추기"), (0.65, 0.55, "조금 밝게"), (0.78, 0.65, "활기차게")),
}
# 밝기·에너지가 정해진 방향으로만 이어져야 하는 쪽 (_can_follow)
ORDERED_SIDES = {"위로", "진정", "발산"}


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


def load_recommendation_candidates() -> list[ScoredSong]:
    """설정된 점수표를 읽고 추천에 사용할 데이터셋만 남깁니다."""
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
    return candidates


def recommend_three(
    emotion: Emotion,
    recent_song_ids: Set[str] = frozenset(),
    *,
    side: TasteSide | None = None,
    candidates: list[ScoredSong] | None = None,
) -> list[Song]:
    """감정·쪽별 순서를 지키면서 이전 추천곡이 가장 적은 3곡을 고릅니다. side가 없으면 기본 쪽."""
    if side is None:
        side = SIDES[emotion][0]
    elif side not in SIDES[emotion]:
        raise ValueError(f"{emotion}의 쪽이 아닙니다: {side}")
    if candidates is None:
        candidates = load_recommendation_candidates()

    def rank(song: ScoredSong, stage: int) -> tuple[bool, float, str]:
        target_v, target_a, _ = SIDE_TARGETS[side][stage]
        return (
            song.song_id in recent_song_ids,
            (song.valence - target_v) ** 2 + (song.arousal - target_a) ** 2,
            song.song_id,
        )

    selected: list[ScoredSong] = []
    for stage in range(3):
        eligible = (
            song for song in candidates
            if song not in selected
            and (not selected or _can_follow(side, selected[-1], song, stage))
        )
        best = min(eligible, key=lambda song: rank(song, stage), default=None)
        if best is None:
            break
        selected.append(best)

    # 새 곡이 충분하면 0곡, 부족하면 부족분이 재추천 곡 수의 하한입니다.
    min_repeats = max(0, 3 - sum(song.song_id not in recent_song_ids for song in candidates))
    if side in ORDERED_SIDES and (
        len(selected) < 3 or sum(song.song_id in recent_song_ids for song in selected) > min_repeats
    ):
        def path_rank(path: tuple[ScoredSong, ...], start: int):
            return (
                sum(song.song_id in recent_song_ids for song in path),
                tuple(rank(song, stage) for stage, song in enumerate(path, start)),
            )

        # 위로·진정·발산은 밝기 또는 에너지가 계속 변하므로 같은 곡이 다시 나올 수 없습니다.
        # 마지막부터 각 후보가 이어 갈 수 있는 최선의 조합을 찾아 모든 유효한 첫 곡을 비교합니다.
        tails: list[tuple[ScoredSong, ...]] = [(song,) for song in candidates]
        for stage in (1, 0):
            tails.sort(key=lambda tail: path_rank(tail, stage + 1))
            paths = []
            for song in candidates:
                tail = next((tail for tail in tails if _can_follow(side, song, tail[0], stage + 1)), None)
                if tail is not None:
                    paths.append((song, *tail))
            tails = paths
        selected = list(min(tails, key=lambda path: path_rank(path, 0), default=()))

    if len(selected) != 3:
        raise ScoreDataError("감정·쪽별 3곡 흐름을 만족하는 후보가 부족합니다.")

    return [
        Song(song_id=song.song_id, brightness=song.valence, energy=song.arousal, step=step)
        for song, (_, _, step) in zip(selected, SIDE_TARGETS[side], strict=True)
    ]


def _can_follow(side: str, previous: ScoredSong, song: ScoredSong, stage: int) -> bool:
    if side == "위로":
        return song.valence > previous.valence
    if side == "진정":
        return song.arousal < previous.arousal and (stage == 1 or song.valence > previous.valence)
    if side == "발산":
        return song.arousal > previous.arousal
    return True
