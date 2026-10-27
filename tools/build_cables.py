"""Build cables.json for the Undersea Cables map layer.

Sources (real public data, nothing made up):
  * Internet / data cables: TeleGeography Submarine Cable Map (submarinecablemap.com, CC BY-NC-SA 3.0)
      api/v3/cable/cable-geo.json, api/v3/cable/<id>.json
  * Undersea power cables: OpenStreetMap (ODbL) via Overpass,
      power=cable + location=underwater/submarine, 110 kV+ or HVDC, inter-array wind farm cables left out

Run: python3 tools/build_cables.py <dir with cable-geo.json, each/, pw_geom.json>
"""
USED_IDS = set()
import json, math, os, re, sys
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', 'watcher'))
import geo  # noqa: E402

SRC = sys.argv[1] if len(sys.argv) > 1 else '/home/sprite/cables'
OUT = os.path.join(HERE, '..', 'cables.json')
HOME = (35.6145, -88.8139)

# The watch zone: Israel & the Eastern Med, the Red Sea, Bab el-Mandeb and the Gulf of Aden
ZONES = [
    ('Israel & the Eastern Med', 30.0, 38.5, 22.0, 36.6),
    ('the Suez Canal & Red Sea', 12.0, 31.5, 32.0, 44.0),
    ('Bab el-Mandeb & the Gulf of Aden', 10.5, 15.5, 42.0, 52.0),
]


def in_zone(lat, lon):
    for n, a1, a2, o1, o2 in ZONES:
        if a1 <= lat <= a2 and o1 <= lon <= o2:
            return n
    return None


def perp(p, a, b):
    (x, y), (x1, y1), (x2, y2) = p, a, b
    dx, dy = x2 - x1, y2 - y1
    if dx == 0 and dy == 0:
        return math.hypot(x - x1, y - y1)
    t = max(0, min(1, ((x - x1) * dx + (y - y1) * dy) / (dx * dx + dy * dy)))
    return math.hypot(x - (x1 + t * dx), y - (y1 + t * dy))


def simplify(pts, tol):
    if len(pts) < 3:
        return pts
    keep = [False] * len(pts)
    keep[0] = keep[-1] = True
    stack = [(0, len(pts) - 1)]
    while stack:
        s, e = stack.pop()
        best, bi = 0, None
        for i in range(s + 1, e):
            d = perp(pts[i], pts[s], pts[e])
            if d > best:
                best, bi = d, i
        if bi is not None and best > tol:
            keep[bi] = True
            stack += [(s, bi), (bi, e)]
    return [p for p, k in zip(pts, keep) if k]


def line_km(pts):
    L = 0
    for (o1, a1), (o2, a2) in zip(pts, pts[1:]):
        L += geo.miles(a1, o1, a2, o2) * 1.609
    return L


def rnd(pts, nd=3):
    out = []
    for o, a in pts:
        q = [round(a, nd), round(o, nd)]  # [lat, lon] for Leaflet
        if not out or out[-1] != q:
            out.append(q)
    return out


def nearest_home(lines):
    best = None
    for ln in lines:
        for a, o in ln:
            d = geo.miles(HOME[0], HOME[1], a, o)
            if best is None or d < best[0]:
                best = (d, a, o)
    return best


def place_of(lat, lon):
    w = geo.where(lat, lon)
    if w.get('sea'):
        return w['sea'][0].upper() + w['sea'][1:] if not w['sea'].startswith('the ') else w['sea']
    if w.get('over'):
        return w['over']
    if w.get('coast'):
        return 'off ' + w['coast']
    return 'the open ocean'


US_STATES = None


def nice(c):
    global US_STATES
    if US_STATES is None:
        US_STATES = {s[0] for s in geo._geo()['states'] if s[3] == 'US'}
    if not c:
        return c
    if c in US_STATES:
        return 'United States'
    return c[4:] if c.startswith('the ') else c


