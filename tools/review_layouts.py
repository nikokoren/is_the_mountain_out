"""Capture the review matrix requested by TRMNL's publishing checklist."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from PIL import Image, ImageDraw, ImageOps
from playwright.sync_api import sync_playwright
from tools.preview import render, SIZES
from tools.browser_support import install_assets, settle

ROOT = Path(__file__).resolve().parents[1]
out = ROOT / '.local/publishing/screens'
out.mkdir(parents=True, exist_ok=True)
sheet = Image.new('RGB', (1200, 1080), '#eeeeee')
draw = ImageDraw.Draw(sheet)
draw.text((16, 8), 'Illustrative fixtures, not live weather - Framework 3.4.0; local browser rendering', fill='black')
profiles = [('OG landscape', None, False, 800, 480),
            ('X landscape', 'v2', False, 1872, 1404),
            ('X portrait', 'v2', True, 1404, 1872)]
with sync_playwright() as p:
    browser = p.chromium.launch(executable_path='/usr/bin/chromium', headless=True, args=['--no-sandbox'])
    page = browser.new_page()
    install_assets(page)
    for row, (label, device, portrait, width, height) in enumerate(profiles):
        page.set_viewport_size({'width': width, 'height': height})
        for col, layout in enumerate(SIZES):
            page.set_content(render('mountain_out', layout, device=device, portrait=portrait))
            settle(page)
            path = out / f'{row}-{layout}.png'
            page.locator('.view').screenshot(path=str(path))
            tile = ImageOps.contain(Image.open(path).convert('RGB'), (280, 300))
            x, y = col * 300, 30 + row * 350
            draw.text((x + 10, y), f'{label} / {layout}', fill='black')
            sheet.paste(tile, (x + (300 - tile.width) // 2, y + 25 + (300 - tile.height) // 2))
    browser.close()
sheet.save(ROOT / 'docs/publishing-layouts.png')
print('Captured 12 views and docs/publishing-layouts.png')
