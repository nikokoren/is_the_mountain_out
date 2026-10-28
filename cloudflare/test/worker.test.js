import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync,readdirSync} from 'node:fs';
import {Miniflare,convertV4MiniflareOptions} from 'miniflare';
import {samples,viewpoints} from '../src/model.js';

async function runtime(){
  const modules=[{type:'ESModule',path:'dist/worker.js'},...readdirSync('dist').filter(s=>s.endsWith('.sql')).map(s=>({type:'Text',path:'dist/'+s}))];
  let upstream=0;
  const mf=new Miniflare(await convertV4MiniflareOptions({modules,compatibilityDate:'2026-10-01',d1Databases:['DB'],
    serviceBindings:{ASSETS:async request=>new Response(readFileSync('../assets'+new URL(request.url).pathname),{headers:{'Content-Type':'image/png'}})},
    outboundService:async()=>{upstream++;throw Error('No network in integration test');}}));
  const request=(path,options={})=>mf.dispatchFetch('https://mountain.test'+path,options);
  assert.equal((await request('/health')).status,200);
  const db=await mf.getD1Database('DB');
  const t=Date.now()/1000;
  for(const location of Object.values(viewpoints))for(const point of samples(location)){
    const payload={hourly:{time:[t],cloud_cover:[0],visibility:[120000],precipitation:[0],weather_code:[0]}};
    await db.prepare('INSERT OR REPLACE INTO weather_cache(key,fetched,payload) VALUES (?,?,?)').bind(point.join(','),t,JSON.stringify(payload)).run();
  }
  return {mf,db,request,upstream:()=>upstream};
}
async function context(request,viewpoint='seattle',browserCookie){
  const mountain=viewpoint==='portland'?'hood':'rainier';
  const display=await (await request(`/api/visibility?mountain=${mountain}&viewpoint=${viewpoint}&feedback=true`)).json();
  const token=display.feedback_qr_path.split('/').at(-1);
  const response=await request('/f/'+token,browserCookie?{headers:{Cookie:browserCookie}}:{});
  const cookie=response.headers.get('Set-Cookie').split(';')[0],html=await response.text();
  const csrf=html.match(/name="csrf" value="([^"]+)"/)[1];
  return {display,token,cookie,csrf};
}
async function vote(request,form,answer,extraHeaders={}){
  return request('/feedback',{method:'POST',headers:{Cookie:form.cookie,'Content-Type':'application/x-www-form-urlencoded',...extraHeaders},body:new URLSearchParams({token:form.token,csrf:form.csrf,answer,present:'yes'})});
}

test('Worker serves assets, initializes D1 and uses persistent weather cache for all four views',async()=>{
  const {mf,request,upstream}=await runtime();
  try{
    assert.match(await (await request('/')).text(),/Connect your TRMNL/);
    for(const location of Object.values(viewpoints)){
      const response=await request(`/api/visibility?mountain=${location.mountain}&viewpoint=${location.id}`),data=await response.json();
      assert.equal(data.status,'mountain_out');assert.equal(data.display_basis,'weather');assert.equal(data.mountain,location.mountain);
      const asset=await request(data.image_path);assert.equal(asset.status,200);assert.equal(asset.headers.get('Content-Type'),'image/png');
      assert.deepEqual(new Uint8Array(await asset.arrayBuffer()),new Uint8Array(readFileSync('../'+data.image_path.slice(1))));
    }
    assert.equal(upstream(),0);
    assert.equal((await request('/api/visibility?mountain=hood&viewpoint=tacoma')).status,400);
    assert.equal((await request('/assets/../README.md')).status,404);
    assert.equal((await request('/api/feedback')).status,404);
  }finally{await mf.dispose();}
});

test('Feedback creates real QR, uses anonymous latest votes, expires per report, and falls back to weather',async()=>{
  const {mf,db,request}=await runtime();
  try{
    const first=await context(request);
    assert.equal(first.display.feedback_ready,true);
    const qr=await request('/q/'+first.token);assert.equal(qr.headers.get('Content-Type'),'image/svg+xml');assert.match(await qr.text(),/<svg/);
    assert.equal((await vote(request,first,'not_out', {Origin:'null','Sec-Fetch-Site':'same-origin'})).status,200);
    let display=await (await request('/api/visibility')).json();
    assert.equal(display.status,'not_out');assert.equal(display.display_basis,'community');assert.equal(display.weather_estimate.status,'mountain_out');
    const timestamp=display.reported_at;
    await vote(request,first,'not_out');
    assert.equal((await (await request('/api/visibility')).json()).reported_at,timestamp,'identical retry cannot extend a vote');
    const second=await context(request);await vote(request,second,'out');
    display=await (await request('/api/visibility')).json();assert.equal(display.status,'unknown');assert.equal(display.report_count,2);
    // An explicit new observation replaces that browser's previous vote.
    await vote(request,first,'out');display=await (await request('/api/visibility')).json();assert.equal(display.status,'mountain_out');
    const newer=await context(request,'seattle',first.cookie);await vote(request,newer,'unsure');
    display=await (await request('/api/visibility')).json();assert.equal(display.report_count,1,'latest unsure withdraws previous vote');
    assert.equal((await (await request('/api/visibility?viewpoint=tacoma')).json()).display_basis,'weather','votes are isolated to a viewpoint');
    await db.prepare('UPDATE reports SET received=?').bind(Date.now()/1000-1201).run();
    display=await (await request('/api/visibility')).json();assert.equal(display.display_basis,'weather');assert.equal(display.status,'mountain_out');
    assert.equal((await vote(request,second,'out',{Origin:'https://evil.example'})).status,403);
    assert.equal((await request('/f/'+('a'.repeat(24)))).status,410);
    await db.prepare('UPDATE contexts SET created=?').bind(Date.now()/1000-7201).run();
    assert.equal((await request('/f/'+first.token)).status,410);
  }finally{await mf.dispose();}
});

test('Provider failure yields UNKNOWN without losing a current community observation',async()=>{
  const {mf,db,request}=await runtime();
  try{
    const f=await context(request,'portland');await vote(request,f,'partial');
    await db.prepare('DELETE FROM weather_cache').run();
    const data=await (await request('/api/visibility?mountain=hood')).json();
    assert.equal(data.status,'halfway_out');assert.equal(data.weather_estimate.status,'unknown');
    assert.equal(data.viewpoint,'portland');
  }finally{await mf.dispose();}
});
