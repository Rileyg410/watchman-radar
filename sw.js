// Watchman Radar: lets Riley add the radar to his home screen.
// Always fetches the radar's own page and files fresh from GitHub (no stale copies on his phone).
const SW_BUILD = '2026-10-26e';
self.addEventListener('install', () => self.skipWaiting());
self.addEventListener('activate', e => e.waitUntil((async () => {
  await self.clients.claim();
  // a new radar version just arrived: reload any radar screen that is still showing the old one
  const wins = await self.clients.matchAll({type: 'window'});
  wins.forEach(c => { try { c.navigate(c.url); } catch (err) { /* ignore */ } });
})()));
self.addEventListener('fetch', e => {
  const req = e.request;
  if (req.method !== 'GET') return;
  const url = new URL(req.url);
  if (url.origin !== self.location.origin) return; // map tiles, data feeds, fonts: browser handles them
  if (req.mode === 'navigate') {
    e.respondWith((async () => {
      try {
        const res = await fetch(req.url, {cache: 'no-cache', credentials: 'same-origin'});
        return res.redirected ? Response.redirect(res.url, 302) : res;
      } catch (err) { return fetch(req); }
    })());
    return;
  }
  e.respondWith(fetch(req, {cache: 'no-cache'}).catch(() => fetch(req)));
});
