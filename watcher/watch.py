#!/usr/bin/env python3
"""WATCHTOWER - the sweep engine behind Watchman Radar.

Runs on a timer (GitHub Actions cron). Each sweep:
  1. reads Riley's settings (sent from the dashboard over his private command channel)
  2. pulls live military aircraft from adsb.lol
  3. pulls world headlines from trusted outlets
  4. scores everything into FLASH / IMMEDIATE / ROUTINE alerts
  5. pushes the ones he wants to his ntfy topic, logs all of them
  6. writes live.json / alerts.json / config.json / state.json for the dashboard

Standard library only.
"""
import hashlib
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime

try:
    from zoneinfo import ZoneInfo
    CENTRAL = ZoneInfo("America/Chicago")
except Exception:  # pragma: no cover
    CENTRAL = timezone(timedelta(hours=-5))

DATA_DIR = os.environ.get("DATA_DIR", "data")
TOPIC = os.environ.get("NTFY_TOPIC", "").strip()
NTFY = os.environ.get("NTFY_SERVER", "https://ntfy.sh").rstrip("/")
DRY_RUN = os.environ.get("DRY_RUN", "") == "1"
TEST_PUSH = os.environ.get("TEST_PUSH", "").lower() in ("1", "true", "yes")
UA = "WatchmanRadar/1.0 (personal dashboard; github actions)"

repo = os.environ.get("GITHUB_REPOSITORY", "")
if repo and "/" in repo:
    _o, _r = repo.split("/", 1)
    SITE_URL = os.environ.get("SITE_URL") or f"https://{_o.lower()}.github.io/{_r}/"
else:
    SITE_URL = os.environ.get("SITE_URL", "")

NOW = datetime.now(timezone.utc)
NOW_TS = int(NOW.timestamp())


def ctl_topic(topic):
    return topic + "-cmd-" + hashlib.sha256((topic + "|watchtower").encode()).hexdigest()[:8]


# ----------------------------------------------------------------- settings
DEFAULT_CONFIG = {
    "watches": {
        "tankers": True, "bombers": True, "airlift": True, "isr": True,
        "foreign_mil": True, "subs": True, "russia": True, "hormuz": True,
        "nuclear": True, "missiles": True, "warships": True, "buildups": True,
        "ukraine": True, "breaking": True,
    },
    "regions": {
        "alaska": True, "europe": True, "ukraine": True, "baltic": True,
        "gulf": True, "easternmed": True, "cuba": True, "pacific": True,
        "conus": True, "hawaii": True,
    },
    "push": {"FLASH": True, "IMMEDIATE": True, "ROUTINE": False},
    "quiet": {"enabled": False, "start": "22:00", "end": "06:00", "flash_breaks": True},
    "sensitivity": "normal",
    "paused": False,
}


def deep_merge(base, over):
    out = json.loads(json.dumps(base))
    if not isinstance(over, dict):
        return out
    for k, v in over.items():
        if k in out and isinstance(out[k], dict) and isinstance(v, dict):
            for k2, v2 in v.items():
                if k2 in out[k] and type(v2) == type(out[k][k2]):
                    out[k][k2] = v2
        elif k in out and type(v) == type(out[k]):
            out[k] = v
    return out


def load_json(name, default):
    try:
        with open(os.path.join(DATA_DIR, name)) as f:
            return json.load(f)
    except Exception:
        return default


def save_json(name, obj):
    os.makedirs(DATA_DIR, exist_ok=True)
    tmp = os.path.join(DATA_DIR, name + ".tmp")
    with open(tmp, "w") as f:
        json.dump(obj, f, ensure_ascii=False, separators=(",", ":"))
    os.replace(tmp, os.path.join(DATA_DIR, name))


def http_get(url, timeout=20, headers=None):
    h = {"User-Agent": UA}
    if headers:
        h.update(headers)
    req = urllib.request.Request(url, headers=h)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def pull_settings(cfg_saved):
    """Newest settings message Riley sent from the dashboard (ntfy keeps ~12h)."""
    cfg = deep_merge(DEFAULT_CONFIG, cfg_saved.get("settings") if cfg_saved else None)
    applied_id = (cfg_saved or {}).get("msg_id")
    applied_at = (cfg_saved or {}).get("set_at", 0)
    status = "saved"
    if not TOPIC:
        return cfg, applied_id, applied_at, "no topic"
    try:
        raw = http_get(f"{NTFY}/{ctl_topic(TOPIC)}/json?poll=1&since=all", timeout=15).decode()
        newest = None
        for line in raw.splitlines():
            try:
                m = json.loads(line)
            except Exception:
                continue
            if m.get("event") != "message":
                continue
            try:
                body = json.loads(m.get("message", ""))
            except Exception:
                continue
            if body.get("type") != "settings":
                continue
            if newest is None or m.get("time", 0) >= newest[0].get("time", 0):
                newest = (m, body)
        if newest and newest[0].get("time", 0) > applied_at:
            cfg = deep_merge(DEFAULT_CONFIG, newest[1].get("settings"))
            applied_id = newest[0].get("id")
            applied_at = newest[0].get("time", 0)
            status = "updated from command center"
    except Exception as e:
        status = f"command channel unreachable ({type(e).__name__})"
    return cfg, applied_id, applied_at, status


# ----------------------------------------------------------------- geography
# (name, label, [ (lat_min, lat_max, lon_min, lon_max), ... ])  first match wins
REGIONS = [
    ("cuba", "Cuba / Caribbean", [(17.0, 27.0, -88.0, -72.0)]),
    ("hawaii", "Hawaii", [(17.0, 25.0, -163.0, -152.0)]),
    ("alaska", "Alaska / Bering", [(51.0, 72.0, -180.0, -129.0), (50.0, 68.0, 165.0, 180.0)]),
    ("ukraine", "Ukraine / Black Sea", [(44.0, 53.0, 22.0, 41.0), (40.5, 47.0, 27.5, 42.0)]),
    ("baltic", "Baltic / Nordic", [(53.5, 71.0, 9.0, 32.0)]),
    ("easternmed", "Eastern Med / Israel", [(29.0, 37.5, 24.0, 38.0)]),
    ("gulf", "Persian Gulf / Hormuz", [(12.0, 31.0, 38.0, 63.0)]),
    ("europe", "Europe / North Atlantic", [(35.0, 72.0, -25.0, 45.0)]),
    ("pacific", "West Pacific / Japan / Taiwan", [(10.0, 46.0, 115.0, 150.0)]),
    ("conus", "Continental US", [(24.0, 50.0, -126.0, -65.0)]),
]
REGION_LABEL = {r[0]: r[1] for r in REGIONS}


