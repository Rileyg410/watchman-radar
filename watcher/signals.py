"""Shared signal math for WATCHTOWER round two.

Used by the live watcher every sweep AND by tools/history_fingerprints.py, which replays
archived ADS-B days (adsb.lol globe_history) through the exact same functions, so the
Deja vu engine compares like with like.
"""
import math

# The Atlantic "bridge" corridor: open ocean between North America and Europe/Africa.
ATL_BOX = (25.0, 66.0, -72.0, -8.0)       # lat_min, lat_max, lon_min, lon_max
# The far side of the bridge: Europe and the Med, where the chain keeps heading east/south-east.
FAR_BOX = (28.0, 60.0, -8.0, 36.0)
ME_REGIONS = ("gulf", "easternmed")


def in_box(p, box):
    a, b, c, d = box
    return p.get("lat") is not None and a <= p["lat"] <= b and c <= p["lon"] <= d


def airborne(p, min_alt=8000):
    return isinstance(p.get("alt"), (int, float)) and p["alt"] >= min_alt


def eastbound(p, lo=25, hi=165):
    t = p.get("trk")
    return isinstance(t, (int, float)) and lo <= t <= hi


def nm_between(a, b):
    la1, lo1, la2, lo2 = map(math.radians, (a["lat"], a["lon"], b["lat"], b["lon"]))
    h = math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2
    return 2 * 3440.1 * math.asin(min(1, math.sqrt(h)))


def tanker_bridge(planes):
    """Find tankers streaming east across the Atlantic (plus the leg continuing over Europe/Med).

    Returns {"atl": n tankers on the ocean leg, "far": n on the far leg, "fighters": n fighters
    being dragged across with them, "strength": score, "chain": [[lat, lon, cs, type, hex], ...]
    sorted west to east}.
    """
    atl = [p for p in planes if p.get("cat") == "tanker" and in_box(p, ATL_BOX) and airborne(p, 15000) and eastbound(p)]
    far = [p for p in planes if p.get("cat") == "tanker" and in_box(p, FAR_BOX) and airborne(p, 15000) and eastbound(p, 60, 175)]
    # fighters over open ocean flying east = a "fighter drag" (tankers escorting jets across)
    fighters = [p for p in planes if p.get("cat") == "fighter" and in_box(p, ATL_BOX) and airborne(p, 15000) and eastbound(p)]
    lift = [p for p in planes if p.get("cat") == "airlift" and in_box(p, ATL_BOX) and airborne(p, 15000) and eastbound(p)]
    chain = sorted(atl + (far if atl else []), key=lambda p: p["lon"])
    strength = len(atl) + 0.5 * (len(far) if atl else 0) + 0.5 * min(len(fighters), 8) + 0.25 * len(lift)
    return {
        "atl": len(atl), "far": len(far) if atl else 0, "fighters": len(fighters), "lift": len(lift),
        "strength": round(strength, 1),
        "chain": [[p["lat"], p["lon"], p.get("cs") or "", p.get("t") or "", p.get("hex") or ""] for p in chain],
        "escorts": [[p["lat"], p["lon"], p.get("cs") or "", p.get("t") or "", p.get("hex") or ""] for p in fighters][:12],
    }


FOREIGN_NEAR = ("alaska", "cuba", "conus", "hawaii", "europe", "baltic")
FOREIGN_NATS = ("RU", "CN", "IR", "CU", "KP")


def sweep_metrics(planes):
    """One sweep's fingerprint numbers. Every value is a count of aircraft seen at once."""
    m = {k: 0 for k in ("mil", "tanker", "airlift", "bomber", "isr", "c2", "fighter",
                        "tanker_me", "airlift_me", "tanker_eur", "airlift_eur", "tanker_pac",
                        "bomber_abroad", "e4", "e6", "sq", "foreign")}
    for p in planes:
        c, rg = p.get("cat"), p.get("rg")
        m["mil"] += 1
        if c in m:
            m[c] += 1
        if c in ("tanker", "airlift"):
            if rg in ME_REGIONS:
                m[c + "_me"] += 1
            elif rg in ("europe", "baltic", "ukraine"):
                m[c + "_eur"] += 1
            elif c == "tanker" and rg == "pacific":
                m["tanker_pac"] += 1
        if c == "bomber" and rg not in (None, "conus", "hawaii") and p.get("nat") == "US":
            m["bomber_abroad"] += 1
        t = (p.get("t") or "").upper()
        if t in ("E4", "E4B") and airborne(p, 1000):
            m["e4"] += 1
        if t == "E6" and airborne(p, 1000):
            m["e6"] += 1
        if p.get("sq") in ("7500", "7600", "7700"):
            m["sq"] += 1
        if p.get("nat") in FOREIGN_NATS and rg in FOREIGN_NEAR:
            m["foreign"] += 1
    b = tanker_bridge(planes)
    m["bridge"] = b["strength"]
    m["bridge_atl"] = b["atl"]
    return m, b


