"""Undersea cable watch for the Watchman Radar.

Two parts, both safe to fail (the main sweep wraps every call):
  1. News: undersea internet / power cable cuts, damage, sabotage, and ships seen hanging over cables.
  2. Live ships (Baltic only): Finland's free open ship feed (Digitraffic, meri.digitraffic.fi) shows
     ships in the Gulf of Finland and northern Baltic. A cargo ship, tanker or unknown ship that sits
     almost still right over a mapped cable for 30+ minutes, away from ports, gets an alert.
     There is no free, reliable live ship feed for the Red Sea or the Eastern Med, so those are news-only.
"""
import hashlib
import json
import math
import os
import re
import time
import urllib.parse
import urllib.request
import gzip
from datetime import timedelta

import geo

HERE = os.path.dirname(os.path.abspath(__file__))
HOME = (35.6145, -88.8139)
UA = "WatchmanRadar/1.0 (personal radar; github pages)"

QUERIES = [
    '("undersea cable" OR "subsea cable" OR "submarine cable" OR "internet cable" OR "undersea cables" OR "subsea cables") '
    '(cut OR severed OR damaged OR damage OR outage OR sabotage OR broken OR fault)',
    '("power cable" OR interconnector OR "data cable" OR "fiber optic cable" OR "telecom cable") '
    '(undersea OR subsea OR seabed OR Baltic OR "Red Sea") (damaged OR cut OR outage OR sabotage OR disrupted)',
    '(Yantar OR "shadow fleet" OR "spy ship" OR "dragging anchor" OR "dragged anchor" OR "anchor drag") '
    '(cable OR cables OR seabed)',
]
EXTRA_TRUSTED = [
    "the record", "datacenter dynamics", "dcd", "subtel forum", "submarine telecoms forum", "capacity media",
    "light reading", "the register", "techcrunch", "ars technica", "wired", "lloyd's list", "splash247",
    "maritime executive", "the maritime executive", "gcaptain", "naval news", "euronews", "politico",
    "err news", "err", "yle", "yle news", "lrt", "svt", "nrk", "dw", "deutsche welle", "france 24",
    "the national", "arab news", "middle east eye", "ynetnews", "i24news", "haaretz", "taipei times",
    "focus taiwan", "south china morning post", "rest of world", "cnbc", "financial times", "the economist",
    "the telegraph", "the independent", "sky news", "usni news", "ukdj", "uk defence journal", "radio free europe",
    "rferl", "the barents observer", "high north news", "kathimerini", "cyprus mail", "anadolu",
]
EXCLUDE = (r"\b(cable news|cable tv|cable television|cable car|cable cars|cable-stayed|jumper cables?|charging cables?|"
           r"cable network|cable box|cable bill|cable company|cable provider|cord-cutting|opinion|podcast|stocks?|"
           r"shares|earnings|market size|market report|cagr|anniversary|years ago|museum|movie|film|review)\b")
STRONG = (r"\b(undersea|subsea|submarine|underwater|seabed|sea-?bed|sea ?floor|deep-sea)\b.{0,30}\b(cables?|lines?|"
          r"interconnectors?|links?)\b|\binternet cables?\b|\binterconnectors?\b|\bcables?\b.{0,40}\b(under the sea|"
          r"on the seabed|on the sea ?floor|sea ?bed)\b|\b(estlink|nordbalt|balticconnector|c-lion ?1?|"
          r"sea-me-we|aae-1|2africa|peace cable|imewe|seacom|fenno-skan|baltic cable)\b|"
          r"\b(baltic|sea|gulf|strait|ocean|offshore)\s+(\w+\s+)?cables?\b")
WEAK = r"\b(power|electricity|data|fib(er|re)[- ]optic|telecom\w*|communications?|optical)\b.{0,20}\bcables?\b"
SEA = (r"\b(sea|seas|ocean|strait|gulf|baltic|channel|island|islands|offshore|ships?|vessels?|anchors?|navy|naval|"
       r"coast ?guard|maritime|tanker)\b")
DAMAGE = (r"\b(cut|cuts|severed|severs?|severing|damaged?|damaging|broken|breaks?|ruptur\w*|outages?|disrupt\w*|"
          r"knocked out|faults?|torn|snapped|destroyed)\b")
CUT = r"\b(cut|cuts|severed|severs?|severing|snapped|torn|ruptur\w*|destroyed)\b"
SABOTAGE = r"\b(sabotag\w*|deliberate\w*|intentional\w*|hybrid (attack|warfare)|act of war|attack\w*)\b"
HYPO = (r"\b(could|would|might|may|fears?|risks?|threat(en|ens|ened)?s?|warns?|warning|if|vulnerab\w*|"
        r"plan(s|ned)?|prepar\w*|protect\w*|drill|exercise|scenario|how to)\b")
