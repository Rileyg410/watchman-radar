# WATCHMAN RADAR

Riley's command center: a live radar of military aircraft and world events, with its own
background watcher (WATCHTOWER) that pushes alerts to his phone through ntfy.

- **Dashboard:** GitHub Pages, from this repo's `main` branch.
- **Watcher:** `.github/workflows/watchtower.yml` runs `watcher/watch.py` about every 10 minutes
  on GitHub's servers. Free for public repos. Nothing else needs to be running.
- **Data:** each sweep writes `live.json`, `alerts.json`, `config.json` and `state.json` to the `data` branch.
- **Alerts:** pushed to the ntfy topic stored in the repo secret `NTFY_TOPIC`.
- **Controls:** the COMMAND panel on the dashboard sends Riley's settings over a private ntfy
  command channel; WATCHTOWER applies them on its next sweep.

Sources: adsb.lol (military ADS-B feed) and headlines from trusted outlets (Google News search
feeds filtered to major outlets, plus BBC, USNI News, Defense News, The War Zone, Times of Israel,
Kyiv Independent, Fox News, Al Jazeera, The Guardian, Breaking Defense, Military Times, Naval News,
UK Defence Journal, Jerusalem Post).

Tiers: FLASH (urgent push), IMMEDIATE (high push), ROUTINE (logged; optional quiet push).

## MIDEAST NEWS tab
A live Iran / Israel / Middle East news desk (bottom-bar MIDEAST tab on the phone, MIDEAST button on
the desktop header). Every sweep, `watcher/mideast.py` reads free RSS feeds (Times of Israel, Jerusalem
Post, Iran International, Al Jazeera, Al-Monitor, BBC, The Guardian, The War Zone, JNS, Ynet, Long War
Journal, The National, plus Reuters, AP, i24NEWS and topic searches through Google News), tags each
story by place (Iran, Israel, Lebanon/Hezbollah, Syria, Yemen/Houthis, Gulf), flags military and
movement headlines, removes repeats and writes the last 48 hours (up to 120 stories) to `mideast.json`
on the `data` branch. It sends no pushes; a red dot on the tab means new military stories.

## Pushing a new version
Bump the build string in `version.json`, in the small script at the top of `index.html` and in `sw.js`
(all three the same). Open radars see the new build within 5 minutes (or the moment the app is reopened)
and reload onto it by themselves.

## Keep it running
GitHub pauses scheduled workflows in a public repo after 60 days with no repository activity.
If that ever happens, open the **Actions** tab and press **Enable workflow**.

## Run a sweep by hand
Actions tab -> WATCHTOWER sweep -> Run workflow (tick "Send a test push" to test the phone alert).
