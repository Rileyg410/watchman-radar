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

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import intel  # noqa: E402  round-two Intel brain
import geo  # noqa: E402  where each plane is + what it has been doing (for "Probably doing")
import cables  # noqa: E402  undersea cable watch: cut/damage news + ships hanging over cables
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
TEST_RECAP = os.environ.get("TEST_RECAP", "").lower() in ("1", "true", "yes")
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
        "skyking": True, "gpsjam": True, "closures": True, "convergence": True,
        "cables": True, "cableships": True,
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
    "recap": {"enabled": True, "time": "21:00"},
    "morning": {"enabled": True, "time": "07:00"},
    "sunday": {"enabled": True, "time": "20:00"},
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
TANKERS = {"K35R", "K35E", "K46", "KC46", "KC10", "DC10", "A39M"}
BOMBERS = {"B52", "B1", "B2", "B21", "TU95", "T95", "TU16", "TU22", "T160", "TU60", "H6"}
AIRLIFT = {"C17", "C5", "C5M", "IL76", "Y20", "A400", "AN12", "AN22", "A124", "KC2"}
TACTICAL_LIFT = {"C130", "C30J", "E390", "C27J", "C295", "CN35"}
ISR = {"R135", "E3TF", "E3CF", "E3", "E8", "E7WW", "E737", "P8", "P3", "EP3", "U2",
       "RQ4", "GLHK", "Q4", "MQ9", "E2", "A50", "IL20", "IL38", "TU14"}
NUKE_C2 = {"E6", "E4", "E4B"}
# Real fighter / attack jet type codes, as the adsb.lol database writes them.
# (Trainers like the T-6, T-38, T-45 and PC-21 used to sit here; they now count as "other".)
# Careful: FA50 in the database is the Dassault Falcon 50 business jet, not a fighter.
FIGHTERS = {"F15", "F15E", "F15X", "F16", "F18", "F18H", "F18S", "E18G", "EA18", "F22", "F35", "F117",
            "F14", "F4", "F5", "F104", "A10", "AV8B", "HAR", "EUFI", "RFAL", "GRIF", "SB39", "JAS39",
            "TOR", "MIR2", "M2000", "MRF1", "KFIR", "TEJS", "JF17", "J10", "J11", "J15", "J16", "J20",
            "SU24", "SU25", "SU27", "SU30", "SU33", "SU34", "SU35", "SU57", "MG21", "MG23", "MG29", "MG31", "AMX"}
TYPE_NAMES = {
    "K35R": "KC-135R", "K35E": "KC-135E", "K46": "KC-46A", "KC46": "KC-46A", "KC10": "KC-10",
    "DC10": "KC-10", "B52": "B-52", "B1": "B-1B", "B2": "B-2", "B21": "B-21", "TU95": "Tu-95",
    "T95": "Tu-95", "T160": "Tu-160", "TU60": "Tu-160", "TU22": "Tu-22M", "H6": "H-6",
    "C17": "C-17", "C5": "C-5", "C5M": "C-5M", "IL76": "Il-76", "Y20": "Y-20", "A400": "A400M",
    "A124": "An-124", "C130": "C-130", "C30J": "C-130J", "R135": "RC-135", "E3TF": "E-3",
    "E3CF": "E-3", "E8": "E-8", "P8": "P-8", "P3": "P-3", "EP3": "EP-3", "U2": "U-2",
    "RQ4": "RQ-4", "GLHK": "RQ-4", "Q4": "RQ-4", "MQ9": "MQ-9", "E6": "E-6B", "E4": "E-4B",
    "E4B": "E-4B", "A50": "A-50", "IL20": "Il-20", "IL38": "Il-38", "E7WW": "E-7", "E737": "E-7",
    "F15": "F-15", "F15E": "F-15E", "F15X": "F-15EX", "F16": "F-16", "F18": "F/A-18", "F18H": "F/A-18 Hornet",
    "F18S": "F/A-18 Super Hornet", "E18G": "EA-18G", "EA18": "EA-18G", "F22": "F-22", "F35": "F-35",
    "A10": "A-10", "AV8B": "AV-8B Harrier", "HAR": "Harrier", "EUFI": "Typhoon", "RFAL": "Rafale",
    "GRIF": "Gripen", "SB39": "Gripen", "JAS39": "Gripen", "TOR": "Tornado", "MIR2": "Mirage 2000",
    "F5": "F-5", "SU27": "Su-27", "SU30": "Su-30", "SU34": "Su-34", "SU35": "Su-35", "MG29": "MiG-29", "MG31": "MiG-31",
}
ISR_CALLSIGNS = ("FORTE", "HOMER", "JAKE", "OLIVE", "COBRA", "SNTRY", "MAGMA", "NCHO")


_CC_RANGES = None


def country_of(hexcode):
    """Any country from the ICAO 24-bit address table (watcher/country_ranges.json). None when unknown."""
    global _CC_RANGES
    if _CC_RANGES is None:
        try:
            with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "country_ranges.json"), encoding="utf-8") as f:
                _CC_RANGES = json.load(f)["ranges"]
        except Exception:
            _CC_RANGES = []
    try:
        s = str(hexcode or "")
        if not s or s.startswith("~"):
            return None
        h = int(s, 16)
    except Exception:
        return None
    for a, b, cc in _CC_RANGES:
        if a <= h <= b:
            return cc
    return None