SOFT = (r"\b(laws?|bill|jail|prison|penalt\w*|fines?|charg(e|es|ed)|court|trial|convict\w*|sentenc\w*|launch(es|ed)?|"
        r"unveil\w*|technology|sensing|report finds|guide|explain\w*|restored|repair\w*|attempt\w*|plot\w*|accus\w*|"
        r"foil\w*|thwart\w*|remain untouched|untouched|odds|insurance|market)\b")
SPY = r"\b(yantar|spy ships?|research vessels?|survey ships?|intelligence ships?)\b"
SHIP = (r"\b(shadow fleet|dragg\w* (its |an |their )?anchors?|anchors? (drag\w*|dragged)|loiter\w*|lingering|"
        r"hover\w*|circling|suspicious (ship|vessel)s?|(vessel|ship|tanker|freighter) (suspected|detained|seized|boarded)|"
        r"detain\w*|seiz\w*|boarded)\b")
SECURITY = (r"\b(protect\w*|patrol\w*|threat\w*|spy|spies|surveil\w*|mapping|russia\w*|china|chinese|houthis?|"
            r"iran\w*|navy|naval|nato|investigat\w*|suspect\w*|drones?|vulnerab\w*|warn\w*|security|sentry|"
            r"sabotag\w*|guard\w*)\b")

# where a story is: (words, short label, plain words, lat, lon, region key for Riley's region switches)
PLACES = [
    (r"red sea|bab el-mandeb|bab al-mandab|mandeb|yemen|houthi|jeddah|djibouti|eritrea|sudan",
     "RED SEA", "the Red Sea", 18.5, 39.8, "gulf"),
    (r"israel|tel aviv|haifa|cyprus|lebanon|eastern mediterranean|east med|gaza|alexandria|egypt|greece|crete|turkey|syria",
     "E. MED", "Israel & the Eastern Med", 33.4, 32.5, "easternmed"),
    (r"suez", "SUEZ", "the Suez Canal", 30.4, 32.4, "easternmed"),
    (r"persian gulf|gulf of oman|hormuz|qatar|bahrain|uae|emirates|oman|iran|kuwait|iraq",
     "GULF", "the Persian Gulf", 26.3, 53.5, "gulf"),
    (r"gulf of finland|estlink|balticconnector|finland|finnish|estonia|tallinn|helsinki",
     "GULF OF FINLAND", "the Gulf of Finland", 59.75, 25.2, "baltic"),
    (r"baltic|gotland|sweden|swedish|latvia|lithuania|poland|nordbalt|c-lion|bornholm|denmark|danish|kaliningrad|germany",
     "BALTIC SEA", "the Baltic Sea", 56.8, 19.0, "baltic"),
    (r"taiwan|matsu|penghu|kinmen", "TAIWAN", "around Taiwan", 24.6, 120.6, "pacific"),
    (r"south china sea|vietnam|philippin|filipino|ph-sg|hong kong|malaysia|singapore|indonesia",
     "S. CHINA SEA", "the South China Sea", 14.0, 114.0, "pacific"),
    (r"north sea|shetland|orkney|norway|norwegian", "NORTH SEA", "the North Sea", 58.5, 3.0, "europe"),
    (r"svalbard|arctic|barents", "ARCTIC", "the Arctic", 77.0, 16.0, "alaska"),
    (r"irish sea|ireland|irish|scotland|britain|british|\buk\b|u\.k\.|english channel|jersey|guernsey|france|french",
     "UK & EUROPE", "the seas around the UK & Europe", 51.5, -4.0, "europe"),
    (r"black sea|ukrain|crimea|odesa|bulgaria|romania|georgia", "BLACK SEA", "the Black Sea", 43.2, 34.0, "ukraine"),
    (r"west africa|ivory coast|nigeria|ghana|senegal|cameroon|angola|congo",
     "W. AFRICA", "off West Africa", 3.5, 2.5, None),
    (r"east africa|kenya|somalia|tanzania|mozambique|madagascar|south africa",
     "E. AFRICA", "off East Africa", -4.0, 44.0, None),
    (r"australia|perth|sydney|darwin|tasmania", "AUSTRALIA", "around Australia", -30.0, 118.0, "pacific"),
    (r"japan|korea|guam|tonga|pacific|australia|new zealand", "PACIFIC", "the Pacific", 22.0, 150.0, "pacific"),
    (r"united states|u\.s\.|\bus\b|america|florida|new york|virginia|california|hawaii|alaska|caribbean|cuba",
     "US", "near the United States", 36.8, -73.0, "conus"),
]
ZONE_LABELS = ("RED SEA", "E. MED", "SUEZ", "GULF")
STRONG_NAMES = {"estlink", "nordbalt", "balticconnector", "c-lion", "sea-me-we", "aae-1", "2africa", "peace cable",
                "imewe", "seacom", "fenno-skan", "eig", "falcon"}


