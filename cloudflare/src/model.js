// Deliberately mirrors mountain/model.py. Parity fixtures are tested against Python.
import locations from './locations.json' with {type:'json'};
export const {viewpoints, mountains} = locations;
export const states = ['not_out','kinda_out','halfway_out','mostly_out','mountain_out'];
export const labels = ['NOT OUT','KINDA OUT','HALFWAY OUT','MOSTLY OUT','MOUNTAIN OUT!'];
const codes = new Set([0,1,2,3,45,48,51,53,55,56,57,61,63,65,66,67,71,73,75,77,80,81,82,85,86,95,96,99]);
export const iso = t => new Date(t * 1000).toISOString();

export function unknown(reason, now, location, fetched=null, forecast=null) {
  return {status:'unknown',verdict:'UNKNOWN',explanation:reason,location,
    checked_at:iso(now),fetched_at:fetched===null?null:iso(fetched),forecast_at:forecast===null?null:iso(forecast),source:'Open-Meteo',estimate:true};
}

export function calculate(payload, now, fetched, location) {
  const fail = (reason,hour=null) => unknown(reason,now,location,fetched,hour);
  if (!(now-fetched>=0 && now-fetched<=3600)) return fail('Weather response is stale. Try again later.');
  let hour, cloud, visibility, rain, code;
  try {
    const h=payload.hourly;
    if (!Array.isArray(h.time) || !h.time.length) return fail('No hourly forecast available.');
    let index=0;
    for (let i=0;i<h.time.length;i++) {
      if(typeof h.time[i]!=='number' || !Number.isFinite(h.time[i])) throw Error();
      if(Math.abs(h.time[i]-now)<Math.abs(h.time[index]-now)) index=i;
    }
    hour=h.time[index];
    if(Math.abs(now-hour)>5400) return fail('No sufficiently recent forecast hour.',hour);
    const number=(key,low,high,optional=false)=>{
      const v=h[key]?.[index];
      if(v==null && optional) return null;
      if(typeof v!=='number'||!Number.isFinite(v)||v<low||v>high) throw Error();
      return v;
    };
    cloud=number('cloud_cover',0,100);
    for (const layer of ['cloud_cover_low','cloud_cover_mid','cloud_cover_high']) cloud=Math.max(cloud,number(layer,0,100,true)??0);
    visibility=number('visibility',0,1e6);rain=number('precipitation',0,1000);code=number('weather_code',0,99);
    if(!codes.has(code)) throw Error();
  } catch {return fail('Weather data is missing or invalid.');}
  let level=cloud<=15?4:cloud<=35?3:cloud<=60?2:cloud<=85?1:0;
  level=Math.min(level,visibility<5000?0:visibility<10000?1:visibility<20000?2:4);
  if(rain>=1||[45,48,65,67,75,82,86,95,96,99].includes(code)) level=0;
  else if(rain>0||code>=51) level=Math.min(level,1);
  const explanations=['Cloud, fog or precipitation makes a view unlikely.',
    'A partial view is plausible; cloud or haze may hide the mountain.',
    'Mixed conditions may reveal some of the mountain.',
    'Conditions favour a view, with some cloud possible.',
    'Clear conditions favour a view of the mountain.'];
  return {...fail(explanations[level],hour),status:states[level],verdict:labels[level],visibility_m:visibility};
}

export function distance(a,b){
  const r=Math.PI/180,la=a[0]*r,lb=b[0]*r;
  return 6371000*2*Math.asin(Math.sqrt(Math.sin((lb-la)/2)**2+Math.cos(la)*Math.cos(lb)*Math.sin((b[1]-a[1])*r/2)**2));
}
export function samples(location){
  const origin=[location.latitude,location.longitude],summit=mountains[location.mountain].summit;
  return location.id==='paradise'?[origin]:[0,1/3,2/3,1].map(f=>origin.map((v,i)=>v+(summit[i]-v)*f));
}
export function corridor(results,points,now,location){
  const evidence=results.map((r,i)=>({latitude:points[i][0],longitude:points[i][1],status:r.status,forecast_at:r.forecast_at,fetched_at:r.fetched_at,visibility_m:r.visibility_m??null}));
  let result;
  if(results.length!==4||results.some(r=>r.status==='unknown'||!r.forecast_at||Math.abs(now-Date.parse(r.forecast_at)/1000)>5400||!r.fetched_at||now-Date.parse(r.fetched_at)/1000<0||now-Date.parse(r.fetched_at)/1000>3600)){
    result=unknown('A viewing-corridor forecast is unavailable or stale.',now,location);
  }else{
    let level=Math.min(...results.map(r=>states.indexOf(r.status))),burden=0;
    for(let i=0;i<3;i++) burden+=distance(points[i],points[i+1])*(1/Math.max(results[i].visibility_m,1)+1/Math.max(results[i+1].visibility_m,1))/2;
    level=Math.min(level,burden<=1?4:burden<=2?3:burden<=4?2:burden<=8?1:0);
    result={...results[0],status:states[level],verdict:labels[level],location,
      forecast_at:results.map(r=>r.forecast_at).sort()[0],fetched_at:results.map(r=>r.fetched_at).sort()[0],
      explanation:`Weather-only estimate from ${location.name} across the ${mountains[location.mountain].name} corridor; not a confirmed view.`,
      distance_m:Math.round(distance(points[0],points.at(-1))),haze_index:Math.round(burden*1000)/1000};
  }
  return {...result,checked_at:iso(now),corridor_samples:evidence,model:location.id+'-corridor-v1-uncalibrated'};
}

export function locationFrom(params){
  if(['latitude','longitude','name'].some(k=>params.has(k))) throw Error('Choose a named viewpoint.');
  const mountain=params.get('mountain')||'rainier';
  const key=params.get('viewpoint')||(mountain==='hood'?'portland':'seattle');
  const location=viewpoints[key];
  if(!mountains[mountain]||!location||location.mountain!==mountain) throw Error('Choose a valid mountain and viewpoint.');
  return location;
}

export function comparison(status,answer){
  const expected={mountain_out:'out',mostly_out:'out',halfway_out:'partial',kinda_out:'partial',not_out:'not_out'};
  return !expected[status]||answer==='unsure'?'uncompared':expected[status]===answer?'same':'different';
}