def tag_countries(alerts, planes):
    """Add a['cc'] = the countries of the planes an alert is about (most planes first)."""
    by = {}
    for p in planes:
        for k in (p.get("cs"), p.get("reg"), p.get("hex")):
            if k:
                by.setdefault(str(k), p)
    for a in alerts:
        if not isinstance(a, dict) or a.get("cc"):
            continue
        counts = {}
        hexes = []
        if a.get("hex"):
            hexes.append(a["hex"])
        main = str(a.get("assets") or "").split(" | ")[0]
        for part in main.split("; "):
            m = re.match(r"^\d+x .+? \((.*)\)$", part.strip())
            if not m:
                continue
            for i in m.group(1).split(", "):
                p = by.get(i.strip())
                if p and p.get("hex"):
                    hexes.append(p["hex"])
        for h in hexes:
            cc = country_of(h)
            if cc:
                counts[cc] = counts.get(cc, 0) + 1
        if counts:
            a["cc"] = sorted(counts, key=lambda c: -counts[c])


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


def classify(t, callsign, emitter=None):
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
    # No type on file, but the transponder says "high performance" (ADS-B emitter category A6:
    # faster than 400 knots and able to pull more than 5 G). That is almost always a fighter.
    if not t and (emitter or "").upper() == "A6":
        return "fighter"
    return "other"


def plane_row(a):
    lat, lon = a.get("lat"), a.get("lon")
    if lat is None:
        lat, lon = a.get("rr_lat"), a.get("rr_lon")
    if lat is None or lon is None:
        return None
    alt = a.get("alt_baro")
    if alt == "ground":
        alt = 0
    cs = (a.get("flight") or "").strip()
    t = (a.get("t") or "").upper()
    emitter = a.get("category") or ""
    cat = classify(t, cs, emitter)
    row = {
        "hex": a.get("hex"), "cs": cs, "t": t, "reg": a.get("r") or "",
        "lat": round(lat, 3), "lon": round(lon, 3),
        "alt": alt if isinstance(alt, (int, float)) else None,
        "gs": round(a["gs"]) if isinstance(a.get("gs"), (int, float)) else None,
        "trk": round(a["track"]) if isinstance(a.get("track"), (int, float)) else None,
        "vr": round(a.get("baro_rate") if isinstance(a.get("baro_rate"), (int, float)) else a["geom_rate"]) if isinstance(a.get("baro_rate"), (int, float)) or isinstance(a.get("geom_rate"), (int, float)) else None,
        "sq": a.get("squawk") or "", "cat": cat, "rg": region_of(lat, lon),
        "nat": nation_of(a.get("hex") or ""),
    }
    if cat == "fighter" and not t:
        row["fg"] = 1  # fighter guessed from the "high performance" flag, type unknown
    return row


# Extra looks around the hottest spots: fighters whose transponder is not in the military
# list (so /v2/mil misses them) but who share a fighter type or the high-performance flag.
FIGHTER_SPOTS = ((32.0, 35.0), (26.5, 53.5))  # Israel & the Eastern Med, Persian Gulf & Hormuz


def pull_aircraft():
    raw = http_get("https://api.adsb.lol/v2/mil", timeout=25)
    d = json.loads(raw)
    out = []
    for a in d.get("ac", []):
        row = plane_row(a)
        if row:
            out.append(row)
    seen = {r["hex"] for r in out}
    for la, lo in FIGHTER_SPOTS:
        try:
            time.sleep(1)
            pd = json.loads(http_get(f"https://api.adsb.lol/v2/point/{la}/{lo}/250", timeout=15))
        except Exception:
            continue
        for a in pd.get("ac", []):
            if a.get("hex") in seen:
                continue
            row = plane_row(a)
            if row and row["cat"] == "fighter":
                out.append(row)
                seen.add(row["hex"])
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
    nwst = state.setdefault("intel", {}).setdefault("nw", {})
    for p in planes:
        e4 = p["t"] in ("E4", "E4B")
        if e4 and w.get("nuclear", True) and isinstance(p.get("alt"), (int, float)) and p["alt"] > 1000:
            # NIGHTWATCH upgrade: always watched (any region), breaks through Quiet Hours, Joel 2:1
            first = nwst.setdefault(p["hex"], {"lat": p["lat"], "lon": p["lon"], "ts": NOW_TS})
            where = f"{REGION_LABEL[p['rg']]} ({p['lat']:.1f}, {p['lon']:.1f})" if p.get("rg") else f"({p['lat']:.1f}, {p['lon']:.1f})"
            hdg = p.get("trk")
            alerts.append(dict(
                tier="IMMEDIATE", key=f"nightwatch:{p['hex']}", cooldown=12 * 3600, watch="nightwatch",
                what="NIGHTWATCH IS AIRBORNE", breaks_quiet=True,
                headline="\U0001F534 The E-4B 'doomsday plane' is in the air.",
                location=where + (f", heading {round(hdg)}\u00B0" if isinstance(hdg, (int, float)) else ""),
                assets=fmt_assets([p]) + alt_txt(p) + f". First seen up at ({first['lat']:.1f}, {first['lon']:.1f})",
                response="The flying Pentagon. Usually training or carrying the Defense Secretary. Watch for other nuclear-force signals.",
                source="adsb.lol live ADS-B (military feed)", threat="HIGH", region=p.get("rg"),
                lat=p["lat"], lon=p["lon"], hex=p["hex"], cs=p.get("cs"), type=p["t"], alt=p.get("alt"),
                gs=p.get("gs"), trk=p.get("trk")))
            continue
        if p["cat"] == "c2" and region_ok(p["rg"]) and not e4:
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
                threat="ELEVATED" if p["sq"] == "7500" else "LOW", region=p["rg"], lat=p["lat"], lon=p["lon"],
                sq=p["sq"], hex=p.get("hex"), cs=p.get("cs") or "", type=p.get("t") or "", reg=p.get("reg") or "",
                alt=p.get("alt"), gs=p.get("gs"), trk=p.get("trk"), vr=p.get("vr"), nat=p.get("nat")))

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
    ]
    try:
        if a.get("cs") or a.get("type"):
            ml = intel.decode_line({"cs": a.get("cs"), "t": a.get("type")})
            if ml:
                lines.insert(-3, f"\U0001F3AF MISSION: {ml}")
        if a.get("watch") not in ("test",):
            ref, txt = intel.verse_for(a)
            lines.append(f"\U0001F4D6 {ref}: {txt}")
    except Exception:
        pass
    lines.append("\u2014 WATCHTOWER")
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


