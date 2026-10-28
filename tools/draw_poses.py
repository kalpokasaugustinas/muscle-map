# draws simple line-art exercise illustrations (black outline on white, start + end frame) as svg,
# in the same format as the everkinetic drawings used in img/poses/.
# usage: python tools/draw_poses.py [--sheet path/to/contact_sheet.html]
#
# figures are built from a jointed 2d body:
#   side view  - faces +x; limb angles in degrees from straight down, + = forward;
#                torso angle from straight up, + = leaning forward; bend = spine curve (+ rounds the back)
#   front view - faces the viewer; limb angles from straight down, + = toward viewer's right
# world coordinates have y pointing up; the floor is y = 0.
import math, pathlib, sys

OUT = pathlib.Path(__file__).resolve().parent.parent / 'img' / 'poses'

# segment lengths
TORSO, NECK, UA, FA, TH, SH = 50, 7, 29, 26, 43, 41
SW_BODY, SW_PROP, SW_HINT = 4.5, 3.5, 2.2

def v(a, b): return (a[0] + b[0], a[1] + b[1])
def s(p, k): return (p[0] * k, p[1] * k)
def sub(a, b): return (a[0] - b[0], a[1] - b[1])
def norm(p):
    l = math.hypot(*p) or 1
    return (p[0] / l, p[1] / l)
def limb_dir(deg):   # angle from straight down, + rotates toward +x
    r = math.radians(deg)
    return (math.sin(r), -math.cos(r))
def up_dir(deg):     # angle from straight up, + rotates toward +x
    r = math.radians(deg)
    return (math.sin(r), math.cos(r))
def rot90cw(d): return (d[1], -d[0])
def rot90ccw(d): return (-d[1], d[0])
def lerp(a, b, t): return a + (b - a) * t
def interp(table, t):
    # piecewise linear interpolation in a [(t, value...)] table
    for (t0, *a), (t1, *b) in zip(table, table[1:]):
        if t0 <= t <= t1:
            k = (t - t0) / (t1 - t0) if t1 > t0 else 0
            return [lerp(x, y, k) for x, y in zip(a, b)]
    return list(table[-1][1:])


class Canvas:
    """collects shapes (world coords, y up) and writes an svg with y flipped."""
    def __init__(self):
        self.items, self.pts = [], []

    def _track(self, pts, pad=0):
        for x, y in pts:
            self.pts += [(x - pad, y - pad), (x + pad, y + pad)]

    def poly(self, pts, sw=SW_BODY, fill='#fff', closed=True):
        self._track(pts, sw)
        d = ' '.join(f'{x:.1f},{-y:.1f}' for x, y in pts)
        tag = 'polygon' if closed else 'polyline'
        self.items.append(f'<{tag} points="{d}" fill="{fill if closed else "none"}" stroke="#000" stroke-width="{sw}" stroke-linejoin="round" stroke-linecap="round"/>')

    def line(self, a, b, sw=SW_PROP):
        self.poly([a, b], sw=sw, closed=False)

    def curve(self, a, c, b, sw=SW_HINT):
        # quadratic bezier a -> b with control c
        self._track([a, b], sw)
        self.items.append(f'<path d="M{a[0]:.1f},{-a[1]:.1f} Q{c[0]:.1f},{-c[1]:.1f} {b[0]:.1f},{-b[1]:.1f}" fill="none" stroke="#000" stroke-width="{sw}" stroke-linecap="round"/>')

    def circle(self, c, r, sw=SW_PROP, fill='#fff'):
        self._track([c], r + sw)
        self.items.append(f'<circle cx="{c[0]:.1f}" cy="{-c[1]:.1f}" r="{r:.1f}" fill="{fill}" stroke="#000" stroke-width="{sw}"/>')

    def ellipse(self, c, rx, ry, deg, sw=SW_BODY):
        # deg = rotation of the rx axis from +x (counter-clockwise, world)
        self._track([c], max(rx, ry) + sw)
        self.items.append(f'<ellipse cx="{c[0]:.1f}" cy="{-c[1]:.1f}" rx="{rx:.1f}" ry="{ry:.1f}" transform="rotate({-deg:.1f} {c[0]:.1f} {-c[1]:.1f})" fill="#fff" stroke="#000" stroke-width="{sw}"/>')

    def rect(self, a, b, sw=SW_PROP):
        (x0, y0), (x1, y1) = a, b
        self.poly([(x0, y0), (x1, y0), (x1, y1), (x0, y1)], sw=sw)

    def bar(self, a, b, w, sw=SW_PROP):
        # thick bar (rotated rectangle) from a to b with width w
        n = s(rot90ccw(norm(sub(b, a))), w / 2)
        self.poly([v(a, n), v(b, n), sub(b, n), sub(a, n)], sw=sw)

    def svg(self, pad=12):
        xs = [p[0] for p in self.pts]; ys = [-p[1] for p in self.pts]
        x0, x1, y0, y1 = min(xs) - pad, max(xs) + pad, min(ys) - pad, max(ys) + pad
        w, h = x1 - x0, y1 - y0
        body = '\n'.join(self.items)
        return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{x0:.1f} {y0:.1f} {w:.1f} {h:.1f}" width="{w:.0f}" height="{h:.0f}">\n'
                f'<rect x="{x0:.1f}" y="{y0:.1f}" width="{w:.1f}" height="{h:.1f}" fill="#fff"/>\n{body}\n</svg>\n')


