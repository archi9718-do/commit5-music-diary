import React, {useEffect, useRef, useState} from "react";
import AudioLibrary from "./AudioLibrary.jsx";
import {MOODS, moodInfo, classify, recommend, getTrack, RESPONSES, NO_MOOD_RESPONSE, canReview, hasCompletedPlayback, nextTrackState, localDay, shiftMonth, monthLabel, dateLabel, forMonth, monthlyMood, monthlyMusic, makeRecord, dayType} from "./domain.js";
import {request, moodId, analysisResult, lpTracks, lpStates, songState, applyReasons, reasonsAction} from "./api.js";
import {readParticipant, startNextParticipant} from "./participant.js";
import {moodDestination, queueCompletion, readPendingLP, retryCompletions, runAfterReactions, saveMoodAnswer, writePendingLP} from "./postListening.js";

const PAGES={
  start:["시작","시작"],
  "audio-library":["등록 음원","음악 감상"],
  login:["로그인","시작"], signup:["회원가입","시작"],
  record:["오늘의 기록","감정 기록"], consent:["음성 녹음 동의","감정 기록"], voice:["음성 녹음","감정 기록"],
  loading:["감정 분석 중","감정 확인"], high:["오늘 이런 기분이었나요?","감정 확인"], medium:["어느 쪽에 더 가까울까요?","감정 확인"],
  low:["어떤 감정에 가까운가요?","감정 확인"], manual:["지금 마음을 직접 골라주세요","감정 확인"],
  recommend:["오늘의 추천 음악","음악 감상"], player:["음악 감상","음악 감상"], react:["곡에 반응 남기기","음악 감상"], complete:["감상 완료","음악 감상"],
  engrave:["LP 새김 확인","LP 기록"], engraved:["LP 새김 완료","LP 기록"], today:["오늘의 LP판","LP 기록"], history:["날짜별 기록","LP 기록"],
  me:["마이페이지","나의 기록"], "monthly-mood":["월간 감정 분석","나의 기록"], "monthly-music":["월간 음악 취향","나의 기록"], daytype:["Day Type","나의 기록"],
  failure:["감정을 분석하지 못했어요","예외 및 안내"], risk:["도움을 받을 수 있어요","예외 및 안내"], error:["문제가 발생했어요","예외 및 안내"],
};
const TABS=[["record","기록","note"],["history","내역","history"],["today","나의 LP","disc"],["me","마이","user"]];
const STORE="moodwave.mvp.records.v1";
const PREF="moodwave.mvp.entry.v1";
const MAX_RECORDING_SECONDS=10;
const read=(key, fallback)=>{try{return JSON.parse(localStorage.getItem(key)??"null")??fallback;}catch{return fallback;}};
const write=(key,data)=>{try{localStorage.setItem(key,JSON.stringify(data));return true;}catch{return false;}};
const route=()=>{const key=location.hash.replace(/^#\/?/,"").split("?")[0];return Object.hasOwn(PAGES,key)?key:"start";};
const fresh=()=>({input:"",mood:null,mode:"text",response:"",askMood:false,tracks:{},engrave:[],queue:[],recordId:null,demo:false,replacing:false,saved:false});
const emptyResult={kind:"low",candidates:[]};
const savedTrack=(record,id)=>record?.queue?.find(track=>track.id===id)??getTrack(id);

function Icon({name,size=19,...props}){
  const paths={note:<><rect x="5" y="4" width="14" height="16" rx="3"/><path d="M8 8h8M8 12h8m-8 4h5"/></>,history:<><circle cx="12" cy="12" r="8"/><path d="M12 7v5l3 2"/></>,disc:<><circle cx="12" cy="12" r="8"/><circle cx="12" cy="12" r="2"/></>,user:<><circle cx="12" cy="8" r="3"/><path d="M5 20v-1a7 7 0 0 1 14 0v1"/></>,back:<path d="m14 6-6 6 6 6"/>,next:<path d="m10 6 6 6-6 6"/>,arrow:<path d="M4 12h15m-6-5 6 5-6 5"/>,play:<path d="m8 5 12 7-12 7z" fill="currentColor" stroke="none"/>,pause:<path d="M9 6v12M15 6v12" strokeWidth="3.5"/>,heart:<path d="M20 9c0 4-8 9-8 9s-8-5-8-9a4 4 0 0 1 8-1 4 4 0 0 1 8 1Z"/>,check:<path d="m5 12 4 4 10-10"/>,mic:<><rect x="9" y="3" width="6" height="12" rx="3"/><path d="M5 11a7 7 0 0 0 14 0m-7 7v3m-3 0h6"/></>,shield:<><path d="M12 3 5 6v5c0 4 3 7 7 10 4-3 7-6 7-10V6z"/><path d="m9 12 2 2 4-4"/></>};
  return <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.65" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" {...props}>{paths[name]}</svg>;
}
function LP({small=false,playing=false,done=false}) {
  return <svg className={`lp ${small?"lp-small":""} ${playing?"lp-playing":""}`} viewBox="0 0 250 158" aria-hidden="true">
    {!small&&<ellipse cx="125" cy="82" rx="115" ry="25" transform="rotate(-20 125 82)" fill="none" stroke="#18121c" strokeWidth="7"/>}
    <circle cx="125" cy="78" r="63" fill="#18121c"/>
    <circle cx="125" cy="78" r="22" fill="#fffaff"/>
    {playing&&<circle cx="125" cy="65" r="2.9" fill="#b798cf" className="spin-dot"/>}
    {done&&<path d="m115 78 7 7 14-15" fill="none" stroke="#6b3e91" strokeWidth="4" strokeLinecap="round" strokeLinejoin="round"/>}
  </svg>;
}
function Cover({theme}){return <span className={`cover ${theme}`} aria-hidden="true"><span/></span>;}
function Btn({children,variant="primary",className="",...props}){return <button type="button" className={`btn ${variant} ${className}`} {...props}>{children}</button>;}
function Mood({id}){const m=moodInfo(id); return <span className="mood" style={{"--mood":m.color,"--mood-ink":m.hue}}><span>{m.symbol}</span>{m.label}</span>;}
function MoodSelect({ids=MOODS.map(x=>x.id),active=null,onPick,stack=false}){
  return <div className={stack?"mood-grid stack":"mood-grid"}>{ids.map(id=><button key={id} type="button" className={`mood-choice ${active===id?"is-selected":""}`} aria-pressed={active===id} onClick={()=>onPick(id)}><Mood id={id}/>{active===id&&<Icon name="check" size={17}/>}</button>)}</div>;
}
function Notice({children,kind=""}){return <p className={`notice ${kind}`}>{children}</p>;}
function Heading({title,desc}){return <div className="heading"><h1 tabIndex={-1}>{title}</h1>{desc&&<p>{desc}</p>}</div>;}
function MonthSelect({month,onChange}){return <div className="month-picker"><button className="icon" aria-label="이전 달" onClick={()=>onChange(shiftMonth(month,-1))}><Icon name="back"/></button><strong>{monthLabel(month)}</strong><button className="icon" aria-label="다음 달" onClick={()=>onChange(shiftMonth(month,1))}><Icon name="next"/></button></div>;}
function ReviewRows({items,states,onAction}) {
  return <div className="cards">{items.map(t=>{const s=states[t.id]??{};return <div className="track-card reaction-card" key={t.id}><Cover theme={t.theme}/><div className="track-body"><strong>{t.title}</strong><small>{s.completed?"완청":s.skipped?"건너뜀":"아직 완청하지 않음"}</small></div><div className="track-controls"><button className={`mini-like ${s.liked?"liked":""}`} aria-label={`${t.title} ${s.liked?"좋아요 취소":"좋아요"}`} aria-pressed={!!s.liked} onClick={()=>onAction(t.id,"like")}><Icon name="heart" size={16} fill={s.liked?"currentColor":"none"}/>{s.liked?"좋아요 취소":"좋아요"}</button>{!s.skipped&&!s.completed&&<button className="link" onClick={()=>onAction(t.id,"skip")}>건너뛰기</button>}</div></div>})}</div>;
}
function Player({queue,index,onIndex,onAction,onReview}){
  const audio=useRef(null),track=queue[index],trackId=track?.id;
  const [time,setTime]=useState(0),[duration,setDuration]=useState(track?.seconds??16),[playing,setPlaying]=useState(false),[issue,setIssue]=useState("");
  const auto=useRef(false);
  useEffect(()=>{
    const a=audio.current;
    setTime(0); setDuration(track?.seconds??16); setPlaying(false);setIssue("");
    if (a && auto.current) {auto.current=false;a.play().catch(()=>{if(audio.current===a)setIssue("재생 버튼을 눌러 들을 수 있어요.");});}
    return ()=>a?.pause();
  },[trackId]);
  if(!track)return null;
  const toggle=()=>{const a=audio.current;if(!a)return;if(!a.paused){a.pause();return;}a.play().catch(()=>{if(audio.current===a)setIssue("재생을 시작하지 못했어요. 잠시 후 다시 눌러주세요.");});};
  const move=(offset,skip=false)=>{if(skip)onAction(trackId,"skip");const next=index+offset;if(next<0||next>=queue.length){onReview();return;}auto.current=!!audio.current&&!audio.current.paused;onIndex(next);};
  const end=event=>{
    setPlaying(false);
    const {played,duration}=event.currentTarget;
    if(hasCompletedPlayback(played,duration)){setIssue("");onAction(trackId,"finish");}
    else setIssue("건너뛴 구간이 있어요. 전체를 들으면 완청으로 기록돼요.");
  };
  const clock=x=>`${Math.floor(x/60)}:${String(Math.floor(x%60)).padStart(2,"0")}`;
  return <><Heading title="음악 감상" desc="추천곡마다 짧은 시연용 합성 음원을 재생해요."/><LP playing={playing}/><div className="track-center"><h2>{track.title}</h2><p>{track.artist}</p></div>
    <audio key={trackId} ref={audio} src={`${import.meta.env.BASE_URL}audio/${track.previewId??track.id}.wav`} preload="metadata" onPlay={()=>setPlaying(true)} onPause={()=>setPlaying(false)} onLoadedMetadata={e=>{if(Number.isFinite(e.currentTarget.duration))setDuration(e.currentTarget.duration);}} onTimeUpdate={e=>setTime(e.currentTarget.currentTime)} onEnded={end} onError={()=>setIssue("시연 음원을 불러오지 못했어요.")}/>
    <label className="seek"><span className="sr-only">재생 위치</span><input type="range" aria-label="재생 위치" min="0" max={duration||16} step=".1" value={Math.min(time,duration)} onChange={e=>{if(audio.current)audio.current.currentTime=Number(e.target.value);setTime(Number(e.target.value));}}/><span><span>{clock(time)}</span><span>{clock(duration)}</span></span></label>
    <div className="player-actions"><button className="icon" aria-label="이전 곡" disabled={index===0} onClick={()=>move(-1)}><Icon name="back"/></button><button className="icon play-main" aria-label={playing?"일시정지":"재생"} onClick={toggle}><Icon name={playing?"pause":"play"} size={25}/></button><button className="icon" aria-label="다음 곡" disabled={index===queue.length-1} onClick={()=>move(1)}><Icon name="next"/></button></div>
    <p className="counter">{index+1} / {queue.length}</p>{issue&&<Notice kind="warn">{issue}</Notice>}
    <div className="actions"><Btn variant="secondary" onClick={onReview}>곡에 반응 남기기</Btn><button className="link" onClick={()=>move(1,true)}>이 곡 건너뛰기</button></div></>;
}
function Voice({onAnalyze,onFail,onBack}){
  const stream=useRef(null),rec=useRef(null),timer=useRef(null),permission=useRef(null),alive=useRef(true);
  const [status,setStatus]=useState("idle"),[seconds,setSeconds]=useState(0),[busy,setBusy]=useState(false);
  const chunks=useRef([]);
  const stopStream=()=>{stream.current?.getTracks().forEach(t=>t.stop());stream.current=null;};
  useEffect(()=>{alive.current=true;return()=>{alive.current=false;clearInterval(timer.current);if(rec.current?.state==="recording")rec.current.stop();stopStream();};},[]);
  const stop=()=>{if(rec.current?.state==="recording")rec.current.stop();};
  const start=async()=>{
    if(busy)return;
    if(!navigator.mediaDevices?.getUserMedia||!window.MediaRecorder){onFail("이 브라우저에서는 마이크를 사용할 수 없어요. localhost에서 실행하거나 글로 기록해주세요.");return;}
    setBusy(true);setSeconds(0);
    let s;
    try{
      permission.current=navigator.mediaDevices.getUserMedia({audio:true});
      s=await permission.current;
      if(!alive.current){s.getTracks().forEach(t=>t.stop());return;}
      stream.current=s;
      const recorder=new MediaRecorder(s);rec.current=recorder;chunks.current=[];
      // 녹음은 메모리에만 모았다가 받아쓰기 요청 한 번에 보냄. 브라우저·서버 어디에도 파일로 남기지 않음
      recorder.ondataavailable=e=>{if(e.data.size)chunks.current.push(e.data);};
      recorder.onstop=()=>{clearInterval(timer.current);stopStream();rec.current=null;if(alive.current)setStatus("done");};
      recorder.onerror=()=>{clearInterval(timer.current);stopStream();if(alive.current)onFail("녹음을 마치지 못했어요. 글이나 직접 선택으로 계속할 수 있어요.");};
      recorder.start();setStatus("recording");
      let i=0;timer.current=setInterval(()=>{i++;setSeconds(i);if(i>=MAX_RECORDING_SECONDS)stop();},1000);
    }catch{stopStream();if(alive.current)onFail("마이크 권한이 없거나 장치를 사용할 수 없어요. 글이나 직접 선택으로 계속할 수 있어요.");}
    finally{if(alive.current)setBusy(false);}
  };
  return <><Heading title="음성 녹음" desc={`최대 ${MAX_RECORDING_SECONDS}초 동안 말해볼 수 있어요.`}/><div className={`mic-stage ${status==="recording"?"live":""}`}><Icon name="mic" size={38}/><strong aria-live="polite">0:{String(seconds).padStart(2,"0")}</strong><span>{status==="recording"?"녹음 중":status==="done"?"녹음 종료 · 원본 미저장":"녹음 대기"}</span></div>
  <Notice>녹음은 받아쓰기를 위해 서버로 한 번 보내요. 서버는 받아쓴 글만 저장하고 원본 음성은 저장하지 않아요.</Notice>
  <div className="actions">{status==="recording"?<Btn onClick={stop}>녹음 종료</Btn>:status==="done"?<><Btn onClick={()=>{const blob=new Blob(chunks.current,{type:chunks.current[0]?.type||"audio/webm"});chunks.current=[];if(onAnalyze(blob)===false){setStatus("idle");setSeconds(0);}}}>기록 완료</Btn><Btn variant="secondary" disabled={busy} onClick={start}>다시 녹음하기</Btn></>:<Btn disabled={busy} onClick={start}>{busy?"권한 확인 중":"녹음 시작"}</Btn>}<button className="link" onClick={onBack}>글로 기록하기</button></div></>;
}

export default function App(){
  const [page,setPage]=useState(route),[navStack,setNavStack]=useState([]);
  const navigation=useRef({page,revision:0});
  const [recovery,setRecovery]=useState(()=>["react","complete","engrave"].includes(route())?readPendingLP():null);
  const [recoveryError,setRecoveryError]=useState("");
  const [entry,setEntry]=useState(()=>read(PREF,"record")==="history"?"history":"record");
  const [records,setRecords]=useState(()=>{const a=read(STORE,[]);return Array.isArray(a)?a.filter(r=>r&&typeof r.day==="string"):[];});
  const [draft,setDraft]=useState(fresh),[result,setResult]=useState(emptyResult),[pick,setPick]=useState(null);
  const [index,setIndex]=useState(0),[agreed,setAgreed]=useState(false),[message,setMessage]=useState(""),[flash,setFlash]=useState("");
  const [month,setMonth]=useState(()=>localDay().slice(0,7)),[viewDay,setViewDay]=useState(""),[demo,setDemo]=useState(false);
  const pending=useRef(false), reactions=useRef(Promise.resolve()), reactionStates=useRef({});
  const reasonSeq=useRef(0), latestDraft=useRef(null); latestDraft.current=draft; // 늦게 온 이유 응답이 지금 화면 상태와 맞는지 볼 때 씀
  const unsavedCompletions=useRef(new Set());
  const [completionSaveFailed,setCompletionSaveFailed]=useState(false);
  const [busy,setBusy]=useState(false);
  const main=useRef(null),today=new Intl.DateTimeFormat("sv-SE",{timeZone:"Asia/Seoul"}).format(new Date());
  const queue=draft.queue,count=queue.filter(t=>draft.tracks[t.id]?.completed).length;
  const thisMonth=forMonth(records,month),todaysRecord=records.find(a=>a.day===today);
  const viewRecord=records.find(a=>a.day===(viewDay||today));
  const liked=queue.filter(t=>draft.tracks[t.id]?.liked);
  const patch=(p)=>setDraft(old=>({...old,...p}));
  function updatePage(to){
    const previous=navigation.current;
    if(previous.page!==to)navigation.current={page:to,revision:previous.revision+1};
    setPage(to);
  }
  useEffect(()=>{const h=()=>updatePage(route());window.addEventListener("hashchange",h);return ()=>window.removeEventListener("hashchange",h);},[]);
  useEffect(()=>{if(!flash)return;const t=setTimeout(()=>setFlash(""),3700);return ()=>clearTimeout(t);},[flash]);
  useEffect(()=>{window.scrollTo({top:0,behavior:"instant"});main.current?.querySelector("h1")?.focus({preventScroll:true});},[page]);
  function go(to, remember=true){
    if(!Object.hasOwn(PAGES,to))return;
    if(page==="complete"&&to!=="complete")patch({askMood:false});
    if(remember&&to!==page)setNavStack(s=>[...s.slice(-24),page]);
    if(location.hash!==`#/${to}`)location.hash=`/${to}`;
    updatePage(to);
  }
  function activeView(){
    const current=navigation.current;
    return ()=>navigation.current===current&&route()===current.page;
  }
  function back(){
    if(pending.current)return;
    const to=navStack.at(-1)??"start";
    setNavStack(s=>s.slice(0,-1));go(to,false);
  }
  const preferred=()=>go(entry);
  const startNew=()=>{if(pending.current)return;writePendingLP(null);setDraft(fresh());setResult(emptyResult);setPick(null);go("record");};
  const goToday=(day="")=>{if(pending.current)return;setViewDay(day);go("today");};
  useEffect(()=>{
    if(page!=="today"||!viewRecord?.recordId||(viewRecord.recordId===draft.recordId&&!draft.saved))return;
    let active=true;
    request(`/records/${viewRecord.recordId}/lp`).then(lp=>{
      if(!active||!lp.confirmed_emotion)return;
      const mood=moodId(lp.confirmed_emotion), tracks=lpTracks(lp.songs,mood);
      setRecords(old=>old.map(record=>record===viewRecord?{
        ...record,input:lp.text,mood,response:lp.mood_after??record.response??"",queue:tracks,trackIds:tracks.map(track=>track.id),tracks:lpStates(lp.songs),
      }:record));
    }).catch(()=>{if(active)setFlash("서버에서 LP를 불러오지 못해 브라우저에 저장된 기록을 표시해요.");});
    return ()=>{active=false;};
  },[page,viewDay,viewRecord?.recordId,draft.recordId,draft.saved]);

  useEffect(()=>{
    if(!recovery)return;
    const isCurrent=activeView();
    let active=true;
    const path=`/records/${recovery.recordId}`;
    Promise.all([request(`${path}/lp`),request(`${path}/post-listening`)]).then(([lp,state])=>{
      if(!active||!isCurrent())return;
      const mood=moodId(lp.confirmed_emotion);
      if(!mood||(!state.mood_asked_at&&state.mood_after==null)){
        writePendingLP(null);
        setRecovery(null);
        return;
      }
      const destination=moodDestination(state);
      const queue=lpTracks(lp.songs,mood), tracks=lpStates(lp.songs);
      reactionStates.current=tracks;
      setDraft({...fresh(),day:recovery.day,recordId:recovery.recordId,input:lp.text,mood,queue,tracks,
        response:state.mood_after??recovery.response??"",askMood:destination==="complete",
        engrave:queue.filter(track=>tracks[track.id]?.liked).map(track=>track.id)});
      setRecovery(null);
      go(destination,false);
    }).catch(error=>{
      if(!active||!isCurrent())return;
      if(error.status===404){
        writePendingLP(null);
        setRecovery(null);
      }else setRecoveryError("저장한 기분을 불러오지 못했어요. 다시 시도해주세요.");
    });
    return ()=>{active=false;};
  },[recovery]);

  useEffect(()=>{
    if(recovery&&!["react","complete","engrave"].includes(page))setRecovery(null);
  },[page,recovery]);

  async function run(work,onError){
    return runAfterReactions(pending,reactions,work,error=>{
      const message=error.name==="TimeoutError"?"서버 응답이 늦어지고 있어요. 다시 시도해주세요."
        :error instanceof TypeError?"서버에 연결할 수 없어요. 백엔드 실행 상태를 확인해주세요.":error.message;
      onError(message);
    },setBusy);
  }
  const confirmReplacement=()=>draft.replacing||!todaysRecord||window.confirm("오늘 저장한 기록을 지금 내용으로 바꿀까요?");

  async function saveReaction(id,action){
    const track=queue.find(song=>song.id===id);
    if(!track)return;
    const previous=reactionStates.current[id]??{};
    if(action==="skip"&&(previous.completed||previous.skipped))return;
    if(action==="finish"&&previous.completed)return;
    const next=nextTrackState(previous,action);
    if(!draft.demo){
      const body=action==="finish"?{is_skipped:false,is_completed:true}
        :{is_liked:next.liked,is_skipped:next.skipped};
      try{
        const saved=await request(`/records/${draft.recordId}/songs/${track.order}`,"PATCH",body);
        reactionStates.current={...reactionStates.current,[id]:songState(saved)};
      }catch(error){
        if(error.status!==409)throw error;
        const lp=await request(`/records/${draft.recordId}/lp`);
        reactionStates.current=lpStates(lp.songs);
      }
    }else{
      reactionStates.current={...reactionStates.current,[id]:next};
    }
    const tracks=reactionStates.current;
    setDraft(old=>old.queue===queue?{...old,tracks,engrave:old.engrave.filter(key=>tracks[key]?.liked)}:old);
  }
  async function saveCompletion(id){
    await saveReaction(id,"finish");
    if(!reactionStates.current[id]?.completed)throw new Error("완청 기록을 저장하지 못했어요. 감상 마치기를 눌러 다시 시도해주세요.");
    unsavedCompletions.current.delete(id);
  }
  function setReaction(id,action){
    if(pending.current)return;
    if(action==="finish"&&!queueCompletion(unsavedCompletions.current,id,reactionStates.current[id]?.completed))return;
    reactions.current=reactions.current.then(()=>action==="finish"?saveCompletion(id):saveReaction(id,action))
      .catch(()=>setFlash(action==="finish"?"완청 기록을 저장하지 못했어요. 감상 마치기를 누르면 다시 저장해요.":"곡 반응을 저장하지 못했어요. 다시 시도해주세요."));
  }
  function analyze(words,kind,isDemo=false){
    if(pending.current)return;
    const localResult=classify(words);
    setPick(null);
    if(localResult.kind==="risk"){go("risk");return;}
    if(isDemo){
      setDraft({...fresh(),input:words,mode:kind,demo:true});
      setResult(localResult);
      go(localResult.kind);
      return;
    }
    if(!confirmReplacement())return;
    setDraft({...fresh(),input:words,mode:kind,replacing:true});
    go("loading");
    return run(async()=>{
      const body={text:words.trim()};
      let recordId, output;
      try{
        const data=await request("/records/analyze","POST",body);
        recordId=data.record_id;
        output=analysisResult(data);
      }catch(error){
        if(error.status!==503)throw error;
        const record=await request("/records","POST",body);
        recordId=record.record_id;
        output=emptyResult;
        setFlash("자동 분석을 사용할 수 없어 감정을 직접 선택해주세요.");
      }
      patch({recordId});
      setResult(output);
      go(output.kind,false);
    },failed);
  }
  function accept(id){
    if(!draft.demo&&classify(draft.input).kind==="risk"){go("risk");return;}
    if(pending.current||(!draft.demo&&!draft.recordId&&!confirmReplacement()))return;
    return run(async()=>{
      let recordId=draft.recordId, tracks={}, songs=recommend(id);
      if(!draft.demo){
        if(!recordId||draft.saved){
          const record=await request("/records","POST",{text:draft.input.trim()});
          recordId=record.record_id;
          patch({recordId,replacing:true,saved:false});
        }
        await request("/recommendations","POST",{record_id:recordId,confirmed_emotion:moodInfo(id).label});
        const lp=await request(`/records/${recordId}/lp`);
        songs=lpTracks(lp.songs,id);
        tracks=lpStates(lp.songs);
      }
      reactionStates.current=tracks;
      unsavedCompletions.current.clear();
      setCompletionSaveFailed(false);
      if(!draft.demo)writePendingLP(null);
      patch({mood:id,queue:songs,tracks,response:"",askMood:false,engrave:[]});
      setIndex(0);
      go("recommend");
      // 이유 한 줄은 기다리지 않음: 단계 이름이 먼저 보이고, 응답이 오면 그 칸만 바꿈
      const seq=++reasonSeq.current;
      if(!draft.demo)request(`/records/${recordId}/reasons`,"POST").then(data=>{
        const action=reasonsAction(latestDraft.current,recordId,route(),data,seq,reasonSeq.current);
        if(action?.type==="risk")go("risk");
        else if(action)setDraft(old=>{const q=applyReasons(old.queue,recordId,old.recordId,data);return q?{...old,queue:q}:old;});
      }).catch(()=>{});
    },setFlash);
  }
  function manual(){if(classify(draft.input).kind==="risk"){go("risk");return;}setPick(null);go("manual");}
  function failed(text){setMessage(text);go("failure");}
  // 녹음 → 서버 받아쓰기 + 감정 분석 + 저장 (POST /records/voice). 응답 형식은 /records/analyze와 같음
  function analyzeVoice(blob){
    if(pending.current||!confirmReplacement())return false; // 보내지 않음 → 녹음 화면이 이번 녹음을 버리고 대기로
    setPick(null);
    go("loading");
    return run(async()=>{
      const data=await request("/records/voice","POST",blob);
      // ponytail: 위험 문장 검사가 서버 저장 뒤에 일어남. 글 경로처럼 앞에서 막으려면 받아쓰기 전용 API 필요
      if(classify(data.text).kind==="risk"){go("risk",false);return;}
      const output=analysisResult(data);
      setDraft({...fresh(),input:data.text,mode:"voice",replacing:true,recordId:data.record_id});
      setResult(output);
      setFlash(`받아쓴 글: ${data.text}`);
      go(output.kind,false);
    },failed);
  }
  function selectTrack(i){setIndex(i);go("player");}
  function review(){go("react");}
  function prepareLP(response){
    patch({response,askMood:false,engrave:queue.filter(t=>reactionStates.current[t.id]?.liked).map(t=>t.id)});
    go("engrave",page!=="complete");
  }
  function persist(ids,next){
    if(!draft.mood)return;
    if(draft.demo&&todaysRecord&&!window.confirm("오늘 저장한 기록을 시연 내용으로 바꿀까요?"))return;
    return run(async()=>{
      const day=draft.day??today;
      let tracks=reactionStates.current, input=draft.input, mood=draft.mood, songs=queue, response;
      if(!draft.demo){
        const path=`/records/${draft.recordId}`;
        await request(`${path}/engrave`,"POST",{recommend_orders:queue.filter(t=>ids.includes(t.id)).map(t=>t.order)});
        const lp=await request(`${path}/lp`);
        input=lp.text;
        mood=moodId(lp.confirmed_emotion);
        response=lp.mood_after??"";
        songs=lpTracks(lp.songs,mood);
        tracks=lpStates(lp.songs);
        ids=songs.filter(t=>tracks[t.id].engraved).map(t=>t.id);
        reactionStates.current=tracks;
      }
      const record={...makeRecord({...draft,input,mood,day,queue:songs,tracks,engrave:ids}),queue:songs,recordId:draft.recordId};
      if(!draft.demo)record.response=response;
      const nextRecords=[record,...records.filter(r=>r.day!==day)];
      setRecords(nextRecords);
      patch({tracks,saved:true});
      setViewDay(day);
      if(!write(STORE,nextRecords))setFlash("이 브라우저에 기록 목록을 저장할 수 없어요.");
      else{
        if(readPendingLP()?.recordId===draft.recordId)writePendingLP(null);
        if(next==="today")setFlash("LP판에 기록했어요.");
      }
      go(next);
    },setFlash);
  }
  function rememberMood(response){
    writePendingLP({recordId:draft.recordId,day:draft.day??today,response});
  }
  function finishReaction(continueWithSaved=false){
    const isCurrent=activeView();
    return run(async()=>{
      if(!isCurrent())return;
      if(draft.demo){
        if(canReview(draft.mood,queue.map(t=>t.id),reactionStates.current)){
          patch({askMood:true});
          go("complete");
        }else prepareLP("");
        return;
      }
      // run이 기존 곡별 PATCH를 모두 기다린 뒤에만 실패한 완청을 다시 보냅니다.
      if(!continueWithSaved){
        await retryCompletions(unsavedCompletions.current,saveCompletion,isCurrent);
        if(!isCurrent())return;
        if(unsavedCompletions.current.size){
          setCompletionSaveFailed(true);
          setFlash("일부 완청 기록을 저장하지 못했어요.");
          return;
        }
      }
      const path=`/records/${draft.recordId}`;
      const state=await request(`${path}/flow/end`,"POST");
      if(!isCurrent())return;
      const lp=await request(`${path}/lp`);
      if(!isCurrent())return;
      reactionStates.current=lpStates(lp.songs);
      patch({tracks:reactionStates.current});
      let question=state;
      if(state.should_ask_mood){
        try{
          question=await request(`${path}/mood-question`,"POST");
        }catch(error){
          if(!isCurrent())return;
          if(error.status!==409)throw error;
          question=await request(`${path}/post-listening`);
        }
      }
      if(!isCurrent())return;
      setCompletionSaveFailed(false);
      if(moodDestination(question)==="complete"){
        const previous=readPendingLP();
        const response=previous?.recordId===draft.recordId?previous.response??"":"";
        rememberMood(response);
        patch({askMood:true,response});
        go("complete");
      }else{
        if(question.mood_after!=null)rememberMood(question.mood_after);
        prepareLP(question.mood_after??"");
      }
    },message=>{if(isCurrent())setFlash(message);});
  }
  function submitMood(response){
    if(!draft.askMood||!response)return;
    if(draft.demo){prepareLP(response);return;}
    const isCurrent=activeView();
    return run(async()=>{
      if(!isCurrent())return;
      const path=`/records/${draft.recordId}`;
      rememberMood(response);
      patch({response});
      const saved=await saveMoodAnswer(request,path,response);
      if(isCurrent())prepareLP(saved.mood_after);
    },message=>{if(isCurrent())setFlash(message);});
  }
  function demoCase(kind){
    const map={high:"오늘은 행복하고 뿌듯하고 즐거웠어요.",medium:"오늘은 뿌듯했지만 한편으로 외롭고 속상했어요.",low:"오늘 하루가 지났어요."};
    if(kind==="risk"){go("risk");return;}
    if(kind==="failure"){failed("시연용 분석 실패 상태예요. 실제 서버에는 연결되어 있지 않아요.");return;}
    if(kind==="error"){setMessage("시연용 오류 상태예요. 실제 서버에는 연결되어 있지 않아요.");go("error");return;}
    analyze(map[kind],"text",true);
  }
  useEffect(()=>{
    if(recovery)return;
    if(page==="complete"&&!draft.askMood){
      const saved=readPendingLP();
      if(saved){setRecoveryError("");setRecovery(saved);return;}
    }
    if(["recommend","player","react","complete","engrave"].includes(page)&&!draft.mood)go("record",false);
    if(page==="voice"&&!agreed)go("consent",false);
    if(page==="complete"&&draft.mood&&!draft.askMood)go("react",false);
    if(page!=="complete"&&draft.askMood)patch({askMood:false});
  },[page,draft.mood,draft.askMood,agreed,recovery]);
  const savePref=to=>{setEntry(to);if(write(PREF,to))setFlash("첫 화면 설정을 저장했어요.");else setFlash("설정을 이 브라우저에 저장할 수 없어요.");};
  const nextParticipant=()=>{
    if(!window.confirm("지금 기록이 이 기기에서 지워져요. 다음 참여자로 시작할까요?"))return;
    try{startNextParticipant();}catch{setFlash("이 브라우저에서는 참여자를 바꿀 수 없어요.");return;}
    location.hash="#/me";location.reload(); // 화면 상태를 지운 저장소에서 새로 읽음
  };
  const clearAll=()=>{
    if(!window.confirm("이 브라우저에 저장한 MoodWave의 모든 기록을 지울까요?"))return;
    if(!write(STORE,[])){setFlash("기록을 지우지 못했어요.");return;}
    setRecords([]);setDraft(fresh());setFlash("이 브라우저의 기록을 지웠어요.");
  };
  const optionalVoice=()=>{patch({mode:"voice"});go(agreed?"voice":"consent");};

  function screen(){
    if(recovery&&["react","complete","engrave"].includes(page))return <>
      <Heading title="저장한 감상 후 기분 불러오기"/>
      {recoveryError?<><Notice>{recoveryError}</Notice><div className="actions">
        <Btn onClick={()=>{setRecoveryError("");setRecovery({...recovery});}}>다시 시도</Btn>
        <Btn variant="secondary" onClick={()=>{setRecovery(null);go("record",false);}}>기록 화면으로 돌아가기</Btn>
      </div></>
        :<p role="status">서버에서 LP 기록을 확인하고 있어요.</p>}
    </>;
    switch(page){
      case "audio-library":return <AudioLibrary/>;
      case "start":return <><div className="start-kicker"><span/> MOOD JOURNAL</div><Heading title="오늘의 마음을 음악으로" desc="하루를 짧게 기록하고, 어울리는 음악을 LP판에 남겨보세요."/><LP/><div className="actions"><Btn onClick={preferred}>기록 시작 <Icon name="arrow" size={17}/></Btn><Btn variant="secondary" onClick={()=>go("history")}>지난 기록 살펴보기</Btn><Btn variant="secondary" onClick={()=>go("audio-library")}>등록 음원 듣기</Btn></div><div className="demo-legal"><button className="link" onClick={()=>go("login")}>로그인 화면 보기</button><span>·</span><button className="link" onClick={()=>go("signup")}>회원가입 화면 보기</button></div><Notice>테스트 계정으로 기록을 저장하는 시제품이에요.</Notice></>;
      case "login":case "signup":return <><Heading title={PAGES[page][0]} desc="화면 미리보기 · 실제 계정 인증은 연결하지 않았어요."/><div className="surface auth-demo"><label className="field">아이디<input value="moodwave-demo" readOnly/></label><label className="field">비밀번호<input value="demo-only" type="password" readOnly/></label><Notice>예시 정보만 표시해요. 실제 아이디나 비밀번호를 입력하지 않아요.</Notice></div><div className="actions"><Btn onClick={preferred}>시연 모드로 계속하기</Btn><Btn variant="secondary" onClick={()=>go(page==="login"?"signup":"login")}>{page==="login"?"회원가입 화면 보기":"로그인 화면 보기"}</Btn></div></>;
      case "record":return <><Heading title="오늘의 기록" desc="오늘의 마음을 한 문장으로 남겨도 좋아요."/><form onSubmit={e=>{e.preventDefault();if(draft.input.trim())analyze(draft.input,"text");}}><div className="surface"><label className="field">오늘 있었던 일<textarea value={draft.input} maxLength={300} rows={6} onChange={e=>patch({input:e.target.value,mode:"text",recordId:null,demo:false})} placeholder="오늘은 어떤 기분이었나요?"/></label><div className="field-meta"><span>기록을 완료하면 입력한 글이 서버로 전송돼요.</span><span>{draft.input.length} / 300</span></div></div><div className="actions"><button className="btn primary" disabled={!draft.input.trim()} type="submit">기록 완료 <Icon name="arrow" size={16}/></button><Btn variant="secondary" onClick={optionalVoice}><Icon name="mic" size={17}/> 음성으로 기록</Btn><button type="button" className="link" onClick={manual}>감정 직접 선택</button></div></form></>;
      case "consent":return <><Heading title="음성 녹음 동의" desc="녹음을 시작하기 전에 확인해주세요."/><div className="surface consent"><Icon name="shield" size={25}/><h2>원본 음성은 저장하지 않아요</h2><p>녹음은 자동 받아쓰기를 위해 서버로 한 번 보내고, 서버는 받아쓴 글만 저장해요. 녹음을 종료하거나 화면에서 나가면 마이크를 닫아요.</p><label className="checkline"><input type="checkbox" checked={agreed} onChange={e=>setAgreed(e.target.checked)}/> 안내를 읽고 마이크 사용에 동의해요.</label></div><div className="actions"><Btn disabled={!agreed} onClick={()=>go("voice")}>녹음 화면으로</Btn><Btn variant="secondary" onClick={()=>go("record")}>글로 기록하기</Btn></div></>;
      case "voice":return <Voice onAnalyze={analyzeVoice} onFail={failed} onBack={()=>go("record")}/>;
      case "loading":return <><Heading title="감정 분석 중" desc="오늘의 마음을 살펴보고 있어요."/><LP playing/><div className="dots" role="status" aria-label="분석 중"><i/><i/><i/></div><Notice>서버에서 입력한 글을 분석하고 있어요.</Notice></>;
      case "high":return <><Heading title={PAGES.high[0]}/><LP/><div className="analysis-result"><small>시제품이 짐작한 감정</small><strong>{moodInfo(result.candidates[0]).label}</strong></div><div className="actions"><Btn onClick={()=>accept(result.candidates[0]??"steady")}>맞아요</Btn><Btn variant="secondary" onClick={manual}>다른 감정이에요</Btn></div></>;
      case "medium":return <><Heading title={PAGES.medium[0]} desc="기록에서 가까운 두 가지 감정을 골랐어요."/><LP/><MoodSelect ids={result.candidates.length?result.candidates:["steady","low"]} stack onPick={accept}/><div className="actions"><button className="link" onClick={manual}>다른 감정 선택</button></div></>;
      case "low":case "manual":return <><Heading title={PAGES[page][0]} desc={page==="low"?"기록만으로는 판단하기 어려워요. 가까운 감정을 골라주세요.":"지금 마음에 가까운 감정을 하나 골라주세요."}/><LP/><MoodSelect active={pick} onPick={id=>page==="low"?accept(id):setPick(id)}/>{page==="manual"&&<div className="actions"><Btn disabled={!pick} onClick={()=>accept(pick)}>선택 완료</Btn></div>}</>;
      case "recommend":return <><Heading title="오늘의 추천 음악" desc="확정한 감정에 맞춰 세 곡을 골랐어요."/><div className="center mood-row"><span>확정 감정</span><Mood id={draft.mood}/></div><div className="cards">{queue.map((t,i)=><div key={t.id} className="track-card"><Cover theme={t.theme}/><div className="track-body"><strong>{t.title}</strong><small>{t.artist}</small><p>{t.reason}</p></div><button className={`icon queue-like ${draft.tracks[t.id]?.liked?"liked":""}`} aria-label={`${t.title} ${draft.tracks[t.id]?.liked?"좋아요 취소":"좋아요"}`} aria-pressed={!!draft.tracks[t.id]?.liked} onClick={()=>setReaction(t.id,"like")}><Icon name="heart" size={17} fill={draft.tracks[t.id]?.liked?"currentColor":"none"}/></button><button className="icon play" aria-label={`${t.title} 재생 화면`} onClick={()=>selectTrack(i)}><Icon name="play" size={17}/></button></div>)}</div><div className="actions"><Btn variant="secondary" onClick={review}>곡에 반응 남기기</Btn></div><Notice>추천 목록은 서버에서 가져와요. 재생에는 직접 합성한 시연 음원을 사용해요.</Notice>{!draft.demo&&<Notice>곡마다 이유 한 줄은 Claude API(Anthropic)가 만들어요. 오늘 고른 감정, 곡의 밝기·에너지, 최근 7일 감정만 보내고 일기 글은 보내지 않아요.</Notice>}</>;
      case "player":return <Player queue={queue} index={index} onIndex={setIndex} onAction={setReaction} onReview={review}/>;
      case "react":return <><Heading title="곡에 반응 남기기" desc="곡마다 좋았던 순간을 표시해보세요."/><ReviewRows items={queue} states={draft.tracks} onAction={setReaction}/><Notice>완청 {count} / 3곡</Notice>
        {completionSaveFailed&&<Notice>일부 완청을 저장하지 못했어요. 다시 시도하거나 저장된 기록으로 계속할 수 있어요.</Notice>}
        <div className="actions"><Btn disabled={busy} onClick={()=>finishReaction()}>{completionSaveFailed?"완청 저장 다시 시도":"감상 마치기"}</Btn>
          {completionSaveFailed&&<Btn disabled={busy} variant="secondary" onClick={()=>finishReaction(true)}>저장된 기록으로 계속</Btn>}
          <Btn disabled={busy} variant="secondary" onClick={()=>go("recommend")}>추천곡으로 돌아가기</Btn></div></>;
      case "complete":return draft.askMood&&<><Heading title="감상 완료"/><LP done/><p className="counter">{count}곡 감상 완료</p><div className="heading compact"><h2>음악을 듣고 난 지금 기분은 어떤가요?</h2></div><div className="actions">{RESPONSES.map(x=><Btn key={x} disabled={busy} variant={draft.response===x?"primary":"secondary"} aria-pressed={draft.response===x} onClick={()=>{if(!draft.demo)rememberMood(x);patch({response:x});}}>{x}</Btn>)}<Btn disabled={busy||!draft.response} onClick={()=>submitMood(draft.response)}>계속하기</Btn><button className="link" disabled={busy} onClick={()=>submitMood(NO_MOOD_RESPONSE)}>건너뛰기</button></div></>;
      case "engrave":return <><Heading title="LP 새김 확인" desc={liked.length?"좋아요한 곡 중 LP판에 남길 곡을 골라주세요.":"좋아요한 곡이 없어요. 감정과 기록만 남길 수 있어요."}/><LP/>{liked.length>0&&<div className="surface mini-list">{liked.map(t=><label className="checkline" key={t.id}><input type="checkbox" checked={draft.engrave.includes(t.id)} onChange={e=>setDraft(d=>({...d,engrave:e.target.checked?[...d.engrave,t.id]:d.engrave.filter(id=>id!==t.id)}))}/>{t.title}</label>)}</div>}<Notice>서버에 기록을 저장하고 이 브라우저에서 날짜별로 볼 수 있어요.</Notice><div className="actions"><Btn disabled={!draft.engrave.length} onClick={()=>persist(draft.engrave,"engraved")}>LP판에 새기기</Btn><Btn variant="secondary" onClick={()=>persist([],"today")}>기록만 저장하기</Btn><button className="link" onClick={back}>돌아가기</button></div></>;
      case "engraved":return <><Heading title="LP 새김 완료" desc={`${Object.values(viewRecord?.tracks??{}).filter(t=>t.engraved).length}곡을 LP판에 담았어요.`}/><LP done/><div className="surface mini-list">{(viewRecord?.trackIds??[]).filter(id=>viewRecord?.tracks[id]?.engraved).map(id=><p key={id}><Icon name="check" size={16}/>{savedTrack(viewRecord,id)?.title}</p>)}</div><div className="actions"><Btn onClick={()=>goToday(viewDay||today)}>LP판 보기</Btn></div></>;
      case "today":return <><Heading title={viewDay&&viewDay!==today?"그날의 LP판":"오늘의 LP판"} desc={dateLabel(viewDay||today)}/>{viewRecord?<div className="surface daily-card"><div className="daily-top"><LP small/><div><Mood id={viewRecord.mood}/><p>{viewRecord.input||"감정만 기록했어요."}</p></div></div>{viewRecord.response&&<p className="daily-response">감상 후 기분 · {viewRecord.response}</p>}<h2>오늘의 추천 음악</h2>{(viewRecord.trackIds??[]).map(id=>{const t=savedTrack(viewRecord,id),s=viewRecord.tracks[id]??{};return t&&<div className="saved-track" key={id}><Cover theme={t.theme}/><div><strong>{t.title}</strong><small>{[s.liked&&"좋아요",s.skipped&&"건너뜀",s.completed&&"완청",s.engraved&&"새김"].filter(Boolean).join(" · ")||"반응 없음"}</small></div></div>;})}</div>:<div className="empty"><LP small/><strong>아직 저장한 기록이 없어요.</strong><p>기록을 마치면 여기에 LP판이 쌓여요.</p></div>}<div className="actions"><Btn variant="secondary" onClick={()=>go("history")}>지난 기록 보기</Btn>{!viewRecord&&<Btn onClick={startNew}>오늘을 기록하기</Btn>}</div></>;
      case "history":return <><Heading title="날짜별 기록" desc="기억하고 싶은 날의 감정과 음악을 다시 만나요."/><MonthSelect month={month} onChange={setMonth}/>{thisMonth.length?<div className="cards">{thisMonth.map(r=><button key={r.day} className="history-row" onClick={()=>goToday(r.day)}><LP small/><span><strong>{dateLabel(r.day)}</strong><Mood id={r.mood}/><small>{savedTrack(r,(r.trackIds??[]).find(id=>r.tracks[id]?.engraved)??r.trackIds?.[0])?.title??"감정 기록"}</small></span><Icon name="next"/></button>)}</div>:<div className="empty"><p>이 달에는 저장한 기록이 없어요.</p></div>}<div className="actions"><Btn onClick={startNew}>오늘을 기록하기</Btn></div></>;
      case "me":return <><Heading title="마이페이지" desc="기록과 나에게 맞는 시작 화면을 관리해요."/><div className="surface"><h2>기록 보기</h2><div className="menu-list">{[["monthly-mood","월간 감정 분석"],["monthly-music","월간 음악 취향"],["daytype","Day Type"],["history","날짜별 기록"]].map(([to,label])=><button key={to} onClick={()=>go(to)}>{label}<Icon name="next" size={16}/></button>)}</div></div><div className="surface settings"><h2>기록 시작 버튼을 누르면</h2><label className="checkline"><input type="radio" name="entry" checked={entry==="record"} onChange={()=>savePref("record")}/> 기록 입력 먼저 보기</label><label className="checkline"><input type="radio" name="entry" checked={entry==="history"} onChange={()=>savePref("history")}/> 지난 기록 먼저 보기</label></div><div className="surface"><h2>평가 참여자</h2>{readParticipant()?<p>참여자 코드 <strong className="participant-code">{readParticipant()}</strong> · 설문에 이 코드를 적어 주세요.</p>:<p className="small">평가에 참여할 때 눌러 주세요. 이 기기의 기록을 지우고 새 참여자 코드를 만들어요.</p>}<Btn variant="secondary" onClick={nextParticipant}>다음 참여자로 시작</Btn></div><div className="surface"><h2>이 브라우저의 기록</h2><p className="small">여기서 지우면 이 브라우저의 목록만 삭제돼요. 서버에 저장된 기록은 별도로 남아요.</p><button className="link danger" onClick={clearAll}>로컬 기록 모두 지우기</button></div><div className="actions"><Btn variant="secondary" onClick={()=>setDemo(!demo)}>{demo?"시연 메뉴 닫기":"시연 메뉴 보기"}</Btn></div>{demo&&<div className="surface demo-cases"><h2>테스트 시나리오</h2>{[["high","높은 확신"],["medium","중간 확신"],["low","낮은 확신"],["failure","분석 실패"],["risk","도움 안내"],["error","오류"]].map(([id,label])=><Btn key={id} variant="secondary" onClick={()=>demoCase(id)}>{label}</Btn>)}</div>}</>;
      case "monthly-mood":{
        const stats=monthlyMood(thisMonth),max=Math.max(1,...stats.map(x=>x.count)),mainMood=[...stats].sort((a,b)=>b.count-a.count)[0];
        return <><Heading title="월간 감정 분석" desc="이 브라우저에 저장한 확정 감정을 모았어요."/><MonthSelect month={month} onChange={setMonth}/>{thisMonth.length?<div className="surface"><div className="month-character"><span style={{background:mainMood.color}}>{mainMood.symbol}</span><p>가장 많이 기록한 감정</p><strong>{mainMood.label}</strong></div>{stats.map(m=><div key={m.id} className="stats"><Mood id={m.id}/><div><i style={{width:`${m.count/max*100}%`,background:m.hue}}/></div><span>{m.count}일</span></div>)}</div>:<div className="empty">이 달에는 감정 기록이 없어요.</div>}<Notice>감정 분포를 보여주는 요약이에요. 성격이나 건강 상태를 판단하지 않아요.</Notice></>;
      }
      case "monthly-music":{const list=monthlyMusic(thisMonth);return <><Heading title="월간 음악 취향" desc="내가 좋아요하거나 끝까지 들은 시연 곡의 기록이에요."/><MonthSelect month={month} onChange={setMonth}/>{list.length?<div className="cards">{list.map(t=><div className="track-card" key={t.id}><Cover theme={t.theme}/><div className="track-body"><strong>{t.title}</strong><small>완청 {t.completed} · 좋아요 {t.liked} · 새김 {t.engraved}</small></div></div>)}</div>:<div className="empty">이 달에는 감상 기록이 없어요.</div>}</>;}
      case "daytype":{const summary=dayType(todaysRecord?.mood);return <><Heading title="Day Type" desc="오늘 남긴 기록으로 하루를 돌아봐요."/><LP/>{summary?<div className="surface center"><h2>{summary.title}</h2><Mood id={todaysRecord.mood}/><p>{summary.copy}</p><small>직접 확정한 감정에 맞춘 시연용 문구예요.</small></div>:<div className="empty">오늘의 LP판을 저장하면 이곳에서 볼 수 있어요.</div>}<div className="actions"><Btn variant="secondary" onClick={()=>goToday(today)}>오늘의 LP판 보기</Btn></div></>;}
      case "failure":return <><Heading title={PAGES.failure[0]} desc={message||"지금 마음은 직접 고를 수 있어요."}/><div className="actions"><Btn onClick={manual}>감정 직접 선택</Btn><Btn variant="secondary" onClick={()=>go("record")}>글로 다시 기록하기</Btn></div></>;
      case "risk":return <><Heading title="도움을 받을 수 있어요" desc="지금 힘들다면 혼자 감당하지 않아도 돼요."/><div className="surface"><h2>한국 자살예방상담전화</h2><p>109에서 24시간 상담을 받을 수 있어요. 지금 바로 안전을 지키기 어렵다면 119에 연락하세요.</p><div className="actions"><a className="btn primary" href="tel:109">109에 전화하기</a><a className="btn secondary" href="https://www.129.go.kr/109" target="_blank" rel="noreferrer">공식 상담 안내 보기</a></div></div><Notice>이 화면은 일부 문구를 확인하는 안내 시연이에요. 앱이 위기 여부를 진단하거나 상담을 연결해주지는 않아요.</Notice><div className="actions"><Btn variant="secondary" onClick={startNew}>기록 화면으로</Btn></div></>;
      case "error":return <><Heading title="문제가 발생했어요" desc={message||"현재 화면을 다시 열어주세요."}/><div className="actions"><Btn onClick={()=>{const p=navStack.at(-1);if(p&&p!=="error")back();else go("record");}}>다시 시도</Btn><Btn variant="secondary" onClick={()=>go("start")}>처음으로</Btn></div></>;
      default:return null;
    }
  }
  const noTabs=["start","login","signup","risk","audio-library"].includes(page);
  const pendingMood=!draft.demo&&!recovery&&["record","history","today"].includes(page)?readPendingLP():null;
  const active=page==="today"||page==="engrave"||page==="engraved"?"today":page==="history"?"history":PAGES[page]?.[1]==="나의 기록"?"me":"record";
  return <div className="layout">
    <aside className="desktop-intro" aria-hidden="true"><span className="series">MOODWAVE / LOCAL DEMO</span><h2>한 장의 LP판에<br/>남기는 하루.</h2><p>감정 기록에서 음악 감상까지, 오늘의 마음을 다시 들여다보는 작은 공간.</p><LP/></aside>
    <div className="phone">
      <header className="header"><div className="header-side">{page!=="start"&&<button className="icon back" aria-label="이전 화면" onClick={back}><Icon name="back"/></button>}</div><button className="brand" onClick={()=>{if(!pending.current)go("start");}} aria-label="MOOD WAVE 시작 화면">MOOD WAVE<i/></button><div className="header-side right"><span className="demo-pill">DEMO</span></div></header>
      <main ref={main} className={`screen page-${page}`} inert={busy?"":undefined} aria-busy={busy}>
        {pendingMood&&<Btn variant="secondary" onClick={()=>{setRecoveryError("");setRecovery(pendingMood);go("complete");}}>감상 후 기록 이어서 하기</Btn>}
        {screen()}
      </main>
      {!noTabs&&<nav className="bottom-nav" aria-label="주 메뉴">{TABS.map(([id,label,ico])=><button key={id} aria-current={active===id?"page":undefined} onClick={()=>{if(!pending.current)(id==="today"?goToday():go(id));}}><Icon name={ico}/><span>{label}</span></button>)}</nav>}
      {flash&&<div className="toast" role="status">{flash}</div>}
    </div>
  </div>;
}
