import test from "node:test";
import assert from "node:assert/strict";
import {classify,recommend,nextTrackState,canReview,hasCompletedPlayback,makeRecord,shiftMonth,localDay,forMonth,monthlyMood,monthlyMusic,dayType} from "../src/domain.js";

test("재생 종료만으로 완청 처리하지 않고 실제 재생 구간을 확인한다",()=>{
  const ranges=intervals=>({length:intervals.length,start:i=>intervals[i][0],end:i=>intervals[i][1]});
  assert.equal(hasCompletedPlayback(ranges([[15.8,16]]),16),false);
  assert.equal(hasCompletedPlayback(ranges([[0,8],[12,16]]),16),false);
  assert.equal(hasCompletedPlayback(ranges([[0,15.9]]),16),true);
  assert.equal(hasCompletedPlayback(ranges([]),0.2),false);
  assert.equal(hasCompletedPlayback(ranges([[0,16]]),Infinity),false);
});

test("텍스트 분석은 높음·중간·낮음으로 구분한다",()=>{
  assert.deepEqual(classify("행복하고 뿌듯하고 즐거웠어요."),{kind:"high",candidates:["good"]});
  const medium=classify("뿌듯했지만 외롭고 속상했어요.");
  assert.equal(medium.kind,"medium");
  assert.deepEqual(medium.candidates,["low","good"]);
  assert.equal(classify("오늘도 집에 왔어요.").kind,"low");
  assert.equal(classify("").kind,"low");
});
test("정해진 위험 표현은 음악 대신 안내 분기로 간다",()=>{
  assert.equal(classify("오늘은 죽고 싶어요.").kind,"risk");
  assert.equal(classify("오늘 자해하고 싶은 마음이 들었어요.").kind,"risk");
  assert.equal(classify("오늘은 더 살고 싶지 않아요.").kind,"risk");
  assert.notEqual(classify("오늘 정말 피곤했어요.").kind,"risk");
});
test("기본 감정마다 중복 없는 시연 곡 세 개를 추천한다",()=>{
  for(const mood of ["good","steady","low","tender"]){
    const list=recommend(mood);
    assert.equal(list.length,3);
    assert.equal(new Set(list.map(x=>x.id)).size,3);
    assert.ok(list.every(x=>x.reason&&x.artist&&x.seconds===16));
  }
  assert.notDeepEqual(recommend("good").map(x=>x.id),recommend("low").map(x=>x.id));
});
test("좋아요·건너뜀·완청 상태와 감상 완료 조건",()=>{
  const a=nextTrackState({}, "like");
  assert.equal(nextTrackState(a,"like").liked,false);
  const skipped=nextTrackState(a,"skip");
  assert.deepEqual(skipped,{liked:false,skipped:true,engraved:false});
  assert.equal(nextTrackState(skipped,"like").skipped,false);
  const complete=nextTrackState(skipped,"finish");
  assert.deepEqual(complete,{liked:false,skipped:false,engraved:false,completed:true});
  assert.equal(nextTrackState(complete,"skip").skipped,false);
  assert.equal(canReview("low",["a","b","c"],{a:complete,b:skipped}),false);
  for(const mood of ["low","tender","good","steady"]){
    assert.equal(canReview(mood,["a","b","c"],{a:complete,b:complete}),mood==="low"||mood==="tender");
  }
});
test("좋아요하지 않은 곡은 LP판에 새기지 않고, 완청 기준이 부족하면 응답은 저장하지 않는다",()=>{
  const queue=recommend("low"), [a,b,c]=queue.map(x=>x.id);
  const draft={day:"2026-11-13",input:" 오늘 ",mood:"low",mode:"text",response:"그대로예요",queue,engrave:[a,b,"unknown"],tracks:{[a]:{liked:true,completed:true},[b]:{skipped:true}}};
  const r=makeRecord(draft);
  assert.equal(r.input,"오늘");
  assert.equal(r.response,"");
  assert.equal(r.tracks[a].engraved,true);
  assert.equal(r.tracks[b].engraved,false);
  assert.equal(r.tracks[c].engraved,false);
  const eligible={...draft,tracks:{...draft.tracks,[b]:{completed:true}}};
  assert.equal(makeRecord(eligible).response,"그대로예요");
  assert.equal(makeRecord({...eligible,response:"무응답"}).response,"무응답");
  assert.equal(makeRecord({...eligible,mood:"good"}).response,"");
});
test("날짜 이동과 월별 요약을 로컬 날짜 기준으로 계산한다",()=>{
  assert.equal(localDay(new Date(2026,10,3)),"2026-11-03");
  assert.equal(shiftMonth("2026-01",-1),"2025-12");
  assert.equal(shiftMonth("2026-12",1),"2027-01");
  const r=[{day:"2026-11-04",mood:"low",tracks:{nightwalk:{liked:true,completed:true}}},{day:"2026-12-01",mood:"good",tracks:{}},{day:"2026-11-08",mood:"low",tracks:{nightwalk:{engraved:true}}}];
  const nov=forMonth(r,"2026-11");
  assert.equal(nov[0].day,"2026-11-08");
  assert.equal(monthlyMood(nov).find(m=>m.id==="low").count,2);
  assert.deepEqual(monthlyMusic(nov).map(({id,liked,completed,engraved})=>({id,liked,completed,engraved})),[{id:"nightwalk",liked:1,completed:1,engraved:1}]);
});

test("Day Type은 확정 감정만 요약하고 기록이 없는 경우를 구분한다",()=>{
  assert.match(dayType("steady").title,/잔잔/);
  assert.equal(dayType(null),null);
});

test("위험 문장 묶음은 서버(ai/agent/rules.py)와 같은 판단을 한다",async()=>{
  const {readFileSync}=await import("node:fs");
  const cases=JSON.parse(readFileSync(new URL("../../backend/tests/fixtures/risk_sentences.json",import.meta.url),"utf8"));
  for(const c of cases)assert.equal(classify(c.text).kind==="risk",c.risk,c.text);
});