def region_of(lat, lon):
    if lat is None or lon is None:
        return None
    for key, _label, boxes in REGIONS:
        for a, b, c, d in boxes:
            if a <= lat <= b and c <= lon <= d:
                return key
    return None


# ----------------------------------------------------------------- aircraft
TANKERS = {"K35R", "K35E", "K46", "KC46", "KC10", "DC10", "KC2", "A39M"}
BOMBERS = {"B52", "B1", "B2", "B21", "TU95", "T95", "TU16", "TU22", "T160", "TU60", "H6"}
AIRLIFT = {"C17", "C5", "C5M", "IL76", "Y20", "A400", "AN12", "AN22", "A124"}
TACTICAL_LIFT = {"C130", "C30J", "E390", "C27J", "C295", "CN35"}
ISR = {"R135", "E3TF", "E3CF", "E3", "E8", "E7WW", "E737", "P8", "P3", "EP3", "U2",
       "RQ4", "GLHK", "Q4", "MQ9", "E2", "A50", "IL20", "IL38", "TU14"}
NUKE_C2 = {"E6", "E4", "E4B"}
FIGHTERS = {"F15", "F16", "F18", "F18S", "F22", "F35", "EUFI", "RFAL", "GRIF", "SU27", "SU30",
            "SU35", "MG29", "MG31", "F14", "A10", "HAWK", "T38", "TEX2", "T6", "M346", "PC21"}
TYPE_NAMES = {
    "K35R": "KC-135R", "K35E": "KC-135E", "K46": "KC-46A", "KC46": "KC-46A", "KC10": "KC-10",
    "DC10": "KC-10", "B52": "B-52", "B1": "B-1B", "B2": "B-2", "B21": "B-21", "TU95": "Tu-95",
    "T95": "Tu-95", "T160": "Tu-160", "TU60": "Tu-160", "TU22": "Tu-22M", "H6": "H-6",
    "C17": "C-17", "C5": "C-5", "C5M": "C-5M", "IL76": "Il-76", "Y20": "Y-20", "A400": "A400M",
    "A124": "An-124", "C130": "C-130", "C30J": "C-130J", "R135": "RC-135", "E3TF": "E-3",
    "E3CF": "E-3", "E8": "E-8", "P8": "P-8", "P3": "P-3", "EP3": "EP-3", "U2": "U-2",
    "RQ4": "RQ-4", "GLHK": "RQ-4", "Q4": "RQ-4", "MQ9": "MQ-9", "E6": "E-6B", "E4": "E-4B",
    "E4B": "E-4B", "A50": "A-50", "IL20": "Il-20", "IL38": "Il-38", "E7WW": "E-7", "E737": "E-7",
}
ISR_CALLSIGNS = ("FORTE", "HOMER", "JAKE", "OLIVE", "COBRA", "SNTRY", "MAGMA", "NCHO")


def nation_of(hexcode):
    try:
        h = int(hexcode.strip("~"), 16)
    except Exception:
        return None
    if 0xA00000 <= h <= 0xAFFFFF:
        return "US"
    if 0x100000 <= h <= 0x1FFFFF:
        return "RU"
    if 0x780000 <= h <= 0x7BFFFF:
        return "CN"
    if 0x730000 <= h <= 0x737FFF:
        return "IR"
    if 0x0B0000 <= h <= 0x0B0FFF:
        return "CU"
    if 0x720000 <= h <= 0x727FFF:
        return "KP"
    return None


NATION_NAME = {"RU": "RUSSIAN", "CN": "CHINESE", "IR": "IRANIAN", "CU": "CUBAN", "KP": "NORTH KOREAN"}


def classify(t, callsign):
    t = (t or "").upper()
    cs = (callsign or "").upper()
    if t in NUKE_C2:
        return "c2"
    if t in BOMBERS:
        return "bomber"
    if t in TANKERS:
        return "tanker"
    if t in AIRLIFT:
        return "airlift"
    if t in ISR or cs.startswith(ISR_CALLSIGNS):
        return "isr"
    if t in TACTICAL_LIFT:
        return "tactical"
    if t in FIGHTERS:
        return "fighter"
    return "other"


def pull_aircraft():
    raw = http_get("https://api.adsb.lol/v2/mil", timeout=25)
    d = json.loads(raw)
    out = []
    for a in d.get("ac", []):
        lat, lon = a.get("lat"), a.get("lon")
        if lat is None:
            lat, lon = a.get("rr_lat"), a.get("rr_lon")
        if lat is None or lon is None:
            continue
        alt = a.get("alt_baro")
        if alt == "ground":
            alt = 0
        cs = (a.get("flight") or "").strip()
        t = (a.get("t") or "").upper()
        cat = classify(t, cs)
        out.append({
            "hex": a.get("hex"), "cs": cs, "t": t, "reg": a.get("r") or "",
            "lat": round(lat, 3), "lon": round(lon, 3),
            "alt": alt if isinstance(alt, (int, float)) else None,
            "gs": round(a["gs"]) if isinstance(a.get("gs"), (int, float)) else None,
            "trk": round(a["track"]) if isinstance(a.get("track"), (int, float)) else None,
            "sq": a.get("squawk") or "", "cat": cat, "rg": region_of(lat, lon),
            "nat": nation_of(a.get("hex") or ""),
        })
    return out


SENS = {"low": 1.4, "normal": 1.0, "high": 0.7}
TANKER_MIN = {"europe": 5, "gulf": 3, "alaska": 3, "pacific": 4, "cuba": 2, "easternmed": 3,
              "ukraine": 2, "baltic": 3, "hawaii": 3, "conus": 16}