def _miles(a1, o1, a2, o2):
    return geo.miles(a1, o1, a2, o2)


_DATA = None


def cable_list():
    """The same cables.json the map draws (built by tools/build_cables.py)."""
    global _DATA
    if _DATA is None:
        try:
            with open(os.path.join(HERE, "..", "cables.json")) as f:
                _DATA = json.load(f)["cables"]
        except Exception:
            _DATA = []
    return _DATA


_ALIASES = None
# single-word cable names that are also everyday words; never used to tag a story
COMMON = {"africa", "america", "atlantic", "pacific", "europe", "asia", "india", "japan", "china", "korea", "taiwan",
          "medusa", "grace", "unity", "hope", "liberty", "victory", "falcon", "eagle", "phoenix", "orient", "express",
          "gemini", "apollo", "jupiter", "venus", "mercury", "polar", "arctic", "aurora", "atlas", "ocean", "coral",
          "pearl", "crystal", "dragon", "tiger", "lion", "comet", "spark", "bridge", "gateway", "harmony", "echo",
          "bifrost", "marea", "dunant", "equiano", "amitie", "south", "north", "east", "west", "global", "royal",
          "dhivaru", "malta", "italy", "greece", "cyprus", "israel", "egypt", "oman", "yemen", "sudan", "kenya",
          "ghana", "nigeria", "brazil", "chile", "peru", "mexico", "cuba", "canada", "alaska", "hawaii", "guam",
          "tonga", "samoa", "fiji", "palau", "nauru", "tuvalu", "honotua", "natitua", "manatua", "havfrue", "celtic",
          "scotland", "ireland", "wales", "iceland", "norway", "sweden", "finland", "estonia", "latvia", "poland",
          "denmark", "germany", "france", "spain", "portugal", "turkey", "russia", "ukraine", "georgia", "persia",
          "arabia", "jordan", "lebanon", "syria", "libya", "tunisia", "algeria", "morocco", "somalia", "djibouti"}


def aliases():
    """Cable names to look for in headlines -> cable ids."""
    global _ALIASES
    if _ALIASES is None:
        out = []
        for c in cable_list():
            n = c["n"].lower()
            base = re.sub(r"\s*\((.*?)\)\s*", " ", n).strip()
            forms = {base}
            for par in re.findall(r"\((.*?)\)", n):
                if 3 <= len(par) <= 20:
                    forms.add(par.strip())
            if base.startswith("hvdc "):
                forms.add(base[5:])
            if base.endswith(" cable"):
                forms.add(base[:-6])
            for f in forms:
                distinctive = (bool(re.search(r"[0-9\-]", f)) or f in STRONG_NAMES or len(f) >= 9
                               or (len(f) >= 5 and " " not in f and f not in COMMON))
                if (len(f) >= 4 or f in STRONG_NAMES) and distinctive and not f.startswith(("undersea power", "power cable")):
                    out.append((re.compile(r"(?<![a-z0-9])" + re.escape(f) + r"(?![a-z0-9])"), c["id"]))
        _ALIASES = out
    return _ALIASES


_COMPACT = None


def compact_aliases():
    """Names with numbers, squeezed (SeaMeWe-5 = SEA-ME-WE 5 = seamewe5)."""
    global _COMPACT
    if _COMPACT is None:
        out = []
        for c in cable_list():
            base = re.sub(r"\s*\((.*?)\)\s*", " ", c["n"].lower())
            for form in [base, base.replace("hvdc ", "")] + re.findall(r"\((.*?)\)", c["n"].lower()):
                sq = re.sub(r"[^a-z0-9]", "", form)
                if re.search(r"[0-9]", sq) and re.search(r"[a-z]", sq) and len(sq) >= 4:
                    out.append((sq, c["id"]))
        _COMPACT = out
    return _COMPACT


def match_cables(text):
    low = text.lower()
    ids = []
    for rx, cid in aliases():
        if cid not in ids and rx.search(low):
            ids.append(cid)
    words = re.findall(r"[a-z0-9\-]+", low)
    for i in range(len(words)):
        for j in range(i + 1, min(len(words), i + 4) + 1):
            sq = re.sub(r"[^a-z0-9]", "", "".join(words[i:j]))
            for name, cid in compact_aliases():
                if sq == name and cid not in ids:
                    ids.append(cid)
    return ids[:6]


def http(url, timeout=20, headers=None):
    h = {"User-Agent": UA, "Accept-Encoding": "gzip"}
    h.update(headers or {})
    with urllib.request.urlopen(urllib.request.Request(url, headers=h), timeout=timeout) as r:
        raw = r.read()
        if r.headers.get("Content-Encoding") == "gzip" or raw[:2] == b"\x1f\x8b":
            raw = gzip.decompress(raw)
        return raw