def capsule(p0, p1, r0, r1, n=10):
    """tapered limb outline between joints p0 and p1 with end radii r0, r1."""
    d = norm(sub(p1, p0)); a = math.atan2(d[1], d[0])
    pts = []
    for i in range(n + 1):   # cap around p1 (front half)
        t = a - math.pi / 2 + math.pi * i / n
        pts.append((p1[0] + r1 * math.cos(t), p1[1] + r1 * math.sin(t)))
    for i in range(n + 1):   # cap around p0 (back half)
        t = a + math.pi / 2 + math.pi * i / n
        pts.append((p0[0] + r0 * math.cos(t), p0[1] + r0 * math.sin(t)))
    return pts


# ---------------------------------------------------------------- side view figure
def side_figure(c, P):
    """P: dict with torso, bend, head, aN/aF (upper, fore[, hand]), lN/lF (thigh, shin, foot), hip, protract.
    returns joints dict. draws far limbs, torso, head, near limbs in order."""
    hip = P.get('hip', (0, 0))
    td = up_dir(P.get('torso', 0))
    front = rot90cw(td)          # chest side
    bend = P.get('bend', 0)      # + rounds the back (cat), - arches (cow)
    # spine as a quadratic curve hip -> shoulder, control pushed toward the back by `bend`
    sh = v(hip, s(td, TORSO))
    ctrl = v(s(v(hip, sh), 0.5), s(front, -bend))
    def spine(t):
        a = s(hip, (1 - t) ** 2); b = s(ctrl, 2 * (1 - t) * t); cc = s(sh, t * t)
        return v(v(a, b), cc)
    def spine_dir(t):
        d = v(s(sub(ctrl, hip), 2 * (1 - t)), s(sub(sh, ctrl), 2 * t))
        return norm(d)
    # widths (front, back) along the spine: glutes, waist, chest, shoulders
    W = [(0, 10, 14), (0.12, 11, 15), (0.38, 10.5, 9.5), (0.72, 16.5, 12.5), (0.93, 13.5, 12.5), (1.0, 7.5, 9.5)]
    frontpts, backpts = [], []
    for i in range(15):
        t = i / 14
        f, b = interp(W, t)
        p = spine(t); dd = spine_dir(t); fn = rot90cw(dd)
        frontpts.append(v(p, s(fn, f))); backpts.append(v(p, s(fn, -b)))
    torso_poly = frontpts + backpts[::-1]

    J = {'hip': hip, 'shoulder': sh, 'chestF': v(spine(0.72), s(rot90cw(spine_dir(0.72)), 14.5)),
         'backP': v(spine(0.72), s(rot90cw(spine_dir(0.72)), -11)), 'butt': v(spine(0.1), s(rot90cw(spine_dir(0.1)), -13)),
         'belly': v(spine(0.35), s(rot90cw(spine_dir(0.35)), 9)), 'lowback': v(spine(0.3), s(rot90cw(spine_dir(0.3)), -8.5))}
    # head
    hd = up_dir(P.get('torso', 0) + P.get('head', 0) + bend * 0.6)
    neck_base = v(sh, s(spine_dir(1.0), 2))
    neck_top = v(neck_base, s(hd, NECK))
    head_c = v(neck_top, s(hd, 9))
    J['head'] = head_c; J['neck'] = neck_top

    shoulder_j = v(sh, s(front, -2 + P.get('protract', 0)))
    def arm(spec, base):
        ua, fa = spec[0], spec[1]
        hand_a = spec[2] if len(spec) > 2 else fa
        e = v(base, s(limb_dir(ua), UA)); w = v(e, s(limb_dir(fa), FA))
        hc = v(w, s(limb_dir(hand_a), 5))
        return base, e, w, hc, hand_a
    def leg(spec, base):
        th, shn, ft = spec
        k = v(base, s(limb_dir(th), TH)); a = v(k, s(limb_dir(shn), SH))
        return base, k, a, ft

    def draw_leg(L, off=(0, 0)):
        b, k, a, ft = [v(p, off) if isinstance(p, tuple) else p for p in L]
        c.poly(capsule(b, k, 12, 7.5))
        c.poly(capsule(k, a, 7.5, 4.6))
        # calf bulge + quad line (muscle hints)
        c.curve(v(b, s(sub(k, b), 0.3)), v(v(b, s(sub(k, b), 0.5)), s(rot90cw(norm(sub(k, b))), 4)), v(b, s(sub(k, b), 0.75)))
        # foot
        f = limb_dir(ft); upv = rot90ccw(f)
        loc = [(-5, -4.5), (-6.5, 1), (2, 4), (9, 1.5), (17, -1.5), (17, -4.5)]
        c.poly([v(a, v(s(f, u), s(upv, w))) for u, w in loc])
        return {'knee': k, 'ankle': a, 'toe': v(a, v(s(f, 17), s(upv, -3))), 'heel': v(a, v(s(f, -5), s(upv, -4.5)))}

    def draw_arm(A, off=(0, 0)):
        b, e, w, hc, ha = A
        b, e, w, hc = [v(p, off) for p in (b, e, w, hc)]
        c.poly(capsule(b, e, 7.4, 5.4))
        c.poly(capsule(e, w, 5.6, 3.8))
        c.ellipse(hc, 6, 4, math.degrees(math.atan2(*reversed(limb_dir(ha)))))
        c.curve(v(b, s(sub(e, b), 0.25)), v(v(b, s(sub(e, b), 0.5)), s(rot90cw(norm(sub(e, b))), 3)), v(b, s(sub(e, b), 0.75)))
        return {'elbow': e, 'wrist': w, 'hand': hc}

    off = P.get('far_off', (-3, 2.5))
    lF = leg(P.get('lF', (0, 0, 90)), v(hip, s(front, 1)))
    lN = leg(P.get('lN', (0, 0, 90)), v(hip, s(front, 1)))
    aF = arm(P.get('aF', (-5, 5)), shoulder_j)
    aN = arm(P.get('aN', (5, 10)), shoulder_j)

    jl = draw_leg(lF, off); J.update({k + 'F': p for k, p in jl.items()})
    ja = draw_arm(aF, off); J.update({k + 'F': p for k, p in ja.items()})
    c.poly(torso_poly)
    # torso hints: pec line + ab line
    c.curve(v(spine(0.6), s(rot90cw(spine_dir(0.6)), 6)), v(spine(0.62), s(rot90cw(spine_dir(0.62)), 13)), v(spine(0.8), s(rot90cw(spine_dir(0.8)), 13)))
    c.curve(v(spine(0.25), s(rot90cw(spine_dir(0.25)), 4)), v(spine(0.35), s(rot90cw(spine_dir(0.35)), 6)), v(spine(0.48), s(rot90cw(spine_dir(0.48)), 5)))
    c.poly(capsule(neck_base, neck_top, 5.5, 5))
    c.ellipse(head_c, 11.5, 9.5, math.degrees(math.atan2(hd[1], hd[0])))
    jl = draw_leg(lN); J.update({k + 'N': p for k, p in jl.items()})
    ja = draw_arm(aN); J.update({k + 'N': p for k, p in ja.items()})
    return J


