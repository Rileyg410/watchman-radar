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

## Keep it running
GitHub pauses scheduled workflows in a public repo after 60 days with no repository activity.
If that ever happens, open the **Actions** tab and press **Enable workflow**.

## Run a sweep by hand
Actions tab -> WATCHTOWER sweep -> Run workflow (tick "Send a test push" to test the phone alert).
