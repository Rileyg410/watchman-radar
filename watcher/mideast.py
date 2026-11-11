"""MIDEAST NEWS - the live Iran / Israel / Middle East news desk for Watchman Radar.

Every sweep it reads free RSS feeds (Mideast outlets direct, plus Reuters / AP / i24NEWS and topic
searches through Google News), keeps the Iran, Israel and regional stories, tags each one by place
(Iran, Israel, Lebanon/Hezbollah, Syria, Yemen/Houthis, Gulf), flags the military / movement ones,
de-duplicates them and merges them into mideast.json (last 48 hours, newest first, up to 120 stories).

Standard library only. Never raises into the main sweep: watch.py wraps run() in try/except.
"""
import hashlib
import html
import re
import time
import urllib.parse
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from datetime import timezone
from email.utils import parsedate_to_datetime

KEEP_HOURS = 48
KEEP_MAX = 120

# (source name, url, home tag) -- home tag: what a story from this outlet is about when no place is named
# (None = general outlet: a story is only kept when it names a Mideast place)
DIRECT = [
    ("Times of Israel", "https://www.timesofisrael.com/feed/", "israel"),
    ("Times of Israel", "https://www.timesofisrael.com/israel-and-the-region/feed/", "israel"),
    ("Jerusalem Post", "https://www.jpost.com/rss/rssfeedsmiddleeastnews.aspx", None),
    ("Jerusalem Post", "https://www.jpost.com/rss/rssfeedsisraelnews.aspx", None),
    ("Iran International", "https://www.iranintl.com/en/feed", "iran"),
    ("Al Jazeera", "https://www.aljazeera.com/xml/rss/all.xml", None),
    ("Al-Monitor", "https://www.al-monitor.com/rss", None),
    ("BBC", "https://feeds.bbci.co.uk/news/world/middle_east/rss.xml", None),
    ("The Guardian", "https://www.theguardian.com/world/middleeast/rss", None),
    ("The War Zone", "https://www.twz.com/feed", None),
    ("JNS", "https://www.jns.org/feed/", None),
    ("Ynet News", "https://www.ynetnews.com/Integration/StoryRss3089.xml", None),
    ("Long War Journal", "https://www.longwarjournal.org/feed", None),
    ("The National", "https://www.thenationalnews.com/arc/outboundfeeds/rss/?outputType=xml", None),
]
GNEWS = [
    "(Iran OR Israel OR Hezbollah OR Houthi OR Syria OR Gaza) site:reuters.com",
    "(Iran OR Israel OR Hezbollah OR Houthi OR Syria OR Gaza) site:apnews.com",
    "site:i24news.tv",
    "site:timesofisrael.com",  # Times of Israel turns GitHub's servers away from its own feed
    "Iran military OR IRGC OR Tehran OR \"Iranian navy\"",
    "Israel IDF OR \"Israeli strike\" OR \"Israeli military\"",
    "Hezbollah OR Lebanon Israel strike",
    "Houthi OR Yemen OR \"Red Sea\" attack OR missile",
    "Syria military OR Damascus OR Golan",
    "\"Strait of Hormuz\" OR \"Persian Gulf\" OR Saudi OR UAE OR Qatar military",
    "\"Middle East\" warships OR carrier OR deployment OR troops",
    "CENTCOM OR \"carrier strike group\" OR B-52 OR F-35 \"Middle East\" OR Iran OR Israel",
    "Iran OR Houthi OR Hezbollah missile OR drone launched OR intercepted",
]

