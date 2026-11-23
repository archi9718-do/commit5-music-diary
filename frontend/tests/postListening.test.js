import assert from "node:assert/strict";
import test from "node:test";
import {request} from "../src/api.js";
import {hasCompletedPlayback} from "../src/domain.js";
import {moodDestination, queueCompletion, readPendingLP, retryCompletions, runAfterReactions, saveMoodAnswer, writePendingLP} from "../src/postListening.js";

test("reload and returning from another tab can open a granted unanswered question", () => {
  const tab = new Map();
  const storage = {getItem: key => tab.get(key), setItem: (key, value) => tab.set(key, value), removeItem: key => tab.delete(key)};
  const selected = {recordId: 1, day: "2026-11-23", response: "그대로예요"};
  writePendingLP(selected, storage);
  assert.deepEqual(readPendingLP(storage), selected);
  const state = {should_ask_mood: false, mood_asked_at: "2026-11-23T10:00:00Z", mood_after: null};
  assert.equal(moodDestination(state), "complete");
  assert.equal(moodDestination({...state, mood_after: "무응답"}), "engrave");
  assert.equal(moodDestination({...state, mood_asked_at: null}), "engrave");
  writePendingLP(null, storage);
  assert.equal(readPendingLP(storage), null);
});

test("failed PATCH stays retryable; a lost response uses the answer already saved", async () => {
  const answer = "그대로예요";
  let saved = null;
  let mode = "offline";
  let writes = 0;
  const api = async (path, method, body) => {
    if (path.endsWith("/post-listening")) return {mood_after: saved};
    assert.equal(method, "PATCH");
    assert.equal(body.mood_after, answer);
    if (mode === "offline") throw new Error("offline");
    saved = body.mood_after;
    writes++;
    throw new Error("response lost");
  };
  await assert.rejects(saveMoodAnswer(api, "/records/1", answer), /offline/);
  mode = "online";
  assert.deepEqual(await saveMoodAnswer(api, "/records/1", answer), {mood_after: answer});
  assert.equal(writes, 1);
});

test("finish waits for like to save and ignores simultaneous clicks", async () => {
  let like;
  const reactions = {current: new Promise(resolve => { like = resolve; })};
  const pending = {current: false};
  const events = [];
  const finish = () => runAfterReactions(pending, reactions, () => events.push("LP"), assert.fail, () => {});
  const first = finish();
  await finish();
  assert.deepEqual(events, []);
  like();
  await first;
  assert.deepEqual(events, ["LP"]);
});

test("completion is queued once and a persistent failure can fall back to saved reactions", async () => {
  const ids = new Set();
  assert.equal(queueCompletion(ids, "a", false), true);
  assert.equal(queueCompletion(ids, "a", false), false);
  assert.equal(queueCompletion(ids, "b", true), false);
  queueCompletion(ids, "c", false);
  const calls = [];
  const save = id => {
    calls.push(id);
    if (id === "a") throw new Error("offline");
    ids.delete(id);
  };
  await retryCompletions(ids, save, () => true);
  await retryCompletions(ids, save, () => true);
  assert.deepEqual(calls, ["a", "c", "a"]);
  assert.deepEqual([...ids], ["a"]);
});

test("HTTP errors retain their status when JSON cannot be read", async t => {
  for (const status of [409, 422, 500, 503]) {
    t.mock.method(globalThis, "fetch", async () => ({
      ok: false, status, json: async () => { throw new TypeError("invalid body"); },
    }));
    await assert.rejects(request("/records/1/post-listening"), {status});
    t.mock.restoreAll();
  }
  t.mock.method(globalThis, "fetch", async () => new Response("invalid"));
  await assert.rejects(request("/records/1/post-listening"), /서버 응답 형식/);
});

test("small gaps are allowed but skipping to the end still does not complete a song", () => {
  const played = (start, end) => ({length: 1, start: () => start, end: () => end});
  assert.equal(hasCompletedPlayback(played(0.35, 16), 16), true);
  assert.equal(hasCompletedPlayback(played(0.6, 16), 16), false);
  assert.equal(hasCompletedPlayback(played(15.8, 16), 16), false);
  assert.equal(hasCompletedPlayback(played(1, 200), 200), false);
});
