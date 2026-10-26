"""Where each plane is and what it has been doing, in plain words, for the "Probably doing" line.

Adds a small "bh" (behavior) box to every plane row in live.json:
  over   country / US state the plane is over          ("Texas", "Jordan")
  sea    named sea it is over                          ("the Persian Gulf")
  coast  country it is just off the coast of           ("Japan")
  near   [base or airport, miles, military 1/0]        (within 40 mi)
  ahead  [base, miles] a base it is pointed at, close enough to be landing there
  frm    [base, minutes ago] where it first showed up low, near a base (took off there)
  up     minutes the radar has seen it on this flight
  orb    minutes it has stayed inside one small area while flying (circling / orbiting)
  orbr   miles across that area
  turn   degrees of turning seen across the sweeps
  climb / sink  feet per minute it climbed or came down between sweeps (when the plane shares no rate)

Memory lives in state["trails"], keyed by the plane's hex code. Everything here is a best guess and must
never break a sweep, so watch.py calls it inside try/except.
"""
import json
import math
import os

HERE = os.path.dirname(os.path.abspath(__file__))
_G = None
TRAIL_KEEP_S = 100 * 60     # remember the last 100 minutes of positions
NEW_FLIGHT_GAP_S = 45 * 60  # unseen this long = a new flight next time


def _geo():
    global _G
    if _G is None:
        with open(os.path.join(HERE, 'geo_data.json'), encoding='utf8') as f:
            _G = json.load(f)
        # rough grid so the base search stays quick
        grid = {}
        for b in _G['bases']:
            grid.setdefault((int(math.floor(b[1])), int(math.floor(b[2]))), []).append(b)
        _G['grid'] = grid
    return _G


def miles(a1, o1, a2, o2):
    r = math.radians
    d = math.sin(r(a2 - a1) / 2) ** 2 + math.cos(r(a1)) * math.cos(r(a2)) * math.sin(r(o2 - o1) / 2) ** 2
    return 3958.8 * 2 * math.asin(min(1, math.sqrt(d)))


def bearing(a1, o1, a2, o2):
    r = math.radians
    y = math.sin(r(o2 - o1)) * math.cos(r(a2))
    x = math.cos(r(a1)) * math.sin(r(a2)) - math.sin(r(a1)) * math.cos(r(a2)) * math.cos(r(o2 - o1))
    return (math.degrees(math.atan2(y, x)) + 360) % 360


def _inring(x, y, ring):
    inside = False
    n = len(ring)
    j = n - 1
    for i in range(n):
        xi, yi = ring[i]
        xj, yj = ring[j]
        if (yi > y) != (yj > y) and x < (xj - xi) * (y - yi) / ((yj - yi) or 1e-12) + xi:
            inside = not inside
        j = i
    return inside


def _hit(feats, lat, lon):
    for f in feats:
        bb = f[1]
        if bb[0] <= lon <= bb[2] and bb[1] <= lat <= bb[3]:
            for ring in f[2]:
                if _inring(lon, lat, ring):
                    return f
    return None


def where(lat, lon):
    g = _geo()
    out = {}
    st = _hit(g['states'], lat, lon)
    if st:
        out['over'] = st[0] if st[3] == 'US' else f'{st[0]}, {st[3]}'
        out['cc'] = st[3]
        return out
    c = _hit(g['countries'], lat, lon)
    if c:
        out['over'] = c[0]
        return out
    s = _hit(g['seas'], lat, lon)
    if s:
        nm = s[0]
        out['sea'] = nm if nm.startswith('the ') else 'the ' + nm
    # over water: is a coast close by?
    best = None
    for dist in (25, 60, 110):
        for brg in range(0, 360, 30):
            dlat = dist / 69.0 * math.cos(math.radians(brg))
            dlon = dist / (69.0 * max(0.2, math.cos(math.radians(lat)))) * math.sin(math.radians(brg))
            la2, lo2 = lat + dlat, ((lon + dlon + 540) % 360) - 180
            h = _hit(g['states'], la2, lo2)
            name = None
            if h:
                name = h[0] if h[3] == 'US' else h[3]
            else:
                h = _hit(g['countries'], la2, lo2)
                name = h[0] if h else None
            if name:
                best = name
                break
        if best:
            break
    if best:
        out['coast'] = best
    return out


