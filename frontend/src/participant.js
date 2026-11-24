// 12/7 평가: 시연 기기 한 대를 돌려 쓰므로 참여자마다 4자리 코드를 만들어 서버에 X-Participant 헤더로 보냄.
// 코드는 인증이 아니고, 참여자끼리 기록이 섞이지 않게 하는 용도.
export const PARTICIPANT_KEY = "moodwave.mvp.participant.v1";
const PREFIX = "moodwave.mvp.";
const CHARS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789";
const CODE = /^[A-Z0-9]{4}$/;
const storageOrNull = () => { try { return globalThis.localStorage ?? null; } catch { return null; } };
const sessionOrNull = () => { try { return globalThis.sessionStorage ?? null; } catch { return null; } };

export const newParticipantCode = (random = Math.random) =>
  Array.from({length: 4}, () => CHARS[Math.floor(random() * CHARS.length)]).join("");

export function readParticipant(storage = storageOrNull()) {
  try {
    const code = JSON.parse(storage?.getItem(PARTICIPANT_KEY) ?? "null");
    return typeof code === "string" && CODE.test(code) ? code : null;
  } catch {
    return null;
  }
}

export function participantHeader(storage = storageOrNull()) {
  const code = readParticipant(storage);
  return code ? {"X-Participant": code} : {};
}

function clearAppKeys(storage) {
  if (!storage) return;
  const keys = Array.from({length: storage.length}, (_, i) => storage.key(i)).filter(k => k?.startsWith(PREFIX));
  keys.forEach(k => storage.removeItem(k)); // 지우면서 key(i) 순서가 바뀌므로 먼저 모은 뒤 지움
}

// 이 앱의 저장 값(moodwave.mvp.*)만 모두 지우고 새 코드를 저장. 다른 사이트·앱 값은 그대로.
// sessionStorage도 지움: 감상 후 "이어서 하기" 정보(pending-lp)가 다음 참여자에게 남지 않게 (11/24 건호 리뷰)
export function startNextParticipant(storage = storageOrNull(), random = Math.random, session = sessionOrNull()) {
  clearAppKeys(storage);
  clearAppKeys(session);
  const code = newParticipantCode(random); // 앞 사람과 같을 확률은 36^4분의 1이라 따로 확인하지 않음
  storage.setItem(PARTICIPANT_KEY, JSON.stringify(code));
  return code;
}
