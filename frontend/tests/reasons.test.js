import test from "node:test";
import assert from "node:assert/strict";
import {applyReasons} from "../src/api.js";

const queue=[{id:"server:deam_2",reason:"맞추기"},{id:"server:deam_3",reason:"조금 밝게"},{id:"server:deam_4",reason:"더 밝게"}];
const data=(source,ids=["deam_2","deam_3","deam_4"])=>({source,risk:false,reasons:ids.map((song_id,i)=>({recommend_order:i+1,song_id,text:`이유 ${i+1}이에요.`}))});

for(const source of ["agent","template"])test(`${source} 응답이면 곡마다 이유를 바꾼다`,()=>{
  assert.deepEqual(applyReasons(queue,7,7,data(source)).map(t=>t.reason),["이유 1이에요.","이유 2이에요.","이유 3이에요."]);
});
test("그사이 다른 기록이 되었으면 버린다",()=>assert.equal(applyReasons(queue,7,8,data("agent")),null));
test("그사이 곡이 바뀌었으면 버린다",()=>assert.equal(applyReasons(queue,7,7,data("agent",["deam_9","deam_3","deam_4"])),null));
test("원래 큐는 바꾸지 않는다",()=>{applyReasons(queue,7,7,data("agent"));assert.equal(queue[0].reason,"맞추기");});
