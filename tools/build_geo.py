"""Builds watcher/geo_data.json: simplified country, state and sea outlines plus military bases and big airports.
Sources: Natural Earth 1:50m (public domain) and OurAirports (public domain).
Run: python3 tools/build_geo.py /tmp  (folder holding the downloaded source files)
"""
import csv
import json
import re
import sys

SRC = sys.argv[1] if len(sys.argv) > 1 else '/tmp'
TOL = 0.03  # degrees, about 2 miles


def dp(pts, tol):
    if len(pts) < 4:
        return pts
    keep = [False] * len(pts)
    keep[0] = keep[-1] = True
    stack = [(0, len(pts) - 1)]
    while stack:
        a, b = stack.pop()
        (x1, y1), (x2, y2) = pts[a], pts[b]
        dx, dy = x2 - x1, y2 - y1
        L = (dx * dx + dy * dy) ** 0.5 or 1e-12
        best, bi = -1, -1
        for i in range(a + 1, b):
            x, y = pts[i]
            d = abs(dy * x - dx * y + x2 * y1 - y2 * x1) / L if (dx or dy) else ((x - x1) ** 2 + (y - y1) ** 2) ** 0.5
            if d > best:
                best, bi = d, i
        if best > tol and bi > 0:
            keep[bi] = True
            stack += [(a, bi), (bi, b)]
    return [p for p, k in zip(pts, keep) if k]


def polys(geom):
    if geom['type'] == 'Polygon':
        rings = [geom['coordinates'][0]]
    elif geom['type'] == 'MultiPolygon':
        rings = [p[0] for p in geom['coordinates']]
    else:
        rings = []
    out = []
    for r in rings:
        s = dp([(round(x, 3), round(y, 3)) for x, y in r], TOL)
        if len(s) >= 4:
            out.append([[round(x, 2), round(y, 2)] for x, y in s])
    return out


def feat_list(path, namef, extra=None):
    out = []
    for f in json.load(open(path, encoding='utf8'))['features']:
        nm = namef(f['properties'])
        if not nm:
            continue
        ps = polys(f['geometry'])
        if not ps:
            continue
        xs = [x for p in ps for x, _ in p]
        ys = [y for p in ps for _, y in p]
        row = [nm, [min(xs), min(ys), max(xs), max(ys)], ps]
        if extra:
            row.append(extra(f['properties']))
        out.append(row)
    return out


COUNTRY_FIX = {'United States of America': 'the US', 'United Kingdom': 'the UK', 'United Arab Emirates': 'the UAE',
               'Bosnia and Herz.': 'Bosnia', 'Dem. Rep. Congo': 'Congo', 'Central African Rep.': 'Central African Republic',
               'Dominican Rep.': 'the Dominican Republic', 'Netherlands': 'the Netherlands', 'Philippines': 'the Philippines',
               'Bahamas': 'the Bahamas', 'Czechia': 'the Czech Republic', 'N. Cyprus': 'Cyprus', 'Palestine': 'the West Bank & Gaza',
               'S. Sudan': 'South Sudan', 'W. Sahara': 'Western Sahara', 'Somaliland': 'Somalia', 'Br. Indian Ocean Ter.': 'Diego Garcia',
               'N. Mariana Is.': 'the Northern Mariana Islands', 'Marshall Is.': 'the Marshall Islands', 'Solomon Is.': 'the Solomon Islands',
               'Cayman Is.': 'the Cayman Islands', 'Faeroe Is.': 'the Faroe Islands', 'Falkland Is.': 'the Falkland Islands',
               'U.S. Virgin Is.': 'the US Virgin Islands', 'British Virgin Is.': 'the British Virgin Islands',
               'Antigua and Barb.': 'Antigua', 'Eq. Guinea': 'Equatorial Guinea', 'Turks and Caicos Is.': 'Turks and Caicos'}
countries = feat_list(f'{SRC}/ne_countries.geojson', lambda p: COUNTRY_FIX.get(p['NAME'], p['NAME']))
states = feat_list(f'{SRC}/ne_admin1.geojson',
                   lambda p: p['name'] if p['admin'] in ('United States of America', 'Canada', 'Australia') else None,
                   lambda p: {'United States of America': 'US', 'Canada': 'Canada', 'Australia': 'Australia'}[p['admin']])
SEA_FIX = {'INDIAN OCEAN': 'Indian Ocean', 'SOUTHERN OCEAN': 'Southern Ocean', 'Inner Sea': 'Seto Inland Sea', 'Inner Seas': 'the Inner Seas'}
seas = feat_list(f'{SRC}/ne_marine.geojson', lambda p: SEA_FIX.get(p.get('name') or '', p.get('name')))
seas = [s for s in seas if s[0] not in ('Amazon River', 'Columbia River', 'Yangtze River')]