def pull_cable_news(parse_feed):
    items, ok = [], 0
    for q in QUERIES:
        u = "https://news.google.com/rss/search?" + urllib.parse.urlencode(
            {"q": q + " when:1d", "hl": "en-US", "gl": "US", "ceid": "US:en"})
        try:
            items += parse_feed(http(u, timeout=15), "")
            ok += 1
        except Exception:
            pass
        time.sleep(0.3)
    return items, ok


def is_cable_story(low):
    if re.search(EXCLUDE, low):
        return False
    if re.search(STRONG, low):
        return True
    if re.search(WEAK, low) and re.search(SEA, low):
        return True
    if re.search(r"\byantar\b", low):
        return True
    if (re.search(SHIP, low) or re.search(SPY, low)) and re.search(r"\bcables?\b", low):
        return True
    return False


def classify(low):
    """-> (tier, label) or None"""
    low = low.replace("fault line", "")
    if re.search(SOFT, low):  # laws, trials, plots foiled, new tech, repairs: worth a look, not an alarm
        return "ROUTINE", "CABLE WATCH"
    if re.search(r"\b(not sabotage|rules? out|ruled out|ruling out|no link|accident|closes?|closed|released?|releases)\b", low):
        return "ROUTINE", "CABLE WATCH"  # an investigation wrapping up, not a new cut
    hypo = re.search(HYPO, low) is not None
    dmg = re.search(DAMAGE, low) is not None
    if dmg and not hypo:
        if re.search(SABOTAGE, low):
            return "FLASH", "CABLE SABOTAGE"
        if re.search(CUT, low):
            return "FLASH" if any(re.search(p[0], low) for p in PLACES if p[1] in ZONE_LABELS) else "IMMEDIATE", "CABLE CUT"
        return "IMMEDIATE", "CABLE DAMAGED"
    if re.search(SABOTAGE, low) and not hypo:
        return "FLASH", "CABLE SABOTAGE"
    if re.search(SPY, low):
        return "IMMEDIATE", "SPY SHIP NEAR CABLES"
    if re.search(SHIP, low):
        return ("ROUTINE" if hypo else "IMMEDIATE"), "SHIP OVER CABLE"
    if dmg or re.search(SECURITY, low):
        return "ROUTINE", "CABLE WATCH"
    return None


def place_of(text, cable_ids):
    low = text.lower()
    for rx, short, words, lat, lon, rk in PLACES:
        if re.search(rx, low):
            return short, words, lat, lon, rk
    # no place word: use the first named cable's watch-zone status
    for c in cable_list():
        if c["id"] in cable_ids and c.get("hl"):
            return "E. MED", "Israel & the Eastern Med", 33.4, 32.5, "easternmed"
    return "WORLD", "somewhere in the world", None, None, None