def nearest_base(lat, lon, max_mi=40):
    g = _geo()
    la0, lo0 = int(math.floor(lat)), int(math.floor(lon))
    best = None
    for dla in (-1, 0, 1):
        for dlo in (-1, 0, 1):
            for b in g['grid'].get((la0 + dla, ((lo0 + dlo + 180) % 360) - 180), ()):
                d = miles(lat, lon, b[1], b[2])
                # a military field counts as closer than a civilian airport the same distance away
                score = d * (0.6 if b[3] else 1.0)
                lim = max_mi if b[3] else max_mi * 0.5
                if d <= lim and (best is None or score < best[0]):
                    best = (score, b, d)
    return (best[1], best[2]) if best else (None, None)


def base_ahead(lat, lon, trk, max_mi=160):
    if trk is None:
        return None, None
    g = _geo()
    la0, lo0 = int(math.floor(lat)), int(math.floor(lon))
    best = None
    for dla in range(-3, 4):
        for dlo in range(-4, 5):
            for b in g['grid'].get((la0 + dla, ((lo0 + dlo + 180) % 360) - 180), ()):
                d = miles(lat, lon, b[1], b[2])
                if d < 3 or d > max_mi:
                    continue
                off = abs(((bearing(lat, lon, b[1], b[2]) - trk + 540) % 360) - 180)
                if off > (25 if d > 30 else 40):
                    continue
                score = (d + off * 2) * (0.7 if b[3] else 1.0)
                if best is None or score < best[0]:
                    best = (score, b, d)
    return (best[1], best[2]) if best else (None, None)


def _turn(trail):
    tot = 0
    hs = [p[4] for p in trail if p[4] is not None]
    for a, b in zip(hs, hs[1:]):
        tot += abs(((b - a + 540) % 360) - 180)
    return round(tot)


def enrich(planes, state, now_ts):
    """Update the trail memory and add the 'bh' box to each plane."""
    trails = state.setdefault('trails', {})
    seen = set()
    for p in planes:
        hx = str(p.get('hex') or '')
        if not hx or p.get('lat') is None:
            continue
        seen.add(hx)
        t = trails.get(hx)
        pt = [now_ts, p['lat'], p['lon'], p.get('alt'), p.get('trk')]
        if not t or now_ts - t['p'][-1][0] > NEW_FLIGHT_GAP_S:
            t = {'f': pt[:4], 'p': []}
        t['p'] = [q for q in t['p'] if now_ts - q[0] <= TRAIL_KEEP_S and q[0] != now_ts] + [pt]
        t['p'] = t['p'][-12:]
        trails[hx] = t

        bh = {}
        try:
            bh.update(where(p['lat'], p['lon']))
            b, d = nearest_base(p['lat'], p['lon'])
            if b:
                bh['near'] = [b[0], round(d), b[3]]
            alt = p.get('alt')
            if alt and alt > 0 and alt < 16000:
                b2, d2 = base_ahead(p['lat'], p['lon'], p.get('trk'))
                if b2 and (not b or b2[0] != b[0] or d2 > 5):
                    bh['ahead'] = [b2[0], round(d2)]
            f = t['f']
            up = round((now_ts - f[0]) / 60)
            bh['up'] = up
            if up >= 5 and (f[3] is None or f[3] < 9000):
                fb, fd = nearest_base(f[1], f[2], 25)
                if fb:
                    bh['frm'] = [fb[0], up]
            tr = t['p']
            if len(tr) >= 3:
                span = (tr[-1][0] - tr[0][0]) / 60
                cla = sum(q[1] for q in tr) / len(tr)
                clo = sum(q[2] for q in tr) / len(tr)
                rad = max(miles(cla, clo, q[1], q[2]) for q in tr)
                gs = p.get('gs') or 0
                # a fast plane that stays inside a small area for 20+ minutes is circling / orbiting
                path = sum(miles(a[1], a[2], b[1], b[2]) for a, b in zip(tr, tr[1:]))
                if span >= 20 and rad <= 45 and (gs >= 140 or (gs == 0 and path >= 20)):
                    bh['orb'] = round(span)
                    bh['orbr'] = round(rad * 2)
                bh['turn'] = _turn(tr)
            if len(tr) >= 2 and p.get('vr') is None:
                a1, a2 = tr[-2][3], tr[-1][3]
                dt = (tr[-1][0] - tr[-2][0]) / 60
                if a1 is not None and a2 is not None and dt > 0:
                    rate = (a2 - a1) / dt
                    if rate > 300:
                        bh['climb'] = round(rate)
                    elif rate < -300:
                        bh['sink'] = round(-rate)
        except Exception as e:  # never let a lookup break the sweep
            bh['err'] = type(e).__name__
        p['bh'] = bh
    for hx in list(trails):
        if hx not in seen and now_ts - trails[hx]['p'][-1][0] > NEW_FLIGHT_GAP_S:
            del trails[hx]
    return planes
