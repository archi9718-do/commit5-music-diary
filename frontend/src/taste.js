// 음악 취향 유형 검사: 12문항(감정마다 3문항)으로 감정별 추천 쪽을 정합니다. (설계 문서 5, 6.3, 6.4절)
export const TASTE_KEY = "moodwave.mvp.taste.v1";
export const OFFERED_KEY = "moodwave.mvp.taste.offered.v1";

// 감정 → [기본 쪽(검사 전과 같은 추천), 다른 쪽]. 서버 schemas.py SIDES와 같은 값
export const SIDES = {
  "가라앉음": ["위로", "머무름"],
  "예민함": ["진정", "발산"],
  "좋음": ["유지", "증폭"],
  "무난함": ["잔잔", "전환"],
};

const q = (emotion, text, a, b) => ({emotion, text, a, b});
// 문항 번호 순. a("가")는 기본 쪽, b("나")는 다른 쪽
export const QUESTIONS = [
  q("가라앉음", "마음이 가라앉은 날, 이어폰을 꽂으면?", "처음엔 차분하다가 점점 밝아지는 노래", "지금 기분 그대로인 잔잔한 노래"),
  q("가라앉음", "슬픈 영화를 보고 난 뒤라면?", "기분을 풀어 줄 노래를 찾는다", "여운에 맞는 노래를 더 듣는다"),
  q("가라앉음", "친구가 우울하다고 할 때 노래를 골라 준다면?", "힘이 나는 노래", "마음을 알아주는 노래"),
  q("예민함", "신경이 곤두선 날 듣고 싶은 노래는?", "숨이 고르게 쉬어지는 차분한 노래", "속이 시원해지는 세고 빠른 노래"),
  q("예민함", "시험이나 마감 직전 머리가 복잡할 때는?", "소리를 줄이고 조용한 곡을 튼다", "볼륨을 올리고 강한 곡을 튼다"),
  q("예민함", "화가 난 친구에게 노래를 골라 준다면?", "마음을 가라앉혀 줄 노래", "대신 소리쳐 주는 듯한 노래"),
  q("좋음", "기분 좋은 날, 이어폰을 꽂으면?", "지금 기분처럼 편안하고 밝은 노래", "더 신나서 몸이 들썩이는 노래"),
  q("좋음", "좋은 소식을 들은 직후라면?", "좋은 기분을 천천히 즐길 노래", "기분을 더 끌어올릴 노래"),
  q("좋음", "신난 친구와 같이 들을 노래를 고른다면?", "둘이 흥얼거릴 밝은 노래", "같이 뛰어오를 만큼 신나는 노래"),
  q("무난함", "별일 없는 평범한 날, 이어폰을 꽂으면?", "배경처럼 편하게 흐르는 노래", "하루에 활기를 더해 줄 노래"),
  q("무난함", "출근·등굣길이 그저 그런 기분일 때는?", "지금 분위기에 맞는 무난한 노래", "기분을 바꿔 줄 밝은 노래"),
  q("무난함", "심심하다는 친구에게 노래를 골라 준다면?", "편하게 들을 만한 노래", "기분 전환이 될 신나는 노래"),
];
// 보여 주는 순서: 축을 섞어 1→2→3→4→1…
export const QUESTION_ORDER = [0, 3, 6, 9, 1, 4, 7, 10, 2, 5, 8, 11];

export const NICKNAMES = {
  "위진유잔": "따뜻한 기본기", "머진유잔": "조용한 공감가",
  "위진유전": "산뜻한 전환가", "머진유전": "잔잔한 기분 전환가",
  "위진증잔": "햇살 같은 응원단", "머진증잔": "고요히 곁을 지키는 감상가",
  "위진증전": "에너지 충전소", "머진증전": "깊고 맑은 파도",
  "위발유잔": "시원한 해소가", "머발유잔": "솔직한 감정 기록가",
  "위발유전": "반전 있는 리듬가", "머발유전": "거침없는 감정 여행자",
  "위발증잔": "뜨거운 응원가", "머발증잔": "진한 감정의 파도",
  "위발증전": "무대 체질", "머발증전": "감정을 끝까지 듣는 사람",
};

// 결과 카드의 감정별 한 줄. 머무름·진정·증폭·잔잔은 설계 문서 예시, 나머지 4개는 초안(상현 검토)
export const SIDE_COPY = {
  "위로": "점점 밝은 곡으로 옮겨 가요", "머무름": "잔잔한 곡에 머물러요",
  "진정": "차분하게 가라앉혀요", "발산": "센 곡으로 시원하게 쏟아내요",
  "유지": "밝은 기분을 그대로 이어 가요", "증폭": "더 신나게 끌어올려요",
  "잔잔": "편하게 흘려 들어요", "전환": "활기찬 곡으로 기분을 바꿔요",
};

export function scoreTaste(answers) {
  return Object.fromEntries(Object.entries(SIDES).map(([emotion, [first, second]]) => {
    const picks = QUESTIONS.flatMap((question, i) => question.emotion === emotion ? [answers[i]] : []);
    return [emotion, picks.filter(a => a === "나").length >= 2 ? second : first];  // 3문항이라 동점 없음
  }));
}

export const typeCode = sides => Object.keys(SIDES).map(emotion => sides[emotion][0]).join("");

// 저장 값 확인. sides는 저장값을 믿지 않고 answers로 다시 계산합니다 (옛 버전·손상 값 대비)
export function parseTaste(value) {
  const answers = value?.answers;
  if (!Array.isArray(answers) || answers.length !== QUESTIONS.length || !answers.every(a => a === "가" || a === "나")) {
    return null;
  }
  return {sides: scoreTaste(answers), answers, takenAt: value.takenAt};
}

export const tasteSideFor = (taste, emotion) => {
  const side = taste?.sides?.[emotion];
  return SIDES[emotion]?.includes(side) ? side : undefined;
};
