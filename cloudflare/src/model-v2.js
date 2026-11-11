// Experimental model; keep parity with mountain/model_v2.py.
import {calculate,corridor,states,labels,iso} from './model.js';

export function daylight(payload,now){
  const unavailable={state:'unknown',explanation:'Daylight data is unavailable or does not cover this time.'};
  const rises=payload?.daily?.sunrise,sets=payload?.daily?.sunset;
  if(!Array.isArray(rises)||!Array.isArray(sets)||!rises.length||rises.length!==sets.length)return unavailable;
  const intervals=[];
  for(let i=0;i<rises.length;i++){
    const rise=rises[i],set=sets[i];
    if(typeof rise!=='number'||typeof set!=='number'||!Number.isFinite(rise)||!Number.isFinite(set)||
       !(set-rise>0&&set-rise<86400)||!Number.isFinite(new Date(rise*1000).getTime())||!Number.isFinite(new Date(set*1000).getTime()))return unavailable;
    intervals.push([rise,set]);
  }
  intervals.sort((a,b)=>a[0]-b[0]);
  if(intervals.some((p,i)=>i+1<intervals.length&&p[1]>=intervals[i+1][0]))return unavailable;
  for(const [rise,set] of intervals)if(rise<=now&&now<set)return {state:'daylight',sunrise_at:iso(rise),sunset_at:iso(set)};
  const earlier=intervals.map(p=>p[1]).filter(t=>t<=now),later=intervals.map(p=>p[0]).filter(t=>t>now);
  if(earlier.length&&later.length){
    const previous=Math.max(...earlier),next=Math.min(...later);
    if(next-previous>0&&next-previous<86400)return {state:'night',previous_sunset_at:iso(previous),next_sunrise_at:iso(next)};
  }
  return unavailable;
}

function gate(weather,observability,now){
  if(observability.state==='daylight'&&!(Date.parse(observability.sunrise_at)/1000<=now&&now<Date.parse(observability.sunset_at)/1000)||
     observability.state==='night'&&!(Date.parse(observability.previous_sunset_at)/1000<=now&&now<Date.parse(observability.next_sunrise_at)/1000)){
    observability={state:'unknown',explanation:'Daylight data no longer covers this evaluation time.'};
  }
  const result={...weather,weather_conditions:Object.fromEntries(['status','verdict','explanation','limiting_factors'].filter(key=>key in weather).map(key=>[key,weather[key]])),observability};
  if(weather.status!=='unknown'&&observability.state!=='daylight'){
    const night=observability.state==='night';
    Object.assign(result,{status:'unknown',verdict:'UNKNOWN',
      explanation:night?'Outside daylight hours; weather alone cannot confirm the view.':'Daylight information is unavailable; visual assessment is uncertain.',
      limiting_factors:[night?'darkness':'daylight_data_unavailable']});
  }
  return result;
}

export function calculateV2(payload,now,fetched,location,baseline){
  baseline??=calculate(payload,now,fetched,location);
  const result={...baseline,model:'local-weather-v2.1-candidate'};
  if(baseline.weather_inputs){
    const inputs={...baseline.weather_inputs};
    const hasLayers=inputs.cloud_cover_low!=null&&inputs.cloud_cover_mid!=null;
    // Sky coverage is not sight-line obstruction. Mid cloud may sit above the
    // summit; keep it as uncertainty rather than letting it veto a view.
    const cloud=hasLayers?inputs.cloud_cover_low:inputs.cloud_cover;
    inputs.effective_cloud_cover=cloud;
    result.weather_inputs=inputs;result.cloud_basis=hasLayers?'low_layer_with_mid_uncertainty':'total_cloud_fallback';
    const limits={cloud_cover:cloud<=15?4:cloud<=35?3:cloud<=60?2:cloud<=85?1:0,
      mid_cloud_cover:hasLayers&&inputs.cloud_cover_mid>15?3:4,
      // Surface visibility is not a maximum viewing distance for a summit.
      // Retain poor-visibility/fog checks; remove the 10–20 km partial-view cap.
      visibility:inputs.visibility<5000?0:inputs.visibility<10000?1:4,
      precipitation:inputs.precipitation>=1?0:inputs.precipitation>0?1:4,
      weather_code:[45,48,65,67,75,82,86,95,96,99].includes(inputs.weather_code)?0:inputs.weather_code>=51?1:4};
    const level=Math.min(...Object.values(limits));
    Object.assign(result,{status:states[level],verdict:labels[level],
      explanation:'Low-cloud weather estimate with mid-cloud uncertainty; cloud heights and the sight line are unverified.',
      limiting_factors:Object.keys(limits).filter(key=>limits[key]===level&&level<4)});
  }
  return gate(result,daylight(payload,now),now);
}

export function corridorV2(results,points,now,location,observability){
  const weather=results.map(r=>({...r,...r.weather_conditions}));
  const result=corridor(weather,points,now,location);
  delete result.weather_conditions;delete result.observability;delete result.cloud_basis;
  result.model=location.id+'-corridor-v2.1-candidate';
  if(result.status!=='unknown'){
    const level=Math.min(...weather.map(r=>states.indexOf(r.status)));
    Object.assign(result,{status:states[level],verdict:labels[level],
      explanation:'Low-cloud corridor estimate with mid-cloud uncertainty; not a confirmed view.',
      limiting_factors:level<4?['corridor_weather']:[]});
  }
  return gate(result,observability??results[0]?.observability??{state:'unknown'},now);
}

export function compareModels(v1,v2,activeModel='v1'){
  if(!['v1','v2'].includes(activeModel))throw Error('WEATHER_MODEL must be v1 or v2.');
  return {...(activeModel==='v2'?v2:v1),model_comparison:{active_model:activeModel,v1,v2,agrees:v1.status===v2.status}};
}