def news_alerts(items, cfg, state, first_run, trusted, now, now_ts):
    w, rg_on = cfg["watches"], cfg["regions"]
    seen = state.setdefault("seen_cable", {})
    fresh_cut = now - timedelta(hours=6)
    groups = {}
    for it in items:
        t = it.get("title") or ""
        src = it.get("source") or ""
        s = src.lower()
        if not t or not (trusted(src) or any(x == s or s.startswith(x) for x in EXTRA_TRUSTED)):
            continue
        low = t.lower()
        if not is_cable_story(low):
            continue
        nid = hashlib.sha1(re.sub(r"[^a-z0-9]", "", low).encode()).hexdigest()[:14]
        if nid in seen:
            continue
        seen[nid] = now_ts
        if first_run or not it.get("dt") or it["dt"] < fresh_cut:
            continue
        cl = classify(low)
        if not cl:
            continue
        tier, label = cl
        watch = "cableships" if label in ("SPY SHIP NEAR CABLES", "SHIP OVER CABLE") else "cables"
        if not w.get(watch, True):
            continue
        ids = match_cables(t)
        short, words, lat, lon, rk = place_of(t, ids)
        if rk and not rg_on.get(rk, True):
            continue
        g = groups.setdefault((label, short), {"tier": tier, "watch": watch, "items": [], "ids": [],
                                               "place": (words, lat, lon, rk)})
        if ["FLASH", "IMMEDIATE", "ROUTINE"].index(tier) < ["FLASH", "IMMEDIATE", "ROUTINE"].index(g["tier"]):
            g["tier"] = tier
        g["items"].append(it)
        g["ids"] += [i for i in ids if i not in g["ids"]]
    for k in [k for k, v in seen.items() if now_ts - v > 4 * 86400]:
        del seen[k]
    names = {c["id"]: c for c in cable_list()}
    alerts = []
    for (label, short), g in groups.items():
        its = sorted(g["items"], key=lambda x: x["dt"], reverse=True)
        top = its[0]
        sources = []
        for x in its:
            if x["source"] not in sources:
                sources.append(x["source"])
        words, lat, lon, rk = g["place"]
        tier = g["tier"]
        threat = {"FLASH": "HIGH", "IMMEDIATE": "ELEVATED", "ROUTINE": "LOW"}[tier]
        if tier == "FLASH" and len(sources) >= 3:
            threat = "SEVERE"
        kinds = []
        alltxt = " ".join(x["title"].lower() for x in its)
        if re.search(r"internet|data|fib(er|re)|telecom|communications?|optical", alltxt):
            kinds.append("Internet / data cables")
        if re.search(r"power|electricity|interconnector|estlink|fenno-skan|nordbalt|baltic cable", alltxt):
            kinds.append("Power cables")
        named = [names[i]["n"] for i in g["ids"] if i in names][:3]
        assets = ", ".join(named + kinds) or "Undersea cables"
        where = words[0].upper() + words[1:]
        far = f" About {round(_miles(HOME[0], HOME[1], lat, lon)):,} miles from home." if lat is not None else ""
        a = dict(
            tier=tier, key=f"cable:{label}:{short}", cooldown={"FLASH": 3, "IMMEDIATE": 6, "ROUTINE": 12}[tier] * 3600,
            watch=g["watch"], what=f"{label} - {short}" if short != "WORLD" else label, headline=top["title"],
            location=where, assets=assets,
            response=(f"{len(its)} reports in the last few hours." if len(its) > 1 else "One report so far.") + far,
            source=", ".join(sources[:3]) + (f" +{len(sources) - 3} more" if len(sources) > 3 else ""),
            threat=threat, area=rk, link=top["link"],
            more=[{"t": x["title"], "s": x["source"], "u": x["link"]} for x in its[:5]])
        if lat is not None:
            a["lat"], a["lon"] = lat, lon
        if g["ids"]:
            a["cables"] = g["ids"][:6]
        alerts.append(a)
    return alerts


# ----------------------------------------------------------------- live ships over cables (Baltic)
AIS = "https://meri.digitraffic.fi/api/ais/v1/"
AIS_AREA = "the Gulf of Finland & northern Baltic"
# ports & anchorages to ignore (ships wait here all the time): (lat, lon, km)
PORTS = [
    (60.16, 24.95, 14), (60.21, 25.19, 10), (60.31, 25.55, 12), (59.44, 24.76, 14), (59.50, 24.95, 10),
    (59.35, 24.05, 10), (60.46, 26.94, 12), (60.57, 27.19, 10), (59.92, 30.25, 30), (59.99, 29.77, 14),
    (59.68, 28.40, 14), (60.35, 28.70, 14), (60.61, 28.57, 12), (59.40, 27.75, 8), (59.82, 22.97, 10),
    (60.44, 22.22, 14), (60.47, 21.99, 8), (60.10, 19.94, 8), (61.13, 21.45, 10), (61.60, 21.45, 10),
    (63.09, 21.57, 12), (64.68, 24.48, 12), (65.01, 25.43, 12), (65.73, 24.55, 12), (65.58, 22.18, 12),
    (63.82, 20.27, 12), (62.39, 17.35, 10), (60.68, 17.17, 12), (59.33, 18.07, 22), (59.72, 19.06, 8),
    (58.90, 17.95, 8), (57.64, 18.29, 8), (56.95, 24.10, 14), (57.40, 21.55, 10), (56.52, 21.00, 10),
    (55.72, 21.12, 12), (54.70, 20.50, 20), (54.36, 18.65, 18), (54.53, 18.55, 10), (55.67, 12.60, 18),
    (55.60, 13.00, 10), (54.18, 12.10, 10), (54.33, 10.15, 12), (53.96, 10.87, 10), (56.16, 15.59, 8),
    (56.66, 16.36, 8), (59.20, 18.65, 8), (60.40, 24.95, 6), (60.30, 22.30, 12),
]
WATCH_NAMES = {"YANTAR"}
LOCAL_FLAGS = {"Finland", "Estonia", "Sweden"}
WATCH_MIDS = {"273": "Russia", "412": "China", "413": "China", "414": "China", "477": "Hong Kong", "422": "Iran"}
FLAGS = {
    "273": "Russia", "230": "Finland", "276": "Estonia", "265": "Sweden", "266": "Sweden", "257": "Norway",
    "258": "Norway", "259": "Norway", "219": "Denmark", "220": "Denmark", "211": "Germany", "218": "Germany",
    "261": "Poland", "275": "Latvia", "277": "Lithuania", "412": "China", "413": "China", "414": "China",
    "477": "Hong Kong", "636": "Liberia", "538": "Marshall Islands", "351": "Panama", "352": "Panama",
    "353": "Panama", "354": "Panama", "355": "Panama", "356": "Panama", "357": "Panama", "370": "Panama",
    "371": "Panama", "372": "Panama", "373": "Panama", "248": "Malta", "249": "Malta", "256": "Malta",
    "215": "Malta", "229": "Malta", "209": "Cyprus", "210": "Cyprus", "212": "Cyprus", "240": "Greece",
    "241": "Greece", "237": "Greece", "239": "Greece", "620": "Comoros", "613": "Cameroon", "667": "Sierra Leone",
    "677": "Tanzania", "422": "Iran", "312": "Belize", "341": "St Kitts & Nevis", "375": "St Vincent",
    "376": "St Vincent", "377": "St Vincent", "518": "Cook Islands", "511": "Palau", "671": "Togo",
    "626": "Gabon", "629": "Gambia", "271": "Turkey", "244": "Netherlands", "245": "Netherlands",
    "246": "Netherlands", "232": "the UK", "233": "the UK", "234": "the UK", "235": "the UK", "366": "the US",
    "367": "the US", "368": "the US", "369": "the US", "338": "the US", "316": "Canada", "431": "Japan",
    "440": "South Korea", "563": "Singapore", "564": "Singapore", "565": "Singapore", "566": "Singapore",
    "308": "the Bahamas", "309": "the Bahamas", "311": "the Bahamas", "305": "Antigua", "304": "Antigua",
    "236": "Gibraltar", "224": "Spain", "225": "Spain", "226": "France", "227": "France", "228": "France",
    "247": "Italy", "255": "Portugal", "263": "Portugal", "207": "Bulgaria", "264": "Romania", "272": "Ukraine",
    "231": "the Faroe Islands", "251": "Iceland", "250": "Ireland", "205": "Belgium", "253": "Luxembourg",
}