# ---------------------------------------------------------------- front view figure
def front_figure(c, P):
    """P: torso (tilt), aR/aL (upper, fore), lR/lL (thigh, shin), hip. R = figure's right = viewer's left."""
    hip = P.get('hip', (0, 0))
    td = up_dir(P.get('torso', 0)); side = rot90cw(td)   # side -> viewer's right
    sp = lambda t: v(hip, s(td, TORSO * t))
    W = [(0, 19), (0.15, 18), (0.38, 15), (0.72, 21), (0.9, 24), (0.97, 17), (1.0, 7.5)]
    left, right = [], []
    for i in range(15):
        t = i / 14; w = interp(W, t)[0]
        left.append(v(sp(t), s(side, -w))); right.append(v(sp(t), s(side, w)))
    J = {'hip': hip, 'shoulder': sp(0.9)}
    shR, shL = v(sp(0.9), s(side, -18)), v(sp(0.9), s(side, 18))
    hR, hL = v(sp(0.02), s(side, -9)), v(sp(0.02), s(side, 9))

    def arm(spec, base):
        e = v(base, s(limb_dir(spec[0]), UA)); w = v(e, s(limb_dir(spec[1]), FA * spec[2] if len(spec) > 2 else FA))
        return base, e, w
    def leg(spec, base):
        k = v(base, s(limb_dir(spec[0]), TH)); a = v(k, s(limb_dir(spec[1]), SH))
        return base, k, a
    def draw_leg(L, sgn):
        b, k, a = L
        c.poly(capsule(b, k, 12, 7.5)); c.poly(capsule(k, a, 7.5, 4.8))
        c.curve(v(b, s(sub(k, b), 0.3)), v(v(b, s(sub(k, b), 0.55)), s(rot90cw(norm(sub(k, b))), -3 * sgn)), v(b, s(sub(k, b), 0.8)))
        c.ellipse(v(a, (sgn * 3, -3)), 6.5, 4.5, 0)
        return {'knee': k, 'ankle': a}
    def draw_arm(A):
        b, e, w = A
        c.poly(capsule(b, e, 7.5, 5.5)); c.poly(capsule(e, w, 5.6, 3.9))
        hd = norm(sub(w, e)); hc = v(w, s(hd, 5))
        c.ellipse(hc, 6, 4.2, math.degrees(math.atan2(hd[1], hd[0])))
        return {'elbow': e, 'wrist': w, 'hand': hc}

    LR, LL = leg(P.get('lR', (-4, 0)), hR), leg(P.get('lL', (4, 0)), hL)
    AR, AL = arm(P.get('aR', (-8, -4)), shR), arm(P.get('aL', (8, 4)), shL)
    # legs and arms behind the torso first if flagged, else after
    J.update({k + 'R': p for k, p in draw_leg(LR, -1).items()})
    J.update({k + 'L': p for k, p in draw_leg(LL, 1).items()})
    behind = P.get('arms_behind', ())
    for nm, A in (('R', AR), ('L', AL)):
        if nm in behind: J.update({k + nm: p for k, p in draw_arm(A).items()})
    c.poly(left + right[::-1])
    # pecs + abs hints
    c.curve(v(sp(0.62), s(side, -14)), v(sp(0.6), s(side, -4)), v(sp(0.66), s(side, 0)))
    c.curve(v(sp(0.62), s(side, 14)), v(sp(0.6), s(side, 4)), v(sp(0.66), s(side, 0)))
    c.line(sp(0.22), sp(0.52), SW_HINT)
    neck_top = v(sp(1.0), s(td, NECK))
    c.poly(capsule(sp(0.97), neck_top, 6, 5.5))
    hc = v(neck_top, s(td, 10))
    c.ellipse(hc, 9.5, 11.5, math.degrees(math.atan2(side[1], side[0])))
    J['head'] = hc
    for nm, A in (('R', AR), ('L', AL)):
        if nm not in behind: J.update({k + nm: p for k, p in draw_arm(A).items()})
    return J


