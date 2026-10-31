import qrcode from 'qrcode-generator';
import schema from '../migrations/0001.sql';
import {calculate,corridor,samples,locationFrom,iso,unknown,states,labels} from './model.js';
import {page,home,form,receipt,choices,escape} from './pages.js';

const encoder=new TextEncoder();
const now=()=>Date.now()/1000;
const randomHex=n=>Array.from(crypto.getRandomValues(new Uint8Array(n)),v=>v.toString(16).padStart(2,'0')).join('');
let initialized;
async function init(env){
  if(!initialized) initialized=(async()=>{
    await env.DB.batch(schema.split(';').map(s=>s.trim()).filter(Boolean).map(s=>env.DB.prepare(s)));
    await env.DB.prepare('INSERT OR IGNORE INTO settings(name,value) VALUES (?,?)').bind('key',randomHex(32)).run();
  })().catch(error=>{initialized=null;throw error;});
  await initialized;
}
async function digest(env,value){
  const {value:key}=await env.DB.prepare('SELECT value FROM settings WHERE name=?').bind('key').first();
  const bytes=Uint8Array.from(key.match(/../g),x=>parseInt(x,16));
  const cryptoKey=await crypto.subtle.importKey('raw',bytes,{name:'HMAC',hash:'SHA-256'},false,['sign']);
  return Array.from(new Uint8Array(await crypto.subtle.sign('HMAC',cryptoKey,encoder.encode(value))),v=>v.toString(16).padStart(2,'0')).join('');
}
function equal(a,b){
  if(typeof a!=='string'||typeof b!=='string'||a.length!==b.length)return false;
  let diff=0;for(let i=0;i<a.length;i++)diff|=a.charCodeAt(i)^b.charCodeAt(i);return diff===0;
}
function output(data,status=200,type='application/json; charset=utf-8',extra={}){
  return new Response(type.startsWith('application/json')?JSON.stringify(data):data,{status,headers:{
    'Content-Type':type,'Cache-Control':'no-store','Referrer-Policy':'no-referrer','X-Content-Type-Options':'nosniff',
    'Content-Security-Policy':"default-src 'none'; style-src 'unsafe-inline'; form-action 'self'; frame-ancestors 'none'; base-uri 'none'",...extra}});
}
const html=(title,content,status=200,extra={})=>output(page(title,content),status,'text/html; charset=utf-8',extra);

async function weatherSample(env,location,point){
  const key=point.join(','),cached=await env.DB.prepare('SELECT fetched,payload FROM weather_cache WHERE key=?').bind(key).first();
  const time=now();let payload, fetched;
  if(cached && time-cached.fetched>=0 && time-cached.fetched<(cached.payload?900:60)){
    payload=cached.payload?JSON.parse(cached.payload):null;fetched=cached.fetched;
  }else{
    const url=new URL('https://api.open-meteo.com/v1/forecast');
    url.search=new URLSearchParams({latitude:point[0],longitude:point[1],hourly:'cloud_cover,cloud_cover_low,cloud_cover_mid,cloud_cover_high,visibility,precipitation,weather_code',timezone:'UTC',timeformat:'unixtime',forecast_days:'2'});
    try{
      const response=await fetch(url,{signal:AbortSignal.timeout(10000)});
      if(!response.ok)throw Error('Weather unavailable');
      payload=await response.json();
    }catch{payload=null;}
    fetched=now();
    await env.DB.prepare('INSERT INTO weather_cache(key,fetched,payload) VALUES (?,?,?) ON CONFLICT(key) DO UPDATE SET fetched=excluded.fetched,payload=excluded.payload').bind(key,fetched,payload===null?null:JSON.stringify(payload)).run();
  }
  return payload===null?unknown('Weather provider unavailable. No current estimate.',now(),location):calculate(payload,now(),fetched,location);
}
async function estimate(env,location){
  const points=samples(location),results=await Promise.all(points.map(p=>weatherSample(env,location,p)));
  const result=points.length===1?{...results[0],model:'local-weather-v1-uncalibrated'}:corridor(results,points,now(),location);
  Object.assign(result,{mountain:location.mountain,viewpoint:location.id,image_path:location.image_path});
  return result;
}

