# screenshots of the 3d exercise animations: start pose (u = 0) and end pose (u = 1) per exercise,
# plus one side-by-side sheet per run, for reviewing new motions.
# usage: python tools/motion_shots.py [out_dir] [exercise name ...]   (no names = every animated exercise)
import base64
import sys
from pathlib import Path
from playwright.sync_api import sync_playwright

root = Path(__file__).resolve().parent.parent
out = Path(sys.argv[1]) if len(sys.argv) > 1 else root / 'shots'
# optional --back: look from behind (to check the shoulder blades)
back = '--back' in sys.argv
names = [a for a in sys.argv[2:] if a != '--back']
out.mkdir(parents=True, exist_ok=True)


def safe(name):
    # file-name friendly version of an exercise name
    return ''.join(c if c.isalnum() else '_' for c in name).strip('_').lower()


with sync_playwright() as p:
    browser = p.chromium.launch(channel='chrome', args=['--use-angle=d3d11', '--enable-gpu', '--ignore-gpu-blocklist'])
    page = browser.new_page(viewport={'width': 1300, 'height': 820})
    page.on('pageerror', lambda e: print('page error:', e))
    page.goto((root / 'index.html').as_uri(), wait_until='domcontentloaded', timeout=180000)
    # wait for the anatomy model to load (the test hook exists once the module ran)
    page.wait_for_function('window.mmTest && !document.getElementById("loading")', timeout=180000)
    page.wait_for_timeout(1000)
    todo = names or page.evaluate('mmTest.motions()')
    files = []
    for name in todo:
        pair = []
        for u in (0, 1):
            # the hook poses the body, renders and returns the canvas as a png data url
            data = page.evaluate('([n, u, c]) => mmTest.show(n, u, c)', [name, u, {'theta': 3.14, 'phi': 1.4} if back else None])
            f = out / f'{safe(name)}_{u}.png'
            f.write_bytes(base64.b64decode(data.split(',', 1)[1]))
            pair.append(f)
        files.append((name, pair))
        print('shot', name)
    # contact sheet: one row per exercise, start | end
    rows = ''.join(
        f'<div class="r"><h3>{n}</h3><img src="{a.as_uri()}"><img src="{b.as_uri()}"></div>' for n, (a, b) in files)
    sheet = out / 'sheet.html'
    sheet.write_text('<html><body style="background:#111;color:#ddd;font:14px sans-serif">'
                     '<style>.r{margin:8px 0}.r img{width:48%;margin-right:1%}</style>' + rows + '</body></html>',
                     encoding='utf-8')
    browser.close()
    print('sheet:', sheet)
