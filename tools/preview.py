"""Render shared TRMNL named template using standard Liquid for local fixture checks.

TRMNL's `template` wrapper is registered as a DictLoader partial; the actual
markup, render calls, escaping and isolated scope are unchanged.
This uses official Framework 3.4.0 CSS, not a substitute stylesheet.
"""
import argparse
import sys
from pathlib import Path
import io
import re
import qrcode
from qrcode.image.svg import SvgPathImage

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from liquid import Environment, DictLoader
from mountain.model import LABELS

ROOT = Path(__file__).resolve().parents[1]
STATES = ['not_out', 'kinda_out', 'halfway_out', 'mostly_out', 'mountain_out', 'unknown']
SIZES = {'full': (800, 480), 'half_horizontal': (800, 240),
         'half_vertical': (400, 480), 'quadrant': (400, 240)}


def qr_code(value, size=1, level='l'):
    # Mirror TRMNL's native filter contract: responsive viewBox, no fixed dimensions,
    # crisp edges and white fill. Python supplies only the QR encoder in this harness.
    qr = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_L, border=0, box_size=int(size))
    qr.add_data(str(value))
    qr.make(fit=True)
    output = io.BytesIO()
    qr.make_image(image_factory=SvgPathImage).save(output)
    svg = output.getvalue().decode().split('?>', 1)[-1].strip()
    svg = re.sub(r' (?:width|height)="[^"]+"', '', svg, count=2)
    return svg.replace('<svg ', '<svg class="qr-code" shape-rendering="crispEdges" ', 1)


def render(state='mountain_out', layout='full', device=None, portrait=False, **overrides):
    shared = (ROOT / 'plugin/src/shared.liquid').read_text()
    body = shared.split('{% template mountain %}', 1)[1].rsplit('{% endtemplate %}', 1)[0]
    env = Environment(loader=DictLoader({'mountain': body}))
    env.add_filter('qr_code', qr_code)
    data = dict(status=state, verdict=(LABELS[STATES.index(state)].upper() if state != 'unknown' else 'UNKNOWN'),
                image_path='/assets/rainier-seattle.png', explanation='Clear conditions favour a view of the mountain.', location={'name': 'Paradise'},
                forecast_at_label='Oct 27 12:00 PDT', checked_at_label='Oct 27 12:14 PDT')
    data.update(overrides)
    markup = env.from_string((ROOT / f'plugin/src/{layout}.liquid').read_text()).render(**data)
    mashups = {'half_horizontal': '1Tx1B', 'half_vertical': '1Lx1R', 'quadrant': '2x2'}
    opening = f'<div class="mashup mashup--{mashups[layout]}">' if layout in mashups else ''
    closing = '</div>' if opening else ''
    device_class = device or ''
    size = 'lg' if device in ('v2', 'kobo_forma') else 'md'
    screen = f"screen screen--{device_class} screen--{size} screen--1bit screen--fonts-inter" if device_class else 'screen screen--md screen--1bit screen--fonts-inter'
    if portrait:
        screen += ' screen--portrait'
    return f'''<!doctype html><html><head><meta charset="utf-8"><title>Mountain fixture — {state}</title>
    <link rel="stylesheet" href="https://trmnl.com/css/3.4.0/plugins.css">
    <script src="https://trmnl.com/js/3.4.0/plugins.js"></script>
    </head><body class="trmnl"><div class="{screen}">
    {opening}<div class="view view--{layout}">{markup}</div>{closing}</div></body></html>'''



if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', default='/tmp/mountain-previews')
    args = parser.parse_args()
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    for layout in SIZES:
        for state in STATES:
            (output / f'{layout}-{state}.html').write_text(render(state, layout))
    print(f'Wrote 24 fixture previews to {output}')