# ---------------------------------------------------------------- props
def dumbbell(c, p):            # seen end-on
    c.circle(p, 8.5); c.circle(p, 3, sw=2.5)
def plate(c, p, r=16):
    c.circle(p, r); c.circle(p, 4, sw=2.5)
def bench(c, x0, x1, top, legs=True):
    c.rect((x0, top - 7), (x1, top))
    if legs:
        for x in (x0 + 8, x1 - 8): c.bar((x, top - 7), (x, 0), 5)
def cable(c, hand, anchor, column=True):
    c.line(hand, anchor, 2.5); c.circle(anchor, 4.5, sw=3)
    if column:
        x = anchor[0] + (6 if anchor[0] > hand[0] else -6)
        c.bar((x, 0), (x, max(anchor[1] + 25, 150)), 9)
def wall(c, x, top=210, w=8):
    c.rect((x - w / 2, 0), (x + w / 2, top))
def floor(c, x0, x1, y=0):
    c.line((x0, y), (x1, y), 3)

# ---------------------------------------------------------------- pose helpers
def stand(**k):
    P = dict(torso=0, aN=(6, 10), aF=(-6, 4), lN=(2, 0, 90), lF=(-2, 0, 90))
    P.update(k); return P
def quad(**k):       # on hands and knees, facing +x
    P = dict(torso=90, aN=(0, 0, 90), aF=(0, 0, 90), lN=(0, -90, -100), lF=(0, -90, -100), head=-10)
    P.update(k); return P
def supine(**k):     # lying on the back, head to the left
    P = dict(torso=-90, head=0, aN=(88, 88), aF=(88, 88), lN=(90, 90, 175), lF=(90, 90, 175))
    P.update(k); return P
def plank(**k):      # forearm plank facing +x
    P = dict(torso=80, aN=(-5, 90, 90), aF=(-5, 90, 90), lN=(-100, -100, -20), lF=(-100, -100, -20), head=-5)
    P.update(k); return P
def walk(phase, **k):
    a = 22 if phase == 0 else -22
    P = dict(torso=4, aN=(-a * 0.8, -a * 0.5 + 15), aF=(a * 0.8, a * 0.5 + 15), lN=(a, a * 0.2 - (8 if a < 0 else 0), 90 + (a * 0.6 if a > 0 else 15)),
             lF=(-a, -a * 0.2 - (8 if a > 0 else 0), 90 + (-a * 0.6 if a < 0 else 15)))
    P.update(k); return P
def kneel_half(**k):  # near leg forward (foot flat), far knee on the floor
    P = dict(torso=0, lN=(88, 2, 90), lF=(-20, -95, -175), aN=(-15, 70), aF=(-15, 70))
    P.update(k); return P

# ---------------------------------------------------------------- the exercises
# slug: (view, [start pose, end pose], props(c, J, frame) or None)
def P_serratus(c, J, f): cable(c, J['handN'], (J['shoulder'][0] - 110, J['shoulder'][1] - 4))
def P_csrow(c, J, f):
    # incline bench under the chest + dumbbells
    hip, sh = J['hip'], J['shoulder']
    d = norm(sub(sh, hip)); n = rot90cw(d)
    a, b = v(v(hip, s(d, 4)), s(n, 21)), v(v(hip, s(d, 60)), s(n, 21))
    c.bar(a, b, 8); c.bar(v(s(v(a, b), 0.5), s(n, 4)), (s(v(a, b), 0.5)[0] + 10, 0), 6)
    c.bar((hip[0] - 25, hip[1] - 14), (hip[0] + 8, hip[1] - 14), 7); c.bar((hip[0] - 8, hip[1] - 14), (hip[0] - 8, 0), 6)
    dumbbell(c, J['handN'])
