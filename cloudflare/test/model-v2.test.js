import test from 'node:test';
import assert from 'node:assert/strict';
import {execFileSync} from 'node:child_process';
import {readFileSync} from 'node:fs';
import {calculateV2,corridorV2,daylight} from '../src/model-v2.js';
import {calculate,corridor,samples,viewpoints} from '../src/model.js';

function normalize(value){
  if(Array.isArray(value))return value.map(normalize);
  if(value&&typeof value==='object')return Object.fromEntries(Object.entries(value).map(([key,v])=>[key,normalize(v)]));
  if(typeof value==='string'&&/^\d{4}-\d\d-\d\dT/.test(value))return new Date(value).toISOString();
  return value;
}

test('Candidate model matches Python for cloud layers, daylight boundaries, missing data and corridors',()=>{
  const script=`
import json,itertools
from datetime import datetime,timedelta,timezone
from mountain.model_v2 import calculate_v2,corridor_v2
from mountain.viewpoints import VIEWPOINTS,samples
anchor=datetime(2026,11,11,20,tzinfo=timezone.utc)
def payload(now,low=0,mid=0,high=0,visibility=24000,rain=0):
 cloud=max(v for v in (low,mid,high) if v is not None)
 return {'hourly':{'time':[now.timestamp()],'cloud_cover':[cloud],'cloud_cover_low':[low],
 'cloud_cover_mid':[mid],'cloud_cover_high':[high],'visibility':[visibility],'precipitation':[rain],'weather_code':[0]},
 'daily':{'sunrise':[(anchor+timedelta(days=d,hours=-5)).timestamp() for d in (-1,0,1)],
 'sunset':[(anchor+timedelta(days=d,hours=5)).timestamp() for d in (-1,0,1)]}}
records=[]
for low,mid,high,vis,rain,hours in itertools.product((0,40,100,None),(0,15,16,50,100,None),(0,100),(4999,9999,10000,18800,19999,20000,24000,120000),(0,1),(0,5,6)):
 now=anchor+timedelta(hours=hours)
 data=payload(now,low,mid,high,vis,rain)
 records.append({'payload':data,'now':now.timestamp(),'fetched':now.timestamp(),
 'result':calculate_v2(data,now,now,VIEWPOINTS['seattle'])})
for daily in (None,{}, {'sunrise':[],'sunset':[]}, {'sunrise':[True],'sunset':[1]},
 {'sunrise':[anchor.timestamp()],'sunset':[anchor.timestamp()-1]}):
 data=payload(anchor);data['daily']=daily
 records.append({'payload':data,'now':anchor.timestamp(),'fetched':anchor.timestamp(),
 'result':calculate_v2(data,anchor,anchor,VIEWPOINTS['seattle'])})
records.append({'payload':payload(anchor),'now':anchor.timestamp(),'fetched':anchor.timestamp()-7200,
 'result':calculate_v2(payload(anchor),anchor,anchor-timedelta(hours=2),VIEWPOINTS['seattle'])})
routes=[]
for key in ('seattle','tacoma','portland'):
 loc=VIEWPOINTS[key]
 for kind in ('clear','high','fog','rain','missing_weather','remote_no_daylight','night'):
  now=anchor+timedelta(hours=6 if kind=='night' else 0)
  data=[payload(now) for _ in range(4)]
  if kind=='high':data=[payload(now,high=100) for _ in range(4)]
  if kind=='fog':data[2]['hourly']['weather_code']=[45]
  if kind=='rain':data[2]['hourly']['precipitation']=[2]
  if kind=='missing_weather':data[2]={}
  if kind=='remote_no_daylight':data[2].pop('daily')
  results=[calculate_v2(p,now,now,loc) for p in data]
  routes.append({'key':key,'payloads':data,'now':now.timestamp(),
   'result':corridor_v2(results,samples(loc),now,loc)})
print(json.dumps({'records':records,'routes':routes}))
`;
  const fixture=JSON.parse(execFileSync('python',['-c',script],{cwd:'..',encoding:'utf8',maxBuffer:8*1024*1024}));
  for(const {payload,now,fetched,result} of fixture.records){
    assert.deepEqual(normalize(calculateV2(payload,now,fetched,viewpoints.seattle)),normalize(result));
  }
  for(const {key,payloads,now,result} of fixture.routes){
    const location=viewpoints[key],points=samples(location);
    const actual=corridorV2(payloads.map(p=>calculateV2(p,now,now,location)),points,now,location);
    assert.deepEqual(normalize(actual),normalize(result));
  }
});

test('Recorded Seattle mid-cloud false negative retains uncertainty without vetoing the view',()=>{
  const fixture=JSON.parse(readFileSync('../tests/fixtures/seattle-2026-11-11-mid-cloud.json','utf8'));
  const seconds=value=>Date.parse(value)/1000,now=seconds(fixture.checked_at),location=viewpoints.seattle;
  const points=fixture.samples.map(s=>[s.latitude,s.longitude]);
  const payloads=fixture.samples.map((sample,index)=>{
    const hourly=Object.fromEntries(Object.entries(sample.weather_inputs).map(([key,value])=>[key,[value]]));
    hourly.time=[seconds(fixture.forecast_at)];
    return {hourly,...(index===0?{daily:{sunrise:[seconds(fixture.sunrise_at)],sunset:[seconds(fixture.sunset_at)]}}:{})};
  });
  const controls=payloads.map((p,i)=>calculate(p,now,seconds(fixture.samples[i].fetched_at),location));
  const candidates=payloads.map((p,i)=>calculateV2(p,now,seconds(fixture.samples[i].fetched_at),location));
  assert.equal(corridor(controls,points,now,location).status,fixture.status_before);
  const result=corridorV2(candidates,points,now,location,daylight(payloads[0],now));
  assert.equal(result.status,'mostly_out');
  assert.equal(result.model,'seattle-corridor-v2.1-candidate');
  assert.equal(result.haze_index,4.026);
  assert.equal(result.observability.state,'daylight');
  for(const sample of result.corridor_samples){
    assert.equal(sample.status,'mostly_out');assert.deepEqual(sample.limiting_factors,['mid_cloud_cover']);
  }
});
