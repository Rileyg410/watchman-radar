"""WATCHTOWER round two: the Intel brain.

Everything here runs once per sweep, after the aircraft and news checks, and never breaks them:
- Skyking listening post: the public HFGCS log at eam.watch (EAMs + Skyking), burst alarm
- GPS jamming map: how many airliners report poor GPS quality (adsb.lol NIC / NACp)
- Sky closures: new FAA security flight restrictions (TFRs) with their shapes
- Tanker bridge detector (signals.tanker_bridge)
- Nightwatch tracker: where the E-4B took off, where it is now
- Convergence alarm: several different signals stacking inside six hours
- Deja vu engine: the last 24 hours compared with real past days (reference_days.json)
- Morning report (7 AM) and Sunday report (8 PM)
- A scripture for every alert
It writes intel.json for the INTEL screen and the map layers.
"""
import json, math, os, re, time, urllib.request
from datetime import datetime, timedelta, timezone

try:
    import signals
except ImportError:  # run from the repo root
    from watcher import signals

HERE = os.path.dirname(os.path.abspath(__file__))
HOME = (35.6145, -88.8139)  # Jackson, TN
UA = "WatchmanRadar/2.0 (+github pages; personal use)"
EAM_API = "https://eam.watch/api/messages?paginate=50&page=1"
SKY_API = "https://eam.watch/api/skykings"
TFR_LIST = "https://tfr.faa.gov/tfrapi/getTfrList"
TFR_GEO = ("https://tfr.faa.gov/geoserver/TFR/ows?service=WFS&version=1.1.0&request=GetFeature"
           "&typeName=TFR:V_TFR_LOC&maxFeatures=400&outputFormat=application/json&srsname=EPSG:4326")
POINT_API = "https://api.adsb.lol/v2/point/{lat}/{lon}/{r}"
LISTEN_URL = "http://websdr.ewi.utwente.nl:8901/?tune=8992usb"

# GPS watch zones: center + radius (nautical miles, the API allows up to 250)
GPS_ZONES = [
    ("israel", "Israel, Lebanon & Syria", 32.8, 35.6, 250),
    ("cyprus", "Cyprus & the Eastern Med", 34.6, 31.2, 250),
    ("gulf", "Persian Gulf & Hormuz", 26.4, 53.0, 250),
    ("blacksea", "Black Sea & Turkey", 42.5, 32.5, 250),
    ("baltic", "Baltic & Kaliningrad", 55.5, 20.5, 250),
]

# ---------------------------------------------------------------- scripture on every alert
VERSES = {
    "watch": ("Isaiah 21:6", "Go, set a watchman, let him declare what he seeth."),
    "trumpet": ("Ezekiel 33:3", "If when he seeth the sword come upon the land, he blow the trumpet, and warn the people."),
    "tower": ("Habakkuk 2:1", "I will stand upon my watch, and set me upon the tower."),
    "walls": ("Isaiah 62:6", "I have set watchmen upon thy walls, O Jerusalem, which shall never hold their peace day nor night."),
    "joel": ("Joel 2:1", "Blow ye the trumpet in Zion, and sound an alarm in my holy mountain."),
    "keeper": ("Psalm 121:4", "Behold, he that keepeth Israel shall neither slumber nor sleep."),
    "all": ("Mark 13:37", "And what I say unto you I say unto all, Watch."),
    "pray": ("Luke 21:36", "Watch ye therefore, and pray always."),
    "wars": ("Matthew 24:6", "And ye shall hear of wars and rumours of wars: see that ye be not troubled."),
    "angels": ("Psalm 91:11", "For he shall give his angels charge over thee, to keep thee in all thy ways."),
    "peace": ("Psalm 122:6", "Pray for the peace of Jerusalem: they shall prosper that love thee."),
    "gog": ("Ezekiel 38:9", "Thou shalt ascend and come like a storm, thou shalt be like a cloud to cover the land."),
    "darkness": ("Luke 21:26", "Men's hearts failing them for fear, and for looking after those things which are coming on the earth."),
    "heavens": ("Luke 21:25", "And there shall be signs in the sun, and in the moon, and in the stars."),
}
WATCH_VERSE = {
    "tankers": "trumpet", "airlift": "trumpet", "bombers": "wars", "nuclear": "joel", "isr": "tower",
    "foreign_mil": "walls", "subs": "tower", "russia": "gog", "hormuz": "wars", "missiles": "wars",
    "warships": "walls", "buildups": "gog", "ukraine": "wars", "breaking": "all", "squawk": "angels",
    "skyking": "joel", "gpsjam": "darkness", "closures": "walls", "convergence": "trumpet",
    "dejavu": "tower", "nightwatch": "joel", "bridge": "trumpet", "report": "keeper", "sunday": "all",
}


def verse_for(a):
    key = WATCH_VERSE.get(a.get("watch"), "watch")
    if a.get("region") == "easternmed" and key not in ("joel",):
        key = "peace"
    ref, txt = VERSES[key]
    return ref, txt


# ---------------------------------------------------------------- mission decoder
_MISSIONS = None


