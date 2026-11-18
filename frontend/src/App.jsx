import React, {useEffect, useRef, useState} from "react";
import {MOODS, moodInfo, classify, recommend, getTrack, RESPONSES, canReview, nextTrackState, localDay, shiftMonth, monthLabel, dateLabel, forMonth, monthlyMood, monthlyMusic, makeRecord, dayType} from "./domain.js";

const PAGES={
  start:["시작","시작"],
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
const read=(key, fallback)=>{try{return JSON.parse(localStorage.getItem(key)??"null")??fallback;}catch{return fallback;}};
const write=(key,data)=>{try{localStorage.setItem(key,JSON.stringify(data));return true;}catch{return false;}};
const route=()=>{const key=location.hash.replace(/^#\/?/,"").split("?")[0];return Object.hasOwn(PAGES,key)?key:"start";};
const fresh=()=>({input:"",mood:null,mode:"text",response:"",tracks:{},engrave:[]});
const emptyResult={kind:"low",candidates:[]};
const reduceMotion=()=>window.matchMedia("(prefers-reduced-motion: reduce)").matches;

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
    if (a && auto.current) {auto.current=false;a.play().catch(()=>setIssue("재생 버튼을 눌러 들을 수 있어요."));}
  },[trackId]);
  if(!track)return null;
  const toggle=()=>{const a=audio.current;if(!a)return;if(!a.paused){a.pause();return;}a.play().catch(()=>setIssue("재생을 시작하지 못했어요. 잠시 후 다시 눌러주세요."));};
  const move=(offset,skip=false)=>{if(skip)onAction(trackId,"skip");const next=index+offset;if(next<0||next>=queue.length){onReview();return;}auto.current=!!audio.current&&!audio.current.paused;onIndex(next);};
  const end=()=>{setPlaying(false);onAction(trackId,"finish");};
  const clock=x=>`${Math.floor(x/60)}:${String(Math.floor(x%60)).padStart(2,"0")}`;
  return <><Heading title="음악 감상" desc="직접 합성한 짧은 시연 음원이에요."/><LP playing={playing}/><div className="track-center"><h2>{track.title}</h2><p>{track.artist}</p></div>
    <audio ref={audio} src={`${import.meta.env.BASE_URL}audio/${track.id}.wav`} preload="metadata" onPlay={()=>setPlaying(true)} onPause={()=>setPlaying(false)} onLoadedMetadata={e=>{if(Number.isFinite(e.currentTarget.duration))setDuration(e.currentTarget.duration);}} onTimeUpdate={e=>setTime(e.currentTarget.currentTime)} onEnded={end} onError={()=>setIssue("시연 음원을 불러오지 못했어요.")}/>
    <label className="seek"><span className="sr-only">재생 위치</span><input type="range" aria-label="재생 위치" min="0" max={duration||16} step=".1" value={Math.min(time,duration)} onChange={e=>{if(audio.current)audio.current.currentTime=Number(e.target.value);setTime(Number(e.target.value));}}/><span><span>{clock(time)}</span><span>{clock(duration)}</span></span></label>
    <div className="player-actions"><button className="icon" aria-label="이전 곡" disabled={index===0} onClick={()=>move(-1)}><Icon name="back"/></button><button className="icon play-main" aria-label={playing?"일시정지":"재생"} onClick={toggle}><Icon name={playing?"pause":"play"} size={25}/></button><button className="icon" aria-label="다음 곡" disabled={index===queue.length-1} onClick={()=>move(1)}><Icon name="next"/></button></div>
    <p className="counter">{index+1} / {queue.length}</p>{issue&&<Notice kind="warn">{issue}</Notice>}
    <div className="actions"><Btn variant="secondary" onClick={onReview}>곡에 반응 남기기</Btn><button className="link" onClick={()=>move(1,true)}>이 곡 건너뛰기</button></div></>;
}
function Voice({onAnalyze,onFail,onBack}){
  const stream=useRef(null),rec=useRef(null),timer=useRef(null),permission=useRef(null),alive=useRef(true);
  const [status,setStatus]=useState("idle"),[seconds,setSeconds]=useState(0),[words,setWords]=useState(""),[busy,setBusy]=useState(false);
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
      const recorder=new MediaRecorder(s);rec.current=recorder;
      // No dataavailable consumer: audio is intentionally discarded, never stored or sent.
      recorder.onstop=()=>{clearInterval(timer.current);stopStream();rec.current=null;if(alive.current)setStatus("done");};
      recorder.onerror=()=>{clearInterval(timer.current);stopStream();if(alive.current)onFail("녹음을 마치지 못했어요. 글이나 직접 선택으로 계속할 수 있어요.");};
      recorder.start();setStatus("recording");
      let i=0;timer.current=setInterval(()=>{i++;setSeconds(i);if(i>=15)stop();},1000);
    }catch{stopStream();if(alive.current)onFail("마이크 권한이 없거나 장치를 사용할 수 없어요. 글이나 직접 선택으로 계속할 수 있어요.");}
    finally{if(alive.current)setBusy(false);}
  };
  return <><Heading title="음성 녹음" desc="최대 15초 동안 말해볼 수 있어요."/><div className={`mic-stage ${status==="recording"?"live":""}`}><Icon name="mic" size={38}/><strong aria-live="polite">0:{String(seconds).padStart(2,"0")}</strong><span>{status==="recording"?"녹음 중":status==="done"?"녹음 종료 · 원본 미저장":"녹음 대기"}</span></div>
  {status==="done"&&<label className="field">말한 내용을 글로 남기고 싶다면<textarea maxLength={300} value={words} onChange={e=>setWords(e.target.value)} rows={3} placeholder="비워두면 감정을 직접 고를 수 있어요."/></label>}
  <Notice>마이크 녹음만 시연해요. 음성 분석·자동 받아쓰기는 연결하지 않았어요. 원본 음성은 저장하거나 전송하지 않아요.</Notice>
  <div className="actions">{status==="recording"?<Btn onClick={stop}>녹음 종료</Btn>:status==="done"?<><Btn onClick={()=>onAnalyze(words)}>기록 완료</Btn><Btn variant="secondary" disabled={busy} onClick={start}>다시 녹음하기</Btn></>:<Btn disabled={busy} onClick={start}>{busy?"권한 확인 중":"녹음 시작"}</Btn>}<button className="link" onClick={onBack}>글로 기록하기</button></div></>;
}

