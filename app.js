/* WATCHMAN RADAR // Riley's command center */
(() => {
'use strict';

// ---------------------------------------------------------------- setup
const TOPIC_HASH = '5daa8df05d78ee6b173a1b863c13feb1bcfd489d8b1544c97eeef6c5f3c1edd2';
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
  tanker:  {n: 'Refueling planes',          s: 'Refueling',  k: 'refueling plane',        c: '#ffb000'},
  bomber:  {n: 'Bombers',                   s: 'Bombers',    k: 'bomber',                 c: '#ff3b3b'},
  airlift: {n: 'Big cargo planes',          s: 'Big cargo',  k: 'big cargo plane',        c: '#38bdf8'},
  tactical:{n: 'Small cargo planes',        s: 'Small cargo', k: 'small cargo plane',     c: '#7dd3fc'},
  isr:     {n: 'Spy & surveillance planes', s: 'Spy',        k: 'spy & surveillance plane', c: '#c084fc'},
  c2:      {n: 'Nuclear command planes',    s: 'Nuclear command', k: 'nuclear command plane', c: '#ff4fd8'},
  fighter: {n: 'Fighter jets',              s: 'Fighters',   k: 'fighter jet',            c: '#a3ff3b'},
  other:   {n: 'Other military planes',     s: 'Other',      k: 'military plane',         c: '#3fbf86'},
};
const WATCHES = [
  ['nuclear', 'Nuclear drills & command planes'], ['missiles', 'Missile tests'], ['bombers', 'Bombers'],
  ['warships', 'Warships near the US or Cuba'], ['foreign_mil', 'Foreign military jets near the US or Europe'], ['subs', 'Submarines & sub hunters'],
  ['tankers', 'Lots of refueling planes'], ['airlift', 'Lots of cargo planes'], ['buildups', 'Troop buildups'],
  ['ukraine', 'Big pushes in Ukraine'], ['russia', 'Russia on the move'], ['hormuz', 'Persian Gulf trouble'],
  ['isr', 'Spy planes'], ['breaking', 'Major breaking news'],
  ['skyking', 'Skyking & EAM bursts on HFGCS'], ['gpsjam', 'GPS jamming spikes'], ['closures', 'New sky closures (FAA)'],
  ['convergence', 'Convergence alarm (signals stacking)'],
];
const REGIONS = {
  alaska: ['Alaska', [[51, -180], [72, -129]]],
  conus: ['Mainland US', [[24, -126], [50, -65]]],
  cuba: ['Cuba & the Caribbean', [[17, -88], [27, -72]]],
  hawaii: ['Hawaii', [[17, -163], [25, -152]]],
  europe: ['Europe & North Atlantic', [[35, -25], [72, 45]]],
  baltic: ['Baltic & Scandinavia', [[53.5, 9], [71, 32]]],
  ukraine: ['Ukraine & the Black Sea', [[40.5, 22], [53, 42]]],
  easternmed: ['Israel & the Eastern Med', [[29, 24], [37.5, 38]]],
  gulf: ['Persian Gulf & Hormuz', [[12, 38], [31, 63]]],
  pacific: ['West Pacific & Taiwan', [[10, 115], [46, 150]]],
};
const DEFAULTS = {
  watches: Object.fromEntries(WATCHES.map(w => [w[0], true])),
  regions: Object.fromEntries(Object.keys(REGIONS).map(r => [r, true])),
  push: {FLASH: true, IMMEDIATE: true, ROUTINE: false},
  quiet: {enabled: false, start: '22:00', end: '06:00', flash_breaks: true},
  sensitivity: 'normal',
  paused: false,
  recap: {enabled: true, time: '21:00'},
  morning: {enabled: true, time: '07:00'},
  sunday: {enabled: true, time: '20:00'},
};
const ICON = {FLASH: '\u{1F7E5}', IMMEDIATE: '\u{1F7E7}', ROUTINE: '\u{1F7E6}'};

const $ = s => document.querySelector(s);
const esc = s => String(s == null ? '' : s).replace(/[&<>"']/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[c]));
const clone = o => JSON.parse(JSON.stringify(o));
function toast(t) { const el = $('#toast'); el.textContent = t; el.classList.add('on'); clearTimeout(toast._t); toast._t = setTimeout(() => el.classList.remove('on'), 3200); }

let live = null, alerts = [], applied = null, recap = null, showLastRecap = false;
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
    $('#sweepAge').textContent = m < 1 ? 'JUST NOW' : (m < 60 ? m + ' MIN AGO' : Math.floor(m / 60) + ' HR ' + (m % 60) + ' MIN AGO');
    const box = $('#sweepbox');
    box.classList.toggle('stale', age > 30 * 60 && age <= 120 * 60);
    box.classList.toggle('dead', age > 120 * 60);
    $('#sysline').textContent = age > 120 * 60 ? 'WATCHTOWER QUIET: NO CHECK IN 2+ HOURS' : 'WATCHTOWER ONLINE \u00B7 CHECK #' + (live.sweeps || 1);
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
const SILVER = window.WR_THEME === 'silver', SC = SILVER ? '226,233,241' : '57,255,143', ACC = SILVER ? '#e8eef5' : '#39ff8f';
function drawScope() {
  const W = cv.width, H = cv.height, r = W / 2 - 4, c = W / 2;
  if (!W) { requestAnimationFrame(drawScope); return; }
  // Silver theme: the scope is see-through so the satellite map shows behind it
  if (SILVER) { cx.clearRect(0, 0, W, H); cx.fillStyle = 'rgba(6,8,11,0.16)'; } else cx.fillStyle = 'rgba(1,10,5,0.28)';
  cx.beginPath(); cx.arc(c, c, r, 0, 2 * Math.PI); cx.fill();
  cx.strokeStyle = `rgba(${SC},0.42)`; cx.lineWidth = 1;
  for (let i = 1; i <= 4; i++) { cx.beginPath(); cx.arc(c, c, r * i / 4, 0, 2 * Math.PI); cx.stroke(); }
  cx.beginPath(); cx.moveTo(c - r, c); cx.lineTo(c + r, c); cx.moveTo(c, c - r); cx.lineTo(c, c + r); cx.stroke();
  cx.save(); cx.strokeStyle = `rgba(${SC},0.22)`;
  for (let a = 0; a < 360; a += 30) { const t = a * Math.PI / 180; cx.beginPath(); cx.moveTo(c + Math.sin(t) * r * .92, c - Math.cos(t) * r * .92); cx.lineTo(c + Math.sin(t) * r, c - Math.cos(t) * r); cx.stroke(); }
  cx.restore();
  // sweep wedge
  const g = cx.createConicGradient ? cx.createConicGradient(ang - Math.PI / 2 - 0.9, c, c) : null;
  if (g) {
    g.addColorStop(0, `rgba(${SC},0)`); g.addColorStop(0.14, `rgba(${SC},0.35)`); g.addColorStop(0.1433, `rgba(${SC},0)`); g.addColorStop(1, `rgba(${SC},0)`);
    cx.fillStyle = g; cx.beginPath(); cx.moveTo(c, c); cx.arc(c, c, r, ang - Math.PI / 2 - 0.9, ang - Math.PI / 2); cx.closePath(); cx.fill();
  }
  cx.strokeStyle = SILVER ? 'rgba(248,250,253,0.95)' : 'rgba(120,255,180,0.9)'; cx.lineWidth = 2; cx.beginPath(); cx.moveTo(c, c); cx.lineTo(c + Math.sin(ang) * r, c - Math.cos(ang) * r); cx.stroke();
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
  cx.fillStyle = ACC; cx.beginPath(); cx.arc(c, c, 3, 0, 2 * Math.PI); cx.fill();
  ang = (ang + 0.018) % (2 * Math.PI);
  requestAnimationFrame(drawScope);
}

// ---------------------------------------------------------------- map
const map = L.map('map', {zoomControl: true, worldCopyJump: true, attributionControl: true, minZoom: 2, maxZoom: 19}).setView([38, -30], 3);
// Base maps: free Esri tiles, no API key needed. Terrain is the default, like Google's terrain view.
const ESRI = 'https://server.arcgisonline.com/ArcGIS/rest/services/';
const esri = (path, o) => L.tileLayer(ESRI + path + '/MapServer/tile/{z}/{y}/{x}', Object.assign({maxZoom: 19, crossOrigin: true}, o));
const ADSB = ' | ADS-B: adsb.lol';
const BASEMAPS = {
  terrain: {n: 'TERRAIN', layers: [
    esri('World_Topo_Map', {maxNativeZoom: 18, attribution: 'Tiles &copy; Esri &mdash; Esri, HERE, Garmin, USGS, NGA, EPA, USDA, NPS, &copy; OpenStreetMap contributors' + ADSB})]},
  satellite: {n: 'SATELLITE', layers: [
    esri('World_Imagery', {maxNativeZoom: 19, attribution: 'Imagery &copy; Esri &mdash; Maxar, Earthstar Geographics, USDA, USGS, AeroGRID, IGN, GIS User Community' + ADSB}),
    esri('Reference/World_Transportation', {maxNativeZoom: 19, opacity: .85}),
    esri('Reference/World_Boundaries_and_Places', {maxNativeZoom: 19})]},
  dark: {n: 'DARK', layers: [
    esri('Canvas/World_Dark_Gray_Base', {maxNativeZoom: 16, attribution: 'Tiles &copy; Esri &mdash; Esri, HERE, Garmin, &copy; OpenStreetMap contributors' + ADSB}),
    esri('Canvas/World_Dark_Gray_Reference', {maxNativeZoom: 16})]},
};
let baseKey = localStorage.getItem('wr_basemap');
if (!BASEMAPS[baseKey]) baseKey = 'terrain';
function setBasemap(k) {
  if (!BASEMAPS[k]) k = 'terrain';
  for (const b of Object.values(BASEMAPS)) b.layers.forEach(l => map.removeLayer(l));
  BASEMAPS[k].layers.forEach(l => l.addTo(map));
  baseKey = k; localStorage.setItem('wr_basemap', k);
  const el = document.getElementById('map');
  el.classList.remove('bm-terrain', 'bm-satellite', 'bm-dark'); el.classList.add('bm-' + k);
  document.querySelectorAll('.bmswitch button').forEach(b => b.classList.toggle('on', b.dataset.bm === k));
}
const BmSwitch = L.Control.extend({options: {position: 'topright'}, onAdd() {
  const d = L.DomUtil.create('div', 'bmswitch');
  d.innerHTML = Object.entries(BASEMAPS).map(([k, v]) => `<button type="button" data-bm="${k}">${v.n}</button>`).join('');
  L.DomEvent.disableClickPropagation(d); L.DomEvent.disableScrollPropagation(d);
  d.querySelectorAll('button').forEach(b => b.onclick = () => setBasemap(b.dataset.bm));
  return d;
}});
new BmSwitch().addTo(map);
setBasemap(baseKey);
// While a plane's info box is open, fade the map buttons away so they never cover it.
// They fade back in when the box is closed or he taps the map somewhere else.
let openPop = null;
function syncPopUi() { document.getElementById('map').classList.toggle('pop-open', !!openPop); }
map.on('popupopen', e => { openPop = e.popup; syncPopUi(); });
map.on('popupclose', e => { if (openPop === e.popup) openPop = null; setTimeout(syncPopUi, 0); });
window.wrMap = map;
const regionLayer = L.layerGroup().addTo(map), acLayer = L.layerGroup().addTo(map), alertLayer = L.layerGroup().addTo(map);
for (const [k, v] of Object.entries(REGIONS)) {
  L.rectangle(v[1], {color: ACC, weight: 1, opacity: .35, dashArray: '4 6', fill: true, fillOpacity: .02, interactive: false}).addTo(regionLayer);
}
L.circleMarker(HOME, {radius: 5, color: ACC, fillColor: ACC, fillOpacity: 1}).bindPopup('<b>HOME BASE</b>').addTo(map);
function planeSvg(col, big) {
  const s = big ? 26 : 18;
  return `<svg width="${s}" height="${s}" viewBox="0 0 24 24" style="color:${col}"><path fill="${col}" stroke="#000" stroke-width="1.3" stroke-linejoin="round" paint-order="stroke" d="M12 2c.6 0 1 .5 1 1.2V9l8 4.6v2l-8-2.3v4.9l2.4 1.7V21L12 20l-3.4 1v-1.1L11 18.2v-4.9L3 15.6v-2L11 9V3.2C11 2.5 11.4 2 12 2z"/></svg>`;
}
const markerByHex = new Map();
function drawPlanes() {
  acLayer.clearLayers(); markerByHex.clear();
  if (!live) return;
  let shown = 0;
  for (const p of live.planes) {
    if (!catOn.has(p.cat)) continue;
    shown++;
    const col = (CATS[p.cat] || CATS.other).c, big = ['bomber', 'tanker', 'c2'].includes(p.cat), f = p.nat && p.nat !== 'US';
    // Fighter jets get their own swept-wing fighter icon
    const fi = (p.cat === 'fighter' && window.WRF) ? WRF.info(p) : null;
    // round two: each type gets its own shape (spice.js)
    const wi = window.WRI ? WRI.icon(p, f) : null;
    const s = wi ? wi.size : big ? 26 : fi ? 22 : 18;
    const icon = L.divIcon({className: 'ac' + (f ? ' foreign' : '') + (fi ? ' fj' : ''), iconSize: [s, s], iconAnchor: [s / 2, s / 2],
      html: `<div style="transform:rotate(${p.trk || 0}deg)">${wi ? wi.html : fi ? WRF.svg(f ? '#ff3b3b' : col) : planeSvg(f ? '#ff3b3b' : col, big)}</div>`});
    const nm = fi ? fi.name : ((window.TYPE_NAMES && TYPE_NAMES[p.t]) || p.t || 'Unknown type');
    const tk = fi ? WRF.nearTanker(p, live.planes) : null;
    const sq = {'7700': '\u{1F198} Signaling an emergency', '7600': '\u{1F4FB} Reporting radio trouble', '7500': '\u{1F6A8} Sent the hijack code'}[p.sq];
    const ids = [p.cs, p.reg].filter(Boolean);
    const cat = CATS[p.cat] ? p.cat : 'other';
    const over = REGIONS[p.rg] ? REGIONS[p.rg][0] : 'open water';
    // A US military Boeing 767 is almost always the KC-46 Pegasus refueling plane
    const kc46 = p.t === 'B762' && !f;
    const kindHtml = kc46 ? `Probably a KC-46 tanker ${tipBtn('kc46')}` : fi ? `${esc(cap(fi.role))} ${tipBtn(fi.tip)}` : `${esc(cap(kindOf(nm, cat)))} ${tipBtn(cat)}`;
    const mk = L.marker([p.lat, p.lon], {icon});
    if (p.hex) markerByHex.set(String(p.hex), mk);
    mk.bindPopup(() =>
      `<div class="pp"><b>${esc(nm)}</b><div class="pk">${kindHtml}</div>` +
      (f ? `<div class="pf">${esc(NATN[p.nat] || p.nat)} military ${tipBtn('foreign')}</div>` : '') +
      (sq ? `<div class="pf">${sq}</div>` : '') +
      (tk ? `<div class="pr">\u26FD Possibly refueling with the tanker nearby (${tk.d} mi) ${tipBtn('refuelnear')}</div>` : '') +
      `<div>${esc(flightLine(p.alt, p.gs, p.trk, p.lat, p.lon, p.vr) || 'No height or speed shared')}</div>` +
      `<div class="pm">Over ${esc(over)} \u00B7 ${esc(fromHome(p.lat, p.lon))}</div>` +
      (ids.length ? `<details class="ids"><summary>Plane ID ${tipBtn('planeid')}</summary><div>${ids.map(esc).join(' &middot; ')}</div></details>` : '') +
      (window.WR && WR.popupExtra ? WR.popupExtra(p) : '') +
      `<a href="https://globe.adsb.lol/?icao=${esc(String(p.hex).replace('~', ''))}" target="_blank" rel="noopener">Follow this plane live &rarr;</a></div>`
    , {maxWidth: 280}).addTo(acLayer);
  }
  $('#mapcount').textContent = `// showing ${shown} of ${live.planes.length} military planes`;
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
window.TYPE_NAMES = {K35R: 'KC-135R', K35E: 'KC-135E', K46: 'KC-46A', KC46: 'KC-46A', B52: 'B-52', B1: 'B-1B', B2: 'B-2', C17: 'C-17', C5M: 'C-5M', C5: 'C-5', C130: 'C-130', C30J: 'C-130J', R135: 'RC-135', E3TF: 'E-3 AWACS', E3CF: 'E-3 AWACS', P8: 'P-8 Poseidon', E6: 'E-6B Mercury', E4B: 'E-4B', RQ4: 'RQ-4', Q4: 'RQ-4', GLHK: 'RQ-4', MQ9: 'MQ-9', A400: 'A400M', F35: 'F-35 Lightning II', F16: 'F-16 Fighting Falcon', F15: 'F-15 Eagle', F18S: 'F/A-18 Super Hornet', F18H: 'F/A-18 Hornet', F22: 'F-22 Raptor', EUFI: 'Eurofighter Typhoon', RFAL: 'Rafale', SB39: 'Gripen', GRIF: 'Gripen', TOR: 'Tornado', A10: 'A-10 Warthog', F5: 'F-5 Tiger II', MIR2: 'Mirage 2000', PC21: 'PC-21 trainer', PC7: 'PC-7 trainer', PC9: 'PC-9 trainer', T6: 'T-6 Texan II', M346: 'M-346 trainer', L39: 'L-39 trainer', H60: 'Black Hawk', H47: 'Chinook', V22: 'V-22 Osprey', TEX2: 'T-6 Texan II', HAWK: 'T-45 Goshawk', T38: 'T-38 Talon', TUCA: 'Tucano', B737: 'Boeing 737', B736: 'Boeing 737', B738: 'Boeing 737', B762: 'Boeing 767', A332: 'Airbus A330', A319: 'Airbus A319', GLF5: 'Gulfstream jet', GL5T: 'Global 5000 jet', C560: 'Citation jet', H25B: 'Hawker jet', F2TH: 'Falcon 2000 jet', BE20: 'King Air', BE9L: 'King Air', AS65: 'Dolphin helicopter', EC45: 'Lakota helicopter', A119: 'Koala helicopter', C27J: 'C-27J Spartan', E390: 'KC-390', P28A: 'Piper Cherokee', C172: 'Cessna 172', DHC6: 'Twin Otter', TWR: 'Ground station'};

// ---------------------------------------------------------------- chips
function buildChips() {
  const cc = $('#catchips'); cc.innerHTML = '';
  for (const [k, v] of Object.entries(CATS)) {
    const b = document.createElement('button');
    b.className = 'chip' + (catOn.has(k) ? ' on' : '');
    b.innerHTML = `<i style="background:${v.c}"></i>${v.s}`;
    b.onclick = () => { catOn.has(k) ? catOn.delete(k) : catOn.add(k); buildChips(); drawPlanes(); };
    cc.appendChild(b);
  }
  cc.insertAdjacentHTML('beforeend', tipBtn('cats'));
  const tc = $('#tierchips'); tc.innerHTML = '';
  for (const [k, cls] of [['ALL', ''], ['FLASH', 'fl'], ['IMMEDIATE', 'im'], ['ROUTINE', 'ro']]) {
    const b = document.createElement('button');
    b.className = 'chip ' + cls + (tierOn === k ? ' on' : '');
    b.textContent = ICON[k] ? ICON[k] + ' ' + {FLASH: 'Urgent', IMMEDIATE: 'Important', ROUTINE: 'FYI'}[k] : 'All';
    b.onclick = () => { tierOn = k; buildChips(); drawFeed(); };
    tc.appendChild(b);
  }
  tc.insertAdjacentHTML('beforeend', tipBtn('tiers'));
}

// ---------------------------------------------------------------- panels
function ago(ts) {
  const s = Math.max(0, Date.now() / 1000 - ts);
  if (s < 90) return 'just now';
  if (s < 3600) return Math.round(s / 60) + ' min ago';
  if (s < 86400) { const h = Math.round(s / 3600); return h + (h === 1 ? ' hour ago' : ' hours ago'); }
  const d = Math.round(s / 86400); return d + (d === 1 ? ' day ago' : ' days ago');
}
function drawStats() {
  const st = live ? live.stats : {};
  const tot = live ? live.planes.length : 0;
  const tiles = [['All military planes', tot, '', 'total'], ['Refueling planes', st.tanker || 0, '', 'tanker'], ['Bombers', st.bomber || 0, (st.bomber || 0) > 0 ? 'red' : '', 'bomber'],
    ['Big cargo planes', st.airlift || 0, '', 'airlift'], ['Spy & surveillance', st.isr || 0, '', 'isr'], ['Nuclear command', st.c2 || 0, (st.c2 || 0) > 0 ? 'hot' : '', 'c2']];
  $('#stats').innerHTML = tiles.map(t => `<div class="stat ${t[2]}"><label>${t[0]} ${tipBtn(t[3])}</label><b>${t[1]}</b></div>`).join('');
  const foreign = live ? live.planes.filter(p => p.nat && p.nat !== 'US').length : 0;
  $('#scopeinfo').innerHTML = `${tot} planes on radar<br>${foreign ? '<span style="color:#ff3b3b">' + foreign + ' foreign military</span>' : 'No foreign military showing'}`;
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
    const n = b.total || 0, bits = [];
    if (t) bits.push(`<b class="${tUp ? 'up' : ''}">${t} refueling${tUp ? ' \u25B2' : ''}</b>`);
    if (a) bits.push(`<b class="${aUp ? 'up' : ''}">${a} cargo${aUp ? ' \u25B2' : ''}</b>`);
    if (b.bomber) bits.push(`<b class="up">${b.bomber} bomber${b.bomber > 1 ? 's' : ''}</b>`);
    return `<div class="brow ${off ? 'off' : ''}" data-r="${k}"><span class="lamp ${off ? 'off' : regionLamp(k)}"></span>` +
      `<span class="bt"><span class="nm">${v[0]}</span><span class="ct">${off ? 'Not watching' : `${n} plane${n === 1 ? '' : 's'}${bits.length ? ' \u00B7 ' + bits.join(' \u00B7 ') : ''}`}</span></span><span class="arr">\u203A</span></div>`;
  }).join('');
  document.querySelectorAll('.brow').forEach(el => el.onclick = () => {
    const r = REGIONS[el.dataset.r]; map.fitBounds(r[1]); showTab('map');
  });
  const s = live ? live.sources || {} : {};
  const SRC = {adsb: 'Plane tracker', news: 'News'};
  const note = v => String(v || '').replace(/military aircraft/, 'military planes').replace(/(\d+) feeds ok, (\d+) failed, (\d+) headlines/, (_, ok, bad, h) => `${ok} sources working${+bad ? ', ' + bad + ' down' : ''} \u00B7 ${h} headlines`);
  $('#srcs').innerHTML = Object.entries(s).map(([k, v]) => `<div><span class="${v.ok ? 'ok' : 'bad'}">\u25CF</span> ${SRC[k] || cap(k)}: ${esc(note(v.note))}</div>`).join('') +
    (live ? `<div>Checks again about every 10 minutes</div>` : '');
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
  $('#feedcount').textContent = `// ${alerts.length} saved`;
  if (!list.length) {
    $('#feed').innerHTML = `<div class="empty">${alerts.length ? 'Nothing like that yet.' : 'All quiet. WATCHTOWER checks about every 10 minutes and will save anything worth knowing here.'}</div>`;
    return;
  }
  $('#feed').innerHTML = list.slice(0, 200).map(a => {
    const st = a.pushed === 'sent' ? `<span class="p">\u2714 Sent to your phone ${tipBtn('sent')}</span>` : a.held ? `<span class="h">${esc(plainHeld(a.held))}</span>` : '<span>Saved here only</span>';
    const links = [];
    if (a.more && a.more.length) a.more.forEach(m => links.push(`<a href="${esc(m.u)}" target="_blank" rel="noopener">\u2197 ${esc(m.t)} <small>(${esc(m.s)})</small></a>`));
    else if (a.link) links.push(`<a href="${esc(a.link)}" target="_blank" rel="noopener">\u2197 Read the news story</a>`);
    const isNew = !seenIds.has(a.id);
    let det = '';
    if (a.watch === 'recap' || a.watch === 'report' || a.watch === 'sunday') det = `<pre class="tfpre">${esc(plainText(a.body || ''))}</pre>`;
    else {
      const pa = parseAssets(a.assets);
      const rows = [];
      if (pa.groups.length) rows.push([a.headline ? 'What it\u2019s about' : 'What\u2019s up there', esc(assetsLine(pa.groups)) + idsBox(idsOf(pa.groups))]);
      const fl = flightLine(pa.f.alt, pa.f.kt, pa.f.trk, a.lat, a.lon);
      if (fl) rows.push(['How it\u2019s flying', esc(fl)]);
      if (a.lat != null && a.watch !== 'test') rows.push(['Distance', esc(cap(fromHome(a.lat, a.lon)))]);
      if (a.response) rows.push(['What it means', esc(plainResponse(a.response))]);
      if (a.threat) rows.push([`Threat level ${tipBtn('threatlvl')}`, esc(THREATW[a.threat] || cap(String(a.threat).toLowerCase()))]);
      if (a.source) rows.push(['Where this came from', esc(plainSource(a.source))]);
      det = rows.map(r => `<div class="drow"><label>${r[0]}</label><div>${r[1]}</div></div>`).join('');
    }
    const mapBtn = a.lat != null && a.watch !== 'test' ? `<button class="mapbtn" data-lat="${a.lat}" data-lon="${a.lon}">\u{1F4CD} Show on map</button>` : '';
    return `<div class="alert ${a.tier} ${isNew ? 'new' : ''}" data-id="${esc(a.id)}">` +
      `<div class="atop">${tierTag(a.tier)} ${TIERW[a.tier] ? tipBtn(a.tier) : ''}<span class="when">${ago(a.ts)}</span></div>` +
      `<h4>${esc(plainWhat(a.what || a.title))}</h4>` +
      (a.headline ? `<div class="hl">${esc(a.headline)}</div>` : '') +
      `<div class="meta"><span>\u{1F4CD} ${esc(plainPlace(a.location, a.region))}</span>${st}</div>` +
      `<div class="more">${det}<div class="links">${links.join('')}</div>${mapBtn}</div>` +
      `<div class="tapmore"></div></div>`;
  }).join('');
  document.querySelectorAll('.alert .mapbtn').forEach(b => b.onclick = ev => {
    ev.stopPropagation(); showTab('map'); setTimeout(() => map.flyTo([+b.dataset.lat, +b.dataset.lon], 5, {duration: 1}), 80);
  });
  document.querySelectorAll('.alert').forEach(el => el.onclick = ev => {
    if (ev.target.closest('a,details,button')) return;
    el.classList.toggle('open'); el.classList.remove('new');
    seenIds.add(el.dataset.id); localStorage.setItem('wr_seen', JSON.stringify([...seenIds].slice(-500)));
    const a = alerts.find(x => x.id === el.dataset.id);
    if (a && a.lat != null && el.classList.contains('open') && window.innerWidth > 900) map.flyTo([a.lat, a.lon], 5, {duration: 1});
    badge();
  });
  badge();
}
// ---------------------------------------------------------------- top finds (end-of-day recap)
const MEDAL = ['\u{1F947}', '\u{1F948}', '\u{1F949}', '4', '5'];
function ctTime(ts, withDay) {
  return new Date(ts * 1000).toLocaleString('en-US', Object.assign({timeZone: 'America/Chicago', hour: 'numeric', minute: '2-digit'}, withDay ? {weekday: 'short'} : {}));
}
function drawTopFinds() {
  const box = $('#topfinds');
  if (!recap || !recap.today) { box.innerHTML = '<div class="tfempty">Today\u2019s tally shows up after the next check.</div>'; return; }
  const t = recap.today, startCT = new Date(t.start * 1000).toLocaleTimeString('en-US', {timeZone: 'America/Chicago', hour: 'numeric', minute: '2-digit'});
  const rat = String(recap.recap_at || '').replace(':00 ', ' ').replace(/ CT$/, '');
  $('#tfsub').textContent = (startCT === '12:00 AM' ? '// today so far' : '// since ' + ctTime(t.start, true)) +
    (recap.enabled ? ' \u00B7 recap at ' + rat : ' \u00B7 recap off');
  const tiers = t.tiers || {}, sw = t.sweeps || 0;
  let html = `<div class="tfstats"><div>Checked ${sw} time${sw === 1 ? '' : 's'} today ${tipBtn('checks')}</div>` +
    `<div>Most military planes seen at once: <b>${t.peak_total || 0}</b> ${tipBtn('peak')}</div>` +
    `<div class="tft"><span class="fl">${ICON.FLASH} ${tiers.FLASH || 0} urgent</span><span class="im">${ICON.IMMEDIATE} ${tiers.IMMEDIATE || 0} important</span><span class="ro">${ICON.ROUTINE} ${tiers.ROUTINE || 0} FYI</span> ${tipBtn('tiers')}</div></div>`;
  if (!t.top || !t.top.length) html += '<div class="tfempty">Nothing notable yet. All quiet on the watch so far.</div>';
  else {
    if (t.quiet) html += '<div class="tfnote">Nothing urgent or important yet. The most notable so far:</div>';
    html += t.top.map((f, i) => {
      const when = ctTime(f.first) + ((f.last - f.first) >= 1200 ? '\u2013' + ctTime(f.last) : '');
      const pa = parseAssets(f.assets);
      return `<div class="tf ${f.tier}" data-i="${i}"><b class="md">${MEDAL[i]}</b><div><div class="atop">${tierTag(f.tier)}</div><h5>${esc(plainWhat(f.what))}</h5>` +
        `<div class="tfm">\u{1F4CD} ${esc(plainPlace(f.location, f.region))}</div>` +
        `<div class="tfm">\u{1F550} ${esc(when)}${f.sweeps > 1 ? ' \u00B7 seen on ' + f.sweeps + ' checks' : ''}</div>` +
        (f.pushed ? `<div class="tfm"><span class="p">\u2714 Sent to your phone</span></div>` : '') +
        (f.headline ? `<div class="tfm hl">${esc(f.headline)}</div>` : (pa.groups.length ? `<div class="tfm hl">${esc(assetsLine(pa.groups))}</div>${idsBox(idsOf(pa.groups))}` : '')) + `</div></div>`;
    }).join('');
  }
  if (t.airframes) html += `<div class="tfm af">\u2708\uFE0F Special planes spotted today: ${esc(plainAirframes(t.airframes))}</div>`;
  if (recap.last && recap.last.body) {
    html += `<button class="tflast" id="tfLast">${showLastRecap ? '\u25BE' : '\u25B8'} Last night\u2019s recap \u00B7 ${esc(recap.last.date)}</button>` +
      (showLastRecap ? `<pre class="tfpre">${esc(plainText(recap.last.title + '\n' + recap.last.body))}</pre>` : '');
  }
  box.innerHTML = html;
  box.querySelectorAll('.tf').forEach(el => el.onclick = ev => {
    if (ev.target.closest('a,details,button')) return;
    const f = t.top[+el.dataset.i];
    if (f && f.lat != null) { showTab('map'); setTimeout(() => map.flyTo([f.lat, f.lon], 5, {duration: 1}), 80); }
  });
  const lb = $('#tfLast'); if (lb) lb.onclick = () => { showLastRecap = !showLastRecap; drawTopFinds(); };
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
    const [l, a, c, rc] = await Promise.all([getJSON('live.json'), getJSON('alerts.json').catch(() => ({alerts: []})), getJSON('config.json').catch(() => null), getJSON('recap.json').catch(() => null)]);
    recap = rc;
    const firstLoad = !live;
    live = l; alerts = (a.alerts || []).filter(x => x && x.tier);
    if (c && c.settings) { applied = c; if (!dirty && !pendingSince) loadSettings(c.settings); }
    if (firstLoad && !seenIds.size) { alerts.forEach(x => seenIds.add(x.id)); localStorage.setItem('wr_seen', JSON.stringify([...seenIds].slice(-500))); }
    setBlips(); drawStats(); drawBoard(); drawPlanes(); drawAlertPings(); drawFeed(); drawTopFinds(); threatcon(); tick();
    checkApplied();
    WR.hooks.forEach(fn => { try { fn(); } catch (e) { console.warn(e); } });
  } catch (e) {
    $('#sysline').textContent = 'WAITING FOR THE FIRST CHECK';
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
  $('#masterHint').textContent = settings.paused ? 'PAUSED: WATCHTOWER keeps watching and saving, but won\u2019t buzz your phone.' : 'ON: WATCHTOWER buzzes your phone for the kinds of alerts you pick below.';
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
    $('#saveMsg').textContent = 'Orders sent. WATCHTOWER switches to them on its next check (within about 10 minutes).';
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
    $('#saveMsg').textContent = 'Orders sent. WATCHTOWER switches to them on its next check (within about 10 minutes).';
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

// ---------------------------------------------------------------- shared with squawk.js (alert screen)
let trackPin = null;
function trackPlane(hex, lat, lon, label) {
  showTab('map');
  setTimeout(() => {
    map.invalidateSize();
    const mk = hex && markerByHex.get(String(hex));
    if (mk) { map.flyTo(mk.getLatLng(), 7, {duration: 1}); setTimeout(() => mk.openPopup(), 1100); return; }
    const lp = hex && live && live.planes ? live.planes.find(q => String(q.hex) === String(hex)) : null;
    if (lp) { lat = lp.lat; lon = lp.lon; }
    const note = lp ? 'This kind of plane is switched off in your map filters, so here is its spot.' : "It isn't on the radar right now, so this is where it was last seen.";
    if (lat == null || isNaN(lat)) { toast('That plane is off the radar now.'); return; }
    if (trackPin) map.removeLayer(trackPin);
    const icon = L.divIcon({className: 'trackpin', iconSize: [34, 34], iconAnchor: [17, 17], html: '<div></div>'});
    trackPin = L.marker([lat, lon], {icon}).bindPopup(`<div class="pp"><b>${esc(label || 'Last seen here')}</b><div class="pm">${esc(fromHome(lat, lon))}</div><div class="pm">${esc(note)}</div></div>`, {maxWidth: 260}).addTo(map);
    map.flyTo([lat, lon], 7, {duration: 1}); setTimeout(() => trackPin && trackPin.openPopup(), 1100);
  }, 80);
}
const WR = window.WR = {hooks: [], drawPlanes, DATA, getJSON, showTab, trackPlane, toast, ago, map,
  get live() { return live; }, get alerts() { return alerts; }, get lastTab() { return lastTab; }};

// ---------------------------------------------------------------- go
buildChips(); buildToggles(); paint();
sizeScope(); requestAnimationFrame(drawScope);
if (topic) unlock(topic, true);
refresh(); setInterval(refresh, REFRESH_MS);
setInterval(() => { if (alerts.length) drawFeed(); }, 60000);
if ('serviceWorker' in navigator) navigator.serviceWorker.register('sw.js').catch(() => {});
})();
