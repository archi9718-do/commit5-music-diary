import test from "node:test";
import assert from "node:assert/strict";
import {MOODS} from "../src/domain.js";
import {
  NICKNAMES, QUESTION_ORDER, QUESTIONS, SIDES, SIDE_COPY, parseTaste, scoreTaste, tasteSideFor, typeCode,
} from "../src/taste.js";

test("문항 번호 순 답으로 축마다 많이 고른 쪽", () => {
  const a = ["나", "나", "가", "가", "가", "가", "가", "나", "나", "가", "가", "가"];
  assert.deepEqual(scoreTaste(a), {"가라앉음": "머무름", "예민함": "진정", "좋음": "증폭", "무난함": "잔잔"});
  assert.equal(typeCode(scoreTaste(a)), "머진증잔");
  assert.equal(NICKNAMES["머진증잔"], "고요히 곁을 지키는 감상가");
});

test("16유형 별명과 8쪽 문구가 모두 있다", () => {
  assert.equal(Object.keys(NICKNAMES).length, 16);
  for (const [first, second] of Object.values(SIDES)) assert.ok(SIDE_COPY[first] && SIDE_COPY[second]);
  assert.deepEqual(Object.keys(SIDES).sort(), MOODS.map(m => m.label).sort());
});

test("보여 주는 순서는 축을 섞는다", () => {
  assert.deepEqual(QUESTION_ORDER.slice(0, 4).map(i => QUESTIONS[i].emotion), ["가라앉음", "예민함", "좋음", "무난함"]);
  assert.deepEqual([...QUESTION_ORDER].sort((x, y) => x - y), [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11]);
  assert.equal(QUESTIONS.length, 12);
});

test("깨진 저장 값은 결과 없음", () => {
  for (const v of [null, "x", {}, {answers: Array(11).fill("가")}, {answers: Array(12).fill("다")}]) {
    assert.equal(parseTaste(v), null);
  }
});

test("저장된 sides는 믿지 않고 답으로 다시 계산한다", () => {
  const t = parseTaste({sides: {"가라앉음": "발산"}, answers: Array(12).fill("나"), takenAt: "2026-11-30T10:00:00+09:00"});
  assert.deepEqual(t.sides, {"가라앉음": "머무름", "예민함": "발산", "좋음": "증폭", "무난함": "전환"});
  assert.equal(t.takenAt, "2026-11-30T10:00:00+09:00");
});

test("그 감정의 쪽이 아니면 taste_side를 보내지 않는다", () => {
  const t = {sides: {"가라앉음": "발산", "예민함": "발산"}, answers: Array(12).fill("가"), takenAt: "2026-11-30T10:00:00+09:00"};
  assert.equal(tasteSideFor(t, "가라앉음"), undefined);
  assert.equal(tasteSideFor(t, "예민함"), "발산");
  assert.equal(tasteSideFor(t, "좋음"), undefined);
  assert.equal(tasteSideFor(null, "좋음"), undefined);
});
