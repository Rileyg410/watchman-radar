"""Build the ICAO 24-bit address -> country table used by the radar.

Source: the ICAO Annex 10 Vol III allocation table, as kept in tar1090's html/flags.js
(https://github.com/wiedehopf/tar1090). Run:  python3 tools/build_countries.py /path/to/flags.js
Writes country-data.js (for the site) and watcher/country_ranges.json (for WATCHTOWER).
Order matters: the first range that matches wins (UK territories sit before the UK catch-all).
"""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
src = Path(sys.argv[1]).read_text(encoding="utf-8")
rows = re.findall(r'start:\s*0x(\w+),\s*end:\s*0x(\w+),\s*country:\s*"([^"]+)",\s*country_code:\s*(?:"(\w+)"|null)', src)
ranges, names = [], {}
for a, b, name, cc in rows:
    if not cc:
        continue  # ICAO temporary / special-use blocks: no country
    cc = cc.upper()
    ranges.append([int(a, 16), int(b, 16), cc])
    names.setdefault(cc, name)
# friendlier short names for a few
names.update({"US": "United States", "GB": "United Kingdom", "AE": "United Arab Emirates", "KP": "North Korea",
              "KR": "South Korea", "RU": "Russia", "IR": "Iran", "SY": "Syria", "TW": "Taiwan"})
data = {"ranges": ranges, "names": names}
(ROOT / "watcher" / "country_ranges.json").write_text(json.dumps(data, separators=(",", ":")), encoding="utf-8")
(ROOT / "country-data.js").write_text(
    "// ICAO 24-bit address blocks by country (ICAO Annex 10 Vol III table, via tar1090). Built by tools/build_countries.py\n"
    "window.WR_CC_DATA = " + json.dumps(data, separators=(",", ":"), ensure_ascii=False) + ";\n", encoding="utf-8")
print(len(ranges), "ranges,", len(names), "countries")