def P_highrow(c, J, f): cable(c, J['handN'], (J['shoulder'][0] + 125, J['shoulder'][1] + 60))
def P_landmine(c, J, f):
    anchor = (J['hip'][0] + 150, 4); h = J['handN']
    c.bar(anchor, h, 5); plate(c, v(h, s(norm(sub(anchor, h)), 26)), 13); c.circle(anchor, 5)
def P_facepull(c, J, f): cable(c, J['handN'], (J['shoulder'][0] + 130, J['head'][1] - 6))
def P_wristcurl(c, J, f):
    bench(c, J['hip'][0] - 30, J['hip'][0] + 18, J['butt'][1] - 2); dumbbell(c, J['handN'])
def P_farmer(c, J, f): dumbbell(c, J['handN'])
def P_suitcase(c, J, f): dumbbell(c, J['handN'])
def P_copen(c, J, f):
    x = J['ankleN'][0]; bench(c, x - 25, x + 25, J['ankleN'][1] - 5)
def P_woodchop(c, J, f): cable(c, J['handR'], (J['hip'][0] + 120, 175))
def P_stir(c, J, f):
    e = J['elbowN']; c.circle((e[0] + 14, 22), 22)
def P_hang(c, J, f): c.circle(J['handN'], 4); c.line((J['handN'][0] - 40, J['handN'][1]), (J['handN'][0] + 40, J['handN'][1]), 3)
def P_pallof(c, J, f): cable(c, J['handN'], (J['shoulder'][0] - 120, J['handN'][1] if f == 1 else J['shoulder'][1] - 18))
def P_tib(c, J, f): wall(c, J['backP'][0] - 6)
def P_cycle(c, J, f):
    hip = J['hip']
    rear, front_w = (hip[0] - 22, 32), (hip[0] + 78, 32)
    c.circle(rear, 30); c.circle(front_w, 30)
    crank = (hip[0] + 14, 30)
    for a, b in [(rear, crank), (crank, (hip[0] - 4, hip[1] - 9)), ((hip[0] - 4, hip[1] - 9), rear), (crank, (hip[0] + 62, 88)), ((hip[0] + 62, 88), front_w), ((hip[0] - 4, hip[1] - 9), (hip[0] + 62, 88))]:
        c.line(a, b, 4)
    c.bar((hip[0] - 16, hip[1] - 9), (hip[0] + 6, hip[1] - 9), 5)
    c.line((hip[0] + 62, 88), J['handN'], 4)
    c.circle(crank, 6)
def P_hike(c, J, f):
    # backpack on the back + trekking pole in the near hand
    bp, sh = J['backP'], J['shoulder']
    d = norm(sub(sh, J['hip'])); n = rot90ccw(d) if d[0] >= 0 else rot90cw(d)
    back_dir = s(rot90cw(d), -1)
    p0, p1 = v(J['lowback'], s(back_dir, 2)), v(v(sh, s(back_dir, 10)), s(d, -4))
    c.bar(v(p0, s(back_dir, 9)), v(p1, s(back_dir, 9)), 20)
    h = J['handN']; c.line(v(h, (0, 8)), (h[0] + 14, 0), 3)
def P_couch(c, J, f): wall(c, J['ankleF'][0] - 9)
def P_hamstring(c, J, f): c.rect((J['heelN'][0] - 25, 0), (J['heelN'][0] + 25, J['heelN'][1] + 1))
def P_criss(c, J, f): c.rect((J['hip'][0] - 30, 0), (J['hip'][0] + 30, J['hip'][1] - 12))
def P_strap(c, J, f): c.line(J['handN'], v(J['toeN'], (-2, 0)), 2.5)
def P_roller(c, J, f): c.circle((J['backP'][0], 10), 10)
def P_door(c, J, f):
    x = J['elbowN'][0] - 7; c.rect((x - 5, 0), (x + 5, 215))
def P_child(c, J, f): pass
def P_calf(c, J, f): wall(c, J['handN'][0] + 6)
def P_bss(c, J, f):
    x = J['toeF'][0]; bench(c, x - 34, x + 16, J['toeF'][1] - 1); dumbbell(c, J['handN'])
def P_cablecrunch(c, J, f): cable(c, J['handN'], (J['head'][0] + 70, 215))
def P_extrot(c, J, f):
    # cable comes from the figure's left side (viewer's right), across the body
    cable(c, J['handR'], (J['hip'][0] + 105, J['handR'][1] + 2))

