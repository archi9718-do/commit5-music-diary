import {MOODS, recommend} from "./domain.js";
import {participantHeader} from "./participant.js";

// 음원 전용 화면에서는 ngrok 로그인과 음원 API가 같은 주소를 사용합니다.
const base = import.meta.env?.VITE_AUDIO_DEMO_ONLY === "1"
  ? ""
  : (import.meta.env?.VITE_API_BASE_URL || "http://127.0.0.1:8000").replace(/\/+$/, "");
export const apiUrl = path => `${base}${path}`;

export async function request(path, method = "GET", body) {
  const response = await fetch(apiUrl(`/api${path}`), {
    method,
    signal: AbortSignal.timeout(30000),
    // 녹음(Blob)은 JSON 대신 본문 그대로 보냄 (POST /records/voice는 raw body)
    ...(body === undefined ? {headers: participantHeader()} : body instanceof Blob ? {
      headers: {"Content-Type": body.type || "application/octet-stream", ...participantHeader()},
      body,
    } : {
      headers: {"Content-Type": "application/json", ...participantHeader()},
      body: JSON.stringify(body),
    }),
  });
  if (!response.ok) {
    const data = await response.json().catch(() => null);
    const error = new Error(typeof data?.detail === "string" ? data.detail : "서버 요청을 처리하지 못했어요.");
    error.status = response.status;
    throw error;
  }
  const data = await response.json().catch(error => {
    if (!(error instanceof SyntaxError)) throw error;
    return null;
  });
  if (!data || typeof data !== "object") throw new Error("서버 응답 형식이 올바르지 않아요.");
  return data;
}

export const moodId = label => MOODS.find(mood => mood.label === label)?.id;

export function analysisResult(data) {
  const kind = {"높음": "high", "중간": "medium", "낮음": "low"}[data.confidence];
  const ranked = Object.entries(data.probs).sort((a, b) => b[1] - a[1]);
  const candidates = kind === "high" ? [moodId(data.emotion)]
    : kind === "medium" ? ranked.slice(0, 2).map(([label]) => moodId(label)) : [];
  return {kind, candidates};
}

export const songState = song => ({
  liked: song.is_liked,
  skipped: song.is_skipped,
  completed: song.is_completed,
  engraved: song.is_engraved,
});

export function lpTracks(songs, mood) {
  const previews = recommend(mood);
  return songs.map((song, i) => ({
    ...previews[i],
    id: `server:${song.song_id}`,
    previewId: previews[i].id,
    order: song.recommend_order,
    title: song.title || song.song_id,
    artist: song.artist || "시연 음원",
    reason: song.step,
  }));
}

export const lpStates = songs => Object.fromEntries(
  songs.map(song => [`server:${song.song_id}`, songState(song)]),
);
