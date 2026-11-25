import test from "node:test";
import assert from "node:assert/strict";
import {request, uncertainTranscript} from "../src/api.js";

const respond = (status, body) => async () => new Response(JSON.stringify(body), {status, headers: {"Content-Type": "application/json"}});

test("애매한 받아쓰기(422 uncertain_transcript)는 받아쓴 글을 돌려준다", async () => {
  globalThis.fetch = respond(422, {detail: {code: "uncertain_transcript", text: "고마워요.", message: "이렇게 들었어요."}});
  const error = await request("/records/voice", "POST", new Blob(["x"])).catch(e => e);
  assert.equal(uncertainTranscript(error), "고마워요.");
  assert.equal(error.message, "이렇게 들었어요.");
});

test("다른 오류는 애매한 받아쓰기가 아니다", async () => {
  globalThis.fetch = respond(422, {detail: "말소리를 알아듣지 못했어요."});
  const error = await request("/records/voice", "POST", new Blob(["x"])).catch(e => e);
  assert.equal(uncertainTranscript(error), null);
  assert.equal(error.message, "말소리를 알아듣지 못했어요.");
  assert.equal(uncertainTranscript(new Error("x")), null);
});