EXERCISES = {
    'cable-serratus-punch': ('side', [stand(aN=(88, 88), lN=(12, 4, 90), lF=(-14, -6, 90)),
                                      stand(aN=(88, 88), protract=8, torso=4, lN=(12, 4, 90), lF=(-14, -6, 90))], P_serratus),
    'chest-supported-row': ('side', [dict(torso=52, lN=(14, -4, 90), lF=(10, -8, 90), aN=(2, 0), aF=(-2, -2), head=-20),
                                     dict(torso=52, lN=(14, -4, 90), lF=(10, -8, 90), aN=(-62, 6), aF=(-58, 4), head=-20)], P_csrow),
    'standing-cable-high-row': ('side', [stand(torso=-6, aN=(128, 128), aF=(124, 124)),
                                         stand(torso=-8, aN=(-72, 150), aF=(-68, 146))], P_highrow),
    'landmine-press': ('side', [stand(torso=8, aN=(12, 168), aF=(0, 60), lN=(18, 4, 90), lF=(-16, -8, 90)),
                                stand(torso=12, aN=(128, 132), aF=(0, 60), lN=(18, 4, 90), lF=(-16, -8, 90))], P_landmine),
    'wall-slides': ('front', [dict(aR=(-62, 182), aL=(62, 178), lR=(-4, 0), lL=(4, 0)),
                              dict(aR=(-152, -165), aL=(152, 165), lR=(-4, 0), lL=(4, 0))], 'wallfront'),
    'face-pull': ('side', [stand(aN=(92, 92), aF=(88, 88), lN=(10, 2, 90), lF=(-10, -4, 90)),
                           stand(torso=-4, aN=(-72, 152), aF=(-68, 148), lN=(10, 2, 90), lF=(-10, -4, 90))], P_facepull),
    'wrist-curl': ('side', [dict(torso=28, lN=(90, 0, 90), lF=(86, -2, 90), aN=(32, 90, 40), aF=(28, 88, 40)),
                            dict(torso=28, lN=(90, 0, 90), lF=(86, -2, 90), aN=(32, 90, 150), aF=(28, 88, 150))], P_wristcurl),
    'reverse-wrist-curl': ('side', [dict(torso=28, lN=(90, 0, 90), lF=(86, -2, 90), aN=(32, 90, 35), aF=(28, 88, 35)),
                                    dict(torso=28, lN=(90, 0, 90), lF=(86, -2, 90), aN=(32, 90, 128), aF=(28, 88, 128))], P_wristcurl),
    'farmers-walk': ('side', [walk(0, aN=(0, 0), aF=(0, 0)), walk(1, aN=(0, 0), aF=(0, 0))], P_farmer),
    'bird-dog': ('side', [quad(), quad(aN=(88, 88, 90), lF=(-88, -88, -170), head=0)], None),
    'suitcase-carry': ('side', [walk(0, aN=(0, 0), aF=(18, 30)), walk(1, aN=(0, 0), aF=(-15, 10))], P_suitcase),
    'hollow-body-hold': ('side', [supine(aN=(-92, -92), aF=(-92, -92)), supine(torso=-72, head=15, aN=(-128, -128), aF=(-128, -128), lN=(68, 68, 160), lF=(68, 68, 160))], None),
    'rkc-plank': ('side', [plank(), plank(torso=82, lN=(-96, -96, -15), lF=(-96, -96, -15), bend=3)], None),
    'bear-plank': ('side', [quad(lN=(0, -90, -100), lF=(0, -90, -100)), quad(lN=(8, -72, -30), lF=(8, -72, -30))], None),
    'copenhagen-plank': ('side', [plank(torso=70, aN=(-5, 90, 90), aF=(-5, 90, 90), lN=(-108, -108, -5), lF=(-120, -40, -100)),
                                  plank(torso=72, lN=(-108, -108, -5), lF=(-108, -108, -5))], P_copen),
    'cable-woodchop': ('front', [dict(torso=-6, aR=(132, 132), aL=(150, 150), lR=(-14, -4), lL=(14, 4)),
                                 dict(torso=8, aR=(-28, -28), aL=(-12, -12), lR=(-16, 6), lL=(12, 2))], P_woodchop),
    'stir-the-pot': ('side', [plank(torso=62, aN=(10, 88, 88), aF=(10, 88, 88), lN=(-115, -115, -25), lF=(-115, -115, -25)),
                              plank(torso=62, aN=(22, 102, 102), aF=(22, 102, 102), lN=(-115, -115, -25), lF=(-115, -115, -25))], P_stir),
    'mountain-climbers': ('side', [dict(torso=72, aN=(0, 0, 90), aF=(0, 0, 90), lN=(68, -40, -30), lF=(-108, -108, -20), head=-8),
                                   dict(torso=72, aN=(0, 0, 90), aF=(0, 0, 90), lN=(-108, -108, -20), lF=(68, -40, -30), head=-8)], None),
    'russian-twist': ('side', [dict(torso=-35, lN=(115, 20, 100), lF=(110, 16, 100), aN=(62, 98), aF=(58, 94)),
                               dict(torso=-35, lN=(115, 20, 100), lF=(110, 16, 100), aN=(15, 40), aF=(25, 62))], 'twist'),
    'plank': ('side', [plank(lN=(-150, -90, -170), lF=(-150, -90, -170), torso=70), plank()], None),
    'hanging-leg-raise': ('side', [stand(hang=True, aN=(178, 178), aF=(176, 176), lN=(2, 0, 30), lF=(-2, -2, 30)),
                                   stand(hang=True, aN=(178, 178), aF=(176, 176), lN=(88, 88, 150), lF=(86, 86, 150), torso=-6)], P_hang),
    'pallof-press': ('side', [stand(aN=(25, 152), aF=(20, 148), lN=(8, 0, 90), lF=(-8, 0, 90)),
                              stand(aN=(88, 88), aF=(86, 86), lN=(8, 0, 90), lF=(-8, 0, 90))], P_pallof),
    'dead-bug': ('side', [supine(aN=(180, 180), aF=(180, 180), lN=(178, 90, 90), lF=(178, 90, 90)),
                          supine(aN=(-100, -100), aF=(180, 180), lN=(178, 90, 90), lF=(92, 92, 150))], None),
    'tibialis-raise': ('side', [stand(torso=-10, lN=(18, 18, 90), lF=(14, 14, 90), aN=(-4, 0), aF=(-8, 0)),
                                stand(torso=-10, lN=(18, 18, 140), lF=(14, 14, 140), aN=(-4, 0), aF=(-8, 0))], P_tib),
    'walking': ('side', [walk(0), walk(1)], None),
    'running': ('side', [dict(torso=12, aN=(-38, 60), aF=(42, 128), lN=(62, -14, 100), lF=(-32, -104, -150)),
                         dict(torso=12, aN=(42, 128), aF=(-38, 60), lN=(-32, -104, -150), lF=(62, -14, 100))], None),
    'cycling': ('side', [dict(torso=48, aN=(72, 82), aF=(70, 80), lN=(80, 8, 100), lF=(28, -6, 80), head=-25),
                         dict(torso=48, aN=(72, 82), aF=(70, 80), lN=(28, -6, 80), lF=(80, 8, 100), head=-25)], P_cycle),
    'hiking': ('side', [walk(0, torso=12, aN=(30, 50)), walk(1, torso=12, aN=(12, 40))], P_hike),
    'half-kneeling-hip-flexor-stretch': ('side', [kneel_half(), kneel_half(lN=(68, 14, 90), lF=(-38, -100, -175), torso=-6)], None),
    'couch-stretch': ('side', [kneel_half(lF=(-20, 172, 172), torso=32, aN=(25, 25), aF=(20, 20)),
                               kneel_half(lF=(-14, 178, 178), torso=2)], P_couch),
    'hamstring-stretch': ('side', [stand(lN=(72, 72, 165), lF=(0, 0, 90), aN=(-12, 60), aF=(-12, 60)),
                                   stand(torso=48, lN=(72, 72, 165), lF=(0, 0, 90), aN=(62, 70), aF=(58, 66), head=-10)], P_hamstring),
    'pigeon-stretch': ('side', [dict(torso=12, lN=(92, -92, -80), lF=(-92, -92, -175), aN=(8, 8, 90), aF=(4, 4, 90)),
                                dict(torso=80, lN=(92, -92, -80), lF=(-92, -92, -175), aN=(60, 92, 92), aF=(56, 90, 90), head=-15)], None),
    '90-90-hip-switches': ('front', [dict(lR=(-80, 4), lL=(70, 172), aR=(-20, -20), aL=(20, 20)),
                                     dict(lR=(-70, -172), lL=(80, -4), aR=(-20, -20), aL=(20, 20))], 'seatfront'),
    'adductor-rock-back': ('side', [quad(lN=(-6, -6, -90)), quad(torso=72, lF=(-48, -90, -100), lN=(-36, -36, -90), aN=(40, 40, 90), aF=(40, 40, 90))], None),
    'worlds-greatest-stretch': ('side', [dict(torso=55, lN=(88, 6, 90), lF=(-62, -62, -20), aN=(18, 18, 90), aF=(18, 18, 90), head=-5),
                                         dict(torso=55, lN=(88, 6, 90), lF=(-62, -62, -20), aN=(18, 18, 90), aF=(175, 175), head=25)], None),
    'criss-cross-sitting': ('front', [dict(lR=(-72, 105), lL=(72, -105), aR=(-15, 20), aL=(15, -20)),
                                      dict(torso=0, lR=(-72, 105), lL=(72, -105), aR=(-30, -45), aL=(30, 45))], P_criss),
    'knees-to-chest': ('side', [supine(lN=(140, 20, 90), lF=(136, 18, 90)),
                                supine(lN=(-155, 100, 160), lF=(-150, 104, 160), aN=(150, 110), aF=(146, 106))], None),
    'figure-4-stretch': ('side', [supine(lF=(140, 20, 90), lN=(120, 30, 100)),
                                  supine(lF=(178, 92, 150), lN=(150, 60, 120), aN=(170, 140), aF=(166, 136))], None),
    'lying-hamstring-strap': ('side', [supine(lN=(130, 130, 200), aN=(132, 132), aF=(88, 88)),
                                       supine(lN=(170, 170, 250), aN=(158, 158), aF=(88, 88))], P_strap),
    'thoracic-extension-roller': ('side', [supine(torso=-62, lN=(140, 20, 90), lF=(136, 18, 90), aN=(-160, 20), aF=(-156, 24), head=10),
                                           supine(torso=-100, lN=(140, 20, 90), lF=(136, 18, 90), aN=(-160, 20), aF=(-156, 24), head=-10)], P_roller),
    'cat-cow': ('side', [quad(bend=14, head=-35), quad(bend=-12, head=25)], None),
    'open-book': ('side', [dict(torso=-90, lN=(140, 50, 120), lF=(136, 48, 120), aN=(90, 90), aF=(90, 90), head=0),
                           dict(torso=-90, lN=(140, 50, 120), lF=(136, 48, 120), aN=(-100, -100), aF=(90, 90), head=-20)], None),
    'doorway-chest-stretch': ('side', [stand(aN=(-88, 178), aF=(4, 8)), stand(torso=8, aN=(-100, 180), aF=(4, 8), lN=(22, 4, 90), lF=(-12, -8, 90))], P_door),
    'childs-pose': ('side', [quad(), dict(torso=118, lN=(58, -94, -175), lF=(58, -94, -175), aN=(100, 100, 100), aF=(100, 100, 100), head=-25, bend=10)], None),
    'calf-stretch': ('side', [stand(torso=10, aN=(80, 80, 140), aF=(78, 78, 140), lN=(10, -4, 90), lF=(-20, -20, 90)),
                              stand(torso=22, aN=(70, 70, 140), aF=(68, 68, 140), lN=(30, -8, 90), lF=(-30, -30, 95))], P_calf),
    'bulgarian-split-squat': ('side', [stand(aN=(0, 0), aF=(0, 0), lN=(14, -2, 90), lF=(-24, -88, -175)),
                                       stand(torso=12, aN=(0, 0), aF=(0, 0), lN=(72, 12, 90), lF=(-10, -100, -175))], P_bss),
    'cable-crunch': ('side', [dict(torso=20, lN=(-6, -90, -175), lF=(-6, -90, -175), aN=(150, -150), aF=(146, -154), head=0),
                              dict(torso=78, bend=16, lN=(-6, -90, -175), lF=(-6, -90, -175), aN=(118, 175), aF=(114, 172), head=-30)], P_cablecrunch),
    'cable-external-rotation': ('front', [dict(aR=(-4, 88), aL=(8, 4)), dict(aR=(-4, -70), aL=(8, 4))], P_extrot),
}