export async function activeReports(db,mountain,viewpoint,time=now()){
  // Select the latest observation per browser BEFORE excluding unsure. A new
  // "can't tell" therefore withdraws that browser's earlier active vote.
  const {results}=await db.prepare(`SELECT r.* FROM reports r WHERE r.mountain=? AND r.viewpoint=? AND r.received>? AND r.received<=?
    AND NOT EXISTS (SELECT 1 FROM reports n WHERE n.mountain=r.mountain AND n.viewpoint=r.viewpoint AND n.browser_hash=r.browser_hash
      AND (n.received>r.received OR (n.received=r.received AND n.id>r.id)) AND n.received<=?)`).bind(mountain,viewpoint,time-1200,time,time).all();
  return results;
}
export function applyReports(weather,reports,time=now()){
  reports=reports.filter(r=>r.received<=time && r.received+1200>time);
  const votes=reports.filter(r=>r.answer!=='unsure'),answers=new Set(votes.map(r=>r.answer));
  if(!votes.length)return {...weather,display_basis:'weather',report_count:0};
  const expires=Math.min(...votes.map(r=>r.received+1200));
  const common={...weather,weather_estimate:weather,display_basis:'community',source:'Community reports',estimate:false,
    report_count:votes.length,reported_at:iso(Math.max(...votes.map(r=>r.received))),reports_expire_at:iso(expires)};
  if(answers.size>1)return {...common,status:'unknown',verdict:'UNKNOWN',explanation:'Current community reports disagree.'};
  const status={out:'mountain_out',partial:'halfway_out',not_out:'not_out'}[votes[0].answer];
  return {...common,status,verdict:labels[states.indexOf(status)],explanation:'Recent self-reported conditions for this viewpoint; not independently verified.'};
}
async function context(env,token){
  if(!/^[a-f0-9]{24}$/.test(token))return null;
  const row=await env.DB.prepare('SELECT created,snapshot FROM contexts WHERE token=?').bind(token).first();
  return row && now()-row.created>=0 && now()-row.created<=7200?JSON.parse(row.snapshot):null;
}
const countReports=reports=>reports.reduce((acc,r)=>(acc[r.answer]=(acc[r.answer]??0)+1,acc),{});
async function cleanup(env){
  await init(env);
  const t=now();
  await env.DB.batch([
    env.DB.prepare('DELETE FROM contexts WHERE created<?').bind(t-7200),
    env.DB.prepare('DELETE FROM reports WHERE received<?').bind(t-90*86400),
    env.DB.prepare('DELETE FROM weather_cache WHERE fetched<?').bind(t-86400)]);
}

async function maybeCleanup(env){
  await init(env);
  const t=now();
  // D1 atomically claims one cleanup slot per hour across all Worker isolates.
  // No Cron Trigger is needed; ordinary recipe polling drives housekeeping.
  const claimed=await env.DB.prepare(`INSERT INTO settings(name,value) VALUES ('last_cleanup',?)
    ON CONFLICT(name) DO UPDATE SET value=excluded.value
    WHERE CAST(settings.value AS REAL)<=? RETURNING value`).bind(String(t),t-3600).first();
  if(!claimed)return;
  try{await cleanup(env);}catch{
    // A transient failure can be retried by the next request.
    await env.DB.prepare("UPDATE settings SET value='0' WHERE name='last_cleanup' AND value=?").bind(String(t)).run();
  }
}