AIRLIFT_MIN = {"europe": 6, "gulf": 4, "alaska": 3, "pacific": 5, "cuba": 2, "easternmed": 3,
               "ukraine": 3, "baltic": 3, "hawaii": 3, "conus": 30}


def fmt_assets(planes, limit=5):
    by = {}
    for p in planes:
        name = TYPE_NAMES.get(p["t"], p["t"] or "unknown type")
        by.setdefault(name, []).append(p["cs"] or p["reg"] or p["hex"])
    parts = []
    for name, calls in sorted(by.items(), key=lambda x: -len(x[1])):
        shown = ", ".join(c for c in calls[:limit] if c)
        more = f" +{len(calls) - limit}" if len(calls) > limit else ""
        parts.append(f"{len(calls)}x {name} ({shown}{more})")
    return "; ".join(parts)


def aircraft_alerts(planes, cfg, state):
    w, rg_on = cfg["watches"], cfg["regions"]
    mult = SENS.get(cfg.get("sensitivity"), 1.0)
    base = state.setdefault("baseline", {})
    alerts = []

    def region_ok(r):
        return r is not None and rg_on.get(r, True)

    counts = {}
    for p in planes:
        counts.setdefault(p["rg"], {}).setdefault(p["cat"], []).append(p)

    # Foreign military (by ICAO block) near the US, Alaska, Cuba, Hawaii or Europe
    if w.get("foreign_mil"):
        for p in planes:
            if p["nat"] in NATION_NAME and p["rg"] in ("alaska", "cuba", "conus", "hawaii", "europe", "baltic") and region_ok(p["rg"]) and not at_home(p):
                nm = NATION_NAME[p["nat"]]
                kind = "BOMBER" if p["cat"] == "bomber" else "MIL AIRCRAFT"
                alerts.append(dict(
                    tier="FLASH", key=f"foreign:{p['hex']}", cooldown=6 * 3600, watch="foreign_mil",
                    what=f"{nm} {kind} NEAR {short_region(p['rg'])}",
                    location=f"{REGION_LABEL[p['rg']]} ({p['lat']:.1f}, {p['lon']:.1f})",
                    assets=fmt_assets([p]) + alt_txt(p),
                    response="No official response reported yet. Watch for NORAD/NATO intercept news.",
                    source="adsb.lol live ADS-B (military feed)", threat="HIGH", region=p["rg"],
                    lat=p["lat"], lon=p["lon"]))

    # Bombers
    if w.get("bombers"):
        for p in planes:
            if p["cat"] != "bomber" or not region_ok(p["rg"]):
                continue
            if p["nat"] in NATION_NAME:
                continue  # already a FLASH above (or out of area)
            r = p["rg"]
            if r in ("europe", "baltic", "ukraine", "gulf", "easternmed", "pacific", "alaska", "cuba"):
                tier, threat = "IMMEDIATE", "ELEVATED"
                what = f"US BOMBER OVER {short_region(r)}"
            else:
                tier, threat = "ROUTINE", "LOW"
                what = f"BOMBER AIRBORNE {short_region(r)}"
            group = counts.get(r, {}).get("bomber", [])
            alerts.append(dict(
                tier=tier, key=f"bomber:{r}", cooldown=8 * 3600, watch="bombers", what=what,
                location=f"{REGION_LABEL[r]} ({p['lat']:.1f}, {p['lon']:.1f})",
                assets=fmt_assets(group) + alt_txt(p),
                response="Bomber task force / presence flight likely. No official statement seen yet.",
                source="adsb.lol live ADS-B (military feed)", threat=threat, region=r,
                lat=p["lat"], lon=p["lon"], count=len(group)))

    # Doomsday plane / TACAMO
    for p in planes:
        if p["cat"] == "c2" and region_ok(p["rg"]):
            e4 = p["t"] in ("E4", "E4B")
            alerts.append(dict(
                tier="IMMEDIATE" if e4 else "ROUTINE", key=f"c2:{p['t']}:{p['rg']}",
                cooldown=12 * 3600, watch="nuclear",
                what="E-4B DOOMSDAY PLANE AIRBORNE" if e4 else "E-6B TACAMO NUKE RELAY AIRBORNE",
                location=f"{REGION_LABEL[p['rg']]} ({p['lat']:.1f}, {p['lon']:.1f})",
                assets=fmt_assets([p]) + alt_txt(p),
                response="Often training or VIP travel. Watch for other nuclear-force activity.",
                source="adsb.lol live ADS-B (military feed)",
                threat="ELEVATED" if e4 else "LOW", region=p["rg"], lat=p["lat"], lon=p["lon"]))

    # Surges: tankers + strategic airlift, per region, against a learned baseline
    for r, cats in counts.items():
        if r is None:
            continue
        for cat, mins, watch, label in (("tanker", TANKER_MIN, "tankers", "TANKER SURGE"),
                                        ("airlift", AIRLIFT_MIN, "airlift", "AIRLIFT SURGE")):
            group = cats.get(cat, [])
            n = len(group)
            bkey = f"{r}:{cat}"
            b = base.get(bkey)
            if not w.get(watch) or not region_ok(r):
                continue
            need = max(2, round(mins.get(r, 4) * mult))
            if b is not None:
                need = max(need, int(b * 2 * mult) + 1)
            if n >= need:
                c = centroid(group)
                alerts.append(dict(
                    tier="IMMEDIATE", key=f"surge:{bkey}", cooldown=6 * 3600, watch=watch,
                    escalate_count=n, what=f"{label} {short_region(r)}",
                    location=f"{REGION_LABEL[r]} (center {c[0]:.1f}, {c[1]:.1f})",
                    assets=fmt_assets(group),
                    response=f"{n} airborne at once vs normal ~{(b or 0):.1f}. Tankers/airlift often move ahead of fighters or bombers.",
                    source="adsb.lol live ADS-B (military feed)", threat="ELEVATED", region=r,
                    lat=c[0], lon=c[1], count=n))
            elif n >= 2 and r != "conus":
                c = centroid(group)
                nm = "TANKERS" if cat == "tanker" else "HEAVY AIRLIFT"
                alerts.append(dict(
                    tier="ROUTINE", key=f"active:{bkey}", cooldown=8 * 3600, watch=watch,
                    what=f"{nm} ACTIVE {short_region(r)}",
                    location=f"{REGION_LABEL[r]} (center {c[0]:.1f}, {c[1]:.1f})",
                    assets=fmt_assets(group), response="Logged. Normal activity level so far.",
                    source="adsb.lol live ADS-B (military feed)", threat="LOW", region=r,
                    lat=c[0], lon=c[1], count=n))

        # Sub hunters: maritime patrol clusters
        mpa = [p for p in cats.get("isr", []) if p["t"] in ("P8", "P3", "IL38", "TU14") or p["cs"].startswith("HOMER")]
        if w.get("subs") and region_ok(r) and len(mpa) >= max(2, round(3 * mult)) and r != "conus":
            c = centroid(mpa)
            hi = len(mpa) >= max(3, round(5 * mult)) or r in ("cuba", "alaska", "hawaii")
            alerts.append(dict(
                tier="IMMEDIATE" if hi else "ROUTINE", key=f"subhunt:{r}", cooldown=8 * 3600,
                watch="subs", escalate_count=len(mpa), what=f"SUB HUNTERS UP {short_region(r)}",
                location=f"{REGION_LABEL[r]} (center {c[0]:.1f}, {c[1]:.1f})",
                assets=fmt_assets(mpa),
                response="Several maritime patrol planes at once can mean a submarine is being tracked.",
                source="adsb.lol live ADS-B (military feed)", threat="ELEVATED" if hi else "LOW",
                region=r, lat=c[0], lon=c[1], count=len(mpa)))

        # Spy plane clusters near hot zones
        spy = [p for p in cats.get("isr", []) if p not in mpa]
        if w.get("isr") and region_ok(r) and r in ("ukraine", "baltic", "gulf", "easternmed", "cuba", "pacific", "alaska") and len(spy) >= max(2, round(3 * mult)):
            c = centroid(spy)
            alerts.append(dict(
                tier="ROUTINE", key=f"isr:{r}", cooldown=8 * 3600, watch="isr",
                escalate_count=len(spy), what=f"SPY PLANES ACTIVE {short_region(r)}",
                location=f"{REGION_LABEL[r]} (center {c[0]:.1f}, {c[1]:.1f})",
                assets=fmt_assets(spy), response="Logged. Recon / radar planes watching the area.",
                source="adsb.lol live ADS-B (military feed)", threat="LOW", region=r,
                lat=c[0], lon=c[1], count=len(spy)))

    # Emergency squawks
    for p in planes:
        if p["sq"] in ("7500", "7600", "7700") and region_ok(p["rg"]):
            meaning = {"7500": "HIJACK CODE", "7600": "RADIO FAILURE", "7700": "EMERGENCY"}[p["sq"]]
            alerts.append(dict(
                tier="IMMEDIATE" if p["sq"] == "7500" else "ROUTINE", key=f"squawk:{p['hex']}:{p['sq']}",
                cooldown=6 * 3600, watch="breaking",
                what=f"MIL JET SQUAWKING {meaning}",
                location=f"{REGION_LABEL.get(p['rg'], 'Unknown')} ({p['lat']:.1f}, {p['lon']:.1f})",
                assets=fmt_assets([p]) + alt_txt(p), response="Squawk " + p["sq"] + " set by the crew.",
                source="adsb.lol live ADS-B (military feed)",
                threat="ELEVATED" if p["sq"] == "7500" else "LOW", region=p["rg"], lat=p["lat"], lon=p["lon"]))

    # Learn the normal level (slow moving average) after scoring
    for r in [x[0] for x in REGIONS]:
        for cat in ("tanker", "airlift"):
            n = len(counts.get(r, {}).get(cat, []))
            k = f"{r}:{cat}"
            base[k] = n if k not in base else round(base[k] * 0.97 + n * 0.03, 3)
    return alerts


