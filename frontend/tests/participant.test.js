import test from "node:test";
import assert from "node:assert/strict";
import {PARTICIPANT_KEY, newParticipantCode, participantHeader, readParticipant, startNextParticipant} from "../src/participant.js";

const fakeStorage = (init = {}) => {
  const data = new Map(Object.entries(init));
  return {
    get length() { return data.size; },
    key: i => [...data.keys()][i] ?? null,
    getItem: k => data.get(k) ?? null,
    setItem: (k, v) => data.set(k, String(v)),
    removeItem: k => data.delete(k),
    keys: () => [...data.keys()],
  };
};

test("코드는 영문 대문자·숫자 4자리", () => {
  for (let i = 0; i < 50; i++) assert.match(newParticipantCode(), /^[A-Z0-9]{4}$/);
  assert.equal(newParticipantCode(() => 0), "AAAA");
  assert.equal(newParticipantCode(() => 0.999999), "9999");
});

test("다음 참여자로 시작은 moodwave.mvp. 키만 모두 지우고 새 코드를 저장한다", () => {
  const s = fakeStorage({
    "moodwave.mvp.records.v1": "[1]", "moodwave.mvp.pending-lp.v1": "{}", "moodwave.mvp.entry.v1": "\"history\"",
    "moodwave.mvp.participant.v1": "\"OLD1\"", "other.app": "x",
  });
  const code = startNextParticipant(s);
  assert.deepEqual(s.keys().sort(), [PARTICIPANT_KEY, "other.app"]);
  assert.equal(readParticipant(s), code);
});

test("코드가 없거나 형식이 틀리면 헤더를 보내지 않는다", () => {
  assert.deepEqual(participantHeader(fakeStorage({})), {});
  assert.deepEqual(participantHeader(fakeStorage({[PARTICIPANT_KEY]: "\"k7qm\""})), {});
  assert.deepEqual(participantHeader(fakeStorage({[PARTICIPANT_KEY]: "깨진값"})), {});
  assert.deepEqual(participantHeader(fakeStorage({[PARTICIPANT_KEY]: "\"K7QM\""})), {"X-Participant": "K7QM"});
  assert.deepEqual(participantHeader(undefined), {});
});