# ----------------------------------------------------------------- alert screen links
# Tapping a phone alert opens the full-screen alert screen on the radar, on that alert.
# The link carries a small copy of the alert, so the screen can show it right away,
# even before this sweep's alerts.json reaches the site.
SCREEN_FIELDS = (("id", "i"), ("ts", "t"), ("tier", "r"), ("what", "w"), ("sq", "q"), ("hex", "h"), ("cs", "c"),
                 ("type", "y"), ("alt", "a"), ("gs", "g"), ("trk", "k"), ("vr", "v"), ("lat", "la"), ("lon", "lo"),
                 ("region", "rg"), ("nat", "n"), ("route", "ro"), ("count", "ct"), ("watch", "wa"))


def screen_url(a, extra=""):
    if not SITE_URL:
        return ""
    import base64
    d = {short: a[k] for k, short in SCREEN_FIELDS if a.get(k) not in (None, "")}
    if a.get("headline"):
        d["hl"] = a["headline"][:150]
    if a.get("assets") and not a.get("sq"):
        d["as"] = a["assets"][:160]
    blob = base64.urlsafe_b64encode(json.dumps(d, ensure_ascii=False, separators=(",", ":")).encode()).decode().rstrip("=")
    return f"{SITE_URL}#alert/{a.get('id', 'x')}/{blob}{extra}"


def track_url(a):
    if not SITE_URL or a.get("lat") is None:
        return ""
    return f"{SITE_URL}#track/{a.get('hex') or 'x'}/{a['lat']}/{a['lon']}"


def push_actions(a):
    acts = []
    if a.get("sq"):
        if track_url(a):
            acts.append({"action": "view", "label": "Track it", "url": track_url(a)})
        acts.append({"action": "view", "label": "Pray", "url": screen_url(a, "/pray")})
    elif a.get("watch") not in ("test",):
        acts.append({"action": "view", "label": "Pray", "url": screen_url(a, "/pray")})
    if not a.get("link") or len(acts) < 2:
        acts.append({"action": "view", "label": "Open Radar", "url": SITE_URL})
    if a.get("link") and len(acts) < 3:
        acts.append({"action": "view", "label": "Read story", "url": a["link"]})
    return acts[:3]