def country_at(lat, lon):
    w = geo.where(lat, lon)
    if w.get('over'):
        if w.get('cc') == 'US':
            return 'United States'
        return nice(w['over'].split(', ')[-1])
    # at sea: only count a country whose shore is within about 12 miles of the cable's end
    for dist in (4, 8, 12):
        for brg in range(0, 360, 45):
            la2 = lat + dist / 69.0 * math.cos(math.radians(brg))
            lo2 = lon + dist / (69.0 * max(0.2, math.cos(math.radians(lat)))) * math.sin(math.radians(brg))
            w = geo.where(la2, lo2)
            if w.get('over'):
                return 'United States' if w.get('cc') == 'US' else nice(w['over'].split(', ')[-1])
    return None


cables = []
BALTIC = (53.0, 67.0, 9.0, 31.5)  # fine-detail copy for the live ship watch (Finland's open ship feed)
baltic = []


def in_baltic(a, o):
    return BALTIC[0] <= a <= BALTIC[1] and BALTIC[2] <= o <= BALTIC[3]


def add_baltic(cid, name, kind, parts):
    for part in parts:
        run = []
        for o, a in part:
            if in_baltic(a, o):
                run.append((o, a))
            elif run:
                if len(run) > 1:
                    baltic.append({'id': cid, 'n': name, 'k': kind, 'g': rnd(simplify(run, 0.002), 4)})
                run = []
        if len(run) > 1:
            baltic.append({'id': cid, 'n': name, 'k': kind, 'g': rnd(simplify(run, 0.002), 4)})

# ---------------------------------------------------------------- internet / data cables (TeleGeography)
geoj = json.load(open(os.path.join(SRC, 'cable-geo.json')))
by_id = defaultdict(list)
names = {}
for f in geoj['features']:
    p = f['properties']
    names[p['id']] = p['name']
    g = f['geometry']
    parts = g['coordinates'] if g['type'] == 'MultiLineString' else [g['coordinates']]
    by_id[p['id']].extend(parts)

for cid, parts in by_id.items():
    try:
        d = json.load(open(os.path.join(SRC, 'each', cid + '.json')))
    except Exception:
        d = {}
    lines, zones, il = [], set(), False
    for part in parts:
        pts = [(o, a) for o, a in part]
        for o, a in pts:
            z = in_zone(a, o)
            if z:
                zones.add(z)
        lines.append(rnd(simplify(pts, 0.03)))
    lps = d.get('landing_points') or []
    countries = []
    for lp in lps:
        c = lp.get('country')
        if c and c not in countries:
            countries.append(c)
    if 'Israel' in countries:
        il = True
    nh = nearest_home(lines)
    c = {'id': cid, 'k': 'net', 'n': names.get(cid) or d.get('name') or cid,
         'c': countries, 'lp': [lp['name'] for lp in lps if lp.get('name')][:40],
         'len': d.get('length') or '', 'rfs': d.get('rfs_year') or '', 'pl': bool(d.get('is_planned')),
         'own': (d.get('owners') or '')[:240], 'g': lines,
         'hm': round(nh[0]) if nh else None}
    if zones or il:
        c['hl'] = 1
        c['z'] = sorted(zones) + (['Israel'] if il and not zones else [])
    if il:
        c['il'] = 1
    cables.append(c)
    add_baltic(cid, c['n'], 'net', parts)

# ---------------------------------------------------------------- undersea power cables (OpenStreetMap)
pw = json.load(open(os.path.join(SRC, 'pw_geom.json')))['elements']


def volt(t):
    try:
        return max(int(x) for x in re.findall(r'\d+', t.get('voltage', '')))
    except ValueError:
        return 0