PORT_CODES = {"RUVYS": "Vysotsk", "RUULU": "Ust-Luga", "RUPRI": "Primorsk", "RULED": "St. Petersburg",
              "RUKGD": "Kaliningrad", "RUBLT": "Baltiysk", "EEMUG": "Muuga", "EETLL": "Tallinn", "EESLM": "Sillam\u00e4e",
              "EEPLA": "Paldiski", "EEKND": "Kunda", "FIHEL": "Helsinki", "FIVUO": "Vuosaari", "FIKTK": "Kotka",
              "FIHMN": "Hamina", "FIPOR": "Porvoo", "FISKV": "Sk\u00f6ldvik", "FIHKO": "Hanko", "FITKU": "Turku",
              "FINLI": "Naantali", "FIRAU": "Rauma", "FIPOR": "Porvoo", "FIOUL": "Oulu", "FIKOK": "Kokkola",
              "SESTO": "Stockholm", "SENYN": "Nyn\u00e4shamn", "SEKPS": "Kapellsk\u00e4r", "LVRIX": "Riga",
              "LVVNT": "Ventspils", "LTKLJ": "Klaip\u0117da", "PLGDN": "Gda\u0144sk", "PLGDY": "Gdynia", "DEKEL": "Kiel",
              "DEROK": "Rostock", "DKCPH": "Copenhagen"}
CC = {"RU": "Russia", "FI": "Finland", "EE": "Estonia", "SE": "Sweden", "LV": "Latvia", "LT": "Lithuania",
      "PL": "Poland", "DE": "Germany", "DK": "Denmark", "NL": "Netherlands", "NO": "Norway", "BE": "Belgium"}


def plain_dest(d):
    """AIS destinations are often port codes (RUVYS = Vysotsk, Russia)."""
    d = (d or "").strip()
    sq = re.sub(r"[^A-Z]", "", d.upper())
    if len(sq) == 5 and sq in PORT_CODES:
        return PORT_CODES[sq] + (", " + CC[sq[:2]] if sq[:2] in CC else "")
    if len(sq) == 5 and sq[:2] in CC and re.fullmatch(r"[A-Z]{2}\s?[A-Z]{3}", d.upper()):
        return f"a port in {CC[sq[:2]]} ({d})"
    return d.title() if d.isupper() and len(d) > 3 else d


def ship_kind(t):
    t = t or 0
    if 70 <= t <= 79:
        return "cargo ship"
    if 80 <= t <= 89:
        return "tanker"
    if 90 <= t <= 99:
        return "other / special ship"
    if t == 35:
        return "military ship"
    if t == 33:
        return "dredger / underwater work ship"
    if t == 0:
        return "ship (type not shared)"
    return None  # fishing, sailing, pleasure, pilot, tug, rescue, police, passenger: left out


