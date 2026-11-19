export const MOODS = [
  {id:"good", label:"좋음", color:"#fff0be", hue:"#c58b32", symbol:"☀"},
  {id:"steady", label:"무난함", color:"#ddf4e5", hue:"#4c9172", symbol:"≈"},
  {id:"low", label:"가라앉음", color:"#e0e7ff", hue:"#6279ba", symbol:"◒"},
  {id:"tender", label:"예민함", color:"#ffe1dc", hue:"#c67465", symbol:"✦"},
];
export const moodInfo = id => MOODS.find(m => m.id === id) ?? MOODS[1];

const WORDS = {
  good:["기뻐","기뻤","기쁘","행복","즐거","신나","뿌듯","기대돼","좋았","좋아","설레"],
  steady:["무난","평온","그냥","평범","보통","괜찮","차분","잔잔","담담","편안","별일"],
  low:["슬프","슬펐","슬퍼","우울","속상","외롭","무거","힘들","지쳐","지쳤","가라앉","울적","눈물","서운"],
  tender:["예민","짜증","화나","화가","초조","답답","불안","긴장","걱정","화났","스트레스","조급"],
};
const SIGNALS = [
  /죽고\s*싶/, /죽어\s*버리고\s*싶/, /살고\s*싶지\s*않/, /목숨을\s*끊/,
  /자해(?:하|를|할|했)/, /자살(?:하|할|을|하고|해야)/, /스스로를\s*해치/,
];

export function classify(input="") {
  const t = input.trim().normalize("NFC");
  if (SIGNALS.some(pattern => pattern.test(t))) return {kind:"risk", candidates:[]};
  const ranked = MOODS.map(m=>({id:m.id,score:WORDS[m.id].reduce((n,w)=>n+Number(t.includes(w)),0)})).sort((a,b)=>b.score-a.score);
  const [a,b]=ranked;
  if (a.score >= 2 && a.score-b.score >= 2) return {kind:"high", candidates:[a.id]};
  if (a.score >= 1 && b.score >= 1 && a.score-b.score <= 1) return {kind:"medium", candidates:[a.id,b.id]};
  return {kind:"low", candidates:[]};
}

export const TRACKS = [
  {id:"nightwalk", title:"밤의 산책", artist:"MoodWave Session", theme:"dusk", description:"느린 건반 패턴", seconds:16},
  {id:"starlight", title:"별빛 아래", artist:"Luna Archive", theme:"stars", description:"부드러운 신스 선율", seconds:16},
  {id:"daybreak", title:"새벽의 온도", artist:"Velvet Sound", theme:"morning", description:"따뜻한 아르페지오", seconds:16},
  {id:"lights", title:"온화한 불빛", artist:"MoodWave Session", theme:"peach", description:"가벼운 리듬", seconds:16},
  {id:"wave", title:"작은 파도", artist:"Luna Archive", theme:"mist", description:"고른 박자의 선율", seconds:16},
  {id:"window", title:"창가의 오후", artist:"Velvet Sound", theme:"rose", description:"공간을 남긴 화음", seconds:16},
];
const ORDER = {
  good:["lights","daybreak","starlight"], steady:["wave","window","nightwalk"],
  low:["nightwalk","starlight","daybreak"], tender:["window","wave","starlight"],
};
const REASONS = {
  good:["가벼운 리듬으로 오늘의 활기를 이어가요.","밝은 화음이 이어지는 곡이에요.","부드러운 신스로 마무리해요."],
  steady:["고른 박자의 선율로 편하게 시작해요.","여백 있는 화음이 이어져요.","차분한 건반으로 마무리해요."],
  low:["잔잔한 피아노로 시작해요.","부드러운 신스가 이어져요.","따뜻한 아르페지오로 마무리해요."],
  tender:["공간을 남긴 화음으로 시작해요.","고른 박자의 선율이 이어져요.","부드러운 신스로 마무리해요."],
};
export const getTrack = id=>TRACKS.find(t=>t.id===id);
export function recommend(mood) {
  const order=ORDER[mood]??ORDER.steady;
  return order.map((id,i)=>({...getTrack(id),reason:(REASONS[mood]??REASONS.steady)[i]}));
}
export const RESPONSES=["조금 나아졌어요","그대로예요","더 무거워졌어요"];
export const NO_MOOD_RESPONSE="무응답";
export const canReview = (mood,ids,states)=>
  (mood==="low"||mood==="tender")&&ids.filter(id=>states[id]?.completed).length>=2;