# Day fingerprint = the peak of each sweep number over the day (plus a couple of sums).
DAY_KEYS = ("mil", "tanker", "airlift", "bomber", "isr", "c2", "fighter", "tanker_me", "airlift_me",
            "tanker_eur", "airlift_eur", "tanker_pac", "bomber_abroad", "e4", "e6", "sq", "foreign",
            "bridge", "bridge_atl")


def fold_day(day, m):
    """Fold one sweep's metrics into a running day record (peaks + sweep count + avg mil)."""
    pk = day.setdefault("peak", {})
    for k in DAY_KEYS:
        v = m.get(k, 0) or 0
        if v > pk.get(k, 0):
            pk[k] = v
    day["sweeps"] = day.get("sweeps", 0) + 1
    day["mil_sum"] = day.get("mil_sum", 0) + (m.get("mil") or 0)
    day["bridge_sweeps"] = day.get("bridge_sweeps", 0) + (1 if (m.get("bridge_atl") or 0) >= 3 else 0)
    return day


# ---- similarity ----------------------------------------------------------------
# Which numbers the Deja vu engine compares, how much each one counts, and a plain name.
SIM_DIMS = [
    ("tanker", 1.0, "refueling planes up at once"),
    ("airlift", 1.0, "big cargo planes up at once"),
    ("tanker_me", 1.4, "refueling planes over Israel and the Gulf"),
    ("airlift_me", 1.4, "cargo planes over Israel and the Gulf"),
    ("tanker_eur", 1.0, "refueling planes over Europe"),
    ("bridge", 1.5, "tanker bridge across the Atlantic"),
    ("bomber", 0.8, "bombers up at once"),
    ("isr", 0.8, "spy and radar planes up at once"),
    ("e4", 0.6, "Nightwatch (E-4B) flying"),
    ("e6", 0.4, "Looking Glass/TACAMO (E-6B) up"),
    ("sq", 0.3, "emergency codes"),
    ("eam", 1.0, "emergency action messages on HFGCS"),
    ("sk", 0.6, "Skyking messages"),
    ("gps", 0.8, "GPS jamming near Israel and the Gulf"),
    ("tfr", 0.4, "new security sky closures"),
]


def day_vector(rec):
    v = dict(rec.get("peak") or {})
    if rec.get("sweeps"):  # a sweep that saw none of a kind counted 0, so a missing peak is a real 0
        for key, _, _ in SIM_DIMS:
            if key in DAY_KEYS:
                v.setdefault(key, 0)
    for k in ("eam", "sk", "gps", "tfr"):
        if rec.get(k) is not None:
            v[k] = rec[k]
    return v


def robust_stats(days, key):
    vals = sorted(day_vector(d).get(key) for d in days if day_vector(d).get(key) is not None)
    if len(vals) < 3:
        return None
    n = len(vals)
    med = vals[n // 2] if n % 2 else (vals[n // 2 - 1] + vals[n // 2]) / 2
    dev = sorted(abs(x - med) for x in vals)
    mad = dev[n // 2] if n % 2 else (dev[n // 2 - 1] + dev[n // 2]) / 2
    spread = max(mad * 1.4826, 1.0, 0.15 * med)
    return med, spread


def similarity(a, b, stats, stats_b=None):
    """Percent alike (0-100) over the numbers both days have, plus the closest/furthest parts.
    stats_b lets day b be measured against its own baseline (history archive vs live radar)."""
    va, vb = day_vector(a), day_vector(b)
    stats_b = stats_b or stats
    tot_w, acc, parts = 0.0, 0.0, []
    for key, w, label in SIM_DIMS:
        if key not in va or key not in vb or key not in stats or key not in stats_b:
            continue
        med, spread = stats[key]
        medb, spreadb = stats_b[key]
        za = max(-3, min(6, (va[key] - med) / spread))
        zb = max(-3, min(6, (vb[key] - medb) / spreadb))
        s = max(0.0, 1 - abs(za - zb) / 3.0)
        # numbers that are high on BOTH days count extra: shared surges are what matter
        boost = 1.0 + 0.5 * min(max(za, 0), max(zb, 0))
        tot_w += w * boost
        acc += w * boost * s
        parts.append({"k": key, "label": label, "a": va[key], "b": vb[key], "za": round(za, 1), "zb": round(zb, 1), "s": round(s, 2)})
    if not tot_w or len(parts) < 5:
        return None, parts
    return round(100 * acc / tot_w), parts