# -------- bases
MIL = re.compile(r'(Air Force Base|\bAFB\b|Air Base|Airbase|Naval Air|\bNAS\b|Army Air ?field|Marine Corps|\bMCAS\b|\bRAF\b|'
                 r'Air Station|Joint Base|Base A[ée]rea|Fliegerhorst|Military|Air Force Station|Coast Guard|JASDF|JMSDF|'
                 r'Base A[ée]rienne|Luchtmachtbasis|Naval Station|Air National Guard|Army|Naval|Garrison|Air Field|Airfield)', re.I)
FORCE = re.compile(r'(Air Force Base|\bAFB\b|Air Base|Airbase|Naval Air|\bNAS\b|Army Air ?field|Marine Corps|\bMCAS\b|\bRAF\b|'
                   r'Joint Base|Base A[ée]rea|Fliegerhorst|Military|JASDF|JMSDF|Base A[ée]rienne|Luchtmachtbasis|Naval Station|'
                   r'Air National Guard|Army|Naval|Garrison|Coast Guard Air Station)', re.I)
bases = []
for r in csv.DictReader(open(f'{SRC}/airports.csv', encoding='utf8')):
    t, nm = r['type'], r['name'].strip()
    if t not in ('large_airport', 'medium_airport', 'small_airport'):
        continue
    mil = bool(FORCE.search(nm))
    if not mil and t == 'small_airport':
        continue
    try:
        la, lo = round(float(r['latitude_deg']), 3), round(float(r['longitude_deg']), 3)
    except ValueError:
        continue
    nm = re.sub(r'\s*\(.*?\)\s*', ' ', nm).strip()
    nm = re.sub(r'\s{2,}', ' ', nm)
    if t == 'small_airport' and not re.search(r'Air Force Base|\bAFB\b|Air Base|Naval Air|Army Air|Marine Corps|Joint Base|RAF', nm, re.I):
        continue
    bases.append([nm, la, lo, 1 if mil else 0, r['iso_country']])

