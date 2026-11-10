"""실제 데이터가 없어도 동작하는 규칙·입력 검증 테스트."""

from pathlib import Path

import pytest
from app.recommender import ScoreDataError, load_song_scores, recommend_three

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