export function nextTrackState(previous={}, action) {
  if (action==="like") return previous.liked
    ? {...previous,liked:false,engraved:false}
    : {...previous,liked:true,skipped:false};
  if (action==="skip") return previous.completed
    ? previous
    : {...previous,liked:false,skipped:true,engraved:false};
  if (action==="finish") return {...previous,completed:true,skipped:false};
  return previous;
}
export function localDay(now=new Date()) {
  return [now.getFullYear(),String(now.getMonth()+1).padStart(2,"0"),String(now.getDate()).padStart(2,"0")].join("-");
}
export function shiftMonth(month,delta) {
  const [year,m]=month.split("-").map(Number);
  return localDay(new Date(year,m-1+delta,1)).slice(0,7);
}
export function monthLabel(month) {
  const [y,m]=month.split("-"); return `${y}년 ${Number(m)}월`;
}
export function dateLabel(day) {
  const [,m,d]=day.split("-");return `${Number(m)}월 ${Number(d)}일`;
}
export const forMonth=(records,month)=>records.filter(r=>r.day.startsWith(month)).sort((a,b)=>b.day.localeCompare(a.day));
export function monthlyMood(records) {
  return MOODS.map(m=>({...m,count:records.filter(r=>r.mood===m.id).length}));
}
export function monthlyMusic(records) {
  const score = {};
  const songs = new Map(records.flatMap(record=>(record.queue??[]).map(track=>[track.id,track])));
  for (const r of records) for(const [id,t] of Object.entries(r.tracks??{})) {
    if(!t.liked&&!t.completed&&!t.engraved) continue;
    const a=score[id]??{liked:0,completed:0,engraved:0};
    score[id]={liked:a.liked+Number(!!t.liked),completed:a.completed+Number(!!t.completed),engraved:a.engraved+Number(!!t.engraved)};
  }
  return Object.entries(score).map(([id,a])=>({track:songs.get(id)??getTrack(id),stats:a}))
    .filter(({track})=>track).map(({track,stats})=>({...track,...stats}))
    .sort((a,b)=>b.completed-a.completed||b.liked-a.liked);
}
export function makeRecord({day,input,mood,mode,response,tracks,queue,engrave}) {
  const ids=queue.map(t=>t.id);
  const keep=new Set(engrave.filter(id=>ids.includes(id)&&tracks[id]?.liked));
  return {day,input:input.trim(),mood,mode,response:canReview(mood,ids,tracks)?response:"",trackIds:ids,tracks:Object.fromEntries(ids.map(id=>[id,{...tracks[id],engraved:keep.has(id)}]))};
}

export function dayType(mood) {
  return ({
    good:{title:"기분 좋은 순간이 있던 날",copy:"오늘 기록에 남긴 좋았던 순간을 한 번 더 떠올려보세요."},
    steady:{title:"잔잔하게 지나간 날",copy:"큰 일이 없던 날의 작은 장면도 한 줄로 기억해둘 수 있어요."},
    low:{title:"마음이 가라앉았던 날",copy:"오늘 기록에 남겨둔 마음을 서두르지 않고 돌아봐도 좋아요."},
    tender:{title:"감각이 예민했던 날",copy:"오늘 무엇에 마음이 쓰였는지 기록에서 천천히 살펴보세요."},
  })[mood]??null;
}