# Key bases written in by hand, so they always show with the name people know
CURATED = [
    ('Incirlik Air Base', 37.002, 35.426, 'TR'), ('Souda Bay naval air base', 35.532, 24.149, 'GR'), ('RAF Akrotiri', 34.590, 32.988, 'CY'),
    ('Aviano Air Base', 46.032, 12.596, 'IT'), ('Naval Station Rota', 36.645, -6.349, 'ES'), ('Lajes Field', 38.762, -27.091, 'PT'),
    ('Ali Al Salem Air Base', 29.347, 47.521, 'KW'), ('Muwaffaq Salti Air Base', 31.827, 36.789, 'JO'), ('Al Asad Air Base', 33.786, 42.441, 'IQ'),
    ('Erbil Air Base', 36.237, 43.963, 'IQ'), ('Isa Air Base', 25.918, 50.591, 'BH'), ('Thumrait Air Base', 17.666, 54.025, 'OM'),
    ('Masirah Air Base', 20.675, 58.890, 'OM'), ('Camp Lemonnier', 11.547, 43.159, 'DJ'), ('Al Minhad Air Base', 25.027, 55.366, 'AE'),
    ('Hatzerim Air Base', 31.234, 34.663, 'IL'), ('Tel Nof Air Base', 31.839, 34.822, 'IL'), ('Ramat David Air Base', 32.665, 35.180, 'IL'),
    ('Palmachim Air Base', 31.898, 34.691, 'IL'), ('Hatzor Air Base', 31.763, 34.727, 'IL'), ('Ovda Air Base', 29.940, 34.936, 'IL'),
    ('Nevatim Air Base', 31.208, 35.012, 'IL'), ('Ramon Air Base', 30.776, 34.667, 'IL'),
    ('Misawa Air Base', 40.703, 141.368, 'JP'), ('Osan Air Base', 37.090, 127.030, 'KR'), ('Kunsan Air Base', 35.904, 126.616, 'KR'),
    ('MCAS Iwakuni', 34.144, 132.236, 'JP'), ('Naval Air Facility Atsugi', 35.455, 139.450, 'JP'), ('MCAS Futenma', 26.274, 127.756, 'JP'),
    ('Naha Air Base', 26.196, 127.646, 'JP'), ('Kadena Air Base', 26.352, 127.769, 'JP'), ('Yokota Air Base', 35.749, 139.348, 'JP'),
    ('Fort Novosel (Fort Rucker)', 31.276, -85.713, 'US'), ('Columbus Air Force Base', 33.644, -88.444, 'US'),
    ('Naval Air Station Meridian', 32.551, -88.556, 'US'), ('Naval Support Activity Mid-South (Millington)', 35.356, -89.870, 'US'),
    ('Joint Base Charleston', 32.899, -80.040, 'US'), ('Joint Base Andrews', 38.811, -76.867, 'US'), ('Dover Air Force Base', 39.130, -75.466, 'US'),
    ('NATO Air Base Geilenkirchen', 50.961, 6.042, 'DE'), ('Mihail Kogalniceanu Air Base', 44.362, 28.488, 'RO'),
    ('Rzeszow airport (Ukraine aid hub)', 50.110, 22.019, 'PL'), ('Siauliai Air Base', 55.894, 23.395, 'LT'), ('Amari Air Base', 59.260, 24.208, 'EE'),
    ('Lask Air Base', 51.551, 19.179, 'PL'), ('Oakey Army Aviation Centre', -27.411, 151.735, 'AU'), ('RAAF Base Williamtown', -32.795, 151.834, 'AU'),
    ('HMAS Albatross (Nowra)', -34.949, 150.537, 'AU'), ('RAAF Base East Sale', -38.099, 147.149, 'AU'), ('RAAF Base Pearce', -31.668, 116.015, 'AU'),
    ('RAAF Base Edinburgh', -34.702, 138.621, 'AU'), ('RAAF Base Amberley', -27.640, 152.712, 'AU'), ('RAAF Base Darwin', -12.415, 130.877, 'AU'),
    ('RAAF Base Tindal', -14.521, 132.378, 'AU'), ('Kamphaeng Saen flying school', 14.102, 99.917, 'TH'), ('Lop Buri air base', 14.874, 100.664, 'TH'),
    ('Hakimpet Air Force Station', 17.553, 78.525, 'IN'), ('Air Force Academy Dundigal', 17.627, 78.403, 'IN'),
    ('Adisutjipto air base (Yogyakarta)', -7.788, 110.432, 'ID'), ('RAF Mildenhall', 52.362, 0.486, 'GB'), ('RAF Lakenheath', 52.409, 0.561, 'GB'),
    ('RAF Fairford', 51.682, -1.790, 'GB'), ('RAF Brize Norton', 51.750, -1.584, 'GB'), ('Ramstein Air Base', 49.437, 7.600, 'DE'),
    ('Spangdahlem Air Base', 49.973, 6.692, 'DE'), ('Al Udeid Air Base', 25.117, 51.315, 'QA'), ('Al Dhafra Air Base', 24.248, 54.548, 'AE'),
    ('Prince Sultan Air Base', 24.063, 47.581, 'SA'), ('Andersen Air Force Base', 13.584, 144.930, 'GU'), ('Diego Garcia', -7.313, 72.411, 'IO'),
    ('Sigonella naval air station', 37.402, 14.922, 'IT'), ('Offutt Air Force Base', 41.119, -95.909, 'US'), ('Tinker Air Force Base', 35.415, -97.387, 'US'),
    ('Whiteman Air Force Base', 38.730, -93.548, 'US'), ('Barksdale Air Force Base', 32.502, -93.663, 'US'), ('Dyess Air Force Base', 32.421, -99.855, 'US'),
    ('Ellsworth Air Force Base', 44.145, -103.104, 'US'), ('Minot Air Force Base', 48.416, -101.358, 'US'), ('Little Rock Air Force Base', 34.917, -92.150, 'US'),
    ('Fort Campbell', 36.674, -87.490, 'US'), ('Joint Base Pearl Harbor-Hickam', 21.319, -157.922, 'US'), ('MCAS Kaneohe Bay', 21.450, -157.768, 'US'),
]
have = [(b[1], b[2]) for b in bases]
for nm, la, lo, cc in CURATED:
    bases = [b for b in bases if not (abs(b[1] - la) < 0.06 and abs(b[2] - lo) < 0.08)]
    bases.append([nm, la, lo, 1, cc])

# names everyone knows them by (OurAirports keeps a few old ones)
RENAME = {'Cairns Army Airfield': 'Fort Novosel (Cairns Army Airfield)', 'Lowe Army Heliport': 'Fort Novosel',
          'Simmons Army Airfield': 'Fort Liberty (Simmons Army Airfield)', 'Robert Gray Army Airfield': 'Fort Cavazos (Robert Gray Army Airfield)',
          'Campbell AAF': 'Fort Campbell', 'Campbell Army Airfield': 'Fort Campbell (Campbell Army Airfield)'}
for b in bases:
    b[0] = RENAME.get(b[0], b[0])

json.dump({'countries': countries, 'states': states, 'seas': seas, 'bases': bases},
          open('watcher/geo_data.json', 'w'), separators=(',', ':'))
print(len(countries), 'countries', len(states), 'states', len(seas), 'seas', len(bases), 'places',
      sum(1 for b in bases if b[3]), 'military')
