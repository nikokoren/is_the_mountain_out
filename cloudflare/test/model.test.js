import test from 'node:test';
import assert from 'node:assert/strict';
import {execFileSync} from 'node:child_process';
import {calculate,corridor,samples,viewpoints,mountains,locationFrom} from '../src/model.js';

test('Cloudflare weather model matches Python across thresholds, failures and all routes',()=>{
  const script=`
import json
from datetime import datetime,timezone,timedelta
from mountain.model import calculate,calculate_corridor
from mountain.viewpoints import VIEWPOINTS,MOUNTAINS,samples
now=datetime(2026,10,28,12,tzinfo=timezone.utc)
records=[]
for cloud in (0,15,16,35,36,60,61,85,86,100,None,-1):
 for visibility in (0,4999,5000,9999,10000,19999,20000,30000,120000):
  payload={'hourly':{'time':[now.timestamp()],'cloud_cover':[cloud],'visibility':[visibility],'precipitation':[0],'weather_code':[0]}}
  records.append({'payload':payload,'result':calculate(payload,now,now,VIEWPOINTS['seattle'])})
for code in (4,45,48,51,61,65,71,75,95,99):
 payload={'hourly':{'time':[now.timestamp()],'cloud_cover':[0],'visibility':[120000],'precipitation':[0],'weather_code':[code]}}
 records.append({'payload':payload,'result':calculate(payload,now,now,VIEWPOINTS['seattle'])})
routes=[]
for location in VIEWPOINTS.values():
 if location['id']=='paradise':continue
 points=samples(location)
 for v in (1000,10000,24000,30000,40000,120000):
  payload={'hourly':{'time':[now.timestamp()],'cloud_cover':[0],'visibility':[v],'precipitation':[0],'weather_code':[0]}}
  results=[calculate(payload,now,now,location) for _ in points]
  routes.append({'location':location,'results':results,'result':calculate_corridor(results,points,now,location)})
print(json.dumps({'now':now.timestamp(),'records':records,'routes':routes,'viewpoints':VIEWPOINTS,'mountains':MOUNTAINS}))
`;
  const fixture=JSON.parse(execFileSync('python',['-c',script],{cwd:'..',encoding:'utf8'}));
  assert.deepEqual(viewpoints,fixture.viewpoints);assert.deepEqual(mountains,fixture.mountains);
  for(const {payload,result} of fixture.records){
    const actual=calculate(payload,fixture.now,fixture.now,viewpoints.seattle);
    assert.equal(actual.status,result.status);assert.equal(actual.verdict,result.verdict);
  }
  for(const {location,results,result} of fixture.routes){
    const actual=corridor(results,samples(location),fixture.now,location);
    assert.equal(actual.status,result.status);assert.equal(actual.distance_m,result.distance_m);assert.equal(actual.haze_index,result.haze_index);
  }
});

test('missing and stale weather stays unknown; mountain and viewpoint must match',()=>{
  const time=Date.now()/1000;
  for(const payload of [{},null,{hourly:{time:[]}}])assert.equal(calculate(payload,time,time,viewpoints.seattle).status,'unknown');
  assert.equal(calculate({},time,time-3601,viewpoints.seattle).status,'unknown');
  assert.throws(()=>locationFrom(new URLSearchParams('mountain=hood&viewpoint=tacoma')));
  assert.equal(locationFrom(new URLSearchParams('mountain=hood')).id,'portland');
});