TAGS = [
    ("iran", r"\biran\w*|\btehran\b|\birgc\b|revolutionary guard|khamenei|pezeshkian|araghchi|isfahan|natanz|fordow|bandar abbas|qeshm|kharg|\bpersia\b"),
    ("israel", r"\bisrael\w*|\bidf\b|netanyahu|jerusalem|tel aviv|\bgaza\b|\bhamas\b|west bank|knesset|mossad|iron dome|\bhaifa\b|\beilat\b|\bshin bet\b|\bnegev\b|\bgalilee\b"),
    ("lebanon", r"leban\w*|hezbollah|hizbullah|hizballah|beirut|\blitani\b|naqoura|unifil|nasrallah|\bqassem\b"),
    ("syria", r"\bsyria\w*|damascus|aleppo|\bgolan\b|al-sharaa|\bsharaa\b|\bidlib\b|latakia|\bhoms\b|deir ez-zor|\bhasakah\b"),
    ("yemen", r"\byemen\w*|houthi|sanaa|hodeidah|red sea|bab el-mandeb|bab al-mandab|\baden\b|ansar allah"),
    ("gulf", r"\bsaudi\w*|riyadh|\buae\b|emirat\w*|abu dhabi|\bdubai\b|\bqatar\w*|\bdoha\b|bahrain\w*|kuwait\w*|\boman\b|muscat|hormuz|persian gulf|gulf of oman|\biraq\w*|baghdad|\bgcc\b|gulf states"),
]
REGION_ANY = r"middle east|mideast|(?<!jim )\bjordan(ian)?\b|\bamman\b|sinai|suez|\begypt\w*|cyprus|eastern mediterranean|centcom"

MIL = [
    # (label, regex) -- matched on the headline; every match is listed, the first is the badge's main word
    ("STRIKE", r"\bstrikes?\b|\bstruck\b|air ?strikes?|\bbomb(s|ed|ing|ings)?\b|\bshell(ed|ing)\b|\braids?\b|\bpound(s|ed|ing)?\b|\bhits?\b.{0,30}\b(targets?|sites?|bases?|ship|tanker|vessel)s?\b|\battack(s|ed)?\b|\bambush\w*|\bclash(es|ed)?\b|\bfirefight|gunfire|\bexplosions?\b|\bblasts?\b|\bassassinat\w*|\beliminat(e|ed|es)\b|(israeli|idf|forces|army|troops|military|houthi|hezbollah|hamas|irgc|airstrike|drone|missile)s?\b.{0,40}\bkill(s|ed|ing)?\b|\bkill(s|ed|ing)?\b.{0,40}\b(commander|operative|militant|fighter|terrorist|soldier)s?\b"),
    ("MISSILES / DRONES", r"\bmissiles?\b|\brockets?\b|\bdrones?\b|\buavs?\b|\bballistic\b|hypersonic|\bshahed\b|\bprojectiles?\b|\bbarrage\b|missile city"),
    ("AIR DEFENSE", r"air defen[cs]e|\bintercept\w*|iron dome|david'?s sling|arrow (2|3|system|interceptor)|\bthaad\b|\bpatriot (system|battery|batteries|missile)|s-300|s-400|\bsirens?\b|anti-aircraft|shot down|shoots? down"),
    ("NAVAL", r"warships?|\bdestroyers?\b|\bfrigates?\b|aircraft carriers?|carrier strike|\buss\b|\bnavy\b|\bnaval\b|submarines?|\bfleet\b|\b(ship|tanker|vessel)s?\b.{0,40}\b(seiz|attack|board|hit|struck|target)\w*|\b(seiz|attack|board|hit|struck|target)\w*\b.{0,40}\b(ship|tanker|vessel)s?\b|\bsea mines?\b|\bblockade\b"),
    ("AIRCRAFT", r"fighter jets?|warplanes?|\bf-\d{2}\w*|\bb-(52|1|2)\w*|\bbombers?\b|military aircraft|air force|\bsorties?\b|refuel(l)?ing (planes?|tankers?|aircraft)|\bawacs\b|\bp-8\b|\bjets? (scrambled|deployed|arrive)"),
    ("TROOPS", r"\btroops?\b|\breservists?\b|\bdeploy\w*|\breinforce\w*|ground (operation|offensive|invasion|forces|incursion)|\bincursion\b|\boffensive\b|\btanks\b|\bbrigades?\b|\bmobiliz\w*|build-?up|\bmarines\b|\bartillery\b|military (moves?|movements?|exercises?|drills?|command)|naval (drills?|exercises?)|live-fire|war ?games|forces? (enter|advance|move|withdraw)\w*"),
]
EXCLUDE = (r"\b(podcast|quiz|recipe|crossword|horoscope|football|soccer|basketball|tennis|euroleague|uefa|fifa|"
           r"eurovision|celebrity|box office|word of the day|newsletter|in pictures|photos of the day|"
           r"shares?|stocks?|equities|ipo|profit|revenue|earnings|tourism|tourists?|hotel|resort|property|"
           r"real estate|fitness|festival|concert|museum|gta|release date|preload|golf|race to dubai|"
           r"formula 1|f1|grand prix|fashion|memoir|padel|ufc|mma|wrestl\w*|art foundation|loyalty|data breach|launches new|cop31|dh\d[\d.,]*\w*|aed)\b")