def render(view, pose, props, frame):
    c = Canvas()
    fig = side_figure if view == 'side' else front_figure
    # draw once to measure, then shift so the lowest body point sits on the floor
    probe = Canvas(); fig(probe, pose)
    miny = min(p[1] for p in probe.pts) + SW_BODY
    pose = dict(pose, hip=(0, -miny + 40 if pose.get('hang') else -miny))
    # equipment is drawn first (behind the body); handheld items again on top afterwards
    tmp = Canvas(); J = fig(tmp, pose)
    if callable(props): props(c, J, frame)
    elif props == 'wallfront':
        c.rect((-70, 0), (70, 215), sw=3)
    elif props == 'seatfront':
        pass
    fig(c, pose)
    if props == 'twist':
        plate(c, s(v(J['handN'], J['handF']), 0.5), 13)
    if callable(props) and props in (P_farmer, P_suitcase, P_bss, P_wristcurl):
        dumbbell(c, J['handN'])   # handheld items in front of the hand
    return c.svg()


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    sheet = []
    for slug, (view, poses, props) in EXERCISES.items():
        for frame, name in enumerate(('relaxation', 'tension')):
            svg = render(view, poses[frame], props, frame)
            path = OUT / f'c-{slug}-{name}.svg'
            path.write_text(svg, encoding='utf-8')
            sheet.append((slug, name, path))
    if '--sheet' in sys.argv:
        out = pathlib.Path(sys.argv[sys.argv.index('--sheet') + 1])
        cells = ''.join(f'<div><img src="{p.as_uri()}"><span>{sl} {n[0]}</span></div>' for sl, n, p in sheet)
        out.write_text(f'<html><body style="margin:0;display:grid;grid-template-columns:repeat(8,180px);gap:4px;font:10px sans-serif">'
                       f'{cells}<style>div{{border:1px solid #ccc}}img{{width:180px;height:150px;object-fit:contain}}</style></body></html>')
    print('wrote', len(sheet), 'svgs to', OUT)


if __name__ == '__main__':
    main()
