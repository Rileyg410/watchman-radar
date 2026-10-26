/* WATCHMAN RADAR // EMERGENCY SQUAWKS screen + tap-to-open alerts
   Routes:  #squawks                    open the screen
            #alert/<id>[/<data>][/pray]  open the screen on one alert (phone alerts link here)
            #track/<hex>/<lat>/<lon>     jump to a plane on the map (the "Track it" button on phone alerts) */
(() => {
'use strict';
const WR = window.WR;
if (!WR) return;
const $ = s => document.querySelector(s);
const E = escH;

const CODES = {
  '7700': {tag: 's77', cls: 'c77', name: 'EMERGENCY', short: 'emergency', verb: 'declared an emergency', em: '\u26A0\uFE0F',
    why: 'The crew is telling air traffic control they have an emergency on board.'},
  '7600': {tag: 's76', cls: 'c76', name: 'LOST RADIO', short: 'lost radio', verb: 'lost its radio', em: '\u{1F4E1}',
    why: 'The crew can\u2019t talk on the radio, so controllers clear the way while it follows lost-radio rules.'},
  '7500': {tag: 's75', cls: 'c75', name: 'HIJACK CODE', short: 'hijack', verb: 'set the hijack code', em: '\u{1F6A8}',
    why: 'This code means someone may have taken over the plane. Sometimes it\u2019s a mis-set dial, so watch whether it stays on.'},
};
const ORDER = ['7700', '7600', '7500'];
const TIERTAG = {FLASH: ['sfl', 'URGENT', 'tfl'], IMMEDIATE: ['sim', 'IMPORTANT', 'tim'], ROUTINE: ['sro', 'FYI', 'tro']};
const BLOB = {i: 'id', t: 'ts', r: 'tier', w: 'what', q: 'sq', h: 'hex', c: 'cs', y: 'type', a: 'alt', g: 'gs', k: 'trk', v: 'vr',
  la: 'lat', lo: 'lon', rg: 'region', n: 'nat', ro: 'route', ct: 'count', wa: 'watch', hl: 'headline', as: 'assets'};

const PRAYERS = {
  '7700': ['Lord, be with the crew and everyone on board this plane. Steady their hands, calm their hearts, and bring them safely to the ground. Send help ahead of them. In Jesus\u2019 name, amen.',
    '\u201CFor he shall give his angels charge over thee, to keep thee in all thy ways.\u201D Psalm 91:11'],
  '7600': ['Lord, when they can\u2019t hear or be heard, be their guide. Clear the sky in front of them and lead them home safely. In Jesus\u2019 name, amen.',
    '\u201CAnd thine ears shall hear a word behind thee, saying, This is the way, walk ye in it.\u201D Isaiah 30:21'],
  '7500': ['Lord, cover every person on this plane with Your protection. If this is real, break every evil plan and bring everyone home safe. If it\u2019s a mistake, let it be cleared up quickly. In Jesus\u2019 name, amen.',
    '\u201CThe LORD shall preserve thee from all evil: he shall preserve thy soul.\u201D Psalm 121:7'],
  israel: ['Lord, watch over Israel and everyone in harm\u2019s way tonight. Bring peace where there is fear, and let Your will be done. Keep me watching and praying. In Jesus\u2019 name, amen.',
    '\u201CPray for the peace of Jerusalem: they shall prosper that love thee.\u201D Psalm 122:6'],
  any: ['Lord, watch over the people in this place. Bring peace where there is fear, and let Your will be done. Give me eyes to watch and a heart to pray. In Jesus\u2019 name, amen.',
    '\u201CWatch ye therefore, and pray always.\u201D Luke 21:36'],
};

let squawks = [], loaded = false, filter = null, focus = null, isOpen = false, prayFor = null;
const store = (k, set) => { try { localStorage.setItem(k, JSON.stringify([...set].slice(-300))); } catch (e) { /* private mode */ } };
const load = k => { try { return new Set(JSON.parse(localStorage.getItem(k) || '[]')); } catch (e) { return new Set(); } };
const seen = load('wr_sqseen'), prayed = load('wr_prayed');

// ------------------------------------------------------------ data
function decodeBlob(b) {
  try {
    b = b.replace(/-/g, '+').replace(/_/g, '/');
    while (b.length % 4) b += '=';
    const bin = atob(b), bytes = new Uint8Array(bin.length);
    for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
    const d = JSON.parse(new TextDecoder().decode(bytes)), o = {};
    for (const [k, v] of Object.entries(d)) o[BLOB[k] || k] = v;
    return o;
  } catch (e) { return null; }
}
function sqOf(a) {
  if (a.sq && CODES[a.sq]) return a.sq;
  const m = String(a.what || '').toUpperCase().match(/SQUAWKING (EMERGENCY|RADIO FAILURE|HIJACK CODE)/);
  return m ? {'EMERGENCY': '7700', 'RADIO FAILURE': '7600', 'HIJACK CODE': '7500'}[m[1]] : '';
}
function allSquawks() {
  const out = squawks.slice(), ids = new Set(out.map(s => s.id));
  for (const a of WR.alerts || []) {
    const q = sqOf(a);
    if (q && !ids.has(a.id)) { out.push(Object.assign({}, a, {sq: q})); ids.add(a.id); }
  }
  return out.sort((x, y) => (y.ts || 0) - (x.ts || 0));
}
function findAlert(id) {
  if (!id) return null;
  return squawks.find(s => s.id === id) || (WR.alerts || []).find(a => a.id === id) || null;
}
function livePlane(hex) {
  const l = WR.live;
  return hex && l && l.planes ? l.planes.find(p => String(p.hex) === String(hex)) : null;
}

// ------------------------------------------------------------ words
function typeName(t) { return (window.TYPE_NAMES && TYPE_NAMES[t]) || t || ''; }
function planeWords(a) {
  const nm = typeName(a.type), k = kindOf(nm, 'other');
  const nat = a.nat && a.nat !== 'US' && NATN[a.nat] ? NATN[a.nat] + ' ' : '';
  if (!nm) return nat + 'military plane';
  return nat + nm + (k === 'military plane' ? ' military plane' : ' ' + k);
}
function placeWords(a) {
  if (a.region && PLACE[a.region]) return PLACE[a.region];
  const p = plainPlace(a.location, a.region);
  return p === 'Open water' ? 'open water' : p;
}
function agoShort(ts) { return ts ? WR.ago(ts).replace(' ago', '').replace('just now', 'now').replace(' min', 'm').replace(/ hours?/, 'h').replace(/ days?/, 'd') + (WR.ago(ts) === 'just now' ? '' : ' ago') : ''; }
function ctTime(ts) {
  try { return new Date(ts * 1000).toLocaleString('en-US', {timeZone: 'America/Chicago', weekday: 'short', hour: 'numeric', minute: '2-digit'}); } catch (e) { return ''; }
}
function milesHome(lat, lon) {
  if (lat == null || isNaN(lat)) return null;
  return Math.round(miles(HOMEPT[0], HOMEPT[1], lat, lon));
}
function tiles(list) { return `<div class="meta">${list.map(t => `<span><b>${E(t[0])}</b>${E(t[1])}</span>`).join('')}</div>`; }

// ------------------------------------------------------------ cards
function squawkCard(s, big) {
  const c = CODES[s.sq];
  const lp = livePlane(s.hex), still = lp && lp.sq === s.sq;
  const cur = still ? Object.assign({}, s, {alt: lp.alt, gs: lp.gs, trk: lp.trk, lat: lp.lat, lon: lp.lon}) : s;
  const who = s.cs || s.reg || (s.hex ? String(s.hex).toUpperCase() : 'UNKNOWN');
  const alt = cur.alt == null ? '\u2014' : cur.alt <= 0 ? 'Ground' : Math.round(cur.alt).toLocaleString('en-US') + ' ft';
  const mi = milesHome(cur.lat, cur.lon);
  const third = s.route ? [String(s.route).replace('-', '\u2192'), 'route']
    : cur.gs ? [Math.round(cur.gs * 1.15078) + ' mph', cur.trk != null ? 'headed ' + compass(cur.trk) : 'speed'] : ['\u2014', 'route unknown'];
  const status = still ? `<div class="nowon">Still squawking ${E(s.sq)} right now</div>`
    : lp ? '<div class="gone">Back on a normal code now</div>'
    : (WR.live && Date.now() / 1000 - (s.ts || 0) > 900 ? '<div class="gone">Off the radar now</div>' : '');
  const done = prayed.has(s.id);
  return `<article class="nt ${big ? 'hi ' + c.cls : ''}" id="sq-${E(s.id)}" data-id="${E(s.id)}">` +
    `<div class="hd"><div class="em">${c.em}</div><span class="ap">WATCHMAN RADAR</span><span class="tm">${E(agoShort(s.ts))}</span></div>` +
    `<div class="ti"><span class="sq ${c.tag}">${E(s.sq)}</span>${E(c.name)} &middot; ${E(who)}</div>` +
    (window.WRC && s.hex ? (o => o.cc ? `<div class="bd" style="font-weight:600">${o.flag} ${E(o.label)}</div>` : '')(WRC.of({hex: s.hex, cs: s.cs, reg: s.reg, t: s.type})) : '') +
    `<div class="bd">${E(cap(planeWords(s)))} over ${E(placeWords(s))} ${E(c.verb)}.${big ? ' ' + E(c.why) : ''}</div>` +
    `<div class="more">${status}${tiles([[alt, 'altitude'], [mi == null ? '\u2014' : mi.toLocaleString('en-US') + ' mi', 'from home'], third])}` +
    `<div class="act"><button class="go" data-track="${E(s.id)}">Track it</button><button class="${done ? 'prayed' : ''}" data-pray="${E(s.id)}">${done ? '\u{1F64F} Prayed' : 'Pray'}</button></div>` +
    `<div class="bd" style="margin-top:8px;font-size:12px;color:#9fb3a8">${E(ctTime(s.ts))} Central</div></div></article>`;
}
function alertCard(a) {
  const test = a.watch === 'test';
  const t = test ? ['sro', 'TEST', 'tro'] : TIERTAG[a.tier] || TIERTAG.ROUTINE;
  const pa = parseAssets(a.assets);
  const body = test ? 'This is the screen your phone alerts open now. Real emergency codes show up right below.'
    : a.headline || (pa.groups.length ? cap(assetsLine(pa.groups)) + '.' : '');
  const mi = milesHome(a.lat, a.lon), list = [];
  if (test) {
    const n = (WR.live && WR.live.planes) ? WR.live.planes.length : null;
    list.push([n == null ? '\u2014' : String(n), 'planes on radar'], ['Online', 'watchtower'], [agoShort(a.ts) || 'now', 'sent']);
  } else {
    if (mi != null) list.push([mi.toLocaleString('en-US') + ' mi', 'from home']);
    const cnt = a.count || pa.groups.reduce((n, g) => n + (g.n || 0), 0);
    if (cnt) list.push([String(cnt), cnt === 1 ? 'plane' : 'planes']);
    list.push([cap(placeWords(a)).replace(/ & .*/, ''), 'where']);
  }
  const done = prayed.has(a.id);
  const canTrack = !test && a.lat != null;
  return `<article class="nt hi ${t[2]}" id="sq-${E(a.id)}" data-id="${E(a.id)}">` +
    `<div class="hd"><div class="em">${test ? '\u{1F4E1}' : a.tier === 'FLASH' ? '\u{1F6A8}' : '\u26A0\uFE0F'}</div><span class="ap">WATCHMAN RADAR</span><span class="tm">${E(agoShort(a.ts))}</span></div>` +
    `<div class="ti"><span class="sq ${t[0]}">${t[1]}</span>${E(plainWhat(a.what || a.title))}</div>` +
    (body ? `<div class="bd">${E(body)}</div>` : '') +
    `<div class="more">${tiles(list)}<div class="act">` +
    (canTrack ? `<button class="go" data-track="${E(a.id)}">Track it</button>` : `<button class="go" data-radar="1">Open radar</button>`) +
    `<button class="${done ? 'prayed' : ''}" data-pray="${E(a.id)}">${done ? '\u{1F64F} Prayed' : 'Pray'}</button></div>` +
    (a.link ? `<div class="act"><a href="${E(a.link)}" target="_blank" rel="noopener">\u2197 Read the news story</a></div>` : '') +
    `</div></article>`;
}
function quietCard(msg) {
  return `<article class="nt quiet"><div class="qi">\u{1F54A}\uFE0F</div><div class="qt">ALL QUIET</div>` +
    `<div class="bd">${E(msg)}</div>` +
    `<div class="qv">\u201CBehold, he that keepeth Israel shall neither slumber nor sleep.\u201D<b>Psalm 121:4</b></div></article>`;
}

// ------------------------------------------------------------ render
let byId = {};
function render() {
  const all = allSquawks();
  byId = {};
  all.forEach(s => { byId[s.id] = s; });
  const l = WR.live;
  $('#sqsys').textContent = l ? 'WATCHTOWER ONLINE' : 'WATCHTOWER LINKING\u2026';
  $('#sqlive').textContent = l && l.updated ? `live \u00B7 last check ${WR.ago(l.updated)}` : 'live \u00B7 waiting for the first check';

  const f = focus ? (findAlert(focus.id) || focus.data) : null;
  if (f) byId[f.id] = Object.assign({}, focus.data || {}, f);
  const fa = f ? byId[f.id] : null;
  const focusSq = fa && sqOf(fa) ? Object.assign(fa, {sq: sqOf(fa)}) : null;
  const alertMode = fa && !focusSq;

  // code chips with counts
  const counts = {};
  all.forEach(s => { counts[s.sq] = (counts[s.sq] || 0) + 1; });
  $('#sqkey').innerHTML = ORDER.map(q => `<button class="k${q.slice(2)} ${filter === q ? 'on' : ''}" data-f="${q}"><b>${q}</b>${CODES[q].short}${counts[q] ? ` <em>\u00B7 ${counts[q]}</em>` : ''}</button>`).join('');
  const list = all.filter(s => !filter || s.sq === filter);

  let feat = '', rest = list;
  if (alertMode) {
    $('.sqttl').firstChild.textContent = 'YOUR ALERT';
    feat = alertCard(fa);
  } else {
    $('.sqttl').firstChild.textContent = 'EMERGENCY SQUAWKS';
    const top = focusSq && (!filter || focusSq.sq === filter) ? focusSq : list[0];
    if (top) { feat = squawkCard(top, true); rest = list.filter(s => s.id !== top.id); }
    else if (!loaded && !all.length) feat = quietCard('Checking the log\u2026');
    else feat = quietCard(filter ? `No ${filter} (${CODES[filter].short}) codes in the log right now.`
      : 'No military plane on the radar is sending an emergency code. The moment one sets 7700, 7600 or 7500, it lights up right here.');
  }
  $('#sqfeat').innerHTML = feat;
  if (alertMode) {
    $('#sqoldt').textContent = 'EMERGENCY SQUAWKS' + (list.length ? ` \u00B7 ${list.length}` : '');
    $('#sqlist').innerHTML = list.length ? list.slice(0, 20).map(s => squawkCard(s, false)).join('')
      : quietCard('No military plane on the radar is sending an emergency code right now.');
  } else {
    $('#sqoldt').textContent = rest.length ? `EARLIER \u00B7 ${rest.length}` : '';
    $('#sqlist').innerHTML = rest.slice(0, 60).map(s => squawkCard(s, false)).join('');
  }
  $('#sqkey').style.display = alertMode ? 'none' : '';
  $('#sqfoot').innerHTML = 'WATCHTOWER checks every military plane on the radar for these codes each time it runs.' +
    (alertMode ? '<br><button class="sqall" id="sqall" style="margin-top:10px;background:none;border:1px solid var(--g2);color:var(--g);font:12px var(--mono);letter-spacing:.1em;padding:8px 12px;cursor:pointer">SEE ALL SQUAWKS</button>' : '');
  wire();
}
function wire() {
  document.querySelectorAll('#sqkey button').forEach(b => b.onclick = () => { filter = filter === b.dataset.f ? null : b.dataset.f; focus = null; render(); });
  document.querySelectorAll('#sqs [data-track]').forEach(b => b.onclick = ev => { ev.stopPropagation(); track(byId[b.dataset.track]); });
  document.querySelectorAll('#sqs [data-pray]').forEach(b => b.onclick = ev => { ev.stopPropagation(); pray(byId[b.dataset.pray]); });
  document.querySelectorAll('#sqs [data-radar]').forEach(b => b.onclick = ev => { ev.stopPropagation(); close(); });
  document.querySelectorAll('#sqlist .nt[data-id]').forEach(el => el.onclick = () => el.classList.toggle('open'));
  const all = $('#sqall');
  if (all) all.onclick = () => { focus = null; setHash('#squawks'); render(); $('#sqscroll').scrollTop = 0; };
}

// ------------------------------------------------------------ actions
function track(a) {
  if (!a) return;
  const lp = livePlane(a.hex);
  const label = a.sq ? `${a.sq} ${CODES[a.sq].short} \u00B7 ${a.cs || String(a.hex || '').toUpperCase()}` : plainWhat(a.what);
  close(true);
  WR.trackPlane(a.hex || null, lp ? lp.lat : a.lat, lp ? lp.lon : a.lon, label);
}
function pray(a) {
  if (!a) return;
  prayFor = a;
  const key = a.sq && PRAYERS[a.sq] ? a.sq : a.region === 'easternmed' ? 'israel' : 'any';
  $('#sqptext').textContent = PRAYERS[key][0];
  $('#sqpverse').textContent = PRAYERS[key][1];
  $('#sqpray').classList.add('on'); $('#sqpray').setAttribute('aria-hidden', 'false');
}
function closePray() { $('#sqpray').classList.remove('on'); $('#sqpray').setAttribute('aria-hidden', 'true'); }
$('#sqpamen').onclick = () => {
  if (prayFor && prayFor.id) { prayed.add(prayFor.id); store('wr_prayed', prayed); }
  closePray(); WR.toast('Amen \u{1F64F}'); render();
};
$('#sqpclose').onclick = closePray;
$('#sqpray').onclick = ev => { if (ev.target.id === 'sqpray') closePray(); };

// ------------------------------------------------------------ open / close
function setHash(h) { try { history.replaceState(null, '', location.pathname + location.search + h); } catch (e) { /* ignore */ } }
function markSeen() {
  allSquawks().forEach(s => seen.add(s.id)); store('wr_sqseen', seen); badge();
}
function open(f, wantPray) {
  focus = f || null;
  isOpen = true;
  const el = $('#sqs');
  el.classList.add('open'); el.setAttribute('aria-hidden', 'false');
  document.querySelectorAll('.tabs button').forEach(b => b.classList.toggle('on', b.dataset.go === 'sq'));
  render();
  $('#sqscroll').scrollTop = 0;
  const card = $('#sqfeat .nt.hi');
  if (f && card) { card.classList.add('flashme'); setTimeout(() => card.classList.remove('flashme'), 3400); }
  if (wantPray && f) setTimeout(() => pray(byId[f.id] || f.data), 250);
  markSeen();
}
function close(keepTab) {
  if (!isOpen) return;
  isOpen = false; focus = null; closePray();
  const el = $('#sqs');
  el.classList.remove('open'); el.setAttribute('aria-hidden', 'true');
  if (/^#(squawks|alert\/)/.test(location.hash)) setHash('');
  if (!keepTab) WR.showTab(WR.lastTab || 'map');
}
$('#closeSq').onclick = () => close();
$('#openSq').onclick = () => { setHash('#squawks'); open(null); };
document.addEventListener('keydown', ev => { if (ev.key === 'Escape' && isOpen) { if ($('#sqpray').classList.contains('on')) closePray(); else close(); } });
document.querySelectorAll('.tabs button').forEach(b => {
  if (b.dataset.go === 'sq') b.onclick = () => { if (isOpen) return; setHash('#squawks'); open(null); };
  else b.addEventListener('click', () => { if (isOpen) { isOpen = false; focus = null; $('#sqs').classList.remove('open'); $('#sqs').setAttribute('aria-hidden', 'true'); setHash(''); } }, true);
});

function badge() {
  const b = $('#sqBadge');
  if (!b) return;
  const now = Date.now() / 1000;
  const fresh = allSquawks().some(s => !seen.has(s.id) && now - (s.ts || 0) < 86400);
  b.classList.toggle('on', fresh && !isOpen);
}

// ------------------------------------------------------------ routes
function route() {
  const h = decodeURIComponent(location.hash || '');
  let m;
  if ((m = h.match(/^#track\/([^/]+)\/(-?[\d.]+)\/(-?[\d.]+)/))) {
    close(true); setHash('');
    const lp = livePlane(m[1]);
    const go = () => WR.trackPlane(m[1] === 'x' ? null : m[1], lp ? lp.lat : +m[2], lp ? lp.lon : +m[3], 'Tracked from your alert');
    if (WR.live) go(); else { const once = () => { WR.hooks.splice(WR.hooks.indexOf(once), 1); WR.trackPlane(m[1] === 'x' ? null : m[1], +m[2], +m[3], 'Tracked from your alert'); }; WR.hooks.push(once); }
    return;
  }
  if ((m = h.match(/^#alert\/([^/]+)(?:\/([A-Za-z0-9_-]{8,}))?(\/pray)?/))) {
    const data = m[2] ? decodeBlob(m[2]) : null;
    open({id: m[1], data: data || {id: m[1], what: 'Alert on its way', ts: 0}}, !!m[3]);
    return;
  }
  if (/^#squawks?$/.test(h)) open(null);
}
window.addEventListener('hashchange', route);

// ------------------------------------------------------------ data refresh (rides the radar's 1-minute refresh)
async function pull() {
  try {
    const d = await WR.getJSON('squawks.json');
    squawks = (d && d.squawks || []).filter(s => s && s.id && CODES[s.sq]);
  } catch (e) { /* no squawk log yet: alerts.json still feeds the screen */ }
  loaded = true;
  badge();
  if (isOpen) {
    const y = $('#sqscroll').scrollTop, openIds = [...document.querySelectorAll('#sqlist .nt.open')].map(x => x.dataset.id);
    render();
    openIds.forEach(id => { const el = document.getElementById('sq-' + id); if (el && !el.classList.contains('hi')) el.classList.add('open'); });
    $('#sqscroll').scrollTop = y;
  }
}
WR.hooks.push(pull);
route();
})();