groups = defaultdict(lambda: {'segs': [], 'v': 0, 'tags': {}, 'ids': []})
for e in pw:
    t = e.get('tags', {})
    n = t.get('name') or t.get('ref') or ''
    if re.search(r'inter.?array|array cable|electrode|export cable', n, re.I):
        continue
    v = volt(t)
    if v < 110000 and 'hvdc' not in n.lower() and t.get('frequency') != '0':
        continue
    pts = [(q['lon'], q['lat']) for q in e.get('geometry', []) if q]
    if len(pts) < 2:
        continue
    k = n or ('osm-%d' % e['id'])
    G = groups[k]
    G['segs'].append(pts)
    G['v'] = max(G['v'], v)
    G['ids'].append(e['id'])
    for kk, vv in t.items():
        G['tags'].setdefault(kk, vv)

npw = 0
for k, G in groups.items():
    L = sum(line_km(s) for s in G['segs'])
    if L < 15:
        continue
    t = G['tags']
    lines, zones = [], set()
    for s in G['segs']:
        for o, a in s:
            z = in_zone(a, o)
            if z:
                zones.add(z)
        lines.append(rnd(simplify(s, 0.005)))
    # which countries it joins: look at the two far ends
    allpts = [p for s in G['segs'] for p in s]
    ends = []
    a0 = allpts[0]
    far = max(allpts, key=lambda p: (p[0] - a0[0]) ** 2 + (p[1] - a0[1]) ** 2)
    far2 = max(allpts, key=lambda p: (p[0] - far[0]) ** 2 + (p[1] - far[1]) ** 2)
    for o, a in (far, far2):
        cc = country_at(a, o)
        if cc and cc not in ends:
            ends.append(cc)
    nh = nearest_home(lines)
    name = (t.get('name:en') or t.get('name') or '').split(';')[0].strip() or (('Power cable ' + t['ref']) if t.get('ref') else 'Undersea power cable')
    hv = 'hvdc' in name.lower() or t.get('frequency') == '0'
    cid = 'pw-' + (re.sub(r'[^a-z0-9]+', '-', k.lower()).strip('-')[:60] or re.sub(r'[^a-z0-9]+', '-', name.lower()).strip('-')[:40] or 'cable')
    while cid in USED_IDS:
        cid += '-x'
    USED_IDS.add(cid)
    c = {'id': cid, 'k': 'pw', 'n': name,
         'c': ends, 'lp': [], 'len': '%s km' % format(round(L), ','), 'rfs': (t.get('start_date') or '')[:4],
         'pl': t.get('construction') is not None, 'own': t.get('operator', '')[:160],
         'kv': round(G['v'] / 1000) if G['v'] else None, 'dc': 1 if hv else 0, 'g': lines,
         'hm': round(nh[0]) if nh else None}
    if zones:
        c['hl'] = 1
        c['z'] = sorted(zones)
    cables.append(c)
    add_baltic(c['id'], name, 'pw', G['segs'])
    npw += 1

cables.sort(key=lambda c: (c.get('hl', 0), c['k'] == 'pw'))  # highlighted ones drawn last (on top)
out = {'built': __import__('time').strftime('%Y-%m-%d'),
       'credit': 'Internet cables: TeleGeography Submarine Cable Map (CC BY-NC-SA). Power cables: © OpenStreetMap contributors.',
       'zones': [[z[0], [[z[1], z[3]], [z[2], z[4]]]] for z in ZONES],
       'cables': cables}
with open(OUT, 'w') as f:
    json.dump(out, f, separators=(',', ':'), ensure_ascii=False)
with open(os.path.join(HERE, '..', 'watcher', 'baltic_cables.json'), 'w') as f:
    json.dump({'built': out['built'], 'lines': baltic}, f, separators=(',', ':'), ensure_ascii=False)
print('baltic lines', len(baltic), os.path.getsize(os.path.join(HERE, '..', 'watcher', 'baltic_cables.json')))
net = sum(1 for c in cables if c['k'] == 'net')
print('internet cables', net, 'power cables', npw, 'highlighted', sum(1 for c in cables if c.get('hl')),
      'size', os.path.getsize(OUT))