def alt_txt(p):
    bits = []
    if p.get("alt"):
        bits.append(f"{int(p['alt']):,} ft")
    if p.get("gs"):
        bits.append(f"{p['gs']} kt")
    if p.get("trk") is not None:
        bits.append(f"hdg {p['trk']}")
    return (" | " + ", ".join(bits)) if bits else ""


def at_home(p):
    """Russian / Belarus-based flights over their own territory are not news."""
    if p["nat"] != "RU":
        return False
    lat, lon = p["lat"], p["lon"]
    if p["rg"] in ("europe", "baltic") and lon >= 23.0 and lat >= 41.0:
        return not (53.8 <= lat <= 59.8 and 21.0 <= lon <= 28.3 and lon < 28.2 and lat < 59.7 and lon < 27.5)
    if 54.2 <= lat <= 55.4 and 19.5 <= lon <= 23.0:  # Kaliningrad
        return True
    return False


def centroid(ps):
    return (sum(p["lat"] for p in ps) / len(ps), sum(p["lon"] for p in ps) / len(ps))


def short_region(r):
    return {"cuba": "CUBA", "hawaii": "HAWAII", "alaska": "ALASKA", "ukraine": "UKRAINE",
            "baltic": "BALTIC", "easternmed": "E. MED", "gulf": "GULF", "europe": "EUROPE",
            "pacific": "W. PACIFIC", "conus": "US"}.get(r, "UNKNOWN")