OPINION = r"^(opinion|op-ed|editorial|letters?|commentary)\b|/(opinion|opinions|op-ed|blogs|letters)/"
DATELINE = r"^(By [A-Z][\w.'-]*( [A-Z][\w.'-]*){0,3} )?[A-Z][A-Z .'-]{1,40}(, [A-Z][A-Za-z .'-]{1,30})?, [A-Z][a-z]{2,8}\.? \d{1,2} \((Reuters|AP|AFP)\) [-\u2013\u2014] "


def _txt(s):
    s = html.unescape(re.sub(r"<[^>]+>", " ", s or ""))
    return re.sub(r"\s+", " ", s).strip()


def _norm(t):
    t = re.sub(r"[\u2018\u2019\u201c\u201d'\"]", "", (t or "").lower())
    return re.sub(r"[^a-z0-9 ]+", " ", t).split()


def _split_src(title, src):
    if src and title.endswith(" - " + src):
        return title[: -len(src) - 3], src
    m = re.match(r"^(.*) - ([^-]{2,60})$", title)
    if m:
        return m.group(1), m.group(2)
    return title, src


def parse(raw, default_source, from_google):
    out = []
    root = ET.fromstring(raw)
    for it in root.iter("item"):
        title = _txt(it.findtext("title"))
        link = (it.findtext("link") or "").strip()
        src_el = it.find("source")
        src = _txt(src_el.text) if src_el is not None and src_el.text else default_source
        if from_google:
            title, src = _split_src(title, src)
        desc = "" if from_google else _txt(it.findtext("description"))
        pub = it.findtext("pubDate") or it.findtext("{http://purl.org/dc/elements/1.1/}date")
        ts = None
        try:
            dt = parsedate_to_datetime(pub) if pub else None
            if dt is not None:
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                ts = int(dt.timestamp())
        except Exception:
            ts = None
        if title and link.startswith("http"):
            out.append({"title": title, "link": link, "src": src or "", "desc": desc, "ts": ts, "g": from_google})
    return out


def snippet(desc, title):
    d = re.sub(DATELINE, "", (desc or "").strip())
    d = re.sub(r"\s*(The post .{0,200} appeared first on .{0,80}$|Continue reading\.*.*$|Read more\.*$|\[\u2026\]|\[\.\.\.\])", "", d).strip()
    if not d or len(d) < 25:
        return ""
    if set(_norm(d)) <= set(_norm(title)) | {"the", "a", "of"}:
        return ""
    if len(d) > 230:
        d = d[:230].rsplit(" ", 1)[0].rstrip(",;:-") + "\u2026"
    return d


def tag_story(title, desc, home):
    head = title.lower()
    body = (title + " " + re.sub(DATELINE, "", desc or "")[:300]).lower()
    tags = [k for k, rx in TAGS if re.search(rx, head)]
    mil = [lab for lab, rx in MIL if re.search(rx, head)]
    if not tags and (home or mil):  # nothing in the headline: look at the story's first lines
        tags = [k for k, rx in TAGS if re.search(rx, body)]
    regional = bool(tags) or bool(re.search(REGION_ANY, head))
    if not regional and home:
        tags, regional = [home], True
    return tags, regional, mil