def missions():
    global _MISSIONS
    if _MISSIONS is None:
        try:
            with open(os.path.join(HERE, "..", "missions.json")) as f:
                _MISSIONS = json.load(f)
        except Exception:
            _MISSIONS = {"callsigns": [], "types": {}, "cats": {}}
    return _MISSIONS


def decode(cs, t, cat=None):
    """Best-guess mission for a callsign + aircraft type: {m, u, d, by}."""
    M = missions()
    cs = (cs or "").upper().replace(" ", "")
    t = (t or "").upper()
    word = re.match(r"[A-Z]+", cs)
    word = word.group(0) if word else ""
    best = None
    for row in M.get("callsigns", []):
        pre, m, u, d = row[:4]
        if word == pre or (len(pre) >= 3 and word.startswith(pre) and len(word) <= len(pre) + 1):
            if not best or len(pre) > len(best[0]):
                best = (pre, m, u, d)
    tinfo = M.get("types", {}).get(t)
    if best:
        out = {"m": best[1], "u": best[2], "d": best[3], "by": "callsign " + best[0]}
        if tinfo:
            out["t"] = tinfo[0]
        return out
    if tinfo:
        return {"m": tinfo[0], "u": tinfo[1], "d": tinfo[2], "by": "aircraft type " + t}
    c = M.get("cats", {}).get(cat or "")
    if c:
        return {"m": c[0], "u": c[1], "d": c[2], "by": "category"}
    return None


def decode_line(p):
    d = decode(p.get("cs"), p.get("t"), p.get("cat"))
    if not d:
        return ""
    return f"{d['m']}" + (f" · {d['u']}" if d.get("u") else "")