# ----------------------------------------------------------------- news
TRUSTED = [
    "reuters", "associated press", "ap news", "apnews", "bbc", "cnn", "fox news", "cbs news", "nbc news",
    "abc news", "al jazeera", "times of israel", "jerusalem post", "defense news", "breaking defense",
    "the war zone", "twz", "usni news", "military times", "stars and stripes", "newsweek",
    "kyiv independent", "bloomberg", "wall street journal", "new york times", "washington post",
    "the guardian", "air & space forces", "navy times", "yonhap", "nhk", "kyodo", "japan times",
    "euronews", "sky news", "france 24", "dw", "politico", "axios", "the hill", "i24", "ynet",
    "israel hayom", "the telegraph", "financial times", "cbc", "military.com", "the aviationist",
    "naval news", "defense one", "task & purpose", "united press international", "upi",
    "nikkei", "south china morning post", "the independent", "daily mail", "new york post",
    "washington examiner", "daily wire", "wion", "arab news", "jns", "all israel news",
    "ukrainska pravda", "kyiv post", "the moscow times", "meduza", "tass", "rt", "nk news",
    "forces news", "uk defence journal", "korea times", "korea herald", "indo-pacific defense forum",
    "the aviation geek club", "the defence blog", "united24", "al arabiya", "gulf news", "middle east eye",
    "the economic times", "times of india", "hindustan times", "cbs", "abc", "nbc", "msn", "yahoo", "janes", "the national", "anadolu", "pbs", "npr",
]
DIRECT_FEEDS = [
    ("BBC World", "https://feeds.bbci.co.uk/news/world/rss.xml"),
    ("USNI News", "https://news.usni.org/feed"),
    ("Defense News", "https://www.defensenews.com/arc/outboundfeeds/rss/?outputType=xml"),
    ("The War Zone", "https://www.twz.com/feed"),
    ("Times of Israel", "https://www.timesofisrael.com/feed/"),
    ("Kyiv Independent", "https://kyivindependent.com/news-archive/rss/"),
    ("Fox News", "https://moxie.foxnews.com/google-publisher/world.xml"),
    ("Al Jazeera", "https://www.aljazeera.com/xml/rss/all.xml"),
    ("The Guardian", "https://www.theguardian.com/world/rss"),
    ("Breaking Defense", "https://breakingdefense.com/feed/"),
    ("Military Times", "https://www.militarytimes.com/arc/outboundfeeds/rss/?outputType=xml"),
    ("Naval News", "https://www.navalnews.com/feed/"),
    ("UK Defence Journal", "https://ukdefencejournal.org.uk/feed/"),
    ("Jerusalem Post", "https://www.jpost.com/rss/rssfeedsfrontpage.aspx"),
]
GNEWS_QUERIES = [
    '"nuclear drill" OR "nuclear exercise" OR "nuclear forces"',
    '"missile test" OR ICBM OR "ballistic missile" OR hypersonic',
    'bombers intercepted OR NORAD OR "Russian bombers" OR "Chinese bombers"',
    'warships Cuba OR "Russian navy" Caribbean OR "Russian warship" OR "Chinese warship"',
    'submarine Russia OR China OR Cuba OR "nuclear submarine"',
    '"Strait of Hormuz" OR "Persian Gulf" OR "Gulf of Oman" OR "Red Sea" attack',
    '"troop buildup" OR "military buildup" OR mobilization OR "massing troops"',
    'Ukraine offensive OR counteroffensive OR breakthrough',
    'Russia NATO airspace OR drones OR Baltic OR Kaliningrad',
    'breaking war OR "martial law" OR "state of emergency" OR DEFCON',
]