export default function App(){
  const [page,setPage]=useState(route),[navStack,setNavStack]=useState([]);
  const [entry,setEntry]=useState(()=>read(PREF,"record")==="history"?"history":"record");
  const [records,setRecords]=useState(()=>{const a=read(STORE,[]);return Array.isArray(a)?a.filter(r=>r&&typeof r.day==="string"):[];});
  const [draft,setDraft]=useState(fresh),[result,setResult]=useState(emptyResult),[pick,setPick]=useState(null);
  const [index,setIndex]=useState(0),[agreed,setAgreed]=useState(false),[message,setMessage]=useState(""),[flash,setFlash]=useState("");
  const [month,setMonth]=useState(()=>localDay().slice(0,7)),[viewDay,setViewDay]=useState(""),[demo,setDemo]=useState(false);
  const main=useRef(null),today=localDay(),queue=draft.mood?recommend(draft.mood):[],count=queue.filter(t=>draft.tracks[t.id]?.completed).length;
  const thisMonth=forMonth(records,month),todaysRecord=records.find(a=>a.day===today);
  const viewRecord=records.find(a=>a.day===(viewDay||today));
  const liked=queue.filter(t=>draft.tracks[t.id]?.liked);
  const patch=(p)=>setDraft(old=>({...old,...p}));
  useEffect(()=>{const h=()=>setPage(route());window.addEventListener("hashchange",h);return ()=>window.removeEventListener("hashchange",h);},[]);
  useEffect(()=>{if(!flash)return;const t=setTimeout(()=>setFlash(""),3700);return ()=>clearTimeout(t);},[flash]);
  useEffect(()=>{window.scrollTo({top:0,behavior:"instant"});main.current?.querySelector("h1")?.focus({preventScroll:true});},[page]);
  function go(to, remember=true){
    if(!Object.hasOwn(PAGES,to))return;
    if(remember&&to!==page)setNavStack(s=>[...s.slice(-24),page]);
    if(location.hash!==`#/${to}`)location.hash=`/${to}`;
    setPage(to);
  }
  function back(){
    const to=navStack.at(-1)??"start";
    setNavStack(s=>s.slice(0,-1));go(to,false);
  }
  const preferred=()=>go(entry);
  const startNew=()=>{setDraft(fresh());setResult(emptyResult);setPick(null);go("record");};
  const goToday=(day="")=>{setViewDay(day);go("today");};
  const setReaction=(id,a)=>setDraft(old=>{
    const updated=nextTrackState(old.tracks[id],a);
    return {...old,tracks:{...old.tracks,[id]:updated},engrave:updated.liked?old.engrave:old.engrave.filter(i=>i!==id)};
  });
  function analyze(words,kind){
    const output=classify(words);
    setPick(null);setResult(output);
    patch({input:words,mood:null,mode:kind,response:"",tracks:{},engrave:[]});
    go("loading");
  }
  function accept(id){patch({mood:id,tracks:{},response:"",engrave:[]});setIndex(0);go("recommend");}
  function manual(){if(classify(draft.input).kind==="risk"){go("risk");return;}setPick(null);go("manual");}
  function failed(text){setMessage(text);go("failure");}
  function selectTrack(i){setIndex(i);go("player");}
  function review(){go("react");}
  function prepareLP(){
    patch({engrave:liked.map(t=>t.id)});go("engrave");
  }
  function persist(ids,next){
    if(!draft.mood)return false;
    if(todaysRecord && !window.confirm("오늘 저장한 기록을 지금 내용으로 바꿀까요?"))return false;
    const record=makeRecord({...draft,day:today,queue,engrave:ids});
    const nextRecords=[record,...records.filter(r=>r.day!==today)];
    if(!write(STORE,nextRecords)){setMessage("이 브라우저에서 기록을 저장할 수 없어요. 로컬 저장 권한과 저장 공간을 확인해주세요.");go("error");return false;}
    setRecords(nextRecords);setViewDay(today);
    if(next==="today")setFlash("오늘의 LP판에 기록했어요.");
    go(next);return true;
  }
  function finishReaction(){
    if(canReview(queue.map(t=>t.id),draft.tracks))go("complete");
    else prepareLP();
  }
  function demoCase(kind){
    const map={high:"오늘은 행복하고 뿌듯하고 즐거웠어요.",medium:"오늘은 뿌듯했지만 한편으로 외롭고 속상했어요.",low:"오늘 하루가 지났어요."};
    if(kind==="risk"){go("risk");return;}
    if(kind==="failure"){failed("시연용 분석 실패 상태예요. 실제 서버에는 연결되어 있지 않아요.");return;}
    if(kind==="error"){setMessage("시연용 오류 상태예요. 실제 서버에는 연결되어 있지 않아요.");go("error");return;}
    analyze(map[kind],"text");
  }
  useEffect(()=>{
    if(page!=="loading")return;
    const target={high:"high",medium:"medium",low:"low",risk:"risk"}[result.kind]??"failure";
    const timer=setTimeout(()=>go(target,false),reduceMotion()?240:700);
    return ()=>clearTimeout(timer);
  },[page,result.kind]);
  useEffect(()=>{
    if(["recommend","player","react","complete","engrave"].includes(page)&&!draft.mood)go("record",false);
    if(page==="voice"&&!agreed)go("consent",false);
    if(page==="complete"&&draft.mood&&!canReview(queue.map(t=>t.id),draft.tracks))go("react",false);
  },[page,draft.mood,draft.tracks,agreed]);
  const savePref=to=>{setEntry(to);if(write(PREF,to))setFlash("첫 화면 설정을 저장했어요.");else setFlash("설정을 이 브라우저에 저장할 수 없어요.");};
  const clearAll=()=>{
    if(!window.confirm("이 브라우저에 저장한 MoodWave의 모든 기록을 지울까요?"))return;
    if(!write(STORE,[])){setFlash("기록을 지우지 못했어요.");return;}
    setRecords([]);setDraft(fresh());setFlash("이 브라우저의 기록을 지웠어요.");
  };
  const optionalVoice=()=>{patch({mode:"voice"});go(agreed?"voice":"consent");};

  function screen(){
    switch(page){
      case "start":return <><div className="start-kicker"><span/> MOOD JOURNAL</div><Heading title="오늘의 마음을 음악으로" desc="하루를 짧게 기록하고, 어울리는 음악을 LP판에 남겨보세요."/><LP/><div className="actions"><Btn onClick={preferred}>기록 시작 <Icon name="arrow" size={17}/></Btn><Btn variant="secondary" onClick={()=>go("history")}>지난 기록 살펴보기</Btn></div><div className="demo-legal"><button className="link" onClick={()=>go("login")}>로그인 화면 보기</button><span>·</span><button className="link" onClick={()=>go("signup")}>회원가입 화면 보기</button></div><Notice>브라우저에서만 작동하는 시제품이에요. 실제 계정은 만들지 않아요.</Notice></>;
      case "login":case "signup":return <><Heading title={PAGES[page][0]} desc="화면 미리보기 · 실제 계정 인증은 연결하지 않았어요."/><div className="surface auth-demo"><label className="field">아이디<input value="moodwave-demo" readOnly/></label><label className="field">비밀번호<input value="demo-only" type="password" readOnly/></label><Notice>예시 정보만 표시해요. 실제 아이디나 비밀번호를 입력하지 않아요.</Notice></div><div className="actions"><Btn onClick={preferred}>시연 모드로 계속하기</Btn><Btn variant="secondary" onClick={()=>go(page==="login"?"signup":"login")}>{page==="login"?"회원가입 화면 보기":"로그인 화면 보기"}</Btn></div></>;
      case "record":return <><Heading title="오늘의 기록" desc="오늘의 마음을 한 문장으로 남겨도 좋아요."/><form onSubmit={e=>{e.preventDefault();if(draft.input.trim())analyze(draft.input,"text");}}><div className="surface"><label className="field">오늘 있었던 일<textarea value={draft.input} maxLength={300} rows={6} onChange={e=>patch({input:e.target.value,mode:"text"})} placeholder="오늘은 어떤 기분이었나요?"/></label><div className="field-meta"><span>입력한 글은 서버에 전송하지 않아요.</span><span>{draft.input.length} / 300</span></div></div><div className="actions"><button className="btn primary" disabled={!draft.input.trim()} type="submit">기록 완료 <Icon name="arrow" size={16}/></button><Btn variant="secondary" onClick={optionalVoice}><Icon name="mic" size={17}/> 음성으로 기록</Btn><button type="button" className="link" onClick={manual}>감정 직접 선택</button></div></form></>;
      case "consent":return <><Heading title="음성 녹음 동의" desc="녹음을 시작하기 전에 확인해주세요."/><div className="surface consent"><Icon name="shield" size={25}/><h2>원본 음성은 저장하지 않아요</h2><p>이 시제품에서는 마이크 동작만 확인해요. 녹음 데이터는 서버로 보내지 않고, 녹음을 종료하거나 화면에서 나가면 마이크를 닫아요. 음성 감정 분석과 자동 받아쓰기는 미연결 상태예요.</p><label className="checkline"><input type="checkbox" checked={agreed} onChange={e=>setAgreed(e.target.checked)}/> 안내를 읽고 마이크 사용에 동의해요.</label></div><div className="actions"><Btn disabled={!agreed} onClick={()=>go("voice")}>녹음 화면으로</Btn><Btn variant="secondary" onClick={()=>go("record")}>글로 기록하기</Btn></div></>;
      case "voice":return <Voice onAnalyze={words=>analyze(words,"voice")} onFail={failed} onBack={()=>go("record")}/>;
      case "loading":return <><Heading title="감정 분석 중" desc="오늘의 마음을 살펴보고 있어요."/><LP playing/><div className="dots" role="status" aria-label="분석 중"><i/><i/><i/></div><Notice>현재는 기기에 내장된 단어 규칙을 사용해요. 진단이나 실제 AI 모델의 결과가 아니에요.</Notice></>;
      case "high":return <><Heading title={PAGES.high[0]}/><LP/><div className="analysis-result"><small>시제품이 짐작한 감정</small><strong>{moodInfo(result.candidates[0]).label}</strong></div><div className="actions"><Btn onClick={()=>accept(result.candidates[0]??"steady")}>맞아요</Btn><Btn variant="secondary" onClick={manual}>다른 감정이에요</Btn></div></>;
      case "medium":return <><Heading title={PAGES.medium[0]} desc="기록에서 가까운 두 가지 감정을 골랐어요."/><LP/><MoodSelect ids={result.candidates.length?result.candidates:["steady","low"]} stack onPick={accept}/><div className="actions"><button className="link" onClick={manual}>다른 감정 선택</button></div></>;
      case "low":case "manual":return <><Heading title={PAGES[page][0]} desc={page==="low"?"기록만으로는 판단하기 어려워요. 가까운 감정을 골라주세요.":"지금 마음에 가까운 감정을 하나 골라주세요."}/><LP/><MoodSelect active={pick} onPick={id=>page==="low"?accept(id):setPick(id)}/>{page==="manual"&&<div className="actions"><Btn disabled={!pick} onClick={()=>accept(pick)}>선택 완료</Btn></div>}</>;
      case "recommend":return <><Heading title="오늘의 추천 음악" desc="확정한 감정에 맞춰 세 곡을 골랐어요."/><div className="center mood-row"><span>확정 감정</span><Mood id={draft.mood}/></div><div className="cards">{queue.map((t,i)=><div key={t.id} className="track-card"><Cover theme={t.theme}/><div className="track-body"><strong>{t.title}</strong><small>{t.artist}</small><p>{t.reason}</p></div><button className={`icon queue-like ${draft.tracks[t.id]?.liked?"liked":""}`} aria-label={`${t.title} ${draft.tracks[t.id]?.liked?"좋아요 취소":"좋아요"}`} aria-pressed={!!draft.tracks[t.id]?.liked} onClick={()=>setReaction(t.id,"like")}><Icon name="heart" size={17} fill={draft.tracks[t.id]?.liked?"currentColor":"none"}/></button><button className="icon play" aria-label={`${t.title} 재생 화면`} onClick={()=>selectTrack(i)}><Icon name="play" size={17}/></button></div>)}</div><div className="actions"><Btn variant="secondary" onClick={review}>곡에 반응 남기기</Btn></div><Notice>시연용 음원은 직접 합성했어요. 외부 음악 서비스는 연결하지 않았어요.</Notice></>;
      case "player":return <Player queue={queue} index={index} onIndex={setIndex} onAction={setReaction} onReview={review}/>;
      case "react":return <><Heading title="곡에 반응 남기기" desc="곡마다 좋았던 순간을 표시해보세요."/><ReviewRows items={queue} states={draft.tracks} onAction={setReaction}/><Notice>완청 {count} / 3곡 · 이 시연에서는 곡이 끝나면 완청으로 표시돼요. 두 곡 이상을 들으면 감상 후 기분을 답할 수 있어요.</Notice><div className="actions"><Btn onClick={finishReaction}>감상 마치기</Btn><Btn variant="secondary" onClick={()=>go("recommend")}>추천곡으로 돌아가기</Btn></div></>;
      case "complete":return <><Heading title="감상 완료"/><LP done/><p className="counter">{count}곡 감상 완료</p><div className="heading compact"><h2>지금 기분은 어떤가요?</h2></div><div className="actions">{RESPONSES.map(x=><Btn key={x} variant={draft.response===x?"primary":"secondary"} aria-pressed={draft.response===x} onClick={()=>patch({response:x})}>{x}</Btn>)}<Btn disabled={!draft.response} onClick={prepareLP}>계속하기</Btn><button className="link" onClick={()=>{patch({response:""});prepareLP();}}>건너뛰기</button></div></>;
      case "engrave":return <><Heading title="LP 새김 확인" desc={liked.length?"좋아요한 곡 중 LP판에 남길 곡을 골라주세요.":"좋아요한 곡이 없어요. 감정과 기록만 남길 수 있어요."}/><LP/>{liked.length>0&&<div className="surface mini-list">{liked.map(t=><label className="checkline" key={t.id}><input type="checkbox" checked={draft.engrave.includes(t.id)} onChange={e=>setDraft(d=>({...d,engrave:e.target.checked?[...d.engrave,t.id]:d.engrave.filter(id=>id!==t.id)}))}/>{t.title}</label>)}</div>}<Notice>하루에 한 기록을 이 브라우저에 저장해요. 이미 기록이 있으면 저장 전에 교체 여부를 물어요.</Notice><div className="actions"><Btn disabled={!draft.engrave.length} onClick={()=>persist(draft.engrave,"engraved")}>LP판에 새기기</Btn><Btn variant="secondary" onClick={()=>persist([],"today")}>기록만 저장하기</Btn><button className="link" onClick={back}>돌아가기</button></div></>;
      case "engraved":return <><Heading title="LP 새김 완료" desc={`${Object.values(todaysRecord?.tracks??{}).filter(t=>t.engraved).length}곡을 LP판에 담았어요.`}/><LP done/><div className="surface mini-list">{(todaysRecord?.trackIds??[]).filter(id=>todaysRecord?.tracks[id]?.engraved).map(id=><p key={id}><Icon name="check" size={16}/>{getTrack(id)?.title}</p>)}</div><div className="actions"><Btn onClick={()=>goToday(today)}>오늘의 LP판 보기</Btn></div></>;
      case "today":return <><Heading title={viewDay&&viewDay!==today?"그날의 LP판":"오늘의 LP판"} desc={dateLabel(viewDay||today)}/>{viewRecord?<div className="surface daily-card"><div className="daily-top"><LP small/><div><Mood id={viewRecord.mood}/><p>{viewRecord.input||"감정만 기록했어요."}</p></div></div>{viewRecord.response&&<p className="daily-response">감상 후 기분 · {viewRecord.response}</p>}<h2>오늘의 추천 음악</h2>{(viewRecord.trackIds??[]).map(id=>{const t=getTrack(id),s=viewRecord.tracks[id]??{};return t&&<div className="saved-track" key={id}><Cover theme={t.theme}/><div><strong>{t.title}</strong><small>{[s.liked&&"좋아요",s.skipped&&"건너뜀",s.completed&&"완청",s.engraved&&"새김"].filter(Boolean).join(" · ")||"반응 없음"}</small></div></div>;})}</div>:<div className="empty"><LP small/><strong>아직 저장한 기록이 없어요.</strong><p>기록을 마치면 여기에 LP판이 쌓여요.</p></div>}<div className="actions"><Btn variant="secondary" onClick={()=>go("history")}>지난 기록 보기</Btn>{!viewRecord&&<Btn onClick={startNew}>오늘을 기록하기</Btn>}</div></>;
      case "history":return <><Heading title="날짜별 기록" desc="기억하고 싶은 날의 감정과 음악을 다시 만나요."/><MonthSelect month={month} onChange={setMonth}/>{thisMonth.length?<div className="cards">{thisMonth.map(r=><button key={r.day} className="history-row" onClick={()=>goToday(r.day)}><LP small/><span><strong>{dateLabel(r.day)}</strong><Mood id={r.mood}/><small>{getTrack((r.trackIds??[]).find(id=>r.tracks[id]?.engraved)??r.trackIds?.[0])?.title??"감정 기록"}</small></span><Icon name="next"/></button>)}</div>:<div className="empty"><p>이 달에는 저장한 기록이 없어요.</p></div>}<div className="actions"><Btn onClick={startNew}>오늘을 기록하기</Btn></div></>;
      case "me":return <><Heading title="마이페이지" desc="기록과 나에게 맞는 시작 화면을 관리해요."/><div className="surface"><h2>기록 보기</h2><div className="menu-list">{[["monthly-mood","월간 감정 분석"],["monthly-music","월간 음악 취향"],["daytype","Day Type"],["history","날짜별 기록"]].map(([to,label])=><button key={to} onClick={()=>go(to)}>{label}<Icon name="next" size={16}/></button>)}</div></div><div className="surface settings"><h2>기록 시작 버튼을 누르면</h2><label className="checkline"><input type="radio" name="entry" checked={entry==="record"} onChange={()=>savePref("record")}/> 기록 입력 먼저 보기</label><label className="checkline"><input type="radio" name="entry" checked={entry==="history"} onChange={()=>savePref("history")}/> 지난 기록 먼저 보기</label></div><div className="surface"><h2>이 브라우저의 기록</h2><p className="small">서버나 다른 기기로 동기화하지 않아요. 공유 기기에서는 민감한 내용을 저장하지 않는 편이 좋아요.</p><button className="link danger" onClick={clearAll}>로컬 기록 모두 지우기</button></div><div className="actions"><Btn variant="secondary" onClick={()=>setDemo(!demo)}>{demo?"시연 메뉴 닫기":"시연 메뉴 보기"}</Btn></div>{demo&&<div className="surface demo-cases"><h2>테스트 시나리오</h2>{[["high","높은 확신"],["medium","중간 확신"],["low","낮은 확신"],["failure","분석 실패"],["risk","도움 안내"],["error","오류"]].map(([id,label])=><Btn key={id} variant="secondary" onClick={()=>demoCase(id)}>{label}</Btn>)}</div>}</>;
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
  const noTabs=["start","login","signup","risk"].includes(page);
  const active=page==="today"||page==="engrave"||page==="engraved"?"today":page==="history"?"history":PAGES[page]?.[1]==="나의 기록"?"me":"record";
  return <div className="layout">
    <aside className="desktop-intro" aria-hidden="true"><span className="series">MOODWAVE / LOCAL DEMO</span><h2>한 장의 LP판에<br/>남기는 하루.</h2><p>감정 기록에서 음악 감상까지, 오늘의 마음을 다시 들여다보는 작은 공간.</p><LP/></aside>
    <div className="phone">
      <header className="header"><div className="header-side">{page!=="start"&&<button className="icon back" aria-label="이전 화면" onClick={back}><Icon name="back"/></button>}</div><button className="brand" onClick={()=>go("start")} aria-label="MOOD WAVE 시작 화면">MOOD WAVE<i/></button><div className="header-side right"><span className="demo-pill">DEMO</span></div></header>
      <main ref={main} className={`screen page-${page}`}>{screen()}</main>
      {!noTabs&&<nav className="bottom-nav" aria-label="주 메뉴">{TABS.map(([id,label,ico])=><button key={id} aria-current={active===id?"page":undefined} onClick={()=>id==="today"?goToday():go(id)}><Icon name={ico}/><span>{label}</span></button>)}</nav>}
      {flash&&<div className="toast" role="status">{flash}</div>}
    </div>
  </div>;
}
