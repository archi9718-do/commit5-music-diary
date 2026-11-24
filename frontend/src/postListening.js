import {NO_MOOD_RESPONSE, RESPONSES} from "./domain.js";

const PENDING_LP = "moodwave.mvp.pending-lp.v1";

export function readPendingLP(storage) {
  try {
    storage ??= globalThis.sessionStorage;
    const saved = JSON.parse(storage.getItem(PENDING_LP) ?? "null");
    if (!Number.isSafeInteger(saved?.recordId) || saved.recordId <= 0 || !/^\d{4}-\d{2}-\d{2}$/.test(saved.day)) return null;
    return {
      recordId: saved.recordId, day: saved.day,
      response: [...RESPONSES, NO_MOOD_RESPONSE].includes(saved.response) ? saved.response : "",
    };
  } catch { return null; }
}

export function writePendingLP(value, storage) {
  try {
    storage ??= globalThis.sessionStorage;
    // 선택지는 같은 탭의 복구용입니다. 저장 여부는 서버 상태로 판정합니다.
    if (value) storage.setItem(PENDING_LP, JSON.stringify(value));
    else storage.removeItem(PENDING_LP);
  } catch {}
}

export function moodDestination(state) {
  if (state.mood_after != null) return "engrave";
  return state.mood_asked_at ? "complete" : "engrave";
}

export async function saveMoodAnswer(request, path, answer) {
  try {
    return await request(`${path}/mood-after`, "PATCH", {mood_after: answer});
  } catch (error) {
    // 응답만 유실되었을 수 있어 서버의 최초 저장값을 먼저 확인합니다.
    const state = await request(`${path}/post-listening`).catch(() => null);
    if (state?.mood_after != null) return state;
    throw error;
  }
}

export async function retryCompletions(ids, save, isCurrent) {
  for (const id of ids) {
    if (!isCurrent()) return;
    try {
      await save(id);
    } catch {
      // 한 곡이 실패해도 나머지 곡의 기록은 재시도합니다.
    }
  }
}

export function queueCompletion(ids, id, completed) {
  if (completed || ids.has(id)) return false;
  ids.add(id);
  return true;
}

export async function runAfterReactions(pending, reactions, work, onError, setBusy) {
  if (pending.current) return;
  pending.current = true;
  setBusy(true);
  try {
    await reactions.current;
    await work();
  } catch (error) {
    onError(error);
  } finally {
    pending.current = false;
    setBusy(false);
  }
}
