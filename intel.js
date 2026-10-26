/* WATCHTOWER round two: INTEL screen, map layers, mission decoder, Hear the pilots, Nightwatch red screen. */
(() => {
'use strict';
const WR = window.WR;
if (!WR) return;
const $ = s => document.querySelector(s);
const esc = s => String(s == null ? '' : s).replace(/[&<>"']/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[c]));
const HOME = [35.6145, -88.8139];
const LIVEATC_HF = 'https://www.liveatc.net/search/?icao=hf';
let intel = null, missions = null, feeds = [], isOpen = false, openSec = {};

function ago(ts) {
  const s = Math.max(0, Date.now() / 1000 - ts);
  if (s < 90) return 'just now';
  if (s < 3600) return Math.round(s / 60) + ' min ago';
  if (s < 86400) return Math.round(s / 3600) + ' hr ago';
  const d = Math.round(s / 86400);
  return d + (d === 1 ? ' day ago' : ' days ago');
}
function when(ts) {
  const d = new Date(ts * 1000);
  return d.toLocaleString([], {month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit', timeZone: 'America/Chicago'}) + ' CT';
}
function miles(a, b, c, d) {
  const r = x => x * Math.PI / 180, p1 = r(a), p2 = r(c), dp = r(c - a), dl = r(d - b);
  const h = Math.sin(dp / 2) ** 2 + Math.cos(p1) * Math.cos(p2) * Math.sin(dl / 2) ** 2;
  return 2 * 3958.8 * Math.asin(Math.min(1, Math.sqrt(h)));
}
async function getJSON(path) {
  try { const r = await fetch(path + (path.includes('?') ? '&' : '?') + 't=' + Date.now(), {cache: 'no-store'}); return r.ok ? r.json() : null; }
  catch (e) { return null; }
}

// ---------------------------------------------------------------- mission decoder
function decode(cs, t, cat) {
  if (!missions) return null;
  cs = (cs || '').toUpperCase().replace(/\s/g, ''); t = (t || '').toUpperCase();
  const word = (cs.match(/^[A-Z]+/) || [''])[0];
  let best = null;
  for (const [pre, m, u, d] of missions.callsigns) {
    if (word === pre || (pre.length >= 3 && word.startsWith(pre) && word.length <= pre.length + 1))
      if (!best || pre.length > best[0].length) best = [pre, m, u, d];
  }
  const ti = missions.types[t];
  if (best) return {m: best[1], u: best[2], d: best[3], by: 'callsign ' + best[0], t: ti ? ti[0] : null};
  if (ti) return {m: ti[0], u: ti[1], d: ti[2], by: 'aircraft type ' + t};
  const c = missions.cats[cat || ''];
  return c ? {m: c[0], u: c[1], d: c[2], by: 'category'} : null;
}
function nearestFeed(lat, lon) {
  let best = null;
  for (const f of feeds) {
    const d = miles(lat, lon, f[2], f[3]);
    if (!best || d < best.d) best = {icao: f[0], name: f[1], d};
  }
  return best;
}
WR.popupExtra = p => {
  let h = '';
  const d = decode(p.cs, p.t, p.cat);
  let pd = null;
  try { pd = window.WRD ? window.WRD.doing(p, (WR.live && WR.live.planes) || [], missions, WR.live && WR.live.updated) : null; } catch (e) { pd = null; }
  if (d || pd) {
    let tipK = '';
    if (d && d.d && window.TIPS_EXTRA) { tipK = 'ms_' + String(d.m).replace(/[^A-Za-z0-9]/g, ''); window.TIPS_EXTRA[tipK] = d.d; }
    const tb = k => (typeof tipBtn === 'function' ? tipBtn(k) : '');
    h += `<div class="ixmis">` +
      (d ? `<b>&#127919; ${esc(d.m)}</b>${tipK ? tb(tipK) : ''}${d.u ? `<br><span>${esc(d.u)}</span>` : ''}` : '') +
      (pd ? `<div class="pdo"><em>Probably doing:</em> ${esc(pd.line)}.</div>${pd.why ? `<div class="pdw">${esc(pd.why)}</div>` : ''}` : d ? `<br><i>${esc(d.d)}</i>` : '') +
      `<small>${pd ? 'Worked out from its ' + esc(pd.by) : 'Decoded from ' + esc(d.by)}${pd ? tb('doing') : ''}</small></div>`;
  }
  if (feeds.length && p.lat != null) {
    const f = nearestFeed(p.lat, p.lon);
    if (f) {
      const far = f.d > 400;
      h += `<a class="ixatc" target="_blank" rel="noopener" href="https://www.liveatc.net/search/?icao=${f.icao}">&#127911; Hear the pilots: ${esc(f.name)} (${f.icao}), ${Math.round(f.d).toLocaleString()} mi</a>`;
      if (far) h += `<a class="ixatc" target="_blank" rel="noopener" href="${LIVEATC_HF}">&#127754; Over the ocean? Try LiveATC's HF oceanic feeds</a>`;
    }
  }
  return h;
};

// ---------------------------------------------------------------- map layers
const map = WR.map;
const layers = {jam: L.layerGroup(), tfr: L.layerGroup(), bridge: L.layerGroup()};
const layerOn = (() => { try { return Object.assign({jam: true, tfr: true, bridge: true}, JSON.parse(localStorage.getItem('wr_layers') || '{}')); } catch (e) { return {jam: true, tfr: true, bridge: true}; } })();
function jamColor(p) { return p >= 60 ? '#ff3b3b' : p >= 30 ? '#ff8a1a' : p >= 10 ? '#ffd21a' : '#39ff8f'; }
function drawLayers() {
  if (!map || !intel) return;
  Object.values(layers).forEach(l => l.clearLayers());
  const now = Date.now() / 1000;
  for (const [la, lo, bad, tot] of ((intel.gps || {}).cells || [])) {
    if (tot < 3) continue;
    const p = Math.round(100 * bad / tot);
    L.rectangle([[la, lo], [la + 1, lo + 1]], {color: jamColor(p), weight: 0.6, fillOpacity: p >= 10 ? 0.35 : 0.12, interactive: true})
      .bindPopup(`<div class="pp"><b>&#128225; GPS check</b><br>${bad} of ${tot} planes in this square report poor GPS (${p}%).<br><small>From each plane's own GPS-quality report. Higher means more jamming or spoofing.</small></div>`)
      .addTo(layers.jam);
  }
  for (const r of (intel.tfr || [])) {
    const isNew = now - r.first < 86400;
    if (!r.watch && !isNew) continue;
    const style = r.watch ? {color: isNew ? '#ff3b3b' : '#ff8a1a', weight: isNew ? 2 : 1.2, dashArray: isNew ? '6 4' : null, fillOpacity: 0.12}
      : {color: '#7fb79a', weight: 1, fillOpacity: 0.05};
    for (const ring of r.rings) {
      L.polygon(ring, style).bindPopup(`<div class="pp"><b>&#9940; ${isNew ? 'NEW ' : ''}Sky closure: ${esc(r.type)}</b><br>${esc(r.desc)}<br>About ${Math.round(r.radius_mi)} mi from center to edge · ${r.home_mi.toLocaleString()} mi from home<br><small>FAA ${esc(r.id)} · first seen ${ago(r.first)}</small></div>`).addTo(layers.tfr);
    }
  }
  const b = intel.bridge;
  if (b && b.chain && b.chain.length >= 2) {
    L.polyline(b.chain.map(c => [c[0], c[1]]), {color: '#ffb000', weight: 2.5, dashArray: '2 8', lineCap: 'round'}).addTo(layers.bridge);
    b.chain.forEach(c => L.circleMarker([c[0], c[1]], {radius: 4, color: '#ffb000', fillOpacity: 0.9})
      .bindPopup(`<div class="pp"><b>&#9981; Tanker bridge</b><br>${esc(c[2] || 'tanker')} heading east</div>`).addTo(layers.bridge));
  }
  for (const k in layers) { if (layerOn[k]) layers[k].addTo(map); else map.removeLayer(layers[k]); }
}
if (map) {
  const Ctl = L.Control.extend({options: {position: 'topright'}, onAdd() {
    const d = L.DomUtil.create('div', 'ixlayers');
    d.innerHTML = [['jam', '&#128225; JAMMING'], ['tfr', '&#9940; CLOSURES'], ['bridge', '&#9981; BRIDGE']]
      .map(([k, l]) => `<button data-l="${k}" class="${layerOn[k] ? 'on' : ''}">${l}</button>`).join('');
    L.DomEvent.disableClickPropagation(d);
    d.querySelectorAll('button').forEach(btn => btn.onclick = () => {
      const k = btn.dataset.l; layerOn[k] = !layerOn[k]; btn.classList.toggle('on', layerOn[k]);
      try { localStorage.setItem('wr_layers', JSON.stringify(layerOn)); } catch (e) { /* private */ }
      drawLayers();
    });
    return d;
  }});
  new Ctl().addTo(map);
}

// ---------------------------------------------------------------- INTEL screen
function sec(id, icon, title, body, sub) {
  return `<section class="ixsec" id="ix-${id}"><h3>${icon} ${title}${sub ? `<small>${sub}</small>` : ''}</h3>${body}</section>`;
}
function render() {
  const el = $('#ixbody');
  if (!el) return;
  if (!intel) { el.innerHTML = '<div class="ixempty">Loading the intel feed&hellip;</div>'; return; }
  const now = Date.now() / 1000;
  let h = '';

  // Nightwatch + Looking Glass
  const c2 = intel.c2 || [];
  const e4 = c2.filter(p => p.t.startsWith('E4')), e6 = c2.filter(p => p.t === 'E6');
  if (e4.length) {
    const p = e4[0];
    h += `<div class="ixnw on"><div class="ixnwt">&#128308; NIGHTWATCH IS AIRBORNE</div><div>${esc(p.cs || p.hex)} · ${p.alt ? Math.round(p.alt).toLocaleString() + ' ft' : ''} ${p.gs ? '· ' + Math.round(p.gs) + ' kt' : ''}</div><div class="ixdim">Up since ${ago(p.from.ts)}, first seen at ${p.from.lat.toFixed(1)}, ${p.from.lon.toFixed(1)}</div><button data-fly="${p.lat},${p.lon}">Track it</button><div class="ixverse">“Blow ye the trumpet in Zion, and sound an alarm in my holy mountain.” Joel 2:1</div></div>`;
  } else {
    h += `<div class="ixnw"><div class="ixnwt">&#128994; NIGHTWATCH ON THE GROUND</div><div class="ixdim">No E-4B showing in the air.${e6.length ? ` ${e6.length} E-6 Mercury (Looking Glass / TACAMO) up right now.` : ' No E-6 Mercury showing either.'}</div></div>`;
  }

  // Convergence
  const cv = intel.convergence || {score: 0, signals: [], level: 'QUIET', hours: 6};
  const segs = [1, 2, 3, 4, 5].map(i => `<i class="${cv.score >= i ? (i >= 4 ? 'r' : i >= 3 ? 'o' : 'y') : ''}"></i>`).join('');
  h += sec('conv', '&#129513;', 'CONVERGENCE', `<div class="ixmeter"><div class="ixscore">${cv.score}<span>/5</span></div><div><div class="ixlvl lv${Math.min(cv.score, 4)}">${esc(cv.level)}</div><div class="ixsegs">${segs}</div></div></div>
    <p class="ixdim">Different kinds of signals inside ${cv.hours} hours. One alone is often routine. Three or more stacking is when it alarms.</p>
    ${cv.signals.length ? '<ul class="ixlist">' + cv.signals.map(s => `<li><b>${esc(s.name)}</b><span>${ago(s.ts)}</span><br><small>${esc(s.what)}</small></li>`).join('') + '</ul>' : '<p class="ixok">Nothing stacking right now.</p>'}`);

  // Deja vu
  const dv = intel.dejavu;
  let dvh = '';
  if (!dv || dv.warming) {
    dvh = `<p class="ixdim">Learning the last 24 hours. Needs 6 hours of sweeps first${dv ? ` (${dv.hours} so far)` : ''}.</p>`;
  } else if (dv.top && dv.top.length) {
    const t = dv.top[0];
    dvh = `<div class="ixdv"><div class="ixdvp">${t.pct}%</div><div>The last ${Math.round(dv.hours)} hours look most like <b>${esc(t.date)}</b><br><span>${esc(t.label)}</span></div></div>
      ${dv.typical != null ? `<p class="ixdim">Ordinary days usually score about ${dv.typical}% against these event days. Alarm sounds at 80% and at least 10 points above ordinary.</p>` : ''}
      ${t.shared.length ? `<p class="ixdim">Running high on both: ${t.shared.map(s => `${esc(s[0])} (${s[1]} now, ${s[2]} then)`).join(', ')}</p>` : ''}
      <ul class="ixbars">${dv.top.slice(0, 6).map(r => `<li><span>${esc(r.date)}</span><div><i style="width:${r.pct}%"></i></div><b>${r.pct}%</b><small>${esc(r.label)}</small></li>`).join('')}</ul>
      <p class="ixdim">Compared with ${dv.ref_days} real days from the public adsb.lol flight archives, run through the same math as the live radar.</p>`;
  }
  h += sec('dv', '&#128257;', 'DEJA VU', dvh);

  // Skyking listening post
  const e = intel.eam || {};
  const lst = (e.log || []).slice(0, 14).map((m, i) => `<li class="ixmsg" data-i="${i}"><div><span class="ixtag t${esc((m.label || '').replace(/\s/g, ''))}">${esc(m.label)}</span><b>${esc(m.sender || '')}</b><span>${ago(m.ts)}</span></div><code>${esc(m.message)}</code>
    <table class="ixparts${openSec['m' + i] ? ' on' : ''}">${(m.parts || []).map(p => `<tr><th>${esc(p[0])}</th><td><b>${esc(p[1])}</b><br><small>${esc(p[2])}</small></td></tr>`).join('')}
    <tr><th>Logged</th><td>${when(m.ts)}${m.rec && m.rec[0] ? ` · <a href="${esc(m.rec[0])}" target="_blank" rel="noopener">&#9654; Recording</a>` : ''}</td></tr></table></li>`).join('');
  const sk = e.last_skyking;
  h += sec('sk', '&#128251;', 'SKYKING LISTENING POST', `<a class="ixlisten" href="${esc(intel.listen_url)}" target="_blank" rel="noopener">&#127911; LISTEN LIVE · 8992 kHz</a>
    <p class="ixdim">Opens the University of Twente shortwave receiver already tuned to the main HFGCS channel.</p>
    <div class="ixstats"><div><b>${e.eam24 || 0}</b><span>EAMs in 24 hr</span></div><div><b>${e.normal || 0}</b><span>normal a day</span></div><div><b>${e.sk24 || 0}</b><span>Skykings in 24 hr</span></div></div>
    ${sk && sk.ts ? `<p class="ixdim">Last Skyking anyone logged: ${when(sk.ts)}${sk.message ? ` · “${esc(sk.message)}”` : ''}. EAMs are most of what's on the air now.</p>` : ''}
    <ul class="ixmsgs">${lst || '<li class="ixdim">No messages loaded yet.</li>'}</ul>
    <p class="ixdim">Tap a message for the code breakdown. From the public listener log at eam.watch, posted by hobbyists, so it can lag behind the air.</p>`);

  // GPS jamming
  const g = intel.gps || {};
  h += sec('gps', '&#128225;', 'GPS JAMMING', `<ul class="ixbars ixjam">${(g.zones || []).map(z => z.ok ? `<li><span>${esc(z.label)}</span><div><i style="width:${Math.max(2, z.pct)}%;background:${jamColor(z.pct)}"></i></div><b>${z.pct}%</b><small>${z.bad} of ${z.total} planes report poor GPS${z.base != null ? ` · normal about ${z.base}%` : ''}</small></li>` : `<li><span>${esc(z.label)}</span><small>Couldn't read this zone this time.</small></li>`).join('')}</ul>
    <button class="ixbtn" data-layer="jam">Show on map</button><p class="ixdim">Checked ${g.ts ? ago(g.ts) : '—'} from every plane's own GPS-quality report (adsb.lol).</p>`);

  // Sky closures
  const t = (intel.tfr || []).filter(r => r.watch).slice(0, 12);
  h += sec('tfr', '&#9940;', 'SKY CLOSURES', `${t.length ? '<ul class="ixlist">' + t.map(r => `<li data-fly="${r.lat},${r.lon}"><b>${now - r.first < 86400 ? '<span class="ixnew">NEW</span> ' : ''}${esc(r.type)} · ${esc(r.state)}</b><span>${r.home_mi.toLocaleString()} mi from home</span><br><small>${esc(r.desc)}</small><br><small>About ${Math.round(r.radius_mi)} mi center to edge · FAA ${esc(r.id)}</small></li>`).join('') + '</ul>' : '<p class="ixok">No security closures right now.</p>'}
    <p class="ixdim">Security, VIP and special-operations flight restrictions from the FAA. Tap one to see it on the map.</p>`);

  // Tanker bridge
  const b = intel.bridge;
  h += sec('br', '&#9981;', 'TANKER BRIDGE', b ? `<div class="ixstats"><div><b>${b.atl}</b><span>tankers eastbound over the Atlantic</span></div><div><b>${b.far}</b><span>over Europe / Med</span></div><div><b>${b.strength}</b><span>bridge strength</span></div></div>
    <p class="ixdim">${b.atl >= 4 ? 'A bridge is forming: tankers in a chain heading east.' : 'No bridge right now. It alarms at 4 or more tankers in a chain heading east.'}</p>${b.chain && b.chain.length > 1 ? '<button class="ixbtn" data-layer="bridge">Show the chain</button>' : ''}` : '<p class="ixdim">Waiting for the next sweep.</p>');

  // Reports
  const rp = intel.reports || {};
  const rep = (r, name, next) => r ? `<details class="ixrep"><summary>${esc(r.title)} <span>${ago(r.ts)}</span></summary><pre>${esc(r.body)}</pre></details>` : `<p class="ixdim">${name}: first one ${next}.</p>`;
  h += sec('rp', '&#128203;', 'REPORTS', rep(rp.morning, 'Morning report', 'at 7 AM') + rep(rp.sunday, 'Sunday report', 'Sunday at 8 PM') +
    '<p class="ixdim">Both ping his phone and land in ALERTS. Times and on/off live in COMMAND.</p>');

  h += `<p class="ixfoot">Updated ${intel.updated ? ago(intel.updated) : '—'} · “I will stand upon my watch, and set me upon the tower.” Habakkuk 2:1</p>`;
  el.innerHTML = h;

  el.querySelectorAll('.ixmsg').forEach(li => li.onclick = ev => {
    if (ev.target.closest('a')) return;
    const tb = li.querySelector('.ixparts'); tb.classList.toggle('on'); openSec['m' + li.dataset.i] = tb.classList.contains('on');
  });
  el.querySelectorAll('[data-fly]').forEach(x => x.onclick = ev => {
    if (ev.target.closest('a')) return;
    const [la, lo] = x.dataset.fly.split(',').map(Number);
    close(); WR.showTab('map'); setTimeout(() => map.flyTo([la, lo], 7, {duration: 1}), 120);
  });
  el.querySelectorAll('[data-layer]').forEach(x => x.onclick = () => {
    const k = x.dataset.layer; layerOn[k] = true; drawLayers();
    document.querySelectorAll(`.ixlayers [data-l="${k}"]`).forEach(bb => bb.classList.add('on'));
    close(); WR.showTab('map');
    setTimeout(() => {
      const bounds = L.featureGroup(layers[k].getLayers()).getBounds();
      if (bounds.isValid()) map.flyToBounds(bounds, {padding: [30, 30], duration: 1});
    }, 120);
  });
}
function open() {
  isOpen = true;
  const el = $('#ixs'); el.classList.add('open'); el.setAttribute('aria-hidden', 'false');
  document.querySelectorAll('.tabs button').forEach(b => b.classList.toggle('on', b.dataset.go === 'intel'));
  if (location.hash !== '#intel') history.replaceState(null, '', '#intel');
  render(); $('#ixbody').scrollTop = 0;
}
function close(keepTab) {
  if (!isOpen) return;
  isOpen = false;
  const el = $('#ixs'); el.classList.remove('open'); el.setAttribute('aria-hidden', 'true');
  if (location.hash === '#intel') history.replaceState(null, '', location.pathname + location.search);
  if (!keepTab) WR.showTab(WR.lastTab || 'map');
}
$('#closeIx').onclick = () => close();
const ob = $('#openIx'); if (ob) ob.onclick = open;
document.querySelectorAll('.tabs button').forEach(b => {
  if (b.dataset.go === 'intel') b.onclick = () => { if (!isOpen) open(); };
  else b.addEventListener('click', () => { if (isOpen) close(true); }, true);
});
document.addEventListener('keydown', ev => { if (ev.key === 'Escape' && isOpen) close(); });

// ---------------------------------------------------------------- Nightwatch red screen (from a tapped alert)
const BLOB = {i: 'id', t: 'ts', r: 'tier', w: 'what', c: 'cs', y: 'type', a: 'alt', g: 'gs', k: 'trk', la: 'lat', lo: 'lon', wa: 'watch', hl: 'headline', as: 'assets', h: 'hex'};
function decodeBlob(b) {
  try {
    b = b.replace(/-/g, '+').replace(/_/g, '/'); while (b.length % 4) b += '=';
    const bin = atob(b), bytes = new Uint8Array(bin.length);
    for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
    const d = JSON.parse(new TextDecoder().decode(bytes)), o = {};
    for (const [k, v] of Object.entries(d)) o[BLOB[k] || k] = v;
    return o;
  } catch (e) { return null; }
}
function nightwatch(a) {
  const el = $('#ixnw');
  el.innerHTML = `<div class="nwin"><div class="nwring"></div><div class="nwt">NIGHTWATCH</div><div class="nws">IS AIRBORNE</div>
    <div class="nwd">${esc(a.cs || 'E-4B')} · ${a.alt ? Math.round(a.alt).toLocaleString() + ' ft' : ''}${a.gs ? ' · ' + Math.round(a.gs) + ' kt' : ''}</div>
    <div class="nwd2">${esc(a.assets || '')}</div>
    <div class="nwd2">The flying Pentagon for the President and Defense Secretary. It also flies for training and VIP trips, so watch for other signals.</div>
    <div class="nwv">“Blow ye the trumpet in Zion, and sound an alarm in my holy mountain.”<br>Joel 2:1</div>
    <div class="nwb">${a.lat != null ? '<button id="nwTrack">Track it</button>' : ''}<button id="nwPray">Pray</button><button id="nwClose">Close</button></div></div>`;
  el.classList.add('on');
  const shut = () => el.classList.remove('on');
  $('#nwClose').onclick = shut;
  $('#nwPray').onclick = () => { shut(); const p = document.querySelector('#sqs [data-pray]'); if (p) p.click(); };
  const tr = $('#nwTrack');
  if (tr) tr.onclick = () => { shut(); if (WR.trackPlane) WR.trackPlane(a.hex, a.lat, a.lon, a.cs || 'NIGHTWATCH'); };
}
function route() {
  const m = location.hash.match(/^#alert\/([^/]+)/);
  if (m) { const a = decodeBlob(m[1]); if (a && a.watch === 'nightwatch') setTimeout(() => nightwatch(a), 300); }
  else if (location.hash === '#intel') open();
}
window.addEventListener('hashchange', route);

// ---------------------------------------------------------------- data
async function refresh() {
  const d = await getJSON(WR.DATA + 'intel.json');
  if (d) { intel = d; drawLayers(); if (isOpen) render(); }
  const dot = $('#ixBadge');
  if (dot && intel) dot.classList.toggle('on', ((intel.convergence || {}).score || 0) >= 3 || (intel.c2 || []).some(p => p.t.startsWith('E4')));
}
(async () => {
  const [m, f] = await Promise.all([getJSON('missions.json'), getJSON('liveatc.json')]);
  missions = m; feeds = f || [];
  await refresh();
  route();
  setInterval(refresh, 60000);
})();
WR.intel = {open, close, decode, nearestFeed, get data() { return intel; }};
})();