# ---------------------------------------------------------------- helpers
def get_json(url, timeout=20, headers=None):
    h = {"User-Agent": UA, "Accept": "application/json"}
    h.update(headers or {})
    with urllib.request.urlopen(urllib.request.Request(url, headers=h), timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8", "replace"))


def miles(a_lat, a_lon, b_lat, b_lon):
    p1, p2 = math.radians(a_lat), math.radians(b_lat)
    dp, dl = p2 - p1, math.radians(b_lon - a_lon)
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * 3958.8 * math.asin(min(1, math.sqrt(h)))


def parse_utc(s):
    try:
        return int(datetime.strptime(s[:19], "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc).timestamp())
    except Exception:
        return None


# ---------------------------------------------------------------- Skyking listening post
def is_sky(m):
    return "SKYKING" in (m.get("type") or "").upper()


def is_eam(m):
    return (m.get("type") or "").upper() in ("ALLSTATIONS", "EAM")


TYPE_LABEL = {"ALLSTATIONS": "EAM", "EAM": "EAM", "RADIOCHECK": "RADIO CHECK", "OTHER": "OTHER",
              "DISREGARDED": "DISREGARD", "SKYKING": "SKYKING"}


def eam_breakdown(msg, batch):
    """Plain facts about one message: what kind, length, header, how it matches its batch."""
    text = (msg.get("message") or "").strip().upper()
    out = []
    if is_sky(msg):
        m = re.search(r"([A-Z]+)\s+TIME\s+(\d{1,2})\s+(?:AUTH|AUTHENTICATION)\s+([A-Z]{2})", text)
        if m:
            out.append(["Codeword", m.group(1), "The order's codeword. Its meaning stays secret."])
            out.append(["Time", m.group(2), f"Minutes after the hour it takes effect (:{int(m.group(2)):02d})."])
            out.append(["Authentication", m.group(3), "Two letters crews check against their codes to know it's real."])
        else:
            out.append(["Message", text or "—", "Skyking: a short order to bombers and missile crews, sent 'do not answer'."])
        return out
    if not is_eam(msg):
        out.append(["Message", text or "\u2014", "A radio check, test count or other traffic, not a coded order."])
        if msg.get("sender"):
            out.append(["Sent by", msg["sender"], "The station callsign heard on the air."])
        return out
    batch = [b for b in batch if is_eam(b)]
    clean = re.sub(r"[^A-Z0-9]", "", text)
    n = len(clean)
    out.append(["Length", f"{n} characters", "Most EAMs this year are 30 characters." if n == 30 else
                ("Shorter than the usual 30." if n < 30 else "Longer than the usual 30. Long ones are rarer.")])
    if clean:
        hdr = clean[:2]
        same = sum(1 for b in batch if re.sub(r"[^A-Z0-9]", "", (b.get("message") or "").upper())[:2] == hdr)
        out.append(["Header", hdr, f"The opening characters work like a header. {same} of the last {len(batch)} messages open with {hdr}."])
        out.append(["Body", clean[2:] if n > 2 else "—", "The rest is encrypted. Nobody outside the chain of command can read it."])
    if msg.get("sender"):
        out.append(["Sent by", msg["sender"], "The station callsign heard reading it."])
    if msg.get("repeats"):
        out.append(["Repeats", str(msg["repeats"]), "How many times it was read on the air."])
    return out


def pull_eam(st, sources):
    """Refresh the HFGCS log at most every 20 minutes. Returns the stored log (newest first)."""
    log = st.setdefault("eam_log", [])
    if time.time() - st.get("eam_pull", 0) < 20 * 60 and log:
        sources["eam"] = {"ok": True, "note": f"cached, {len(log)} messages"}
        return log, []
    new = []
    try:
        d = get_json(EAM_API, headers={"X-Requested-With": "XMLHttpRequest"})
        rows = d.get("data") or []
        known = {m["id"] for m in log}
        first = not log
        for x in rows:
            ts = parse_utc(x.get("time") or "")
            if not ts or x.get("id") in known:
                continue
            rec = {"id": x.get("id"), "ts": ts, "type": x.get("type"), "sender": x.get("sender") or "",
                   "message": x.get("message") or "", "repeats": x.get("repeats") or 0,
                   "label": TYPE_LABEL.get((x.get("type") or "").upper(), (x.get("type") or "").upper()),
                   "rec": [r.get("link") or r.get("url") for r in (x.get("recordings") or []) if isinstance(r, dict)][:1]}
            log.append(rec)
            if not first:
                new.append(rec)
        log.sort(key=lambda m: m["ts"], reverse=True)
        del log[200:]
        st["eam_pull"] = int(time.time())
        sources["eam"] = {"ok": True, "note": f"{len(rows)} messages read, {len(new)} new"}
    except Exception as e:
        sources["eam"] = {"ok": False, "note": f"{type(e).__name__}: {str(e)[:60]}"}
    if time.time() - st.get("sky_pull", 0) > 6 * 3600:
        try:
            sk = get_json(SKY_API, headers={"X-Requested-With": "XMLHttpRequest"})
            rows = sk.get("data") if isinstance(sk, dict) else sk
            if rows:
                r0 = rows[0]
                st["last_skyking"] = {"ts": parse_utc(r0.get("time") or ""), "message": r0.get("message") or ""}
            st["sky_pull"] = int(time.time())
        except Exception:
            pass
    return log, new


def eam_status(log, now):
    day = [m for m in log if now - m["ts"] < 86400]
    eams = [m for m in day if is_eam(m)]
    sks = [m for m in day if is_sky(m)]
    # "normal" = average per day over the last 30 days of the log (excluding the last 24h)
    month = [m for m in log if 86400 <= now - m["ts"] < 31 * 86400 and is_eam(m)]
    normal = round(len(month) / 30.0, 1)
    three = [m for m in eams if now - m["ts"] < 3 * 3600]
    return {"eam24": len(eams), "sk24": len(sks), "normal": normal, "eam3h": len(three)}


# ---------------------------------------------------------------- GPS jamming map
def gps_bad(a):
    """True when an aircraft says its own GPS position is poor."""
    if a.get("type") in ("mlat", "tisb_icao", "tisb_other", "tisb_trackfile", "adsr_icao", "mode_s"):
        return None
    if a.get("version") in (0, None) or a.get("lat") is None:
        return None
    if (a.get("seen_pos") or 0) > 60:
        return None
    nic, nacp = a.get("nic"), a.get("nac_p")
    if nic is None and nacp is None:
        return None
    return (nic is not None and nic < 7) or (nacp is not None and nacp < 8)


def pull_gps(st, sources):
    """Every 20 minutes: count good/bad GPS per zone and per 1-degree square."""
    cache = st.get("gps_cache")
    if cache and time.time() - cache.get("ts", 0) < 20 * 60:
        return cache, False
    zones, cells, ok = [], {}, 0
    for key, label, lat, lon, r in GPS_ZONES:
        try:
            d = get_json(POINT_API.format(lat=lat, lon=lon, r=r), timeout=20)
            ok += 1
        except Exception:
            zones.append({"k": key, "label": label, "ok": False})
            continue
        tot = bad = 0
        for a in d.get("ac") or []:
            b = gps_bad(a)
            if b is None:
                continue
            tot += 1
            bad += 1 if b else 0
            ck = (math.floor(a["lat"]), math.floor(a["lon"]))
            c = cells.setdefault(ck, [0, 0])
            c[0] += 1 if b else 0
            c[1] += 1
        zones.append({"k": key, "label": label, "ok": True, "total": tot, "bad": bad,
                      "pct": round(100 * bad / tot) if tot else 0, "lat": lat, "lon": lon})
        time.sleep(0.4)
    cache = {"ts": int(time.time()), "zones": zones,
             "cells": [[k[0], k[1], v[0], v[1]] for k, v in cells.items()]}
    sources["gps"] = {"ok": ok > 0, "note": f"{ok}/{len(GPS_ZONES)} zones read"}
    st["gps_cache"] = cache
    return cache, True


# ---------------------------------------------------------------- Sky closures (FAA TFRs)
TFR_WATCH_TYPES = ("SECURITY", "VIP", "SPECIAL", "HAZARDS", "SPACE OPERATIONS")


def pull_tfrs(st, sources):
    """Every 30 minutes. Returns (list of closures for the map, newly seen closures)."""
    cache = st.get("tfr_cache")
    if cache and time.time() - cache.get("ts", 0) < 30 * 60:
        return cache["list"], []
    seen = st.setdefault("tfr_seen", {})
    first = not seen
    try:
        meta = {x.get("notam_id"): x for x in get_json(TFR_LIST, timeout=25)}
        geo = get_json(TFR_GEO, timeout=30)
    except Exception as e:
        sources["tfr"] = {"ok": False, "note": f"{type(e).__name__}: {str(e)[:60]}"}
        return (cache or {}).get("list", []), []
    out, new = [], []
    for f in geo.get("features") or []:
        pr = f.get("properties") or {}
        nid = pr.get("NOTAM_KEY", "").split("-")[0] or pr.get("GID")
        m = meta.get(nid) or {}
        typ = (m.get("type") or pr.get("LEGAL") or "").upper()
        g = f.get("geometry") or {}
        rings = []
        if g.get("type") == "Polygon":
            rings = [g["coordinates"][0]]
        elif g.get("type") == "MultiPolygon":
            rings = [p[0] for p in g["coordinates"]]
        if not rings:
            continue
        pts = [pt for r in rings for pt in r]
        clat = sum(p[1] for p in pts) / len(pts)
        clon = sum(p[0] for p in pts) / len(pts)
        rad = max(miles(clat, clon, p[1], p[0]) for p in pts)
        if nid not in seen:
            seen[nid] = int(time.time())
            if not first:
                new.append(nid)
        rec = {"id": nid, "type": typ.title(), "desc": (m.get("description") or pr.get("TITLE") or "")[:160],
               "state": m.get("state") or pr.get("STATE") or "", "lat": round(clat, 3), "lon": round(clon, 3),
               "radius_mi": round(rad, 1), "home_mi": round(miles(HOME[0], HOME[1], clat, clon)),
               "first": seen[nid], "watch": typ in TFR_WATCH_TYPES,
               "rings": [[[round(p[1], 3), round(p[0], 3)] for p in r[:: max(1, len(r) // 60)]] for r in rings][:4]}
        out.append(rec)
    for k in [k for k in seen if k not in {r["id"] for r in out} and time.time() - seen[k] > 14 * 86400]:
        del seen[k]
    out.sort(key=lambda r: (-r["first"], r["home_mi"]))
    st["tfr_cache"] = {"ts": int(time.time()), "list": out}
    sources["tfr"] = {"ok": True, "note": f"{len(out)} closures, {len(new)} new"}
    return out, [r for r in out if r["id"] in new]


# ---------------------------------------------------------------- Deja vu
_REF = None


def reference():
    global _REF
    if _REF is None:
        try:
            with open(os.path.join(HERE, "reference_days.json")) as f:
                _REF = json.load(f)
        except Exception:
            _REF = {"days": {}, "labels": {}}
    return _REF


def rolling_record(st, m, now):
    """Keep 24 hours of sweep numbers and fold them into one day-shaped record."""
    sw = st.setdefault("sweeps24", [])
    sw.append([now, m])
    sw[:] = [s for s in sw if now - s[0] < 86400]
    rec = {}
    for _, mm in sw:
        signals.fold_day(rec, mm)
    return rec


def dejavu(rec24, st):
    ref = reference()
    days = ref.get("days", {})
    labels = ref.get("labels", {})
    live_days = list((st.get("days") or {}).values())
    hist_base = [d for k, d in days.items() if k not in labels]
    base = hist_base + live_days
    # each source is measured against its own normal: archive days vs archive, live radar vs live radar
    stats_h, stats_l = {}, {}
    for key, _, _ in signals.SIM_DIMS:
        s = signals.robust_stats(hist_base, key)
        if s:
            stats_h[key] = s
        s = signals.robust_stats(live_days, key) if len(live_days) >= 7 else None
        if s:
            stats_l[key] = s
    live_ok = len(live_days) >= 7
    stats_a = stats_l if live_ok else stats_h
    stats = stats_h
    res = []
    for k, lab in labels.items():
        if k not in days:
            continue
        pct, parts = signals.similarity(rec24, days[k], stats_a, stats_h)
        if pct is None:
            continue
        shared = sorted([p for p in parts if p["za"] > 1 and p["zb"] > 1], key=lambda p: -(p["za"] + p["zb"]))[:3]
        apart = sorted(parts, key=lambda p: p["s"])[:2]
        res.append({"date": k, "label": lab, "pct": pct,
                    "shared": [[p["label"], p["a"], p["b"]] for p in shared],
                    "apart": [[p["label"], p["a"], p["b"]] for p in apart if p["s"] < 0.6]})
    res.sort(key=lambda r: -r["pct"])
    # how alike are ordinary days to these event days? (so 70% means something)
    normal = []
    for d in hist_base[:40]:
        sims = [signals.similarity(d, days[k], stats)[0] for k in labels if k in days]
        sims = [s for s in sims if s is not None]
        if sims:
            normal.append(max(sims))
    typical = sorted(normal)[len(normal) // 2] if normal else None
    now24 = {k: rec24.get("peak", {}).get(k) for k in ("tanker", "airlift", "tanker_me", "airlift_me", "bridge", "bomber", "isr")}
    return {"top": res[:6], "typical": typical, "now": now24, "ref_days": len(days), "base_days": len(base),
            "live_days": len(live_days), "calibrated": live_ok}


# ---------------------------------------------------------------- Convergence
SIGNAL_NAMES = {
    "nightwatch": "Nightwatch (E-4B) airborne",
    "eam_burst": "Burst of emergency action messages",
    "skyking": "Skyking broadcast",
    "bridge": "Tanker bridge across the Atlantic",
    "tanker_surge": "Tanker surge",
    "airlift_surge": "Airlift surge",
    "bomber": "Bombers on the move",
    "isr": "Spy planes stacking up",
    "squawk": "Emergency squawk",
    "gps": "GPS jamming spike",
    "tfr": "New security sky closure",
    "foreign": "Foreign military jet near the US or Europe",
    "breaking": "Major breaking news",
    "e6": "Looking Glass / TACAMO up",
}


def kind_of(a):
    if a.get("tier") not in ("FLASH", "IMMEDIATE"):
        return None
    k = a.get("key", "")
    if k.startswith("nightwatch:"):
        return "nightwatch"
    if k.startswith("c2:"):
        return "e6"
    if k.startswith("surge:") or k.startswith("active:"):
        return "tanker_surge" if "tanker" in k else "airlift_surge"
    if k.startswith("bomber:"):
        return "bomber"
    if k.startswith("isr:") or k.startswith("subhunt:"):
        return "isr"
    if k.startswith("squawk:"):
        return "squawk"
    if k.startswith("foreign:"):
        return "foreign"
    if k.startswith("news:"):
        return "breaking"
    for p in ("eam_burst", "skyking", "bridge", "gps", "tfr"):
        if k.startswith(p + ":"):
            return p
    return None


def note_signals(st, alerts, now):
    sig = st.setdefault("signals", [])
    for a in alerts:
        k = kind_of(a)
        if not k:
            continue
        if any(s["k"] == k and now - s["ts"] < 1800 for s in sig):
            continue
        sig.append({"k": k, "ts": now, "what": a.get("what", "")[:80], "region": a.get("region")})
    sig[:] = [s for s in sig if now - s["ts"] < 7 * 86400][-300:]


def convergence(st, now, hours=6):
    win = [s for s in st.get("signals", []) if now - s["ts"] < hours * 3600]
    kinds = {}
    for s in win:
        kinds.setdefault(s["k"], s)
    n = len(kinds)
    level = "QUIET" if n == 0 else "WATCH" if n < 3 else "CONVERGENCE" if n < 4 else "HIGH CONVERGENCE"
    return {"score": n, "level": level, "hours": hours,
            "signals": [{"k": k, "name": SIGNAL_NAMES.get(k, k), "ts": s["ts"], "what": s["what"]}
                        for k, s in sorted(kinds.items(), key=lambda kv: -kv[1]["ts"])]}


# ---------------------------------------------------------------- the main hook
def run(state, cfg, planes, candidates, now, central, sources):
    """Returns (new alert candidates, intel dict for intel.json). Never raises."""
    st = state.setdefault("intel", {})
    w = cfg.get("watches", {})
    out = []
    intel = {"updated": now, "listen_url": LISTEN_URL}

    # --- Skyking listening post
    try:
        log, new = pull_eam(st, sources)
        es = eam_status(log, now)
        batch = log[:20]
        intel["eam"] = dict(es, log=[dict(m, parts=eam_breakdown(m, batch)) for m in log[:25]],
                            last_skyking=st.get("last_skyking"))
        sk_new = [m for m in new if is_sky(m) and now - m["ts"] < 6 * 3600]
        if sk_new and w.get("skyking", True):
            m = sk_new[0]
            out.append(dict(
                tier="IMMEDIATE", key=f"skyking:{m['id']}", cooldown=3600, watch="skyking",
                what="SKYKING BROADCAST ON HFGCS", location="HF Global Communications System, 8992 kHz",
                assets=f"\"{m['message'][:80]}\"" + (f" read by {m['sender']}" if m.get("sender") else ""),
                response="A Skyking is a short order to nuclear forces, broadcast 'do not answer'. Usually exercises. Logged by listeners on eam.watch.",
                source="eam.watch public HFGCS log", threat="ELEVATED", count=1))
        if es["eam3h"] >= 3 and es["eam24"] >= max(4, 3 * es["normal"]) and w.get("skyking", True):
            out.append(dict(
                tier="IMMEDIATE", key="eam_burst:hfgcs", cooldown=6 * 3600, watch="skyking",
                what="BURST OF EMERGENCY ACTION MESSAGES", location="HF Global Communications System",
                assets=f"{es['eam3h']} EAMs in 3 hours, {es['eam24']} in 24 hours (normal lately: about {es['normal']} a day)",
                response="EAMs are coded orders to US nuclear forces. Bursts often come with exercises. Watch for other signals.",
                source="eam.watch public HFGCS log", threat="ELEVATED", count=es["eam3h"], escalate_count=es["eam3h"]))
    except Exception as e:
        print("intel eam error:", type(e).__name__, e)

    # --- GPS jamming
    try:
        g, fresh = pull_gps(st, sources)
        base = st.setdefault("gps_base", {})
        for z in g["zones"]:
            if not z.get("ok") or not z.get("total"):
                continue
            b = base.get(z["k"])
            z["base"] = round(b) if b is not None else None
            if fresh:
                base[z["k"]] = z["pct"] if b is None else round(0.9 * b + 0.1 * z["pct"], 1)
            if fresh and b is not None and z["total"] >= 8 and z["pct"] >= 35 and z["pct"] >= b + 20 and w.get("gpsjam", True):
                out.append(dict(
                    tier="IMMEDIATE" if z["k"] in ("israel", "gulf", "cyprus") else "ROUTINE",
                    key=f"gps:{z['k']}", cooldown=8 * 3600, watch="gpsjam",
                    what=f"GPS JAMMING SPIKE: {z['label'].upper()}", location=z["label"],
                    assets=f"{z['bad']} of {z['total']} planes report poor GPS ({z['pct']}%, normal about {round(b)}%)",
                    response="Jamming jumps when militaries expect drones or missiles. Planes keep flying on backup navigation.",
                    source="adsb.lol live ADS-B (GPS quality NIC/NACp)", threat="ELEVATED",
                    region="easternmed" if z["k"] in ("israel", "cyprus") else "gulf" if z["k"] == "gulf" else None,
                    lat=z["lat"], lon=z["lon"], count=z["bad"]))
        intel["gps"] = g
    except Exception as e:
        print("intel gps error:", type(e).__name__, e)

    # --- Sky closures
    try:
        tfrs, tnew = pull_tfrs(st, sources)
        intel["tfr"] = tfrs[:120]
        for r in tnew:
            if not r["watch"] or not w.get("closures", True):
                continue
            near = r["home_mi"] <= 200
            out.append(dict(
                tier="IMMEDIATE" if near else "ROUTINE", key=f"tfr:{r['id']}", cooldown=86400, watch="closures",
                what=f"NEW SKY CLOSURE: {r['type'].upper()}" + (" NEAR HOME" if near else ""),
                location=f"{r['state']} ({r['lat']:.2f}, {r['lon']:.2f}), {r['home_mi']:,} mi from home",
                assets=f"FAA flight restriction {r['id']}, about {r['radius_mi']:.0f} mi across from its center. {r['desc'][:110]}",
                response="Security closures go up for VIP visits, big events and sensitive operations.",
                source="FAA TFR list (tfr.faa.gov)", threat="LOW" if not near else "ELEVATED",
                region="conus", lat=r["lat"], lon=r["lon"]))
    except Exception as e:
        print("intel tfr error:", type(e).__name__, e)

    # --- Tanker bridge + day fingerprint
    m, bridge = signals.sweep_metrics(planes) if planes else ({}, None)
    if bridge:
        intel["bridge"] = bridge
        if bridge["atl"] >= 4 and w.get("tankers", True):
            out.append(dict(
                tier="FLASH" if bridge["atl"] >= 8 else "IMMEDIATE", key="bridge:atlantic", cooldown=8 * 3600,
                watch="bridge", what="TANKER BRIDGE ACROSS THE ATLANTIC",
                location="North Atlantic, flying east toward Europe and the Middle East",
                assets=f"{bridge['atl']} tankers eastbound over the ocean, {bridge['far']} more over Europe/Med, "
                       f"{bridge['fighters']} fighters and {bridge['lift']} cargo jets with them",
                response="A chain of tankers heading east is how fighters get moved overseas fast. Seen before big operations.",
                source="adsb.lol live ADS-B (military feed)", threat="HIGH" if bridge["atl"] >= 8 else "ELEVATED",
                region="europe", lat=bridge["chain"][0][0] if bridge["chain"] else None,
                lon=bridge["chain"][0][1] if bridge["chain"] else None,
                count=bridge["atl"], escalate_count=bridge["atl"]))

    # --- Nightwatch + Looking Glass status
    nw = st.setdefault("nw", {})
    air = []
    for p in planes:
        t = (p.get("t") or "").upper()
        if t in ("E4", "E4B", "E6") and isinstance(p.get("alt"), (int, float)) and p["alt"] > 1000:
            first = nw.setdefault(p["hex"], {"lat": p["lat"], "lon": p["lon"], "ts": now})
            air.append({"hex": p["hex"], "cs": p.get("cs"), "t": t, "lat": p["lat"], "lon": p["lon"],
                        "alt": p.get("alt"), "gs": p.get("gs"), "trk": p.get("trk"), "from": first,
                        "mission": decode_line(p)})
    for h in [h for h, v in nw.items() if now - v["ts"] > 18 * 3600 and h not in {a["hex"] for a in air}]:
        del nw[h]
    intel["c2"] = air

    # --- Convergence (counts everything that fired this sweep too)
    note_signals(st, candidates + out, now)
    conv = convergence(st, now)
    intel["convergence"] = conv
    prev = st.get("conv_alerted") or {}
    if conv["score"] >= 3 and w.get("convergence", True) and (
            now - prev.get("ts", 0) > 6 * 3600 or conv["score"] > prev.get("score", 0)):
        st["conv_alerted"] = {"ts": now, "score": conv["score"]}
        names = ", ".join(s["name"] for s in conv["signals"][:5])
        out.append(dict(
            tier="FLASH" if conv["score"] >= 4 else "IMMEDIATE", key=f"convergence:{conv['score']}", cooldown=0,
            watch="convergence", what=f"CONVERGENCE: {conv['score']} SIGNALS STACKING",
            location="Across the watch", assets=names,
            response=f"{conv['score']} different kinds of signals inside {conv['hours']} hours. One alone is often routine. Several together is what stood out before past operations.",
            source="WATCHTOWER convergence alarm", threat="HIGH" if conv["score"] >= 4 else "ELEVATED",
            count=conv["score"]))

    # --- Deja vu (rolling 24 hours vs real past days)
    try:
        if m:
            es = (intel.get("eam") or {})
            m = dict(m)
            rec24 = rolling_record(st, m, now)
            rec24["eam"] = es.get("eam24")
            rec24["sk"] = es.get("sk24")
            gz = {z["k"]: z for z in (intel.get("gps") or {}).get("zones", []) if z.get("ok")}
            if gz:
                rec24["gps"] = max((gz[k].get("pct") or 0) for k in gz if k in ("israel", "gulf", "cyprus")) if any(k in gz for k in ("israel", "gulf", "cyprus")) else None
            rec24["tfr"] = sum(1 for r in (intel.get("tfr") or []) if r["watch"] and now - r["first"] < 86400)
            # store finished days (Central dates) for the baseline
            today = datetime.fromtimestamp(now, central).strftime("%Y-%m-%d")
            days = st.setdefault("days", {})
            dr = days.setdefault(today, {"date": today})
            signals.fold_day(dr, m)
            for k in ("eam", "sk", "gps", "tfr"):
                if rec24.get(k) is not None:
                    dr[k] = max(dr.get(k) or 0, rec24[k])
            for k in sorted(days)[:-120]:
                del days[k]
            if len(st["sweeps24"]) >= 36:
                dv = dejavu(rec24, {"days": {k: v for k, v in days.items() if k != today and v.get("sweeps", 0) >= 100}})
                dv["hours"] = round((now - st["sweeps24"][0][0]) / 3600, 1)
                intel["dejavu"] = dv
                top = dv["top"][0] if dv["top"] else None
                typ = dv.get("typical") or 70
                if top and top["pct"] >= max(80, typ + 10) and w.get("buildups", True):
                    pa = st.get("dv_alerted") or {}
                    if now - pa.get("ts", 0) > 12 * 3600 or top["pct"] >= pa.get("pct", 0) + 8:
                        st["dv_alerted"] = {"ts": now, "pct": top["pct"]}
                        out.append(dict(
                            tier="IMMEDIATE", key=f"dejavu:{top['date']}", cooldown=0, watch="dejavu",
                            what=f"DEJA VU: TODAY LOOKS {top['pct']}% LIKE {top['date']}",
                            location="The whole sky, last 24 hours",
                            assets=f"{top['label']}. Shared: " + (", ".join(s[0] for s in top["shared"]) or "overall pattern"),
                            response=f"Ordinary days usually score about {typ}% against these event days.",
                            source="WATCHTOWER Deja vu engine (adsb.lol history archives)", threat="ELEVATED",
                            count=top["pct"]))
            else:
                intel["dejavu"] = {"warming": True, "hours": round((now - st["sweeps24"][0][0]) / 3600, 1)}
    except Exception as e:
        print("intel dejavu error:", type(e).__name__, e)

    return out, intel


# ---------------------------------------------------------------- reports
def _bar(n, mx, width=10):
    if not mx:
        return ""
    k = max(0, min(width, round(width * n / mx)))
    return "█" * k + "░" * (width - k)


def morning_report(state, log, intel, now, central):
    """Overnight summary: 9 PM yesterday to now."""
    since = now - 10 * 3600
    night = [a for a in log.get("alerts", []) if a.get("ts", 0) >= since and a.get("watch") not in ("test", "recap", "report", "sunday")]
    tiers = {t: sum(1 for a in night if a.get("tier") == t) for t in ("FLASH", "IMMEDIATE", "ROUTINE")}
    st = state.get("intel", {})
    sw = [s for s in st.get("sweeps24", []) if s[0] >= since]
    peak = lambda k: max([s[1].get(k) or 0 for s in sw] or [0])
    es = intel.get("eam") or {}
    conv = intel.get("convergence") or {}
    dv = (intel.get("dejavu") or {}).get("top") or []
    lines = []
    if night:
        lines.append(f"Overnight: {tiers['FLASH']} flash, {tiers['IMMEDIATE']} immediate, {tiers['ROUTINE']} routine.")
        for a in sorted(night, key=lambda a: {"FLASH": 0, "IMMEDIATE": 1, "ROUTINE": 2}.get(a.get("tier"), 3))[:4]:
            lines.append(f"• {a.get('what', '')}")
    else:
        lines.append("A quiet night. Nothing tripped an alert.")
    lines.append("")
    lines.append(f"⛽ Most refueling planes up at once: {peak('tanker')}  ✈️ Big cargo: {peak('airlift')}")
    lines.append(f"📻 HFGCS: {es.get('eam24', 0)} EAMs and {es.get('sk24', 0)} Skykings in 24 hours (normal about {es.get('normal', 0)} a day)")
    if conv:
        lines.append(f"🧩 Convergence: {conv.get('score', 0)} signals in the last 6 hours")
    if dv:
        lines.append(f"🔁 Deja vu: closest match {dv[0]['date']} at {dv[0]['pct']}%")
    lines.append("")
    lines.append("📖 Psalm 121:4: Behold, he that keepeth Israel shall neither slumber nor sleep.")
    d = datetime.fromtimestamp(now, central)
    return {"title": f"☀️ MORNING REPORT // {d.strftime('%a %b')} {d.day}", "body": "\n".join(lines),
            "date": d.strftime("%Y-%m-%d"), "ts": now}


def count_alerts(state, alerts, now, central):
    """Keep a per-day tally of real alerts (the alert log only holds the newest 400)."""
    today = datetime.fromtimestamp(now, central).strftime("%Y-%m-%d")
    dr = state.setdefault("intel", {}).setdefault("days", {}).setdefault(today, {"date": today})
    for a in alerts:
        if a.get("tier") not in ("FLASH", "IMMEDIATE", "ROUTINE") or a.get("watch") in ("test", "recap", "report", "sunday"):
            continue
        dr["alerts"] = dr.get("alerts", 0) + 1
        if a.get("region"):
            rg = dr.setdefault("regions", {})
            rg[a["region"]] = rg.get(a["region"], 0) + 1


def sunday_report(state, log, now, central, region_label=None):
    """This week vs last week, from the alert log + stored day fingerprints."""
    wk = [a for a in log.get("alerts", []) if now - a.get("ts", 0) < 7 * 86400 and a.get("tier") in ("FLASH", "IMMEDIATE", "ROUTINE") and a.get("watch") not in ("test", "recap", "report", "sunday")]
    lw = [a for a in log.get("alerts", []) if 7 * 86400 <= now - a.get("ts", 0) < 14 * 86400 and a.get("tier") in ("FLASH", "IMMEDIATE", "ROUTINE") and a.get("watch") not in ("test", "recap", "report", "sunday")]
    days = (state.get("intel", {}) or {}).get("days", {})
    keys = sorted(days)
    this = [days[k] for k in keys[-7:]]
    last = [days[k] for k in keys[-14:-7]]
    pk = lambda ds, k: max([(d.get("peak") or {}).get(k, 0) for d in ds] or [0])
    if any("alerts" in d for d in this):
        wk_n = sum(d.get("alerts", 0) for d in this)
    else:
        wk_n = len(wk)
    lw_n = sum(d.get("alerts", 0) for d in last) if any("alerts" in d for d in last) else len(lw)
    rows = [("Alerts", wk_n, lw_n), ("Refueling peak", pk(this, "tanker"), pk(last, "tanker")),
            ("Big cargo peak", pk(this, "airlift"), pk(last, "airlift")), ("Bombers peak", pk(this, "bomber"), pk(last, "bomber")),
            ("Spy planes peak", pk(this, "isr"), pk(last, "isr")), ("EAMs (best day)", max([d.get("eam") or 0 for d in this] or [0]), max([d.get("eam") or 0 for d in last] or [0]))]
    have_last = len(last) >= 3 or bool(lw)
    lines = ["This week vs last week:" if have_last else
             "This week (last week's numbers start showing once the radar has a full week saved):"]
    for name, a, b in rows:
        if not have_last:
            lines.append(f"{name}: {a}")
            continue
        mx = max(a, b, 1)
        arrow = "▲" if a > b else "▼" if a < b else "="
        lines.append(f"{name}: {a} {arrow} (last week {b})")
        lines.append(f"  {_bar(a, mx)} this")
        lines.append(f"  {_bar(b, mx)} last")
    reg = {}
    for d in this:
        for k, v in (d.get("regions") or {}).items():
            reg[k] = reg.get(k, 0) + v
    if not reg:
        for a in wk:
            if a.get("region"):
                reg[a["region"]] = reg.get(a["region"], 0) + 1
    if reg:
        hot = max(reg, key=reg.get)
        lines.append(f"🔥 Hottest region: {(region_label or {}).get(hot, hot)} ({reg[hot]} alerts)")
    top = sorted(wk, key=lambda a: {"FLASH": 0, "IMMEDIATE": 1, "ROUTINE": 2}[a["tier"]])[:3]
    if top:
        lines.append("Biggest moments:")
        lines += [f"• {a.get('what', '')}" for a in top]
    lines.append("")
    lines.append("📖 Mark 13:37: And what I say unto you I say unto all, Watch.")
    d = datetime.fromtimestamp(now, central)
    return {"title": f"📊 SUNDAY REPORT // week ending {d.strftime('%b')} {d.day}", "body": "\n".join(lines),
            "date": d.strftime("%Y-%m-%d"), "ts": now}
