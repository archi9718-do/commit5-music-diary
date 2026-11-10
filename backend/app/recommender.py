from .schemas import Emotion, Song

# 아래 값은 API 연동 테스트 전용의 '가상 곡'입니다.
# DEAM/PMEmo의 실제 곡 ID나 실제 평가 점수가 아닙니다.
MOCK_SONGS: dict[str, list[tuple[str, float, float, str]]] = {
    "좋음": [
        ("mock_happy_01", 0.80, 0.70, "비슷한 분위기 1"),
        ("mock_happy_02", 0.78, 0.72, "비슷한 분위기 2"),
        ("mock_happy_03", 0.82, 0.68, "비슷한 분위기 3"),
    ],
    "무난함": [
        ("mock_neutral_01", 0.50, 0.40, "비슷한 분위기 1"),
        ("mock_neutral_02", 0.55, 0.45, "비슷한 분위기 2"),
        ("mock_neutral_03", 0.52, 0.42, "비슷한 분위기 3"),
    ],
    "가라앉음": [
        ("mock_sad_01", 0.20, 0.30, "맞추기"),
        ("mock_sad_02", 0.45, 0.32, "조금 밝게"),
        ("mock_sad_03", 0.70, 0.35, "더 밝게"),
    ],
    "예민함": [
        ("mock_tense_01", 0.25, 0.85, "맞추기"),
        ("mock_tense_02", 0.30, 0.50, "에너지 낮추기"),
        ("mock_tense_03", 0.55, 0.30, "차분하고 조금 밝게"),
    ],
}


def recommend_three(emotion: Emotion) -> list[Song]:
    return [
        Song(song_id=song_id, brightness=brightness, energy=energy, step=step)
        for song_id, brightness, energy, step in MOCK_SONGS[emotion]
    ]