FOREIGN = r"(russia|russian|china|chinese|iran|iranian|north korea|pyongyang|kremlin|moscow|beijing|tehran)"
US_AREA = r"(cuba|havana|caribbean|florida|u\.?s\.? coast|east coast|west coast|alaska|hawaii|gulf of mexico|california|virginia|puerto rico|guam|aleutian|bering)"
RULES = [
    # (watch, tier, regex, label, needs) -- needs: optional extra regex that must also match
    ("breaking", "FLASH", r"\b(nuclear (attack|strike|detonation|explosion|blast)|declares? war|defcon [12]|martial law declared|nuclear weapon (used|detonated))\b", "NUCLEAR / WAR DECLARATION", r"^(?!.*\b(escort|exercise|drill|simulat|threat|threaten|warns?|could|would|if|fears?|risk|image|video|picture|ai\b|deepfake|plan|scenario|game)).*$"),
    ("nuclear", "FLASH", r"\b(nuclear|strategic|deterrence) (forces )?(drill|drills|exercise|exercises|war ?games|launch drill)\b|\bgrom\b|\bglobal thunder\b", "NUCLEAR DRILL", None),
    ("missiles", "FLASH", r"\b(icbm|slbm|hypersonic missile|ballistic missile)s?\b.{0,50}\b(test|tests|tested|launch|launches|launched|fires|fired)\b|\b(test[- ]?(fire|fires|fired|launch|launches|launched))\b.{0,40}\b(missile|icbm|rocket)s?\b|\bmissile tests?\b|\b(tests?|tested|testing)\b.{0,50}\b(missile|icbm|slbm)s?\b|\b(north korea|pyongyang)\b.{0,40}\b(fires?|fired|launch(es|ed)?)\b.{0,40}\bmissiles?\b", "MISSILE TEST", None),
    ("bombers", "FLASH", r"\b(bombers?|tu-95|tu-160|tu-22|h-6)\b.{0,70}\b(intercept|intercepted|alaska|norad|adiz|off the coast|near (the )?(u\.?s|us|alaska|japan|europe|uk|britain|norway|poland))|\bintercept(s|ed)?\b.{0,50}\b(bombers?|russian (military )?(aircraft|jets|planes)|chinese (military )?(aircraft|jets|planes))\b", "BOMBERS NEAR US/EUROPE", None),
    ("warships", "FLASH", r"\b(warships?|frigates?|destroyers?|submarines?|flotilla|naval (group|squadron|task force)|navy ships?|cruisers?)\b", "WARSHIPS NEAR US/CUBA", FOREIGN + r".{0,120}" + US_AREA + r"|" + US_AREA + r".{0,120}" + FOREIGN),
    ("buildups", "IMMEDIATE", r"\b(troop|military|force|forces) (build-?up|buildup|massing|surge)\b|\bbuild-?up of (troops|forces)\b|\bmass(es|ed|ing)? (troops|forces|tanks)\b|\bmobiliz(ation|es|ed|ing)\b|\bdeploy(s|ed|ing)? (thousands|\d[\d,]* (troops|soldiers|marines))", "TROOP BUILDUP", None),
    ("ukraine", "IMMEDIATE", r"\b(major|massive|large-scale|new|biggest|summer|winter|spring|fall) (offensive|assault|push)\b|\bcounteroffensive\b|\bbreakthrough\b|\bencircl(e|ed|ement)\b|\bfront (collapses|collapse)\b", "MAJOR UKRAINE PUSH", r"(ukrain|russia|kyiv|donbas|donetsk|zaporizh|kharkiv|kherson|pokrovsk|kursk|sumy|dnipro)"),
    ("hormuz", "IMMEDIATE", r"\b(hormuz|persian gulf|gulf of oman|bab el-mandeb|red sea|houthi)\b", "HORMUZ / GULF", r"\b(seiz(e|ed|es|ure)|attack(ed|s)?|clos(e|ed|ure|ing)|mines?|strike|struck|drone|missile|hijack|boarded|blockade|fire)\b"),
    ("russia", "IMMEDIATE", r"\b(airspace (violation|violated|incursion)|violat(e|es|ed) .{0,30}airspace|drones? (over|into|in) (poland|romania|lithuania|latvia|estonia|finland|denmark|germany|norway|moldova)|article 4|article 5)\b", "RUSSIA VS NATO", None),
    ("subs", "ROUTINE", r"\bsubmarines?\b|\bsubs? (spotted|surfaces|surfaced|detected|tracked)\b", "SUB WATCH", r"\b(spotted|surfac\w*|detected|track\w*|shadow\w*|near|off the|patrol\w*|deploy\w*|arriv\w*|sails?|sailing|docks?|docked|port call|launch\w*|hunt\w*|sighted|enters?|entered|transit\w*|heads?|moves?|missile)\b"),
    ("russia", "ROUTINE", r"\b(russia|russian|kremlin|putin)\b.{0,60}\b(deploys?|deployed|moves?|moved|warns?|warned|threatens?|nato|baltic|kaliningrad|belarus|nuclear)\b", "RUSSIA MOVES", None),
    ("buildups", "ROUTINE", r"\b(carrier strike group|amphibious ready group|aircraft carrier)\b.{0,60}\b(deploy|deploys|deployed|heads?|sails?|arrives?|moves?|ordered)\b", "CARRIER MOVES", None),
]
EXCLUDE = r"\b(ai-generated|opinion|analysis|explainer|podcast|anniversary|years ago|in history|movie|film|book|review|video game|quiz|obituary|what to know|how to|soviet|cold war|wwii|world war ii|inquiry|commission|affair|lawsuit|stocks?|shares|earnings|contract award|museum)\b"
REGION_WORDS = [
    ("cuba", r"cuba|havana|caribbean|venezuela|puerto rico"),
    ("alaska", r"alaska|aleutian|bering|arctic"),
    ("hawaii", r"hawaii|pearl harbor"),
    ("ukraine", r"ukrain|kyiv|donbas|donetsk|crimea|black sea|zaporizh|kharkiv|kherson|odesa|kursk|sumy"),
    ("baltic", r"baltic|kaliningrad|lithuania|latvia|estonia|finland|sweden|norway|poland|belarus"),
    ("easternmed", r"israel|gaza|lebanon|hezbollah|syria|cyprus|jerusalem|idf|west bank"),
    ("gulf", r"iran|hormuz|persian gulf|gulf of oman|yemen|houthi|red sea|iraq|saudi|qatar|uae|bahrain|tehran"),
    ("pacific", r"china|taiwan|japan|korea|pyongyang|beijing|south china sea|philippines|guam|okinawa"),
    ("europe", r"nato|europe|germany|france|britain|uk |u\.k\.|romania|moldova|moscow|russia"),
    ("conus", r"united states|u\.s\.|pentagon|washington|norad|america"),
]
ASSET_WORDS = [
    (r"icbm|ballistic missile|hypersonic|cruise missile|missiles?", "Missiles"),
    (r"bombers?|tu-95|tu-160|b-52|b-2|b-1", "Bombers"),
    (r"submarines?|\bsubs?\b", "Submarine(s)"),
    (r"warships?|frigates?|destroyers?|cruisers?|navy|naval|carrier", "Warships / naval forces"),
    (r"fighter jets?|f-35|f-16|su-35|jets", "Fighter jets"),
    (r"drones?|uav", "Drones"),
    (r"troops|soldiers|forces|tanks|armou?r", "Ground forces"),
    (r"tankers?", "Tankers"),
]


def clean_title(t):
    return re.sub(r"\s+", " ", (t or "")).strip()


def split_source(title, src):
    if src:
        suf = " - " + src
        if title.endswith(suf):
            return title[: -len(suf)], src
    m = re.match(r"^(.*) - ([^-]{2,60})$", title)
    if m:
        return m.group(1), m.group(2)
    return title, src or ""


def parse_feed(raw, default_source):
    items = []
    root = ET.fromstring(raw)
    for it in root.iter("item"):
        title = clean_title(it.findtext("title"))
        link = (it.findtext("link") or "").strip()
        src_el = it.find("source")
        src = clean_title(src_el.text) if src_el is not None and src_el.text else default_source
        pub = it.findtext("pubDate")
        try:
            dt = parsedate_to_datetime(pub) if pub else None
            if dt and dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
        except Exception:
            dt = None
        title, src = split_source(title, src)
        items.append({"title": title, "link": link, "source": src, "dt": dt})
    return items


def pull_news():
    items, ok, bad = [], 0, 0
    urls = [(None, "https://news.google.com/rss/search?" + urllib.parse.urlencode(
        {"q": q + " when:1d", "hl": "en-US", "gl": "US", "ceid": "US:en"})) for q in GNEWS_QUERIES]
    urls += [(name, u) for name, u in DIRECT_FEEDS]
    for name, u in urls:
        try:
            items += parse_feed(http_get(u, timeout=15), name or "")
            ok += 1
        except Exception:
            bad += 1
        time.sleep(0.3)
    return items, ok, bad


def trusted(src):
    s = (src or "").lower()
    return any(t == s or s.startswith(t) or (" " + t) in (" " + s) for t in TRUSTED)


