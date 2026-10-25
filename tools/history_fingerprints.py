#!/usr/bin/env python3
"""Replay one archived ADS-B day (adsb.lol globe_history, free and public) through the
same sweep math the live watcher uses, and print that day's Deja vu fingerprint.

Usage (streams ~3.5 GB, keeps nothing on disk):
  (curl -sfL <url>.tar.aa; curl -sfL <url>.tar.ab; ...) | python3 tools/history_fingerprints.py 2026-02-21 > out.json

Only aircraft the adsb.lol database flags as military are read in full (the same set the
live /v2/mil feed serves). A sweep is simulated every 10 minutes of the UTC day.
"""
import bisect
import gzip
import json
import os
import sys
import tarfile
import zlib
from datetime import datetime, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "watcher"))
import signals  # noqa: E402

# classify / region_of / nation_of live in watch.py; import without running main()
os.environ.setdefault("DATA_DIR", "/tmp/wr_hist_data")
import watch  # noqa: E402

WINDOW = 120  # a plane counts in a sweep if it reported a position in the 2 minutes before it


def is_mil(head):
    i = head.find(b'"dbFlags"')
    if i < 0:
        return False
    j = i + 10
    while j < len(head) and head[j:j + 1] in b" :":
        j += 1
    k = j
    while k < len(head) and head[k:k + 1].isdigit():
        k += 1
    try:
        return int(head[j:k]) & 1 == 1
    except ValueError:
        return False


def main():
    date = sys.argv[1]
    day0 = int(datetime.strptime(date, "%Y-%m-%d").replace(tzinfo=timezone.utc).timestamp())
    tracks = []  # (meta, times, points)
    files = mil = 0
    tf = tarfile.open(fileobj=sys.stdin.buffer, mode="r|")
    try:
        for m in tf:
            if not m.isfile() or "/traces/" not in m.name:
                continue
            files += 1
            raw = tf.extractfile(m).read()
            try:
                head = zlib.decompressobj(16 + zlib.MAX_WBITS).decompress(raw, 600)
            except zlib.error:
                head = raw[:600]
            if not is_mil(head):
                continue
            try:
                j = json.loads(gzip.decompress(raw))
            except Exception:
                try:
                    j = json.loads(raw)
                except Exception:
                    continue
            mil += 1
            base = j.get("timestamp") or day0
            times, pts = [], []
            cs, sq = "", ""
            for pt in j.get("trace", []):
                if len(pt) < 6:
                    continue
                d = pt[8] if len(pt) > 8 and isinstance(pt[8], dict) else None
                if d:
                    cs = (d.get("flight") or cs or "").strip()
                    sq = d.get("squawk") or sq
                alt = pt[3]
                if alt == "ground":
                    alt = 0
                times.append(base + pt[0])
                pts.append((pt[1], pt[2], alt if isinstance(alt, (int, float)) else None,
                            pt[4], pt[5], cs, sq))
            if times:
                tracks.append(({"hex": j.get("icao"), "t": (j.get("t") or "").upper(), "r": j.get("r") or ""}, times, pts))
    except tarfile.ReadError:
        pass  # end of a truncated/concatenated stream

    day = {"date": date, "src": "adsb.lol globe_history (archived ADS-B, military-flagged aircraft)"}
    best_bridge = None
    for t in range(day0 + 300, day0 + 86400, 600):
        planes = []
        for meta, times, pts in tracks:
            i = bisect.bisect_right(times, t) - 1
            if i < 0 or t - times[i] > WINDOW:
                continue
            lat, lon, alt, gs, trk, cs, sq = pts[i]
            if lat is None or lon is None:
                continue
            planes.append({"hex": meta["hex"], "cs": cs, "t": meta["t"], "lat": round(lat, 3), "lon": round(lon, 3),
                           "alt": alt, "gs": gs, "trk": trk, "sq": sq,
                           "cat": watch.classify(meta["t"], cs), "rg": watch.region_of(lat, lon),
                           "nat": watch.nation_of(meta["hex"] or "")})
        if not planes:
            continue
        m, b = signals.sweep_metrics(planes)
        signals.fold_day(day, m)
        if best_bridge is None or b["strength"] > best_bridge["strength"]:
            best_bridge = dict(b, ts=t)
    day["bridge_best"] = best_bridge
    day["files"], day["mil_aircraft"] = files, mil
    json.dump(day, sys.stdout)


if __name__ == "__main__":
    main()
