import {mountains, comparison} from './model.js';
export const choices={out:'Out',partial:'Partly out',not_out:'Not out',unsure:'Can’t tell'};
export const escape=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
export function page(title,content){
  return `<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>${escape(title)} · Is the Mountain Out?</title>
  <style>body{font:18px/1.5 system-ui,sans-serif;max-width:34rem;margin:3rem auto;padding:0 1.25rem;color:#111;background:#fff}h1{line-height:1.15}fieldset{border:0;padding:0}label{display:block;padding:.7rem 0}button{font:inherit;background:#111;color:white;border:0;border-radius:.3rem;padding:.8rem 1.2rem;width:100%;margin-top:1rem}small{display:block;margin-top:1.5rem}input{margin-right:.6rem}a{color:inherit}code{overflow-wrap:anywhere}</style></head><body>${content}</body></html>`;
}
export function home(origin){
  return page('Is the Mountain Out?',`<h1>Is the Mountain Out?</h1><p>Weather estimates and short-lived community observations for Mount Rainier / Tahoma and Mount Hood / Wy’east.</p>
  <p>This service supplies the TRMNL recipe. To report a view, scan the QR code on your display.</p>
  <h2>Connect your TRMNL</h2><p>Set the recipe’s service URL to:</p><code>${escape(origin)}</code>
  <p>Choose a mountain and viewpoint, and enable the optional feedback QR.</p>
  <p>Community reports count for 20 minutes from submission. They are self-reported, not independently verified. Conflicting current reports show UNKNOWN; when none remain, weather estimates resume.</p>
  <small>Weather: <a href="https://open-meteo.com/">Open-Meteo</a>. Weather estimates are uncalibrated, not confirmed observations. A TRMNL’s screen can remain unchanged until its next refresh.</small>`);
}
export function form(snapshot,token,csrf){
  const opts=Object.entries(choices).map(([v,label])=>`<label><input type="radio" name="answer" value="${v}" required>${escape(label)}</label>`).join('');
  return page('Report the view',`<h1>Is ${escape(mountains[snapshot.mountain].name)} out right now?</h1>
  <p>Viewpoint: <strong>${escape(snapshot.location.name)}</strong></p><p>Report what you see now. If you are elsewhere or cannot check, please skip this report.</p>
  <form method="post" action="/feedback"><input type="hidden" name="token" value="${escape(token)}"><input type="hidden" name="csrf" value="${escape(csrf)}">
  <fieldset><legend>What can you see?</legend>${opts}</fieldset>
  <label><input type="checkbox" name="present" value="yes" required>I’m at or near this viewpoint and looking now.</label><button type="submit">Send observation</button></form>
  <small>No name, photo, GPS or IP address is stored by this application. A random first-party cookie lets your latest report replace your previous vote. Reports count for 20 minutes; history is kept for up to 90 days. Community reports are unverified and may disagree. The weather estimate is retained separately.</small>`);
}
export function receipt(snapshot,answer,counts){
  const weather=snapshot.weather_estimate??snapshot;
  const relation=comparison(weather.status,answer);
  const text=relation==='different'?'Your report differs from the weather estimate and is available for review.':relation==='same'?'Your report agrees with the weather estimate.':'Your report was saved without an agreement/disagreement score.';
  return page('Thank you',`<h1>Your observation was saved. Thank you.</h1><p>You reported: <strong>${escape(choices[answer])}</strong>.</p><p>${text}</p>
  <p>The weather estimate behind the code was <strong>${escape(weather.verdict)}</strong>.</p>
  <h2>Current reports — ${escape(snapshot.location.name)}</h2><p>Latest report per browser, past 20 minutes:</p><ul>${Object.entries(choices).map(([v,label])=>`<li>${escape(label)}: ${counts[v]??0}</li>`).join('')}</ul>
  <p>Your report counts for 20 minutes from submission. Updating your report replaces your earlier vote. Other people’s reports do not extend it. Can’t tell does not vote for a condition; conflicting answers produce UNKNOWN until resolved or expired.</p>
  <p>The device will pick up current conditions on its next refresh, usually within 15 minutes. An expired report may remain on a screen until the following refresh.</p>`);
}
