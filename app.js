/* WATCHMAN RADAR // Riley's command center */
(() => {
'use strict';

// ---------------------------------------------------------------- setup
const TOPIC_HASH = 'f19ce2db454c167d228ebb49b7a15d8639a244af8ed7c447accc8ee61ae5c08f';
const NTFY = 'https://ntfy.sh';
const HOME = [35.6145, -88.8139]; // home base (Jackson, TN)
const REFRESH_MS = 60 * 1000;

function dataBase() {
  const h = location.hostname;
  if (h.endsWith('.github.io')) {
    const owner = h.split('.')[0];
    const repo = location.pathname.split('/').filter(Boolean)[0] || (owner + '.github.io');
    return `https://raw.githubusercontent.com/${owner}/${repo}/data/`;
  }
  return 'data/';
}
const DATA = dataBase();

const CATS = {
  tanker:  {n: 'TANKERS',  c: '#ffb000'},
  bomber:  {n: 'BOMBERS',  c: '#ff3b3b'},
  airlift: {n: 'AIRLIFT',  c: '#38bdf8'},
  tactical:{n: 'C-130s',   c: '#7dd3fc'},
  isr:     {n: 'SPY/ISR',  c: '#c084fc'},
  c2:      {n: 'NUKE C2',  c: '#ff4fd8'},
  fighter: {n: 'FIGHTERS', c: '#a3ff3b'},
  other:   {n: 'OTHER',    c: '#3fbf86'},
};
const WATCHES = [
  ['nuclear', 'Nuclear drills'], ['missiles', 'Missile tests'], ['bombers', 'Bombers'],
  ['warships', 'Warships near US/Cuba'], ['foreign_mil', 'Foreign jets near US/EU'], ['subs', 'Sub Watch'],
  ['tankers', 'Tanker surges'], ['airlift', 'Airlift surges'], ['buildups', 'Troop buildups'],
  ['ukraine', 'Ukraine pushes'], ['russia', 'Russia moves'], ['hormuz', 'Hormuz watch'],
  ['isr', 'Spy planes'], ['breaking', 'Major breaking news'],
];
const REGIONS = {
  alaska: ['Alaska / Bering', [[51, -180], [72, -129]]],
  conus: ['Continental US', [[24, -126], [50, -65]]],
  cuba: ['Cuba / Caribbean', [[17, -88], [27, -72]]],
  hawaii: ['Hawaii', [[17, -163], [25, -152]]],
  europe: ['Europe / N. Atlantic', [[35, -25], [72, 45]]],
  baltic: ['Baltic / Nordic', [[53.5, 9], [71, 32]]],
  ukraine: ['Ukraine / Black Sea', [[40.5, 22], [53, 42]]],
  easternmed: ['E. Med / Israel', [[29, 24], [37.5, 38]]],
  gulf: ['Gulf / Hormuz', [[12, 38], [31, 63]]],
  pacific: ['W. Pacific / Taiwan', [[10, 115], [46, 150]]],
};
const DEFAULTS = {
  watches: Object.fromEntries(WATCHES.map(w => [w[0], true])),
  regions: Object.fromEntries(Object.keys(REGIONS).map(r => [r, true])),
  push: {FLASH: true, IMMEDIATE: true, ROUTINE: false},
  quiet: {enabled: false, start: '22:00', end: '06:00', flash_breaks: true},
  sensitivity: 'normal',
  paused: false,
};
const ICON = {FLASH: '\u{1F7E5}', IMMEDIATE: '\u{1F7E7}', ROUTINE: '\u{1F7E6}'};

const $ = s => document.querySelector(s);
const esc = s => String(s == null ? '' : s).replace(/[&<>"']/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[c]));
const clone = o => JSON.parse(JSON.stringify(o));
function toast(t) { const el = $('#toast'); el.textContent = t; el.classList.add('on'); clearTimeout(toast._t); toast._t = setTimeout(() => el.classList.remove('on'), 3200); }

let live = null, alerts = [], applied = null;
let catOn = new Set(Object.keys(CATS));
let tierOn = 'ALL';
let settings = clone(DEFAULTS);
let seenIds = new Set(JSON.parse(localStorage.getItem('wr_seen') || '[]'));

// ---------------------------------------------------------------- clocks
function tick() {
  const d = new Date();
  $('#clockCT').textContent = d.toLocaleTimeString('en-US', {timeZone: 'America/Chicago', hour12: false});
  $('#clockZ').textContent = d.toISOString().substr(11, 8) + 'Z';
  if (live) {
    const age = Math.max(0, Math.round(Date.now() / 1000 - live.updated));
    const m = Math.floor(age / 60);
    $('#sweepAge').textContent = m < 1 ? 'JUST NOW' : (m < 60 ? m + ' MIN AGO' : Math.floor(m / 60) + 'H ' + (m % 60) + 'M AGO');
    const box = $('#sweepbox');
    box.classList.toggle('stale', age > 30 * 60 && age <= 120 * 60);
    box.classList.toggle('dead', age > 120 * 60);
    $('#sysline').textContent = age > 120 * 60 ? 'WATCHTOWER SILENT - CHECK BACKEND' : 'WATCHTOWER ONLINE \u00B7 SWEEP #' + (live.sweeps || 1);
  }
}
setInterval(tick, 1000); tick();

// ---------------------------------------------------------------- scope (PPI)
const cv = $('#scope'), cx = cv.getContext('2d');
let ang = 0, blips = [];
function sizeScope() { const r = cv.getBoundingClientRect(); const dpr = window.devicePixelRatio || 1; cv.width = r.width * dpr; cv.height = r.width * dpr; }
window.addEventListener('resize', sizeScope);
function project(lat, lon) {
  // azimuthal equidistant around home base: whole planet fits in the disc
  const R = Math.PI / 180, p1 = HOME[0] * R, l1 = HOME[1] * R, p2 = lat * R, l2 = lon * R;
  const c = Math.acos(Math.min(1, Math.max(-1, Math.sin(p1) * Math.sin(p2) + Math.cos(p1) * Math.cos(p2) * Math.cos(l2 - l1))));
  const az = Math.atan2(Math.sin(l2 - l1) * Math.cos(p2), Math.cos(p1) * Math.sin(p2) - Math.sin(p1) * Math.cos(p2) * Math.cos(l2 - l1));
  const rr = Math.pow(c / Math.PI, 0.6); // compress far away
  return {x: Math.sin(az) * rr, y: -Math.cos(az) * rr, az: (az + 2 * Math.PI) % (2 * Math.PI)};
}
function setBlips() {
  blips = (live ? live.planes : []).map(p => Object.assign(project(p.lat, p.lon), {cat: p.cat, f: p.nat && p.nat !== 'US', glow: 0}));
}
function drawScope() {
  const W = cv.width, H = cv.height, r = W / 2 - 4, c = W / 2;
  if (!W) { requestAnimationFrame(drawScope); return; }
  cx.fillStyle = 'rgba(1,10,5,0.28)';
  cx.beginPath(); cx.arc(c, c, r, 0, 2 * Math.PI); cx.fill();
  cx.strokeStyle = 'rgba(57,255,143,0.35)'; cx.lineWidth = 1;
  for (let i = 1; i <= 4; i++) { cx.beginPath(); cx.arc(c, c, r * i / 4, 0, 2 * Math.PI); cx.stroke(); }
  cx.beginPath(); cx.moveTo(c - r, c); cx.lineTo(c + r, c); cx.moveTo(c, c - r); cx.lineTo(c, c + r); cx.stroke();
  cx.save(); cx.strokeStyle = 'rgba(57,255,143,0.15)';
  for (let a = 0; a < 360; a += 30) { const t = a * Math.PI / 180; cx.beginPath(); cx.moveTo(c + Math.sin(t) * r * .92, c - Math.cos(t) * r * .92); cx.lineTo(c + Math.sin(t) * r, c - Math.cos(t) * r); cx.stroke(); }
  cx.restore();
  // sweep wedge
  const g = cx.createConicGradient ? cx.createConicGradient(ang - Math.PI / 2 - 0.9, c, c) : null;
  if (g) {
    g.addColorStop(0, 'rgba(57,255,143,0)'); g.addColorStop(0.14, 'rgba(57,255,143,0.35)'); g.addColorStop(0.1433, 'rgba(57,255,143,0)'); g.addColorStop(1, 'rgba(57,255,143,0)');
    cx.fillStyle = g; cx.beginPath(); cx.moveTo(c, c); cx.arc(c, c, r, ang - Math.PI / 2 - 0.9, ang - Math.PI / 2); cx.closePath(); cx.fill();
  }
  cx.strokeStyle = 'rgba(120,255,180,0.9)'; cx.lineWidth = 2; cx.beginPath(); cx.moveTo(c, c); cx.lineTo(c + Math.sin(ang) * r, c - Math.cos(ang) * r); cx.stroke();
  for (const b of blips) {
    let d = ang - b.az; d = ((d % (2 * Math.PI)) + 2 * Math.PI) % (2 * Math.PI);
    if (d < 0.06) b.glow = 1;
    b.glow *= 0.985;
    if (b.glow < 0.04 && !b.f) continue;
    const col = CATS[b.cat] ? CATS[b.cat].c : '#3fbf86';
    cx.globalAlpha = Math.max(b.f ? 0.5 : 0, b.glow);
    cx.fillStyle = b.f ? '#ff3b3b' : col;
    cx.shadowColor = cx.fillStyle; cx.shadowBlur = 8;
    cx.beginPath(); cx.arc(c + b.x * r, c + b.y * r, (b.cat === 'bomber' || b.cat === 'tanker' || b.f) ? 3.5 : 2.2, 0, 2 * Math.PI); cx.fill();
    cx.shadowBlur = 0; cx.globalAlpha = 1;
  }
  cx.fillStyle = '#39ff8f'; cx.beginPath(); cx.arc(c, c, 3, 0, 2 * Math.PI); cx.fill();
  ang = (ang + 0.018) % (2 * Math.PI);
  requestAnimationFrame(drawScope);
}

// ---------------------------------------------------------------- map
const map = L.map('map', {zoomControl: true, worldCopyJump: true, attributionControl: true, minZoom: 2}).setView([38, -30], 3);
L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png', {
  subdomains: 'abcd', maxZoom: 12, attribution: '&copy; OpenStreetMap &copy; CARTO | ADS-B: adsb.lol'
}).addTo(map);
const regionLayer = L.layerGroup().addTo(map), acLayer = L.layerGroup().addTo(map), alertLayer = L.layerGroup().addTo(map);
for (const [k, v] of Object.entries(REGIONS)) {
  L.rectangle(v[1], {color: '#39ff8f', weight: 1, opacity: .35, dashArray: '4 6', fill: true, fillOpacity: .02, interactive: false}).addTo(regionLayer);
}
L.circleMarker(HOME, {radius: 5, color: '#39ff8f', fillColor: '#39ff8f', fillOpacity: 1}).bindPopup('<b>HOME BASE</b>').addTo(map);
function planeSvg(col, big) {
  const s = big ? 26 : 18;
  return `<svg width="${s}" height="${s}" viewBox="0 0 24 24" style="color:${col}"><path fill="${col}" d="M12 2c.6 0 1 .5 1 1.2V9l8 4.6v2l-8-2.3v4.9l2.4 1.7V21L12 20l-3.4 1v-1.1L11 18.2v-4.9L3 15.6v-2L11 9V3.2C11 2.5 11.4 2 12 2z"/></svg>`;
}
function drawPlanes() {
  acLayer.clearLayers();
  if (!live) return;
  let shown = 0;
  for (const p of live.planes) {
    if (!catOn.has(p.cat)) continue;
    shown++;
    const col = (CATS[p.cat] || CATS.other).c, big = ['bomber', 'tanker', 'c2'].includes(p.cat), f = p.nat && p.nat !== 'US';
    const s = big ? 26 : 18;
    const icon = L.divIcon({className: 'ac' + (f ? ' foreign' : ''), iconSize: [s, s], iconAnchor: [s / 2, s / 2],
      html: `<div style="transform:rotate(${p.trk || 0}deg)">${planeSvg(f ? '#ff3b3b' : col, big)}</div>`});
    const nm = (window.TYPE_NAMES && TYPE_NAMES[p.t]) || p.t || '?';
    L.marker([p.lat, p.lon], {icon}).bindPopup(
      `<b>${esc(p.cs || p.reg || p.hex)}</b> &middot; ${esc(nm)}<br>${esc((CATS[p.cat] || CATS.other).n)}${f ? ' &middot; <span style="color:#ff3b3b">FOREIGN (' + esc(p.nat) + ')</span>' : ''}<br>` +
      `ALT ${p.alt != null ? esc(p.alt.toLocaleString()) + ' ft' : '--'} &middot; GS ${p.gs != null ? esc(p.gs) + ' kt' : '--'} &middot; HDG ${p.trk != null ? esc(p.trk) : '--'}<br>` +
      `${esc(REGIONS[p.rg] ? REGIONS[p.rg][0] : 'Open ocean / other')}${p.sq ? ' &middot; SQK ' + esc(p.sq) : ''}<br>` +
      `<a href="https://globe.adsb.lol/?icao=${esc(String(p.hex).replace('~', ''))}" target="_blank" rel="noopener" style="color:#3ba7ff">Track on adsb.lol &rarr;</a>`
    ).addTo(acLayer);
  }
  $('#mapcount').textContent = `// ${shown} OF ${live.planes.length} MIL AIRCRAFT`;
}
function drawAlertPings() {
  alertLayer.clearLayers();
  const cutoff = Date.now() / 1000 - 6 * 3600;
  for (const a of alerts) {
    if (a.ts < cutoff || a.lat == null) continue;
    const col = a.tier === 'FLASH' ? '#ff3b3b' : a.tier === 'IMMEDIATE' ? '#ffa31a' : '#3ba7ff';
    const icon = L.divIcon({className: '', iconSize: [44, 44], iconAnchor: [22, 22], html: `<div class="ping" style="width:44px;height:44px;border-color:${col}"></div>`});
    L.marker([a.lat, a.lon], {icon, interactive: false}).addTo(alertLayer);
  }
}
window.TYPE_NAMES = {K35R: 'KC-135R', K35E: 'KC-135E', K46: 'KC-46A', KC46: 'KC-46A', B52: 'B-52', B1: 'B-1B', B2: 'B-2', C17: 'C-17', C5M: 'C-5M', C5: 'C-5', C130: 'C-130', C30J: 'C-130J', R135: 'RC-135', E3TF: 'E-3 AWACS', E3CF: 'E-3 AWACS', P8: 'P-8 Poseidon', E6: 'E-6B Mercury', E4B: 'E-4B', RQ4: 'RQ-4', Q4: 'RQ-4', GLHK: 'RQ-4', MQ9: 'MQ-9', A400: 'A400M', F35: 'F-35', F16: 'F-16', F15: 'F-15', F18S: 'F/A-18', F22: 'F-22', EUFI: 'Typhoon', H60: 'Black Hawk', H47: 'Chinook', V22: 'V-22 Osprey'};

// ---------------------------------------------------------------- chips
function buildChips() {
  const cc = $('#catchips'); cc.innerHTML = '';
  for (const [k, v] of Object.entries(CATS)) {
    const b = document.createElement('button');
    b.className = 'chip' + (catOn.has(k) ? ' on' : '');
    b.innerHTML = `<i style="background:${v.c}"></i>${v.n}`;
    b.onclick = () => { catOn.has(k) ? catOn.delete(k) : catOn.add(k); buildChips(); drawPlanes(); };
    cc.appendChild(b);
  }
  const tc = $('#tierchips'); tc.innerHTML = '';
  for (const [k, cls] of [['ALL', ''], ['FLASH', 'fl'], ['IMMEDIATE', 'im'], ['ROUTINE', 'ro']]) {
    const b = document.createElement('button');
    b.className = 'chip ' + cls + (tierOn === k ? ' on' : '');
    b.textContent = (ICON[k] ? ICON[k] + ' ' : '') + k;
    b.onclick = () => { tierOn = k; buildChips(); drawFeed(); };
    tc.appendChild(b);
  }
}

// ---------------------------------------------------------------- panels
function ago(ts) {
  const s = Math.max(0, Date.now() / 1000 - ts);
  if (s < 90) return 'just now';
  if (s < 3600) return Math.round(s / 60) + 'm ago';
  if (s < 86400) return Math.round(s / 3600) + 'h ago';
  return Math.round(s / 86400) + 'd ago';
}
function drawStats() {
  const st = live ? live.stats : {};
  const tot = live ? live.planes.length : 0;
  const tiles = [['MIL AIRCRAFT', tot, ''], ['TANKERS', st.tanker || 0, ''], ['BOMBERS', st.bomber || 0, (st.bomber || 0) > 0 ? 'red' : ''],
    ['AIRLIFT', st.airlift || 0, ''], ['SPY / ISR', st.isr || 0, ''], ['NUKE C2', st.c2 || 0, (st.c2 || 0) > 0 ? 'hot' : '']];
  $('#stats').innerHTML = tiles.map(t => `<div class="stat ${t[2]}"><label>${t[0]}</label><b>${t[1]}</b></div>`).join('');
  const foreign = live ? live.planes.filter(p => p.nat && p.nat !== 'US').length : 0;
  $('#scopeinfo').innerHTML = `${tot} CONTACTS<br>${foreign ? '<span style="color:#ff3b3b">' + foreign + ' FOREIGN</span>' : 'NO FOREIGN MIL ON ADS-B'}`;
}
function regionLamp(r) {
  const day = Date.now() / 1000 - 24 * 3600;
  const rs = alerts.filter(a => a.region === r && a.ts > day);
  if (rs.some(a => a.tier === 'FLASH')) return 'r';
  if (rs.some(a => a.tier === 'IMMEDIATE')) return 'a';
  return 'g';
}
function drawBoard() {
  const bd = live ? live.board || {} : {};
  $('#board').innerHTML = Object.entries(REGIONS).map(([k, v]) => {
    const b = bd[k] || {};
    const off = settings.regions && settings.regions[k] === false;
    const t = b.tanker || 0, a = b.airlift || 0;
    const tUp = b.base_tanker != null && t >= Math.max(2, b.base_tanker * 2);
    const aUp = b.base_airlift != null && a >= Math.max(2, b.base_airlift * 2);
    return `<div class="brow ${off ? 'off' : ''}" data-r="${k}"><span class="lamp ${off ? 'off' : regionLamp(k)}"></span><span class="nm">${v[0]}</span>` +
      `<span class="ct">\u2708 <b>${b.total || 0}</b> T<b class="${tUp ? 'up' : ''}">${t}</b> A<b class="${aUp ? 'up' : ''}">${a}</b> B<b class="${(b.bomber || 0) ? 'up' : ''}">${b.bomber || 0}</b></span></div>`;
  }).join('');
  document.querySelectorAll('.brow').forEach(el => el.onclick = () => {
    const r = REGIONS[el.dataset.r]; map.fitBounds(r[1]); showTab('map');
  });
  const s = live ? live.sources || {} : {};
  $('#srcs').innerHTML = Object.entries(s).map(([k, v]) => `<div><span class="${v.ok ? 'ok' : 'bad'}">\u25CF</span> ${k.toUpperCase()}: ${esc(v.note)}</div>`).join('') +
    (live ? `<div>NEXT SWEEP: ~every 10 min (GitHub timer)</div>` : '');
}
function threatcon() {
  const six = Date.now() / 1000 - 6 * 3600;
  const recent = alerts.filter(a => a.ts > six && a.watch !== 'test');
  const el = $('#threatcon');
  el.classList.remove('green', 'amber', 'red');
  if (recent.some(a => a.tier === 'FLASH')) { el.classList.add('red'); el.querySelector('b').textContent = 'HIGH'; }
  else if (recent.some(a => a.tier === 'IMMEDIATE')) { el.classList.add('amber'); el.querySelector('b').textContent = 'ELEVATED'; }
  else { el.classList.add('green'); el.querySelector('b').textContent = 'NORMAL'; }
}
function drawFeed() {
  const list = alerts.filter(a => tierOn === 'ALL' || a.tier === tierOn);
  $('#feedcount').textContent = `// ${alerts.length} LOGGED`;
  if (!list.length) {
    $('#feed').innerHTML = `<div class="empty">${alerts.length ? 'Nothing in this tier yet.' : 'All quiet. WATCHTOWER is sweeping every ~10 minutes and will log anything worth knowing here.'}</div>`;
    return;
  }
  $('#feed').innerHTML = list.slice(0, 200).map(a => {
    const st = a.pushed === 'sent' ? '<span class="p">\u25B2 PUSHED</span>' : a.held ? `<span class="h">HELD: ${esc(a.held)}</span>` : '<span>LOGGED</span>';
    const links = [];
    if (a.more && a.more.length) a.more.forEach(m => links.push(`<a href="${esc(m.u)}" target="_blank" rel="noopener">\u2197 ${esc(m.t)} <small>(${esc(m.s)})</small></a>`));
    else if (a.link) links.push(`<a href="${esc(a.link)}" target="_blank" rel="noopener">\u2197 Open source report</a>`);
    const isNew = !seenIds.has(a.id);
    return `<div class="alert ${a.tier} ${isNew ? 'new' : ''}" data-id="${esc(a.id)}">` +
      `<h4>${esc(a.title || (ICON[a.tier] + ' ' + a.tier + ' // ' + a.what))}</h4>` +
      (a.headline ? `<div class="hl">${esc(a.headline)}</div>` : '') +
      `<div class="meta"><span>${ago(a.ts)}</span><span>\u{1F4CD} ${esc(a.location || '')}</span>${st}</div>` +
      `<pre>${esc(a.body || '')}</pre><div class="links">${links.join('')}</div></div>`;
  }).join('');
  document.querySelectorAll('.alert').forEach(el => el.onclick = ev => {
    if (ev.target.closest('a')) return;
    el.classList.toggle('open'); el.classList.remove('new');
    seenIds.add(el.dataset.id); localStorage.setItem('wr_seen', JSON.stringify([...seenIds].slice(-500)));
    const a = alerts.find(x => x.id === el.dataset.id);
    if (a && a.lat != null && el.classList.contains('open') && window.innerWidth > 900) map.flyTo([a.lat, a.lon], 5, {duration: 1});
    badge();
  });
  badge();
}
function badge() {
  const n = alerts.filter(a => !seenIds.has(a.id) && a.tier !== 'ROUTINE').length;
  const b = $('#feedBadge'); b.textContent = n; b.classList.toggle('on', n > 0);
}

// ---------------------------------------------------------------- data
async function getJSON(name) {
  const r = await fetch(DATA + name + '?t=' + Math.floor(Date.now() / 30000), {cache: 'no-store'});
  if (!r.ok) throw new Error(name + ' ' + r.status);
  return r.json();
}
async function refresh() {
  try {
    const [l, a, c] = await Promise.all([getJSON('live.json'), getJSON('alerts.json').catch(() => ({alerts: []})), getJSON('config.json').catch(() => null)]);
    const firstLoad = !live;
    live = l; alerts = (a.alerts || []).filter(x => x && x.tier);
    if (c && c.settings) { applied = c; if (!dirty && !pendingSince) loadSettings(c.settings); }
    if (firstLoad && !seenIds.size) { alerts.forEach(x => seenIds.add(x.id)); localStorage.setItem('wr_seen', JSON.stringify([...seenIds].slice(-500))); }
    setBlips(); drawStats(); drawBoard(); drawPlanes(); drawAlertPings(); drawFeed(); threatcon(); tick();
    checkApplied();
  } catch (e) {
    $('#sysline').textContent = 'NO DATA YET - FIRST SWEEP PENDING';
    console.warn(e);
  }
}

// ---------------------------------------------------------------- command center
let topic = localStorage.getItem('wr_topic') || '';
let dirty = false, pendingSince = Number(localStorage.getItem('wr_pending') || 0);
async function sha256(s) {
  const b = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(s));
  return [...new Uint8Array(b)].map(x => x.toString(16).padStart(2, '0')).join('');
}
async function ctlTopic() { return topic + '-cmd-' + (await sha256(topic + '|watchtower')).slice(0, 8); }

function get(o, path) { return path.split('.').reduce((x, k) => x == null ? x : x[k], o); }
function set(o, path, v) { const ks = path.split('.'); let x = o; ks.slice(0, -1).forEach(k => { x[k] = x[k] || {}; x = x[k]; }); x[ks[ks.length - 1]] = v; }

function buildToggles() {
  $('#watchGrid').innerHTML = WATCHES.map(([k, n]) => `<button class="tbtn" data-k="watches.${k}">${n}</button>`).join('');
  $('#regionGrid').innerHTML = Object.entries(REGIONS).map(([k, v]) => `<button class="tbtn" data-k="regions.${k}">${v[0]}</button>`).join('');
  document.querySelectorAll('.tbtn').forEach(b => b.onclick = () => { set(settings, b.dataset.k, !get(settings, b.dataset.k)); markDirty(); paint(); });
  document.querySelectorAll('#controls input[data-k]').forEach(inp => inp.onchange = () => {
    set(settings, inp.dataset.k, inp.type === 'checkbox' ? inp.checked : inp.value); markDirty(); paint();
  });
  $('#masterOn').onchange = e => { settings.paused = !e.target.checked; markDirty(); paint(); };
  document.querySelectorAll('#sensSeg button').forEach(b => b.onclick = () => { settings.sensitivity = b.dataset.v; markDirty(); paint(); });
  document.querySelectorAll('#testSeg button').forEach(b => b.onclick = () => { document.querySelectorAll('#testSeg button').forEach(x => x.classList.toggle('on', x === b)); });
}
function paint() {
  document.querySelectorAll('.tbtn').forEach(b => b.classList.toggle('on', !!get(settings, b.dataset.k)));
  document.querySelectorAll('#controls input[data-k]').forEach(inp => {
    const v = get(settings, inp.dataset.k);
    if (inp.type === 'checkbox') inp.checked = !!v; else inp.value = v || '';
  });
  $('#masterOn').checked = !settings.paused;
  $('#masterHint').textContent = settings.paused ? 'PAUSED: WATCHTOWER keeps watching and logging, but sends nothing to your phone.' : 'ON: WATCHTOWER pushes the tiers you pick below straight to your phone.';
  document.querySelectorAll('#sensSeg button').forEach(b => b.classList.toggle('on', b.dataset.v === settings.sensitivity));
  drawBoard();
}
function loadSettings(s) {
  settings = clone(DEFAULTS);
  for (const k of Object.keys(DEFAULTS)) {
    if (s[k] === undefined) continue;
    if (typeof DEFAULTS[k] === 'object') Object.assign(settings[k], s[k]); else settings[k] = s[k];
  }
  paint();
}
function markDirty() { dirty = true; $('#saveMsg').textContent = 'Changes not sent yet. Hit TRANSMIT to make them live.'; $('#saveMsg').classList.remove('err'); }
function checkApplied() {
  if (!pendingSince) return;
  if (applied && applied.set_at >= pendingSince) {
    pendingSince = 0; localStorage.removeItem('wr_pending');
    $('#saveMsg').textContent = '\u2714 WATCHTOWER CONFIRMED YOUR ORDERS (' + new Date(applied.applied * 1000).toLocaleTimeString('en-US', {timeZone: 'America/Chicago', hour: 'numeric', minute: '2-digit'}) + ' CT).';
    toast('WATCHTOWER confirmed your orders');
  } else {
    $('#saveMsg').textContent = 'Orders transmitted. WATCHTOWER locks them in on its next sweep (within ~10 min).';
  }
}
async function pullPending() {
  // show Riley's latest transmitted orders even before the next sweep applies them
  try {
    const r = await fetch(`${NTFY}/${await ctlTopic()}/json?poll=1&since=all`);
    const lines = (await r.text()).trim().split('\n').filter(Boolean);
    let newest = null;
    for (const ln of lines) { try { const m = JSON.parse(ln); const b = JSON.parse(m.message); if (b.type === 'settings' && (!newest || m.time >= newest.time)) newest = {time: m.time, s: b.settings}; } catch (e) {} }
    if (newest && (!applied || newest.time > (applied.set_at || 0))) { loadSettings(newest.s); pendingSince = newest.time; checkApplied(); }
  } catch (e) {}
}
async function unlock(t, quiet) {
  t = (t || '').trim();
  if (!t) return false;
  const ok = (await sha256(t)) === TOPIC_HASH;
  if (!ok) { if (!quiet) { $('#lockMsg').textContent = 'That is not the topic WATCHTOWER was built for.'; $('#lockMsg').classList.add('err'); } return false; }
  topic = t; localStorage.setItem('wr_topic', t);
  $('#lockBox').style.display = 'none'; $('#controls').classList.remove('locked');
  $('#ntfyLink').href = `${NTFY}/${encodeURIComponent(t)}`;
  pullPending();
  return true;
}
$('#unlockBtn').onclick = () => unlock($('#topicIn').value);
$('#topicIn').onkeydown = e => { if (e.key === 'Enter') unlock($('#topicIn').value); };
$('#lockAgain').onclick = () => { localStorage.removeItem('wr_topic'); topic = ''; $('#lockBox').style.display = ''; $('#controls').classList.add('locked'); $('#topicIn').value = ''; toast('Locked on this device'); };

$('#saveBtn').onclick = async () => {
  if (!topic) return;
  const btn = $('#saveBtn'); btn.disabled = true;
  try {
    const r = await fetch(`${NTFY}/${await ctlTopic()}`, {method: 'POST', body: JSON.stringify({type: 'settings', settings, sent: Date.now()}), headers: {'Title': 'orders'}});
    if (!r.ok) throw new Error('ntfy ' + r.status);
    const m = await r.json();
    dirty = false; pendingSince = m.time || Math.floor(Date.now() / 1000); localStorage.setItem('wr_pending', pendingSince);
    $('#saveMsg').classList.remove('err');
    $('#saveMsg').textContent = 'Orders transmitted. WATCHTOWER locks them in on its next sweep (within ~10 min).';
    toast('Orders transmitted to WATCHTOWER');
  } catch (e) {
    $('#saveMsg').textContent = 'Could not reach WATCHTOWER. Check your signal and try again.'; $('#saveMsg').classList.add('err');
  }
  btn.disabled = false;
};

$('#testBtn').onclick = async () => {
  if (!topic) return;
  const tier = document.querySelector('#testSeg button.on').dataset.v;
  const now = new Date().toLocaleString('en-US', {timeZone: 'America/Chicago', hour: 'numeric', minute: '2-digit', weekday: 'short', month: 'short', day: 'numeric'});
  const n = live ? live.planes.length : 0;
  const body = [
    '\u{1F4CD} LOCATION: Riley\'s command center (test)',
    `\u{1F550} TIME: ${now} CT`,
    `\u{1F6E9}\uFE0F ASSETS: ${n} military aircraft on the scope right now`,
    '\u{1F6E1}\uFE0F RESPONSE: None needed. This is only a test.',
    '\u{1F4E1} SOURCE: Watchman Radar command center',
    '\u26A0\uFE0F THREAT LEVEL: NONE (TEST)',
    '\u2014 WATCHTOWER'].join('\n');
  const prio = {FLASH: 5, IMMEDIATE: 4, ROUTINE: 2}[tier];
  const btn = $('#testBtn'); btn.disabled = true;
  try {
    const r = await fetch(NTFY + '/', {method: 'POST', body: JSON.stringify({topic, title: `${ICON[tier]} ${tier} // TEST ALERT`, message: body, priority: prio, tags: ['test_tube'], click: location.href.split('#')[0]})});
    if (!r.ok) throw new Error(r.status);
    $('#testMsg').classList.remove('err'); $('#testMsg').textContent = `\u2714 ${tier} test fired ${new Date().toLocaleTimeString('en-US', {hour: 'numeric', minute: '2-digit'})}. Check your phone.`;
  } catch (e) { $('#testMsg').classList.add('err'); $('#testMsg').textContent = 'Test could not be sent. Try again.'; }
  btn.disabled = false;
};

function openCmd() { $('#cmd').classList.add('open'); $('#shade').classList.add('on'); $('#cmd').setAttribute('aria-hidden', 'false'); }
function closeCmd() { $('#cmd').classList.remove('open'); $('#shade').classList.remove('on'); $('#cmd').setAttribute('aria-hidden', 'true'); if (window.innerWidth <= 900) showTab(lastTab); }
$('#openCmd').onclick = openCmd; $('#closeCmd').onclick = closeCmd; $('#shade').onclick = closeCmd;

// ---------------------------------------------------------------- tabs (phone)
let lastTab = 'map';
function showTab(t) {
  if (t === 'cmd') { openCmd(); document.querySelectorAll('.tabs button').forEach(b => b.classList.toggle('on', b.dataset.go === 'cmd')); return; }
  lastTab = t;
  document.querySelectorAll('.panel').forEach(p => p.classList.toggle('show', p.dataset.tab === t));
  document.querySelectorAll('.tabs button').forEach(b => b.classList.toggle('on', b.dataset.go === t));
  if (t === 'map') setTimeout(() => map.invalidateSize(), 50);
  if (t === 'scope') setTimeout(sizeScope, 50);
}
document.querySelectorAll('.tabs button').forEach(b => b.onclick = () => showTab(b.dataset.go));
showTab('map');

// ---------------------------------------------------------------- go
buildChips(); buildToggles(); paint();
sizeScope(); requestAnimationFrame(drawScope);
if (topic) unlock(topic, true);
refresh(); setInterval(refresh, REFRESH_MS);
setInterval(() => { if (alerts.length) drawFeed(); }, 60000);
if ('serviceWorker' in navigator) navigator.serviceWorker.register('sw.js').catch(() => {});
})();