def _fetch(job, http_get):
    name, url, home, google = job
    try:
        return job, parse(http_get(url, timeout=15), name, google), None
    except Exception as e:  # one bad feed never stops the desk
        return job, [], type(e).__name__


def pull(http_get):
    jobs = [(n, u, h, False) for n, u, h in DIRECT]
    jobs += [("", "https://news.google.com/rss/search?" + urllib.parse.urlencode(
        {"q": q + " when:1d", "hl": "en-US", "gl": "US", "ceid": "US:en"}), None, True) for q in GNEWS]
    items, ok, bad = [], 0, 0
    with ThreadPoolExecutor(max_workers=8) as ex:
        for job, got, err in ex.map(lambda j: _fetch(j, http_get), jobs):
            if err:
                bad += 1
                continue
            ok += 1
            for g in got:
                g["home"] = job[2]
            items += got
    return items, ok, bad


def _sid(title):
    return hashlib.sha1(" ".join(_norm(title))[:90].encode()).hexdigest()[:10]


def _same(a, b):
    wa, wb = set(_norm(a)), set(_norm(b))
    if not wa or not wb:
        return False
    return len(wa & wb) / len(wa | wb) >= 0.75


def build(items, old, now_ts, trusted):
    fresh = []
    for it in items:
        t, d = it["title"], it["desc"]
        if len(t) < 20 or re.search(EXCLUDE, t.lower()) or re.search(OPINION, t.lower()) or re.search(OPINION, it["link"].lower()):
            continue
        if it["g"] and not trusted(it["src"]) and not re.search(r"iran international|al-monitor|i24", it["src"].lower()):
            continue
        tags, regional, mil = tag_story(t, d, it["home"])
        if not regional:
            continue
        ts = it["ts"] or now_ts
        if ts > now_ts + 300:
            ts = now_ts
        if now_ts - ts > KEEP_HOURS * 3600:
            continue
        fresh.append({"id": _sid(t), "t": ts, "src": it["src"] or "News", "title": t, "link": it["link"],
                      "snip": snippet(d, t), "tags": tags, "mil": mil, "g": 1 if it["g"] else 0})
    # direct outlet copies first (real link + snippet), then the Google News copies
    fresh.sort(key=lambda s: (s["g"], -s["t"]))
    keep = []
    for s in fresh + [dict(o, g=o.get("g", 0)) for o in old if now_ts - o.get("t", 0) <= KEEP_HOURS * 3600]:
        dup = next((k for k in keep if k["id"] == s["id"] or _same(k["title"], s["title"])), None)
        if dup is None:
            s.setdefault("seen", now_ts)
            keep.append(s)
        else:
            dup["seen"] = min(dup.get("seen", now_ts), s.get("seen", now_ts))
            dup["t"] = min(dup["t"], s["t"])
            if not dup.get("snip") and s.get("snip"):
                dup["snip"] = s["snip"]
            for k in s.get("tags", []):
                if k not in dup["tags"]:
                    dup["tags"].append(k)
    keep.sort(key=lambda s: -s["t"])
    return keep[:KEEP_MAX]


def run(http_get, load_json, save_json, now_ts, central_time, trusted):
    t0 = time.time()
    items, ok, bad = pull(http_get)
    old = load_json("mideast.json", {}).get("stories", [])
    stories = build(items, old, now_ts, trusted) if ok else old
    counts = {k: sum(1 for s in stories if k in s["tags"]) for k, _ in TAGS}
    counts["mil"] = sum(1 for s in stories if s["mil"])
    out = {"updated": now_ts, "updated_ct": central_time(now_ts), "keep_hours": KEEP_HOURS,
           "feeds_ok": ok, "feeds_bad": bad, "count": len(stories), "counts": counts, "stories": stories}
    save_json("mideast.json", out)
    secs = time.time() - t0
    print(f"mideast news: {len(stories)} stories ({counts['mil']} military) from {ok} feeds, {bad} failed, {secs:.1f}s")
    return {"ok": ok > 0, "note": f"{len(stories)} stories \u00B7 {ok} sources working" + (f", {bad} down" if bad else "")}