def news_alerts(items, cfg, state, first_run):
    w, rg_on = cfg["watches"], cfg["regions"]
    seen = state.setdefault("seen_news", {})
    fresh_cut = NOW - timedelta(hours=3)
    groups = {}
    for it in items:
        if not it["title"] or not trusted(it["source"]):
            continue
        nid = hashlib.sha1(re.sub(r"[^a-z0-9]", "", it["title"].lower()).encode()).hexdigest()[:14]
        if nid in seen:
            continue
        seen[nid] = NOW_TS
        if first_run or (it["dt"] and it["dt"] < fresh_cut) or not it["dt"]:
            continue
        low = it["title"].lower()
        if re.search(EXCLUDE, low):
            continue
        for watch, tier, rx, label, needs in RULES:
            if not re.search(rx, low):
                continue
            if needs and not re.search(needs, low):
                continue
            region = next((k for k, rr in REGION_WORDS if re.search(rr, low)), None)
            if watch == "warships" and region not in ("cuba", "alaska", "hawaii", "conus"):
                continue
            if region and not rg_on.get(region, True):
                break
            if not w.get(watch, True):
                break
            g = groups.setdefault((watch, label, region), {"tier": tier, "items": []})
            g["items"].append(it)
            break  # first (highest) rule wins
    alerts = []
    for (watch, label, region), g in groups.items():
        its = sorted(g["items"], key=lambda x: x["dt"] or NOW, reverse=True)
        top = its[0]
        sources = []
        for x in its:
            if x["source"] not in sources:
                sources.append(x["source"])
        assets = [name for rx, name in ASSET_WORDS if re.search(rx, " ".join(x["title"].lower() for x in its))]
        tier = g["tier"]
        threat = {"FLASH": "HIGH", "IMMEDIATE": "ELEVATED", "ROUTINE": "LOW"}[tier]
        if tier == "FLASH" and len(sources) >= 3:
            threat = "SEVERE"
        what = label if not region else f"{label} - {short_region(region)}"
        if label.endswith("/CUBA") or label.endswith("US/EUROPE"):
            what = label.replace("US/CUBA", short_region(region) if region else "US/CUBA")
        alerts.append(dict(
            tier=tier, key=f"news:{watch}:{label}:{region}", cooldown={"FLASH": 3, "IMMEDIATE": 5, "ROUTINE": 8}[tier] * 3600,
            watch=watch, what=what, headline=top["title"],
            location=REGION_LABEL.get(region, "Global") if region else "Global / see report",
            assets=", ".join(assets) if assets else "See report",
            response="Developing. " + (f"{len(its)} reports in the last 3 hours." if len(its) > 1 else "Single report so far."),
            source=", ".join(sources[:3]) + (f" +{len(sources) - 3} more" if len(sources) > 3 else ""),
            threat=threat, region=region, link=top["link"],
            more=[{"t": x["title"], "s": x["source"], "u": x["link"]} for x in its[:5]]))
    # forget old ids (keep 4 days)
    cut = NOW_TS - 4 * 86400
    for k in [k for k, v in seen.items() if v < cut]:
        del seen[k]
    return alerts


# ----------------------------------------------------------------- output
TIER_ICON = {"FLASH": "\U0001F7E5", "IMMEDIATE": "\U0001F7E7", "ROUTINE": "\U0001F7E6"}
TIER_PRIO = {"FLASH": 5, "IMMEDIATE": 4, "ROUTINE": 2}
TIER_RANK = {"FLASH": 0, "IMMEDIATE": 1, "ROUTINE": 2}


def central_time(ts=None):
    dt = (datetime.fromtimestamp(ts, timezone.utc) if ts else NOW).astimezone(CENTRAL)
    return dt.strftime("%-I:%M %p CT, %a %b %-d")


def make_title(tier, what):
    title = f"{TIER_ICON[tier]} {tier} // {what.upper()}"
    if len(title) > 39:
        title = title[:38].rstrip(" /-,") + "\u2026"
    return title


def make_body(a):
    lines = []
    if a.get("headline"):
        lines.append(a["headline"])
        lines.append("")
    lines += [
        f"\U0001F4CD LOCATION: {a['location']}",
        f"\U0001F550 TIME: {central_time(a.get('ts'))}",
        f"\U0001F6E9\uFE0F ASSETS: {a['assets']}",
        f"\U0001F6E1\uFE0F RESPONSE: {a['response']}",
        f"\U0001F4E1 SOURCE: {a['source']}",
        f"\u26A0\uFE0F THREAT LEVEL: {a['threat']}",
        "\u2014 WATCHTOWER",
    ]
    return "\n".join(lines)


def in_quiet(cfg):
    q = cfg.get("quiet", {})
    if not q.get("enabled"):
        return False
    try:
        now = NOW.astimezone(CENTRAL)
        mins = now.hour * 60 + now.minute
        sh, sm = map(int, q["start"].split(":"))
        eh, em = map(int, q["end"].split(":"))
        s, e = sh * 60 + sm, eh * 60 + em
        return (s <= mins < e) if s < e else (mins >= s or mins < e)
    except Exception:
        return False


