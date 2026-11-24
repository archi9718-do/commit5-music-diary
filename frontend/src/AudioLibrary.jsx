import React, {useEffect, useRef, useState} from "react";
import {apiUrl, request} from "./api.js";

export default function AudioLibrary() {
  const [tracks, setTracks] = useState(null);
  const [selected, setSelected] = useState("");
  const [listError, setListError] = useState(false);
  const [playError, setPlayError] = useState(false);
  const [attempt, setAttempt] = useState(0);
  const audio = useRef(null);

  useEffect(() => {
    let active = true;
    request("/audio").then(({tracks}) => {
      if (!active) return;
      if (!Array.isArray(tracks)) throw new Error("Invalid audio catalog");
      setTracks(tracks);
      setSelected(tracks[0]?.audio_id ?? "");
    }).catch(() => {
      if (active) setListError(true);
    });
    return () => {active = false;};
  }, [attempt]);

  const track = tracks?.find(item => item.audio_id === selected);
  useEffect(() => {
    const player = audio.current;
    return () => player?.pause();
  }, [track?.audio_id]);
  return <>
    <div className="heading"><h1 tabIndex={-1}>등록 음원</h1></div>
    {listError ? <div className="empty">
      <p role="alert">음원 목록을 불러오지 못했어요.</p>
      <button type="button" className="btn secondary" onClick={() => {setListError(false);setAttempt(attempt + 1);}}>다시 시도</button>
    </div> : tracks === null ? <p role="status">음원 목록을 불러오고 있어요.</p>
      : tracks.length === 0 ? <div className="empty"><p>이 환경에서 재생할 수 있는 등록 음원이 없어요.</p></div>
      : <div className="surface audio-library">
        <label className="field">재생할 곡
          <select value={selected} onChange={event => {setSelected(event.target.value);setPlayError(false);}}>
            {tracks.map(item => <option key={item.audio_id} value={item.audio_id}>{item.title} · {item.artist}</option>)}
          </select>
        </label>
        {track && <audio key={track.audio_id} ref={audio} controls preload="metadata"
          aria-label={`${track.title} 재생`} src={apiUrl(track.audio_url)}
          onError={() => setPlayError(true)} />}
        {playError && <>
          <p role="alert">이 음원을 불러오지 못했어요.</p>
          <button type="button" className="btn secondary" onClick={() => {
            setPlayError(false);
            audio.current?.load();
          }}>같은 곡 다시 불러오기</button>
        </>}
      </div>}
  </>;
}
