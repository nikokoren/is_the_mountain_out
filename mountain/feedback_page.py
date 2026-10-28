"""Small mobile HTML form. No third-party scripts, analytics or location tracking."""
from html import escape
from mountain.feedback import CHOICES, comparison
from mountain.viewpoints import MOUNTAINS


def page(title, content):
    return f'''<!doctype html><html lang="en"><head><meta charset="utf-8">
    <meta name="viewport" content="width=device-width,initial-scale=1">
    <title>{escape(title)} · Is the Mountain Out?</title>
    <style>body{{font:18px/1.5 system-ui,sans-serif;max-width:32rem;margin:3rem auto;padding:0 1.25rem;color:#111;background:#fff}}
    h1{{line-height:1.15}}fieldset{{border:0;padding:0}}label{{display:block;padding:.7rem 0}}button{{font:inherit;background:#111;color:white;border:0;border-radius:.3rem;padding:.8rem 1.2rem;width:100%;margin-top:1rem}}small{{display:block;margin-top:1.5rem}}input{{margin-right:.6rem}}</style>
    </head><body>{content}</body></html>'''.encode()


def form(snapshot, token, csrf):
    mountain = escape(MOUNTAINS[snapshot['mountain']]['name'])
    location = escape(snapshot['location']['name'])
    options = ''.join(f'<label><input type="radio" name="answer" value="{value}" required>{escape(label)}</label>' for value, label in CHOICES.items())
    # Avoid anchoring reports by asking for the observation before showing any prediction.
    return page('Report the view', f'''<h1>Is {mountain} out right now?</h1>
    <p>Viewpoint: <strong>{location}</strong></p>
    <p>Report what you can see yourself now. If you are elsewhere or cannot check, please skip this report.</p>
    <form method="post" action="/feedback">
    <input type="hidden" name="token" value="{escape(token)}">
    <input type="hidden" name="csrf" value="{escape(csrf)}">
    <fieldset><legend>What can you see?</legend>{options}</fieldset>
    <label><input type="checkbox" name="present" value="yes" required>I’m at or near this viewpoint and looking now.</label>
    <button type="submit">Send observation</button></form>
    <small>No name, photo or precise location is requested. We store your answer, receipt time,
    selected viewpoint and the weather estimate behind this code for up to 90 days.
    A random first-party cookie limits repeat submissions. Reports are unverified and
    do not change the display verdict.</small>''')


def receipt(snapshot, answer, accepted, recent):
    heading = 'Your observation was saved. Thank you.' if accepted else 'You already reported from this viewpoint in this ten-minute window.'
    content = f'<h1>{heading}</h1>'
    if accepted:
        content += f'<p>You reported: <strong>{escape(CHOICES[answer])}</strong>.</p>'
        relation = comparison(snapshot['status'], answer)
        if relation == 'different':
            content += '<p>Your observation differs from the weather estimate. It is now in our review queue.</p>'
        elif relation == 'same':
            content += '<p>Your observation agrees with the weather estimate.</p>'
        else:
            content += '<p>This report was saved without an agreement/disagreement score.</p>'
        content += f'<p>The estimate behind this code was <strong>{escape(snapshot["verdict"])}</strong>.</p>'
    content += f'<h2>Recent reports — {escape(snapshot["location"]["name"])}</h2><p>Past 20 minutes, including your saved report:</p><ul>'
    for value, label in CHOICES.items():
        content += f'<li>{escape(label)}: {recent.get(value, 0)}</li>'
    content += '</ul><p>These are self-reported observations, not independent confirmations. Conflicting reports remain visible. Reports do not automatically change the display verdict.</p>'
    return page('Thank you', content)