def push(a, title, body):
    if not TOPIC:
        return "no topic"
    payload = {"topic": TOPIC, "title": title, "message": body, "priority": a.get("priority_override") or TIER_PRIO[a["tier"]],
               "tags": [{"FLASH": "rotating_light", "IMMEDIATE": "warning", "ROUTINE": "satellite"}[a["tier"]]]}
    click = a.get("link") or SITE_URL
    if click:
        payload["click"] = click
    if SITE_URL:
        payload["actions"] = [{"action": "view", "label": "Open Radar", "url": SITE_URL}]
    if DRY_RUN:
        print("DRY PUSH:", json.dumps(payload, ensure_ascii=False)[:600])
        return "dry"
    req = urllib.request.Request(NTFY + "/", data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json", "User-Agent": UA}, method="POST")
    with urllib.request.urlopen(req, timeout=15) as r:
        return "sent" if r.status == 200 else f"http {r.status}"


def main():
    os.makedirs(DATA_DIR, exist_ok=True)
    state = load_json("state.json", {})
    first_run = not state.get("initialized")
    cfg_saved = load_json("config.json", {})
    cfg, msg_id, set_at, cfg_status = pull_settings(cfg_saved)
    save_json("config.json", {"settings": cfg, "msg_id": msg_id, "set_at": set_at,
                              "applied": NOW_TS, "status": cfg_status})

    log = load_json("alerts.json", {"alerts": []})
    sources = {}
    planes = []
    try:
        planes = pull_aircraft()
        sources["adsb"] = {"ok": True, "note": f"{len(planes)} military aircraft"}
    except Exception as e:
        sources["adsb"] = {"ok": False, "note": f"{type(e).__name__}: {str(e)[:80]}"}
    items, ok, bad = [], 0, 0
    try:
        items, ok, bad = pull_news()
        sources["news"] = {"ok": ok > 0, "note": f"{ok} feeds ok, {bad} failed, {len(items)} headlines"}
    except Exception as e:
        sources["news"] = {"ok": False, "note": f"{type(e).__name__}"}

    candidates = []
    if planes:
        candidates += aircraft_alerts(planes, cfg, state)
    candidates += news_alerts(items, cfg, state, first_run)

    last = state.setdefault("last_alert", {})
    new_alerts = []
    for a in candidates:
        prev = last.get(a["key"])
        if prev and NOW_TS - prev["ts"] < a["cooldown"]:
            esc = a.get("escalate_count")
            if not (esc and prev.get("count") and esc >= prev["count"] * 1.5 and esc - prev["count"] >= 2):
                continue
        if first_run and a["key"].startswith(("active:", "isr:")):
            last[a["key"]] = {"ts": NOW_TS, "count": a.get("count")}
            continue
        last[a["key"]] = {"ts": NOW_TS, "count": a.get("count") or a.get("escalate_count")}
        a["ts"] = NOW_TS
        new_alerts.append(a)
    for k in [k for k, v in last.items() if NOW_TS - v["ts"] > 3 * 86400]:
        del last[k]

    new_alerts.sort(key=lambda a: TIER_RANK[a["tier"]])
    quiet = in_quiet(cfg)
    pushes_left = 4
    day_key = NOW.astimezone(CENTRAL).strftime("%Y-%m-%d")
    if state.get("push_day") != day_key:
        state["push_day"], state["push_count"] = day_key, 0
    for a in new_alerts:
        title = make_title(a["tier"], a["what"])
        body = make_body(a)
        a["title"], a["body"] = title, body
        want = cfg["push"].get(a["tier"], False) and not cfg.get("paused")
        if quiet and not (a["tier"] == "FLASH" and cfg["quiet"].get("flash_breaks", True)):
            want = False
            a["held"] = "quiet hours"
        if a["tier"] != "FLASH" and state["push_count"] >= 25:
            want = False
            a["held"] = "daily cap"
        if want and pushes_left > 0:
            try:
                a["pushed"] = push(a, title, body)
                if a["pushed"] in ("sent", "dry"):
                    pushes_left -= 1
                    state["push_count"] += 1
            except Exception as e:
                a["pushed"] = f"failed: {type(e).__name__}"
            time.sleep(1)
        elif want:
            a["held"] = "too many this sweep"
        a["id"] = hashlib.sha1(f"{a['key']}{NOW_TS}".encode()).hexdigest()[:10]

    if TEST_PUSH:
        t = {"tier": "ROUTINE", "what": "TEST - WATCHTOWER ONLINE", "location": "Riley's command center",
             "assets": f"{len(planes)} military aircraft on the scope", "response": "No action needed. This is a test.",
             "source": "Watchman Radar backend (GitHub Actions)", "threat": "NONE", "ts": NOW_TS,
             "key": "test", "watch": "test"}
        t["title"], t["body"] = make_title("ROUTINE", t["what"]), make_body(t)
        t["priority_override"] = 3
        try:
            t["pushed"] = push(t, t["title"], t["body"])
        except Exception as e:
            t["pushed"] = f"failed: {type(e).__name__}"
        t["id"] = "test" + str(NOW_TS)
        new_alerts.append(t)
        print("TEST PUSH:", t["pushed"])

    keep = ("id", "ts", "tier", "what", "title", "body", "headline", "location", "assets", "response",
            "source", "threat", "region", "lat", "lon", "link", "more", "pushed", "held", "watch", "count")
    log["alerts"] = ([{k: a[k] for k in keep if k in a} for a in new_alerts] + log.get("alerts", []))[:400]
    save_json("alerts.json", log)

    stats = {c: 0 for c in ("tanker", "bomber", "airlift", "tactical", "isr", "c2", "fighter", "other")}
    board = {}
    for p in planes:
        stats[p["cat"]] = stats.get(p["cat"], 0) + 1
        if p["rg"]:
            b = board.setdefault(p["rg"], {"total": 0})
            b["total"] += 1
            b[p["cat"]] = b.get(p["cat"], 0) + 1
    for r in board:
        board[r]["base_tanker"] = state["baseline"].get(f"{r}:tanker") if state.get("baseline") else None
        board[r]["base_airlift"] = state["baseline"].get(f"{r}:airlift") if state.get("baseline") else None
    save_json("live.json", {
        "updated": NOW_TS, "updated_ct": central_time(), "planes": planes, "stats": stats,
        "board": board, "sources": sources, "new_alerts": len(new_alerts), "quiet_now": quiet,
        "first_run": first_run, "regions": {k: REGION_LABEL[k] for k in REGION_LABEL},
        "sweeps": state.get("sweeps", 0) + 1,
    })
    state["initialized"] = True
    state["sweeps"] = state.get("sweeps", 0) + 1
    state["last_sweep"] = NOW_TS
    save_json("state.json", state)
    print(f"sweep ok: {len(planes)} aircraft, {len(items)} headlines, {len(new_alerts)} new alerts, "
          f"settings: {cfg_status}, quiet={quiet}")
    for a in new_alerts:
        print(" ", a.get("title"), "|", a.get("pushed") or a.get("held") or "logged")


if __name__ == "__main__":
    main()