def _km_to_seg(lat, lon, a1, o1, a2, o2):
    k = math.cos(math.radians(lat))
    x, y = lon * k * 111.32, lat * 110.57
    x1, y1, x2, y2 = o1 * k * 111.32, a1 * 110.57, o2 * k * 111.32, a2 * 110.57
    dx, dy = x2 - x1, y2 - y1
    if dx == 0 and dy == 0:
        return math.hypot(x - x1, y - y1)
    t = max(0, min(1, ((x - x1) * dx + (y - y1) * dy) / (dx * dx + dy * dy)))
    return math.hypot(x - (x1 + t * dx), y - (y1 + t * dy))


def _km(a1, o1, a2, o2):
    return _miles(a1, o1, a2, o2) * 1.609


_SEGS = None


def baltic_segments():
    global _SEGS
    if _SEGS is None:
        segs = []
        try:
            with open(os.path.join(HERE, "baltic_cables.json")) as f:
                lines = json.load(f)["lines"]
        except Exception:
            lines = []
        for ln in lines:
            g = ln["g"]
            for (a1, o1), (a2, o2) in zip(g, g[1:]):
                segs.append((min(a1, a2), max(a1, a2), min(o1, o2), max(o1, o2), a1, o1, a2, o2, ln["id"], ln["n"], ln["k"]))
        _SEGS = segs
    return _SEGS


def nearest_cable(lat, lon, max_km):
    best = None
    pad_a, pad_o = max_km / 110.0, max_km / (111.0 * max(0.2, math.cos(math.radians(lat))))
    for s in baltic_segments():
        if lat < s[0] - pad_a or lat > s[1] + pad_a or lon < s[2] - pad_o or lon > s[3] + pad_o:
            continue
        d = _km_to_seg(lat, lon, s[4], s[5], s[6], s[7])
        if d <= max_km and (best is None or d < best[0]):
            best = (d, s[8], s[9], s[10])
    return best


def near_port(lat, lon):
    return any(_km(lat, lon, a, o) <= r for a, o, r in PORTS)


