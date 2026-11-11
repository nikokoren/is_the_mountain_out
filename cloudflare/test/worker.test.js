import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync,readdirSync} from 'node:fs';
import {Miniflare,convertV4MiniflareOptions} from 'miniflare';
import {samples,viewpoints} from '../src/model.js';

async function runtime(outbound,bindings={WEATHER_MODEL:'v1'}){
  const modules=[{type:'ESModule',path:'dist/worker.js'},...readdirSync('dist').filter(s=>s.endsWith('.sql')).map(s=>({type:'Text',path:'dist/'+s}))];
  let upstream=0;
  const mf=new Miniflare(await convertV4MiniflareOptions({modules,bindings,compatibilityDate:'2026-10-01',d1Databases:['DB'],
    serviceBindings:{ASSETS:async request=>new Response(readFileSync('../assets'+new URL(request.url).pathname),{headers:{'Content-Type':'image/png'}})},
    outboundService:async request=>{upstream++;if(outbound)return outbound(request);throw Error('No network in integration test');}}));
  const request=(path,options={})=>mf.dispatchFetch('https://mountain.test'+path,options);
  assert.equal((await request('/health')).status,200);
  const db=await mf.getD1Database('DB');
  const t=Date.now()/1000;
  for(const location of Object.values(viewpoints))for(const point of samples(location)){
    const payload={hourly:{time:[t],cloud_cover:[0],visibility:[120000],precipitation:[0],weather_code:[0]}};
    await db.prepare('INSERT OR REPLACE INTO weather_cache(key,fetched,payload) VALUES (?,?,?)').bind('solar-v1:'+point.join(','),t,JSON.stringify(payload)).run();
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

function weatherCandidate(options={}){
  const {cloud=0,low=0,mid=0,high=0,visibility=24000,rain=0}=options,t=Date.now()/1000;
  return {hourly:{time:[t],cloud_cover:[cloud],cloud_cover_low:[low],cloud_cover_mid:[mid],cloud_cover_high:[high],
    visibility:[visibility],precipitation:[rain],weather_code:[0]},
    daily:{sunrise:[-1,0,1].map(d=>t-18000+d*86400),sunset:[-1,0,1].map(d=>t+18000+d*86400)}};
}

test('V1 rollback shares solar inputs with v2 and refreshes pre-rollout cache entries',async()=>{
  const urls=[];
  const {mf,db,request,upstream}=await runtime(request=>{
    urls.push(new URL(request.url));return new Response(JSON.stringify(weatherCandidate()));
  });
  try{
    await db.prepare("UPDATE weather_cache SET key=replace(key,'solar-v1:','')").run();
    const data=await (await request('/api/visibility')).json();
    assert.equal(data.status,'kinda_out');
    assert.equal(data.model_comparison.active_model,'v1');
    assert.equal(data.model_comparison.v1.status,'kinda_out');
    assert.equal(data.model_comparison.v2.status,'mountain_out');
    assert.equal(data.model_comparison.v2.observability.state,'daylight');
    assert.equal(data.model_comparison.agrees,false);
    assert.equal(data.model_comparison.v1.corridor_samples[0].weather_inputs.visibility,24000);
    assert.equal(upstream(),4);
    for(const url of urls){
      assert.equal(url.searchParams.get('daily'),'sunrise,sunset');
      assert.equal(url.searchParams.get('past_days'),'1');
      assert.equal(url.searchParams.get('timezone'),'UTC');
      assert.equal(url.searchParams.get('timeformat'),'unixtime');
    }
    await request('/api/visibility');assert.equal(upstream(),4);
  }finally{await mf.dispose();}
});

test('V2 is the default weather estimate, retains v1 evidence and still yields to current reports',async()=>{
  const {mf,db,request}=await runtime(undefined,{});
  try{
    assert.equal((await (await request('/health')).json()).weather_model,'v2');
    await db.prepare('UPDATE weather_cache SET payload=?').bind(JSON.stringify(weatherCandidate({cloud:100,high:100}))).run();
    const first=await context(request);
    assert.equal(first.display.status,'mountain_out');
    assert.equal(first.display.model,'seattle-corridor-v2.1-candidate');
    const comparison=first.display.model_comparison;
    assert.equal(comparison.active_model,'v2');
    assert.equal(comparison.v1.status,'not_out');
    assert.equal(comparison.v1.corridor_samples[0].weather_inputs.effective_cloud_cover,100);
    assert.equal(comparison.v2.corridor_samples[0].weather_inputs.effective_cloud_cover,0);
    const response=await vote(request,first,'not_out');
    assert.match(await response.text(),/differs from/);
    const saved=JSON.parse((await db.prepare('SELECT snapshot FROM reports WHERE context_token=?').bind(first.token).first()).snapshot);
    assert.equal(saved.submission_weather_estimate.model_comparison.active_model,'v2');
    assert.equal(saved.submission_weather_estimate.status,'mountain_out');
    let data=await (await request('/api/visibility')).json();
    assert.equal(data.status,'not_out');assert.equal(data.display_basis,'community');
    assert.equal(data.weather_estimate.status,'mountain_out');
    assert.equal(data.weather_estimate.model_comparison.v1.status,'not_out');
    await db.prepare('UPDATE reports SET received=?').bind(Date.now()/1000-1201).run();
    data=await (await request('/api/visibility')).json();
    assert.equal(data.display_basis,'weather');assert.equal(data.status,'mountain_out');
    const night=weatherCandidate();
    for(const field of ['sunrise','sunset'])night.daily[field]=night.daily[field].map(t=>t-36000);
    await db.prepare('UPDATE weather_cache SET payload=?').bind(JSON.stringify(night)).run();
    data=await (await request('/api/visibility')).json();
    assert.equal(data.status,'unknown');assert.deepEqual(data.limiting_factors,['darkness']);
    assert.equal(data.weather_conditions.status,'mountain_out');
  }finally{await mf.dispose();}
});

test('Mid-cloud overcast with moderate visibility no longer vetoes any viewpoint; poor conditions still do',async()=>{
  const {mf,db,request}=await runtime(undefined,{WEATHER_MODEL:'v2'});
  try{
    const fixture=JSON.parse(readFileSync('../tests/fixtures/seattle-2026-11-11-mid-cloud.json','utf8'));
    const inputs=fixture.samples[0].weather_inputs;
    const base=weatherCandidate({cloud:inputs.cloud_cover,low:inputs.cloud_cover_low,mid:inputs.cloud_cover_mid,
      high:inputs.cloud_cover_high,visibility:inputs.visibility});
    base.hourly.weather_code=[inputs.weather_code];
    for(const obstruction of [null,'low_cloud','rain','fog','poor_visibility']){
      const payload=structuredClone(base);
      if(obstruction==='low_cloud')payload.hourly.cloud_cover_low=[100];
      if(obstruction==='rain')payload.hourly.precipitation=[2];
      if(obstruction==='fog')payload.hourly.weather_code=[45];
      if(obstruction==='poor_visibility')payload.hourly.visibility=[4999];
      await db.prepare('UPDATE weather_cache SET payload=?').bind(JSON.stringify(payload)).run();
      for(const location of Object.values(viewpoints)){
        const data=await (await request(`/api/visibility?mountain=${location.mountain}&viewpoint=${location.id}`)).json();
        assert.equal(data.status,obstruction?'not_out':'mostly_out',`${location.id}: ${obstruction??'mid cloud only'}`);
        assert.equal(data.model_comparison.active_model,'v2');
        assert.equal(data.model_comparison.v1.status,'not_out');
        assert.match(data.model,/v2\.1-candidate$/);
        assert.equal(data.report_count,0);
      }
    }
  }finally{await mf.dispose();}
});

test('Submission evaluates both models now, preserves QR evidence and keeps retries immutable',async()=>{
  const {mf,db,request}=await runtime();
  try{
    const first=await context(request);
    await db.prepare('UPDATE weather_cache SET payload=?').bind(JSON.stringify(weatherCandidate({rain:2}))).run();
    const response=await vote(request,first,'not_out');
    assert.equal(response.status,200);
    const receipt=await response.text();assert.match(receipt,/agrees with/);assert.match(receipt,/at submission/);
    const original=await db.prepare('SELECT received,snapshot FROM reports WHERE context_token=?').bind(first.token).first();
    const snapshot=JSON.parse(original.snapshot);
    assert.equal(snapshot.status,'mountain_out');
    assert.equal(snapshot.submission_weather_estimate.status,'not_out');
    assert.equal(snapshot.submission_weather_estimate.model_comparison.v2.status,'not_out');
    assert.deepEqual(snapshot.corridor_samples,first.display.corridor_samples);
    const qr=await db.prepare('SELECT snapshot FROM contexts WHERE token=?').bind(first.token).first();
    assert.equal(JSON.parse(qr.snapshot).submission_weather_estimate,undefined);
    await db.prepare('UPDATE weather_cache SET payload=?').bind(JSON.stringify(weatherCandidate())).run();
    await vote(request,first,'not_out');
    const replay=await db.prepare('SELECT received,snapshot FROM reports WHERE context_token=?').bind(first.token).first();
    assert.deepEqual(replay,original);
    await vote(request,first,'out');
    const updated=JSON.parse((await db.prepare('SELECT snapshot FROM reports WHERE context_token=?').bind(first.token).first()).snapshot);
    assert.equal(updated.status,'mountain_out');
    assert.equal(updated.submission_weather_estimate.status,'kinda_out');
    assert.equal(updated.submission_weather_estimate.model_comparison.v2.status,'mountain_out');
  }finally{await mf.dispose();}
});

test('Weather failure during submission saves the observation with unknown current estimates',async()=>{
  const {mf,db,request}=await runtime();
  try{
    const first=await context(request);
    await db.prepare('DELETE FROM weather_cache').run();
    const response=await vote(request,first,'out');
    assert.equal(response.status,200);
    assert.match(await response.text(),/without an agreement/);
    const snapshot=JSON.parse((await db.prepare('SELECT snapshot FROM reports WHERE context_token=?').bind(first.token).first()).snapshot);
    assert.equal(snapshot.status,'mountain_out');
    assert.equal(snapshot.submission_weather_estimate.status,'unknown');
    assert.equal(snapshot.submission_weather_estimate.model_comparison.v2.status,'unknown');
  }finally{await mf.dispose();}
});

test('Worker serves assets, initializes D1 and uses persistent weather cache for all four views',async()=>{
  const {mf,request,upstream}=await runtime();
  try{
    const landing = await (await request('/')).text();
    assert.match(landing,/Connect your TRMNL/);
    assert.match(landing,/shared service automatically/);
    assert.doesNotMatch(landing,/Set the recipe’s service URL/);
    for(const location of Object.values(viewpoints)){
      const response=await request(`/api/visibility?mountain=${location.mountain}&viewpoint=${location.id}`),data=await response.json();
      assert.equal(data.status,'mountain_out');assert.equal(data.display_basis,'weather');assert.equal(data.mountain,location.mountain);
      const inputs = location.id==='paradise'?data.weather_inputs:data.corridor_samples[0].weather_inputs;
      assert.equal(inputs.cloud_cover,0);assert.equal(inputs.visibility,120000);
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
    const saved = await db.prepare('SELECT snapshot FROM reports WHERE context_token=?').bind(first.token).first();
    const savedEstimate = JSON.parse(saved.snapshot);
    assert.deepEqual(savedEstimate.corridor_samples.map(s=>s.weather_inputs),first.display.corridor_samples.map(s=>s.weather_inputs));
    assert.deepEqual(savedEstimate.limiting_factors,first.display.limiting_factors);
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

test('QR opt-in accepts common checkbox encodings and returns a native feedback URL',async()=>{
  const {mf,request}=await runtime();
  try{
    for(const enabled of ['true','TRUE','1','yes','on']){
      const response=await (await request('/api/visibility?feedback='+enabled)).json();
      assert.equal(response.feedback_ready,true);
      assert.match(response.feedback_url,/^https:\/\/mountain\.test\/f\/[a-f0-9]{24}$/);
      assert.equal(response.feedback_qr_path.replace('/q/','/f/'),'/' + response.feedback_url.split('/').slice(3).join('/'));
    }
    for(const disabled of ['false','0','no','off']){
      const response=await (await request('/api/visibility?feedback='+disabled)).json();
      assert.equal(response.feedback_ready,false);
      assert.equal(response.feedback_url,undefined);
    }
  }finally{await mf.dispose();}
});

test('Normal requests clean expired data without cron, preserving fresh data and throttling cleanup',async()=>{
  const {mf,db,request}=await runtime();
  const pause=()=>new Promise(resolve=>setTimeout(resolve,20));
  const awaitDeletion=async token=>{
    for(let attempt=0;attempt<100;attempt++){
      if(!await db.prepare('SELECT token FROM contexts WHERE token=?').bind(token).first())return;
      await pause();
    }
    assert.fail('Background cleanup did not remove the expired context');
  };
  try{
    const t=Date.now()/1000;
    const expired='a'.repeat(24),fresh='b'.repeat(24);
    await db.prepare('INSERT INTO contexts VALUES (?,?,?)').bind(expired,t-7201,'{}').run();
    await db.prepare('INSERT INTO contexts VALUES (?,?,?)').bind(fresh,t,'{}').run();
    await db.prepare('INSERT INTO weather_cache VALUES (?,?,?)').bind('old',t-86401,'{}').run();
    await db.prepare('INSERT INTO reports(received,mountain,viewpoint,answer,browser_hash,context_token,snapshot) VALUES (?,?,?,?,?,?,?)').bind(t-91*86400,'rainier','seattle','out','old','old','{}').run();
    await request('/api/visibility');await awaitDeletion(expired);
    assert.ok(await db.prepare('SELECT token FROM contexts WHERE token=?').bind(fresh).first());
    // All statements in the D1 batch are complete when these checks run.
    for(let i=0;i<100 && await db.prepare("SELECT key FROM weather_cache WHERE key='old'").first();i++)await pause();
    assert.equal(await db.prepare("SELECT key FROM weather_cache WHERE key='old'").first(),null);
    assert.equal(await db.prepare("SELECT id FROM reports WHERE browser_hash='old'").first(),null);
    const lease=await db.prepare("SELECT value FROM settings WHERE name='last_cleanup'").first();
    assert.ok(Number(lease.value)>=t);
    await db.prepare('INSERT INTO contexts VALUES (?,?,?)').bind(expired,t-7201,'{}').run();
    await request('/api/visibility');await pause();
    assert.ok(await db.prepare('SELECT token FROM contexts WHERE token=?').bind(expired).first(),'the next request does not repeat cleanup within an hour');
    await db.prepare("UPDATE settings SET value='0' WHERE name='last_cleanup'").run();
    await request('/api/visibility');await awaitDeletion(expired);
    const config=JSON.parse(readFileSync('../wrangler.jsonc','utf8'));
    assert.deepEqual(config.triggers.crons,[]);
  }finally{await mf.dispose();}
});
