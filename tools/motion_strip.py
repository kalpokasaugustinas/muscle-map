# six frames through one full period of each exercise animation, saved as one 3x2 picture per exercise
# (phases 0, 1/8, 1/4, 3/8, 1/2 = top of the rep, 3/4 = on the way back / the other side for alternating moves)
# usage: python tools/motion_strip.py out_dir [--cam theta,phi | --side] [exercise name ...]   (no names = every animated exercise)
import base64
import io
import sys
from pathlib import Path
from PIL import Image, ImageDraw
from playwright.sync_api import sync_playwright

root = Path(__file__).resolve().parent.parent
args = sys.argv[1:]
out = Path(args.pop(0)) if args else root / 'shots' / 'strips'
cam, tag = None, ''
if '--cam' in args:
    i = args.index('--cam'); t, ph = args[i + 1].split(','); cam = {'theta': float(t), 'phi': float(ph)}
    del args[i:i + 2]; tag = '_cam'
# --side: the exercise's own view turned 90 degrees around the body, near eye level (file name ends in _side)
if '--side' in args:
    args.remove('--side'); cam = {'dtheta': 1.5708, 'phi': 1.45}; tag = '_side'
names = args
out.mkdir(parents=True, exist_ok=True)
phases = [0, 0.125, 0.25, 0.375, 0.5, 0.75]


def safe(name):
    # file-name friendly version of an exercise name
    return ''.join(c if c.isalnum() else '_' for c in name).strip('_').lower()


with sync_playwright() as p:
    browser = p.chromium.launch(channel='chrome', args=['--use-angle=d3d11', '--enable-gpu', '--ignore-gpu-blocklist'])
    page = browser.new_page(viewport={'width': 1800, 'height': 900})
    page.on('pageerror', lambda e: print('page error:', e))
    page.goto((root / 'index.html').as_uri(), wait_until='domcontentloaded', timeout=180000)
    page.wait_for_function('window.mmTest && !document.getElementById("loading")', timeout=180000)
    page.wait_for_timeout(1000)
    todo = names or page.evaluate('mmTest.motions()')
    for name in todo:
        frames = []
        for ph in phases:
            data = page.evaluate('([n, c, ph]) => mmTest.show(n, 0, c, ph)', [name, cam, ph])
            frames.append(Image.open(io.BytesIO(base64.b64decode(data.split(',', 1)[1]))).convert('RGB'))
        # 3 x 2 grid at half size, phase written in the corner
        w, h = frames[0].size[0] // 2, frames[0].size[1] // 2
        grid = Image.new('RGB', (w * 3, h * 2 + 24), (17, 17, 17))
        d = ImageDraw.Draw(grid)
        d.text((6, 4), name, fill=(230, 230, 230))
        for k, (f, ph) in enumerate(zip(frames, phases)):
            x, y = (k % 3) * w, 24 + (k // 3) * h
            grid.paste(f.resize((w, h)), (x, y))
            d.text((x + 6, y + 4), f'ph {ph}', fill=(255, 220, 120))
        grid.save(out / f'{safe(name)}{tag}.png')
        print('strip', name)
    browser.close()