async function route(request,env){
  const url=new URL(request.url),path=url.pathname;
  if(request.method==='GET' && path.startsWith('/assets/')){
    const allowed=new Set(['rainier.png','rainier-seattle.png','rainier-tacoma.png','hood-portland.png','cloud-bank.png']);
    if(!allowed.has(path.slice(8)))return output({error:'Not found'},404);
    const assetURL=new URL(url);assetURL.pathname=path.slice(7);
    return env.ASSETS.fetch(new Request(assetURL,request));
  }
  if(request.method==='GET' && path==='/')return output(home(),200,'text/html; charset=utf-8');
  if(request.method==='GET' && path==='/health'){
    await init(env);await env.DB.prepare('SELECT 1').first();return output({status:'ok',storage:'d1'});
  }
  if(request.method==='GET' && path==='/api/visibility'){
    let location;try{location=locationFrom(url.searchParams);}catch(error){return output({error:error.message},400);}
    await init(env);
    const weather=await estimate(env,location),reports=await activeReports(env.DB,location.mountain,location.id);
    const result=applyReports(weather,reports);
    // Checked time is this evaluation; forecast/fetch times remain weather provenance.
    result.checked_at=iso(now());
    const formatter=new Intl.DateTimeFormat('en-US',{timeZone:'America/Los_Angeles',month:'short',day:'2-digit',hour:'2-digit',minute:'2-digit',hour12:false,timeZoneName:'short'});
    for(const field of ['checked_at','forecast_at','fetched_at'])result[field+'_label']=result[field]?formatter.format(new Date(result[field])):'Unavailable';
    result.feedback_ready=false;
    if(['true','1','yes','on'].includes((url.searchParams.get('feedback')??'').trim().toLowerCase())){
      const token=randomHex(12);
      await env.DB.prepare('INSERT INTO contexts(token,created,snapshot) VALUES (?,?,?)').bind(token,now(),JSON.stringify(result)).run();
      result.feedback_ready=true;result.feedback_qr_path='/q/'+token;result.feedback_url=url.origin+'/f/'+token;
    }
    return output(result);
  }
  if(request.method==='GET' && (path.startsWith('/f/')||path.startsWith('/q/'))){
    await init(env);const token=path.split('/').at(-1),snapshot=await context(env,token);
    if(!snapshot)return html('Link expired','<h1>Use a fresh QR code</h1><p>This link has expired. Scan the code after the display refreshes.</p>',410);
    if(path.startsWith('/q/')){
      const qr=qrcode(0,'M');qr.addData(url.origin+'/f/'+token);qr.make();
      return output(qr.createSvgTag({cellSize:2,margin:8,scalable:true}),200,'image/svg+xml');
    }
    let browser=request.headers.get('Cookie')?.match(/(?:^|;\s*)mountain_browser=([a-f0-9]{32})(?:;|$)/)?.[1]??randomHex(16);
    const csrf=await digest(env,'csrf:'+token+':'+browser);
    return output(form(snapshot,token,csrf),200,'text/html; charset=utf-8',{'Set-Cookie':`mountain_browser=${browser}; Path=/; HttpOnly; SameSite=Lax; Max-Age=7776000${url.protocol==='https:'?'; Secure':''}`});
  }
  if(request.method==='POST' && path==='/feedback'){
    await init(env);
    const origin=request.headers.get('Origin');
    if(request.headers.get('Sec-Fetch-Site')==='cross-site'||(origin && origin!=='null' && origin!==url.origin))return output({error:'Form origin does not match.'},403);
    if(request.headers.get('Content-Type')?.split(';')[0]!=='application/x-www-form-urlencoded')return output({error:'Use the feedback form.'},400);
    // A streaming size bound also covers requests without Content-Length.
    if(Number(request.headers.get('Content-Length'))>4096)return output({error:'Form is too large.'},413);
    const reader=request.body?.getReader();let size=0,text='';const decoder=new TextDecoder();
    if(!reader)return output({error:'Missing form'},400);
    while(true){const {value,done}=await reader.read();if(done)break;size+=value.length;if(size>4096){await reader.cancel();return output({error:'Form is too large.'},413);}text+=decoder.decode(value,{stream:true});}
    text+=decoder.decode();const fields=new URLSearchParams(text),token=fields.get('token')??'';
    const snapshot=await context(env,token);
    if(!snapshot)return html('Link expired','<h1>Report not saved</h1><p>Scan a fresh QR code.</p>',410);
    const browser=request.headers.get('Cookie')?.match(/(?:^|;\s*)mountain_browser=([a-f0-9]{32})(?:;|$)/)?.[1];
    if(!browser||!equal(await digest(env,'csrf:'+token+':'+browser),fields.get('csrf')))return html('Report not saved','<h1>Open the feedback form again</h1>',400);
    const answer=fields.get('answer');
    if(!Object.hasOwn(choices,answer)||fields.get('present')!=='yes')return html('Report not saved','<h1>Choose an answer and confirm you are looking now.</h1>',400);
    const browserHash=await digest(env,'browser:'+browser),old=await env.DB.prepare('SELECT answer FROM reports WHERE context_token=? AND browser_hash=?').bind(token,browserHash).first();
    // Identical retries do not extend a vote. A changed answer replaces it;
    // independently issued QR contexts preserve separate historical reports.
    if(!old||old.answer!==answer)await env.DB.prepare(`INSERT INTO reports(received,mountain,viewpoint,answer,browser_hash,context_token,snapshot) VALUES (?,?,?,?,?,?,?)
      ON CONFLICT(context_token,browser_hash) DO UPDATE SET received=excluded.received,answer=excluded.answer,snapshot=excluded.snapshot`).bind(now(),snapshot.mountain,snapshot.viewpoint,answer,browserHash,token,JSON.stringify(snapshot.weather_estimate??snapshot)).run();
    const reports=await activeReports(env.DB,snapshot.mountain,snapshot.viewpoint);
    return output(receipt(snapshot,answer,countReports(reports)),200,'text/html; charset=utf-8');
  }
  return output({error:'Not found'},404);
}

export default {
  async fetch(request,env,ctx){
    try{
      const response=await route(request,env);
      if(response.status<500 && ['/api/visibility','/feedback'].includes(new URL(request.url).pathname)){
        ctx.waitUntil(maybeCleanup(env));
      }
      return response;
    }catch{
      // Keep database/credentials, IPs and submitted tokens out of application logs.
      return html('Temporarily unavailable','<h1>Temporarily unavailable</h1><p>Please try again later.</p>',503);
    }
  }
};
