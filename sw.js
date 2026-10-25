// Watchman Radar: lets Riley add the radar to his home screen. Always fetches fresh.
self.addEventListener('install', e => self.skipWaiting());
self.addEventListener('activate', e => self.clients.claim());
self.addEventListener('fetch', () => {});