def push(a, title, body):
    if not TOPIC:
        return "no topic"
    payload = {"topic": TOPIC, "title": title, "message": body, "priority": a.get("priority_override") or TIER_PRIO[a["tier"]],
               "tags": [{"FLASH": "rotating_light", "IMMEDIATE": "warning", "ROUTINE": "satellite"}[a["tier"]]]}
    click = screen_url(a) or a.get("link") or SITE_URL
    if click:
        payload["click"] = click
    if SITE_URL:
        payload["actions"] = push_actions(a)
    if DRY_RUN:
        print("DRY PUSH:", json.dumps(payload, ensure_ascii=False)[:600])
        return "dry"
    req = urllib.request.Request(NTFY + "/", data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json", "User-Agent": UA}, method="POST")
    with urllib.request.urlopen(req, timeout=15) as r:
        return "sent" if r.status == 200 else f"http {r.status}"


# ----------------------------------------------------------------- morning + Sunday reports
def report_minutes(cfg, key, default):
    try:
        h, m = map(int, str(cfg.get(key, {}).get("time", default)).split(":"))
        return max(0, min(23 * 60 + 59, h * 60 + m))
    except Exception:
        h, m = map(int, default.split(":"))
        return h * 60 + m


def push_report(r, cfg, tag):
    if cfg.get("paused"):
        return "held: pushes paused"
    if not TOPIC:
        return "no topic"
    payload = {"topic": TOPIC, "title": r["title"], "message": r["body"], "priority": 3, "tags": [tag]}
    if SITE_URL:
        payload["click"] = SITE_URL + "#intel"
        payload["actions"] = [{"action": "view", "label": "Open Intel", "url": SITE_URL + "#intel"},
                              {"action": "view", "label": "Open Radar", "url": SITE_URL}]
    if DRY_RUN:
        print("DRY REPORT:", json.dumps(payload, ensure_ascii=False)[:900])
        return "dry"
    try:
        req = urllib.request.Request(NTFY + "/", data=json.dumps(payload).encode(),
                                     headers={"Content-Type": "application/json", "User-Agent": UA}, method="POST")
        with urllib.request.urlopen(req, timeout=15) as resp:
            return "sent" if resp.status == 200 else f"http {resp.status}"
    except Exception as e:
        return f"failed: {type(e).__name__}"


def run_reports(state, cfg, log, intel_data):
    """7 AM morning report and Sunday 8 PM weekly report (Central). Returns log entries."""
    now_ct = NOW.astimezone(CENTRAL)
    today = now_ct.strftime("%Y-%m-%d")
    mins = now_ct.hour * 60 + now_ct.minute
    st = state.setdefault("intel", {})
    reps = st.setdefault("reports", {})
    out = []
    force = os.environ.get("REPORT_TEST", "")
    jobs = [("morning", "07:00", "sunny", lambda: intel.morning_report(state, log, intel_data or {}, NOW_TS, CENTRAL), True),
            ("sunday", "20:00", "bar_chart", lambda: intel.sunday_report(state, log, NOW_TS, CENTRAL, REGION_LABEL), now_ct.weekday() == 6)]
    for key, dflt, tag, build, day_ok in jobs:
        start = report_minutes(cfg, key, dflt)
        due = cfg.get(key, {}).get("enabled", True) and day_ok and start <= mins < start + 180 and st.get(key + "_sent") != today
        if not (due or force == key):
            continue
        r = build()
        r["pushed"] = push_report(r, cfg, tag)
        if not force:
            st[key + "_sent"] = today
        reps[key] = r
        out.append({"id": key + today.replace("-", "") + ("t" + str(NOW_TS) if force else ""), "ts": NOW_TS,
                    "tier": "ROUTINE", "watch": "report" if key == "morning" else "sunday",
                    "what": ("MORNING REPORT" if key == "morning" else "SUNDAY REPORT") + (" (TEST)" if force else ""),
                    "title": r["title"], "body": r["body"], "location": "All theaters",
                    "pushed": r["pushed"] if r["pushed"] in ("sent", "dry") else None,
                    "held": None if r["pushed"] in ("sent", "dry") else r["pushed"]})
    return out


# ----------------------------------------------------------------- end-of-day recap
# WATCHTOWER keeps a running record of everything notable it sees between recaps
# (one record per watch day, carried across sweeps in state.json). At the recap time
# (default 9:00 PM Central) it ranks the day's finds and pushes one recap to the phone.
RECAP_TOP = 5
TIER_PTS = {"FLASH": 100, "IMMEDIATE": 60, "ROUTINE": 20}
THREAT_PTS = {"SEVERE": 30, "HIGH": 20, "ELEVATED": 10, "LOW": 0, "NONE": 0}
WATCH_PTS = {"nuclear": 15, "missiles": 12, "foreign_mil": 10, "bombers": 8, "warships": 8, "hormuz": 5}
REGION_PTS = {"easternmed": 6, "gulf": 3}
HV_TYPES = {"R135", "U2", "RQ4", "GLHK", "Q4", "E3TF", "E3CF", "E8", "E7WW", "E737", "E6", "E4", "E4B",
            "A50", "IL20", "IL38"}
MEDALS = ["\U0001F947", "\U0001F948", "\U0001F949", "4\uFE0F\u20E3", "5\uFE0F\u20E3"]
FIND_KEEP = ("tier", "what", "headline", "location", "assets", "threat", "region", "lat", "lon", "link", "watch",
             "cables")


def recap_minutes(cfg):
    try:
        h, m = map(int, str(cfg.get("recap", {}).get("time", "21:00")).split(":"))
        return max(0, min(23 * 60 + 59, h * 60 + m))
    except Exception:
        return 21 * 60


def recap_clock(cfg):
    mins = recap_minutes(cfg)
    return datetime(2000, 1, 1, mins // 60, mins % 60).strftime("%-I:%M %p") + " CT"


def new_day(date_str, start_ts):
    return {"date": date_str, "start": start_ts, "sweeps": 0, "peak_total": 0, "peak_cats": {},
            "tiers": {"FLASH": 0, "IMMEDIATE": 0, "ROUTINE": 0}, "finds": {}, "airframes": {}}


def find_score(f):
    s = TIER_PTS.get(f["tier"], 0) + THREAT_PTS.get(f.get("threat"), 0)
    s += WATCH_PTS.get(f.get("watch"), 0) + REGION_PTS.get(f.get("region"), 0)
    s += min(f.get("peak") or 0, 12) * 2          # more aircraft / more reports = bigger
    s += min(f.get("sweeps", 1), 18)              # stayed on the scope longer = bigger
    if f.get("pushed"):
        s += 3
    return s


def record_find(day, a, pushed=False, ts=None):
    if a.get("watch") in ("test", "recap") or not a.get("key") and not a.get("what"):
        return
    key = a.get("key") or ("log:" + a["what"])
    ts = ts or NOW_TS
    n = a.get("count") or a.get("escalate_count") or len(a.get("more") or []) or 1
    f = day["finds"].get(key)
    if f is None:
        f = {k: a[k] for k in FIND_KEEP if a.get(k) is not None}
        f.update(first=ts, last=ts, sweeps=1, peak=n, pushed=bool(pushed))
        day["finds"][key] = f
        return
    f["sweeps"] = f.get("sweeps", 1) + (1 if ts != f.get("last") else 0)
    f["last"] = max(f.get("last", ts), ts)
    f["pushed"] = f.get("pushed") or bool(pushed)
    upgrade = TIER_RANK.get(a["tier"], 9) < TIER_RANK.get(f["tier"], 9)
    if upgrade or n > (f.get("peak") or 0):
        for k in FIND_KEEP:
            if a.get(k) is not None:
                f[k] = a[k]
        if upgrade:
            f["tier"] = a["tier"]
        f["peak"] = max(n, f.get("peak") or 0)


def record_sweep(day, planes, candidates, new_alerts):
    day["sweeps"] += 1
    if planes:
        day["peak_total"] = max(day.get("peak_total", 0), len(planes))
        cats = {}
        for p in planes:
            cats[p["cat"]] = cats.get(p["cat"], 0) + 1
            notable = p["cat"] in ("bomber", "c2") or p["t"] in HV_TYPES or (p["nat"] in NATION_NAME and not at_home(p))
            if notable and p.get("hex"):
                af = day["airframes"].get(p["hex"])
                if af is None and len(day["airframes"]) < 250:
                    day["airframes"][p["hex"]] = {"t": p["t"], "cat": p["cat"], "nat": p["nat"], "cs": p["cs"],
                                                  "rg": p["rg"], "first": NOW_TS, "last": NOW_TS}
                elif af is not None:
                    af["last"] = NOW_TS
        pc = day.setdefault("peak_cats", {})
        for c, n in cats.items():
            pc[c] = max(pc.get(c, 0), n)
    sent = {a["key"] for a in new_alerts if a.get("pushed") == "sent" and a.get("key")}
    for a in new_alerts:
        if a.get("watch") not in ("test", "recap") and a.get("tier") in day["tiers"]:
            day["tiers"][a["tier"]] += 1
    for a in candidates:
        record_find(day, a, pushed=a.get("key") in sent)


def ranked_finds(day):
    fs = list(day.get("finds", {}).values())
    for f in fs:
        f["score"] = find_score(f)
    fs.sort(key=lambda f: (-f["score"], -f.get("last", 0)))
    return fs


def airframe_line(day):
    by = {}
    for af in day.get("airframes", {}).values():
        name = TYPE_NAMES.get(af["t"], af["t"] or "unknown")
        if af.get("nat") in NATION_NAME:
            name = NATION_NAME[af["nat"]] + " " + name
        by[name] = by.get(name, 0) + 1
    order = sorted(by.items(), key=lambda x: (-("RUSSIAN" in x[0] or "CHINESE" in x[0] or "IRANIAN" in x[0]), -x[1], x[0]))
    return ", ".join(f"{n}x {nm}" for nm, n in order[:8]) + (f" +{len(order) - 8} more types" if len(order) > 8 else "")


def recap_summary(day, cfg):
    fs = ranked_finds(day)
    big = [f for f in fs if f["tier"] in ("FLASH", "IMMEDIATE")]
    top = fs[:RECAP_TOP if big else 3]  # ranked: FLASH/IMMEDIATE naturally rise to the top
    pc = day.get("peak_cats", {})
    return {
        "date": day["date"], "start": day.get("start"), "end": NOW_TS, "sweeps": day.get("sweeps", 0),
        "peak_total": day.get("peak_total", 0), "peak_tankers": pc.get("tanker", 0), "peak_bombers": pc.get("bomber", 0),
        "tiers": day.get("tiers", {}), "quiet": not big, "airframes": airframe_line(day),
        "recap_at": recap_clock(cfg), "total_finds": len(fs),
        "top": [{k: f[k] for k in ("tier", "what", "headline", "location", "assets", "threat", "region", "lat",
                                     "lon", "link", "first", "last", "sweeps", "peak", "pushed", "score", "watch")
                 if f.get(k) is not None} for f in top],
        "cables": cable_summary(fs),
    }


def cable_summary(fs):
    """Today's undersea cable news and ships for the 9 PM recap and Top Finds."""
    cf = [f for f in fs if f.get("watch") in ("cables", "cableships")]
    return [{k: f[k] for k in ("tier", "what", "headline", "location", "assets", "link", "first", "last", "pushed",
                                "watch", "cables", "lat", "lon") if f.get(k) is not None} for f in cf[:4]]


def short_time(ts):
    return datetime.fromtimestamp(ts, timezone.utc).astimezone(CENTRAL).strftime("%-I:%M %p")


def day_time(ts):
    return datetime.fromtimestamp(ts, timezone.utc).astimezone(CENTRAL).strftime("%a %-I:%M %p")


def make_recap(s, late=False, test=False):
    d = datetime.strptime(s["date"], "%Y-%m-%d").strftime("%a %b %-d").upper()
    lead = "\U0001F9EA TEST " if test else ""
    title = f"{lead}\U0001F3C6 TOP FINDS // {d}" if not s["quiet"] else f"{lead}\U0001F7E9 QUIET DAY // {d}"
    t = s["tiers"]
    lines = ["WATCHTOWER END-OF-DAY RECAP" + (" (late)" if late else "") + (" (TEST)" if test else ""),
             f"\U0001F5D3\uFE0F WATCH: {day_time(s['start'])} \u2192 {day_time(s['end'])} CT",
             f"\U0001F4E1 {s['sweeps']} sweep{'' if s['sweeps'] == 1 else 's'} \u00B7 peak {s['peak_total']} mil aircraft \u00B7 {s['peak_tankers']} tankers up at once",
             f"{TIER_ICON['FLASH']} {t.get('FLASH', 0)} FLASH \u00B7 {TIER_ICON['IMMEDIATE']} {t.get('IMMEDIATE', 0)} IMMEDIATE \u00B7 {TIER_ICON['ROUTINE']} {t.get('ROUTINE', 0)} ROUTINE",
             ""]
    if s["quiet"]:
        lines.append("No FLASH or IMMEDIATE finds today. The skies stayed within normal.")
        lines.append("Most notable on the log:" if s["top"] else "Nothing worth logging. All quiet on the watch.")
    else:
        lines.append("MOST NOTABLE FIRST:")
    for i, f in enumerate(s["top"]):
        lines.append(f"{MEDALS[i]} {TIER_ICON[f['tier']]} {f['what'].upper()}")
        if f.get("headline"):
            hl = f["headline"]
            lines.append("   \U0001F4F0 " + (hl if len(hl) <= 110 else hl[:107].rstrip() + "\u2026"))
        when = short_time(f["first"]) + (f"\u2013{short_time(f['last'])}" if f.get("last", 0) - f["first"] >= 1200 else "")
        lines.append(f"   \U0001F4CD {f.get('location', 'Unknown')} \u00B7 \U0001F550 {when} CT")
        if f.get("assets") and f["assets"] != "See report":
            a = f["assets"]
            lines.append("   \U0001F6E9\uFE0F " + (a if len(a) <= 110 else a[:107].rstrip() + "\u2026"))
        extra = [f"\u26A0\uFE0F {f.get('threat', 'LOW')}"]
        if f.get("sweeps", 1) > 1:
            extra.append(f"on scope {f['sweeps']} sweeps")
        extra.append("\u25B2 pushed" if f.get("pushed") else "logged")
        lines.append("   " + " \u00B7 ".join(extra))
    cab = s.get("cables") or []
    if cab:
        lines += ["", "\U0001F30A UNDERSEA CABLES TODAY:"]
        for f in cab[:3]:
            hl = f.get("headline") or ""
            lines.append(f"\u2022 {TIER_ICON[f['tier']]} {f['what'].upper()}")
            if hl:
                lines.append("   \U0001F4F0 " + (hl if len(hl) <= 110 else hl[:107].rstrip() + "\u2026"))
    else:
        lines += ["", "\U0001F30A UNDERSEA CABLES: no cable cuts, damage or ships hanging over cables today."]
    if s["airframes"]:
        lines += ["", "\u2708\uFE0F NOTABLE AIRFRAMES: " + s["airframes"]]
    lines.append("\u2014 WATCHTOWER")
    return title, "\n".join(lines)


def push_recap(s, cfg, late=False, test=False):
    title, body = make_recap(s, late, test)
    s["title"], s["body"] = title, body
    if cfg.get("paused") and not test:
        s["pushed"] = "held: pushes paused"
        return s
    if not TOPIC:
        s["pushed"] = "no topic"
        return s
    payload = {"topic": TOPIC, "title": title, "message": body,
               "priority": 2 if in_quiet(cfg) else 3,
               "tags": ["trophy"] if not s["quiet"] else ["green_circle"]}
    if SITE_URL:
        payload["click"] = SITE_URL
        payload["actions"] = [{"action": "view", "label": "Open Radar", "url": SITE_URL}]
    if DRY_RUN:
        print("DRY RECAP:", json.dumps(payload, ensure_ascii=False))
        s["pushed"] = "dry"
        return s
    try:
        req = urllib.request.Request(NTFY + "/", data=json.dumps(payload).encode(),
                                     headers={"Content-Type": "application/json", "User-Agent": UA}, method="POST")
        with urllib.request.urlopen(req, timeout=15) as r:
            s["pushed"] = "sent" if r.status == 200 else f"http {r.status}"
    except Exception as e:
        s["pushed"] = f"failed: {type(e).__name__}"
    return s


def recap_log_entry(s):
    return {"id": "recap" + s["date"].replace("-", "") + ("t" + str(NOW_TS) if s.get("test") else ""),
            "ts": NOW_TS, "tier": "ROUTINE", "watch": "recap",
            "what": "END-OF-DAY RECAP" + (" (TEST)" if s.get("test") else ""), "title": s["title"], "body": s["body"],
            "location": "All theaters", "pushed": s.get("pushed") if s.get("pushed") in ("sent", "dry") else None,
            "held": None if s.get("pushed") in ("sent", "dry") else s.get("pushed")}


def run_recap(state, cfg, planes, candidates, new_alerts, log):
    """Track the watch day, and send the end-of-day recap when it is due. Returns log entries."""
    now_ct = NOW.astimezone(CENTRAL)
    today = now_ct.strftime("%Y-%m-%d")
    mins_now = now_ct.hour * 60 + now_ct.minute
    enabled = cfg.get("recap", {}).get("enabled", True)
    entries = []
    day = state.get("day")
    if not isinstance(day, dict) or "date" not in day:
        midnight = int(now_ct.replace(hour=0, minute=0, second=0, microsecond=0).timestamp())
        # if today's recap time has already passed, this record belongs to tomorrow
        if mins_now >= recap_minutes(cfg):
            day = new_day((now_ct + timedelta(days=1)).strftime("%Y-%m-%d"), NOW_TS)
        else:
            day = new_day(today, midnight)
            for a in log.get("alerts", []):  # backfill what was already logged today
                if a.get("ts", 0) >= midnight and a.get("watch") not in ("test", "recap") and a.get("tier") in TIER_PTS:
                    record_find(day, dict(a, key="log:" + a.get("what", "")), pushed=a.get("pushed") == "sent", ts=a["ts"])
                    day["tiers"][a["tier"]] += 1

    record_sweep(day, planes, candidates, new_alerts)

    due = today > day["date"] or (today == day["date"] and mins_now >= recap_minutes(cfg))
    if due:
        late = today > day["date"] or mins_now - recap_minutes(cfg) > 90
        s = recap_summary(day, cfg)
        if enabled and state.get("recap_sent") != day["date"]:
            push_recap(s, cfg, late=late)
            entries.append(recap_log_entry(s))
            print("RECAP:", s["title"], "|", s.get("pushed"))
        else:
            s["pushed"] = "recap off" if not enabled else "already sent"
        state["recap_sent"] = day["date"]
        state["last_recap"] = s
        nxt = (now_ct + timedelta(days=1)).strftime("%Y-%m-%d") if today == day["date"] else today
        if today > day["date"] and mins_now >= recap_minutes(cfg):
            nxt = (now_ct + timedelta(days=1)).strftime("%Y-%m-%d")
        day = new_day(nxt, NOW_TS)
    state["day"] = day

    if TEST_RECAP:
        # what the recap would say right now (or the one just sent, if the day only just rolled over)
        s = dict(state["last_recap"]) if (not day["sweeps"] and state.get("last_recap")) else recap_summary(day, cfg)
        s["end"] = NOW_TS
        s["test"] = True
        push_recap(s, cfg, test=True)
        entries.append(recap_log_entry(s))
        print("TEST RECAP:", s.get("pushed"))
        print(s["body"])

    cur = recap_summary(day, cfg)
    save_json("recap.json", {"updated": NOW_TS, "enabled": enabled, "recap_at": recap_clock(cfg),
                             "today": cur, "last": state.get("last_recap")})
    return entries


# ----------------------------------------------------------------- squawk log
# squawks.json: every emergency code (7700 / 7600 / 7500) WATCHTOWER has caught, newest first.
# Feeds the EMERGENCY SQUAWKS screen on the radar.
SQUAWK_KEEP = ("id", "ts", "tier", "sq", "what", "hex", "cs", "type", "reg", "alt", "gs", "trk", "vr", "lat", "lon",
               "region", "location", "nat", "route", "pushed", "held")
SQUAWK_DAYS = 60


def lookup_route(a):
    """Where the flight is going, if adsb.lol knows (usually only airline flights). Never fails loudly."""
    if DRY_RUN or not a.get("cs") or a.get("lat") is None:
        return None
    try:
        body = json.dumps({"planes": [{"callsign": a["cs"], "lat": a["lat"], "lng": a["lon"]}]}).encode()
        req = urllib.request.Request("https://api.adsb.lol/api/0/routeset", data=body, method="POST",
                                     headers={"Content-Type": "application/json", "User-Agent": UA})
        with urllib.request.urlopen(req, timeout=8) as r:
            res = json.loads(r.read())
        for x in res if isinstance(res, list) else []:
            iata = str(x.get("_airport_codes_iata") or "")
            if x.get("plausible") and iata and "unknown" not in iata.lower() and "-" in iata:
                return iata.replace("-", "\u2192")
    except Exception as e:
        print("route lookup skipped:", type(e).__name__)
    return None


def save_squawks(new_alerts):
    log = load_json("squawks.json", {"squawks": []})
    fresh = []
    for a in new_alerts:
        if not a.get("sq"):
            continue
        if "route" not in a:
            a["route"] = lookup_route(a)
        fresh.append({k: a[k] for k in SQUAWK_KEEP if a.get(k) is not None})
    cutoff = NOW_TS - SQUAWK_DAYS * 86400
    old = [s for s in log.get("squawks", []) if s.get("ts", 0) >= cutoff]
    save_json("squawks.json", {"updated": NOW_TS, "days": SQUAWK_DAYS, "squawks": (fresh + old)[:150]})
    for s in fresh:
        print("SQUAWK:", s.get("sq"), s.get("cs") or s.get("hex"), s.get("route") or "")


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
    cablewatch = None
    try:  # undersea cables: news + Baltic live ships; must never break the regular alerts
        t0 = time.time()
        extra, cablewatch = cables.run(items, cfg, state, first_run, trusted, parse_feed, NOW, NOW_TS)
        candidates += extra
        sources["cables"] = {"ok": bool(cablewatch.get("news_ok") or cablewatch["ais"].get("ok")),
                             "note": f"{len(extra)} cable items, ships checked {cablewatch['ais'].get('checked', 0)}"}
        print(f"cable watch: {len(extra)} candidates in {time.time() - t0:.1f}s, ais={cablewatch['ais'].get('ok')}")
    except Exception as e:
        print("cable watch error:", type(e).__name__, e)
    intel_data = None
    try:  # round two Intel brain: must never break the regular alerts
        extra, intel_data = intel.run(state, cfg, planes, candidates, NOW_TS, CENTRAL, sources)
        if first_run:
            extra = [x for x in extra if not x["key"].startswith(("convergence:", "dejavu:"))]
        candidates += extra
    except Exception as e:
        print("intel error:", type(e).__name__, e)

    try:  # which countries' planes each alert is about (shown on the alert cards); never breaks alerts
        tag_countries(candidates, planes or [])
    except Exception as e:
        print("country tag error:", type(e).__name__, e)

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
        a["id"] = hashlib.sha1(f"{a['key']}{NOW_TS}".encode()).hexdigest()[:10]
        if a.get("sq") and "route" not in a:
            a["route"] = lookup_route(a)
        want = cfg["push"].get(a["tier"], False) and not cfg.get("paused")
        if quiet and not ((a["tier"] == "FLASH" and cfg["quiet"].get("flash_breaks", True)) or a.get("breaks_quiet")):
            want = False
            a["held"] = "quiet hours"
        if a["tier"] != "FLASH" and not a.get("breaks_quiet") and state["push_count"] >= 25:
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

    if TEST_PUSH:
        t = {"tier": "ROUTINE", "what": "TEST - WATCHTOWER ONLINE", "location": "Riley's command center",
             "assets": f"{len(planes)} military aircraft on the scope",
             "response": "Tap this alert to open your alert screen. No action needed, this is only a test.",
             "source": "Watchman Radar backend (GitHub Actions)", "threat": "NONE", "ts": NOW_TS,
             "key": "test", "watch": "test", "id": "test" + str(NOW_TS)}
        t["title"], t["body"] = make_title("ROUTINE", t["what"]), make_body(t)
        t["priority_override"] = 3
        try:
            t["pushed"] = push(t, t["title"], t["body"])
        except Exception as e:
            t["pushed"] = f"failed: {type(e).__name__}"
        new_alerts.append(t)
        print("TEST PUSH:", t["pushed"])

    keep = ("id", "ts", "tier", "what", "title", "body", "headline", "location", "assets", "response",
            "source", "threat", "region", "lat", "lon", "link", "more", "pushed", "held", "watch", "count",
            "sq", "hex", "cs", "type", "reg", "alt", "gs", "trk", "vr", "nat", "route", "cc", "cables", "mmsi")
    try:
        recap_entries = run_recap(state, cfg, planes, candidates, new_alerts, log)
    except Exception as e:  # the recap must never break the regular alerts
        print("recap error:", type(e).__name__, e)
        recap_entries = []
    try:
        intel.count_alerts(state, new_alerts, NOW_TS, CENTRAL)
    except Exception as e:
        print("tally error:", type(e).__name__, e)
    try:
        recap_entries += run_reports(state, cfg, log, intel_data)
    except Exception as e:  # the reports must never break the regular alerts
        print("report error:", type(e).__name__, e)
    if intel_data is not None:
        try:
            intel_data["reports"] = state.get("intel", {}).get("reports", {})
            save_json("intel.json", intel_data)
        except Exception as e:
            print("intel save error:", type(e).__name__, e)
    log["alerts"] = ([{k: a[k] for k in keep if a.get(k) is not None} for a in recap_entries] +
                     [{k: a[k] for k in keep if k in a} for a in new_alerts] + log.get("alerts", []))[:400]
    save_json("alerts.json", log)
    if cablewatch:
        try:
            save_json("cablewatch.json", cablewatch)
        except Exception as e:
            print("cablewatch save error:", type(e).__name__, e)
    try:
        save_squawks(new_alerts)
    except Exception as e:  # the squawk log must never break the regular alerts
        print("squawk log error:", type(e).__name__, e)

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
    try:
        t0 = time.time()
        geo.enrich(planes, state, int(NOW_TS))
        print(f"behavior notes: {len(planes)} planes in {time.time() - t0:.1f}s")
    except Exception as e:  # the 'Probably doing' notes must never break a sweep
        print("behavior notes error:", type(e).__name__, e)
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