def ship_watch(cfg, state, now_ts):
    """-> (alerts, info for cablewatch.json)"""
    hdr = {"Digitraffic-User": "WatchmanRadar/1.0"}
    locs = json.loads(http(AIS + "locations", timeout=40, headers=hdr))["features"]
    meta = {}
    try:
        for v in json.loads(http(AIS + "vessels", timeout=40, headers=hdr)):
            meta[v.get("mmsi")] = v
    except Exception:
        pass
    cache = state.setdefault("ais_meta", {})
    for m, v in meta.items():
        cache[str(m)] = {"n": (v.get("name") or "").strip(), "t": v.get("shipType") or 0,
                         "d": plain_dest(v.get("destination"))[:40], "cs": (v.get("callSign") or "").strip(),
                         "seen": now_ts}
    for m in [m for m, v in cache.items() if now_ts - v.get("seen", 0) > 7 * 86400]:
        del cache[m]

    watch = state.setdefault("cable_ships", {})
    now_ms = now_ts * 1000
    checked, near_now = 0, []
    for f in locs:
        p = f.get("properties", {})
        lon, lat = f["geometry"]["coordinates"][:2]
        if now_ms - (p.get("timestampExternal") or 0) > 20 * 60 * 1000:
            continue
        checked += 1
        mmsi = str(f.get("mmsi") or p.get("mmsi"))
        sog = p.get("sog") or 0
        nav = p.get("navStat")
        if sog > 3.0 or nav == 5:  # moving along, or tied up in port
            continue
        m = cache.get(mmsi, {})
        kind = ship_kind(m.get("t", 0))
        mid = mmsi[:3]
        flag = FLAGS.get(mid, "")
        name = m.get("n") or ""
        on_list = name.upper() in WATCH_NAMES or mid in WATCH_MIDS
        if not kind and not on_list:
            continue
        if near_port(lat, lon):
            continue
        if not on_list and flag in LOCAL_FLAGS and kind in ("other / special ship", "ship (type not shared)",
                                                              "dredger / underwater work ship", "military ship"):
            continue  # the area's own work boats, buoy tenders, navy and exercise markers
        if re.search(r"exercise|firing|warning|buoy|dredg|survey", name.lower()) and not on_list:
            continue
        nc = nearest_cable(lat, lon, 2.0)
        if not nc:
            continue
        w = watch.get(mmsi) or {"first": now_ts}
        if w.get("cable") != nc[1]:
            w = {"first": now_ts}
        w.update({"last": now_ts, "lat": round(lat, 4), "lon": round(lon, 4), "sog": sog, "nav": nav,
                  "cable": nc[1], "cname": nc[2], "ck": nc[3], "km": round(nc[0], 2), "name": name,
                  "kind": kind or "ship (type not shared)", "flag": flag, "dest": m.get("d", ""),
                  "list": on_list})
        watch[mmsi] = w
        near_now.append(mmsi)
    for k in [k for k, v in watch.items() if now_ts - v.get("last", 0) > 25 * 60]:
        del watch[k]

    alerts, ships = [], []
    for mmsi, v in watch.items():
        mins = round((v["last"] - v["first"]) / 60)
        place = geo.where(v["lat"], v["lon"])
        pname = (place.get("sea") or ("off " + place["coast"] if place.get("coast") else AIS_AREA))
        home = round(_miles(HOME[0], HOME[1], v["lat"], v["lon"]))
        ship = {"mmsi": mmsi, "name": v["name"] or f"Ship {mmsi}", "kind": v["kind"], "flag": v["flag"],
                "lat": v["lat"], "lon": v["lon"], "sog": v["sog"], "at_anchor": v.get("nav") == 1,
                "cable": v["cable"], "cname": v["cname"], "ck": v["ck"], "mi": round(v["km"] / 1.609, 1),
                "mins": mins, "place": pname, "home_mi": home, "dest": v["dest"], "list": v["list"],
                "hanging": mins >= 30}
        ship["cphrase"] = ("an unnamed undersea power cable" if v["cname"].lower().startswith(("undersea power", "power cable"))
                           else v["cname"])
        ships.append(ship)
        russian_waters = v["lon"] > 27.8 and v["lat"] > 59.4  # eastern Gulf of Finland, near Russia's own ports
        flagged = v["list"] and not russian_waters
        if mins < (30 if flagged else 60):
            continue
        if not cfg["watches"].get("cableships", True) or not cfg["regions"].get("baltic", True):
            continue
        tier = "IMMEDIATE" if flagged else "ROUTINE"
        flagw = f", flag of {v['flag']}" if v["flag"] else ""
        cablew = ("power cable" if v["ck"] == "pw" else "internet cable")
        cphrase = (f"an unnamed undersea {cablew}" if v["cname"].lower().startswith(("undersea power", "power cable"))
                   else f"the {v['cname']} {cablew}")
        state_w = "anchored" if v.get("nav") == 1 else f"barely moving ({v['sog']:.1f} knots)"
        alerts.append(dict(
            tier=tier, key=f"cableship:{mmsi}", cooldown=24 * 3600, watch="cableships",
            what="SHIP OVER CABLE - " + ("GULF OF FINLAND" if "Finland" in pname else "BALTIC SEA"),
            headline=(f"{ship['name']} ({v['kind']}{flagw}) has been {state_w} right over {cphrase} for {mins} minutes"),
            location=pname[0].upper() + pname[1:],
            assets=f"{ship['name']}, {v['kind']}" + (f", {v['flag']}" if v["flag"] else "") + f" / {v['cname']}",
            response=(f"About {ship['mi']} miles from the cable line on the map. "
                      + (f"Says it is headed to {v['dest']}. " if v["dest"] else "")
                      + ("On the watch list. " if v["list"] else "")
                      + "Ships often wait at anchor for a port, so this can be harmless. "
                      + f"About {home:,} miles from home."),
            source="Finland's open ship feed (Digitraffic)", threat="ELEVATED" if v["list"] else "LOW",
            area="baltic", lat=v["lat"], lon=v["lon"], cables=[v["cable"]], mmsi=mmsi))
    ships.sort(key=lambda s: (-int(s["hanging"]), -s["mins"]))
    info = {"ok": True, "area": AIS_AREA, "checked": checked, "near": len(near_now),
            "hanging": sum(1 for s in ships if s["hanging"]), "ships": ships[:25]}
    return alerts, info


# ----------------------------------------------------------------- one call from the main sweep
def run(items, cfg, state, first_run, trusted, parse_feed, now, now_ts):
    """-> (alerts, cablewatch dict). Never raises for one half failing."""
    alerts = []
    out = {"updated": now_ts, "news_ok": False, "ais": {"ok": False, "area": AIS_AREA, "note": "not checked"},
           "zone_cables": sum(1 for c in cable_list() if c.get("hl")), "cables": len(cable_list())}
    try:
        extra, ok = pull_cable_news(parse_feed)
        out["news_ok"] = ok > 0
        seen_titles = {i["title"] for i in items}
        allitems = items + [i for i in extra if i["title"] not in seen_titles]
        alerts += news_alerts(allitems, cfg, state, first_run, trusted, now, now_ts)
    except Exception as e:
        print("cable news error:", type(e).__name__, e)
    try:
        a2, info = ship_watch(cfg, state, now_ts)
        if not first_run:
            alerts += a2
        out["ais"] = info
    except Exception as e:
        out["ais"] = {"ok": False, "area": AIS_AREA, "note": f"{type(e).__name__}"}
        print("ship watch error:", type(e).__name__, e)
    return alerts, out
