"""실제 데이터가 없어도 동작하는 규칙·입력 검증 테스트."""

from pathlib import Path

import pytest

from app.recommender import ScoreDataError, load_song_scores, recommend_three
from app.schemas import SIDES

FIXTURE = Path(__file__).parent / "fixtures" / "sample_song_scores.csv"


@pytest.mark.parametrize("emotion", ["좋음", "무난함", "가라앉음", "예민함"])
def test_all_emotions_return_three_distinct_deam_songs(monkeypatch, emotion):
    monkeypatch.setenv("MOODWAVE_SCORES_CSV", str(FIXTURE))
    monkeypatch.delenv("MOODWAVE_RECOMMEND_SCOPE", raising=False)
    songs = recommend_three(emotion)
    assert len(songs) == 3
    assert len({song.song_id for song in songs}) == 3
    assert all(song.song_id.startswith("deam_") for song in songs)
    assert all(0 <= song.brightness <= 1 and 0 <= song.energy <= 1 for song in songs)


def test_sad_brightness_increases(monkeypatch):
    monkeypatch.setenv("MOODWAVE_SCORES_CSV", str(FIXTURE))
    songs = recommend_three("가라앉음")
    assert songs[0].brightness < songs[1].brightness < songs[2].brightness
    assert [song.step for song in songs] == ["맞추기", "조금 밝게", "더 밝게"]


def test_tense_energy_decreases(monkeypatch):
    monkeypatch.setenv("MOODWAVE_SCORES_CSV", str(FIXTURE))
    songs = recommend_three("예민함")
    assert songs[0].energy > songs[1].energy > songs[2].energy
    assert songs[2].brightness > songs[1].brightness


def test_optional_internal_scope_allows_pmemo(monkeypatch):
    monkeypatch.setenv("MOODWAVE_SCORES_CSV", str(FIXTURE))
    monkeypatch.setenv("MOODWAVE_RECOMMEND_SCOPE", "ALL")
    songs = recommend_three("좋음")
    assert any(song.song_id.startswith("pmemo_") for song in songs)


def test_recent_songs_fill_slots_when_only_two_new_songs_are_available(monkeypatch):
    monkeypatch.setenv("MOODWAVE_SCORES_CSV", str(FIXTURE))
    new_ids = {"deam_2", "deam_3"}
    recent_ids = {song.song_id for song in load_song_scores(FIXTURE)} - new_ids

    ids = [song.song_id for song in recommend_three("좋음", recent_ids)]
    assert len(set(ids)) == 3
    assert set(ids[:2]) == new_ids
    assert ids[2] in recent_ids


@pytest.mark.parametrize(("emotion", "new_in_order"), [
    ("가라앉음", ["deam_2", "deam_5", "deam_3"]),
    ("예민함", ["deam_4", "deam_3", "deam_7"]),
])
def test_reorders_new_songs_to_complete_the_emotion_progression(monkeypatch, emotion, new_in_order):
    monkeypatch.setenv("MOODWAVE_SCORES_CSV", str(FIXTURE))
    recent_ids = {song.song_id for song in load_song_scores(FIXTURE)} - set(new_in_order)

    assert [song.song_id for song in recommend_three(emotion, recent_ids)] == new_in_order


def test_recent_preference_minimizes_repeats_when_new_song_must_go_last(monkeypatch):
    monkeypatch.setenv("MOODWAVE_SCORES_CSV", str(FIXTURE))
    # 가장 밝은 곡으로 시작하면 이후 두 곡의 밝기를 높일 수 없습니다.
    recent_ids = {song.song_id for song in load_song_scores(FIXTURE)} - {"deam_10"}

    songs = recommend_three("가라앉음", recent_ids)
    assert songs[0].brightness < songs[1].brightness < songs[2].brightness
    assert songs[2].song_id == "deam_10"


def test_missing_csv_is_not_silently_mocked(monkeypatch, tmp_path):
    monkeypatch.setenv("MOODWAVE_SCORES_CSV", str(tmp_path / "not_exists.csv"))
    with pytest.raises(ScoreDataError):
        recommend_three("무난함")


def test_out_of_range_and_duplicate_ids_rejected(tmp_path):
    invalid = tmp_path / "bad.csv"
    invalid.write_text(
        "song_id,dataset,valence,arousal\n"
        "deam_2,DEAM,0.4,0.5\n"
        "deam_2,DEAM,0.4,0.5\n",
        encoding="utf-8",
    )
    with pytest.raises(ScoreDataError, match="중복"):
        load_song_scores(invalid)
    invalid.write_text("song_id,dataset,valence,arousal\ndeam_2,DEAM,1.2,0.5\n", encoding="utf-8")
    with pytest.raises(ScoreDataError, match="0~1"):
        load_song_scores(invalid)


NEW_STEPS = {
    ("가라앉음", "머무름"): ["맞추기", "곁에 머물기", "잔잔하게 마무리"],
    ("예민함", "발산"): ["맞추기", "쏟아내기", "끝까지 쏟아내기"],
    ("좋음", "증폭"): ["맞추기", "더 신나게", "끌어올리기"],
    ("무난함", "전환"): ["맞추기", "조금 밝게", "활기차게"],
}


@pytest.mark.parametrize(("emotion", "side"), NEW_STEPS)
def test_new_sides_return_three_songs_with_their_steps(monkeypatch, emotion, side):
    monkeypatch.setenv("MOODWAVE_SCORES_CSV", str(FIXTURE))
    songs = recommend_three(emotion, side=side)
    assert [s.step for s in songs] == NEW_STEPS[(emotion, side)]
    assert len({s.song_id for s in songs}) == 3


@pytest.mark.parametrize("emotion", ["좋음", "무난함", "가라앉음", "예민함"])
def test_default_side_equals_no_side(monkeypatch, emotion):
    monkeypatch.setenv("MOODWAVE_SCORES_CSV", str(FIXTURE))
    assert recommend_three(emotion) == recommend_three(emotion, side=SIDES[emotion][0])


def test_side_of_other_emotion_is_rejected(monkeypatch):
    monkeypatch.setenv("MOODWAVE_SCORES_CSV", str(FIXTURE))
    with pytest.raises(ValueError):
        recommend_three("가라앉음", side="발산")
