// Undersea cables: the cable map layer, ships hanging over cables, the Cable Watch card and Top Finds lines.
// Cable lines: TeleGeography Submarine Cable Map (internet / data) + OpenStreetMap (power). Built by tools/build_cables.py.
(function () {
  if (!window.WR || !WR.map) return;
  const map = WR.map;
  const LS = 'wr_cables';
  let on = localStorage.getItem(LS) === '1';  // off until he taps 🌊 CABLES, then it remembers
  let data = null, loading = null, layer = null, shipLayer = null, legend = null, btn = null, watch = null;
  const lines = {};   // cable id -> [polyline, ...]
  const byId = {};
  const renderer = L.canvas({padding: 0.4, tolerance: 12});
  const COL = {net: '#22d3ee', pw: '#facc15', hl: '#ff8a1f', news: '#ff3b3b'};
  const HOME = [35.6145, -88.8139];
  const e = s => String(s == null ? '' : s).replace(/[&<>"']/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[c]));
  const tb = k => (typeof tipBtn === 'function' ? tipBtn(k) : '');
  const num = n => Number(n).toLocaleString('en-US');

  if (typeof TIPS === 'object') Object.assign(TIPS, {
    cables: 'Undersea cables lie on the ocean floor. Internet cables carry almost all the internet and phone traffic between countries; power cables carry electricity between countries and islands.',
    cablezone: 'Orange lines pass near Israel, the Eastern Mediterranean, the Suez Canal, the Red Sea or Bab el-Mandeb, the area this radar watches most closely.',
    powercable: 'A power cable carries electricity under the sea, for example between two countries. "High-voltage DC" ones send lots of power over long distances.',
    netcable: 'An internet cable is a bundle of glass fibers that carries internet, phone and bank traffic between countries at the speed of light.',
    cablenews: 'A red line means this cable was named in a cut, damage or sabotage news alert in the last 7 days.',
    cableships: 'Ships that sit almost still right over a cable, away from ports, for 30 minutes or more. Dragging an anchor is how many cables get cut. Live ships come from Finland\'s free ship feed, which covers the Gulf of Finland and the northern Baltic. Cable routes on public maps are only approximate, so "over a cable" means within about a mile.',
    cablelive: 'There is no free, reliable live ship feed for the Red Sea or the Eastern Mediterranean, so there the radar watches the news instead.',
    cablecheck: 'Every 10 minutes the radar checks the news for undersea cable cuts, damage, sabotage and spy ships, and checks the Baltic ship feed. Urgent and Important ones go to your phone like plane alerts.'
  });

  // ---------- helpers
  function miles(a1, o1, a2, o2) {
    const r = Math.PI / 180, R = 3958.8;
    const d = Math.sin((a2 - a1) * r / 2) ** 2 + Math.cos(a1 * r) * Math.cos(a2 * r) * Math.sin((o2 - o1) * r / 2) ** 2;
    return 2 * R * Math.asin(Math.sqrt(d));
  }
  function agoT(ts) {
    const s = Math.max(0, Date.now() / 1000 - ts);
    if (s < 3600) return Math.max(1, Math.round(s / 60)) + ' min ago';
    if (s < 86400) return Math.round(s / 3600) + ' hr ago';
    return Math.round(s / 86400) + ' days ago';
  }
  function cableAlerts(days) {
    const cut = Date.now() / 1000 - (days || 7) * 86400;
    return (WR.alerts || []).filter(a => (a.watch === 'cables' || a.watch === 'cableships') && (a.ts || 0) >= cut);
  }
  function newsById() {
    const m = {};
    cableAlerts(7).forEach(a => (a.cables || []).forEach(id => {
      if (a.tier !== 'ROUTINE' && (!m[id] || m[id].ts < a.ts)) m[id] = a;
    }));
    return m;
  }
  // keep every cable / ship box inside the visible map on a phone (above the tab bar), scrolling inside if long
  function popOpts() {
    const h = map.getSize().y;
    return {maxWidth: Math.min(290, map.getSize().x - 40), maxHeight: Math.max(160, h - 80), className: 'cbpopwrap',
      autoPanPaddingTopLeft: [10, 14], autoPanPaddingBottomRight: [10, 24]};
  }
  let cbPop = null;
  const syncCb = () => { const m = document.getElementById('map'); if (m) m.classList.toggle('cb-open', !!cbPop); };
  map.on('popupopen', ev => { cbPop = /cbpopwrap/.test(ev.popup.options.className || '') ? ev.popup : null; syncCb(); });
  map.on('popupclose', ev => { if (cbPop === ev.popup) cbPop = null; setTimeout(syncCb, 0); });
  const TAG = {FLASH: '\uD83D\uDFE5 Urgent', IMMEDIATE: '\uD83D\uDFE7 Important', ROUTINE: '\uD83D\uDFE6 FYI'};
  const whatP = a => (typeof plainWhat === 'function' ? plainWhat(a.what) : a.what);

  // ---------- styles
  function styleOf(c, news) {
    if (news) return {color: COL.news, weight: 3.6, opacity: 1, dashArray: null};
    if (c.hl) return {color: COL.hl, weight: c.k === 'pw' ? 3 : 2.6, opacity: 0.95, dashArray: c.pl ? '6 5' : null};
    if (c.k === 'pw') return {color: COL.pw, weight: 2.2, opacity: 0.85, dashArray: c.pl ? '5 5' : null};
    return {color: COL.net, weight: 1.4, opacity: 0.55, dashArray: c.pl ? '4 5' : null};
  }

  function popupHtml(c) {
    const news = newsById()[c.id];
    const kind = c.k === 'pw'
      ? `\u26A1 Undersea power cable${c.dc ? ' (high-voltage DC)' : ''}${c.kv ? `, ${c.kv} kV` : ''} ${tb('powercable')}`
      : `\uD83C\uDF10 Undersea internet cable ${tb('netcable')}`;
    let h = `<div class="cbpop"><b class="cbname">\uD83C\uDF0A ${e(c.n)}</b><div class="cbkind">${kind}</div>`;
    if (news) h += `<div class="cbnews">${TAG[news.tier] || ''}: in the news ${agoT(news.ts)} ${tb('cablenews')}<br><span>${e(news.headline || '')}</span></div>`;
    if (c.c && c.c.length) h += `<div class="cbrow"><em>Connects</em> ${e(c.c.join(' \u00B7 '))}</div>`;
    if (c.lp && c.lp.length) {
      const shown = c.lp.slice(0, 5).map(e).join('; ');
      h += `<div class="cbrow"><em>Comes ashore at</em> ${shown}${c.lp.length > 5 ? ` +${c.lp.length - 5} more` : ''}</div>`;
    }
    if (c.hl) h += `<div class="cbzone">\uD83D\uDFE0 Watch zone: passes ${e((c.z || []).join(', '))} ${tb('cablezone')}</div>`;
    const bits = [];
    if (c.len) {
      const km = parseFloat(String(c.len).replace(/,/g, ''));
      bits.push(isFinite(km) ? `${num(Math.round(km * 0.6214))} miles long` : e(c.len));
    }
    if (c.pl) bits.push(c.rfs ? `Planned for ${e(c.rfs)}` : 'Planned, not built yet');
    else if (c.rfs) bits.push(`In use since ${e(c.rfs)}`);
    if (c.hm != null) bits.push(`Closest point ${num(c.hm)} miles from home`);
    if (bits.length) h += `<div class="cbrow">${bits.join(' \u00B7 ')}</div>`;
    if (c.own) h += `<div class="cbown">Owned by ${e(c.own.length > 150 ? c.own.slice(0, 147) + '\u2026' : c.own)}</div>`;
    return h + '</div>';
  }

  // ---------- build the layer
  function load() {
    if (data) return Promise.resolve(data);
    if (!loading) loading = fetch('cables.json?v=' + (window.WR_VERSION || '1')).then(r => r.json()).then(d => { data = d; return d; });
    return loading;
  }
  function build() {
    layer = L.layerGroup();
    const news = newsById();
    data.cables.forEach(c => {
      byId[c.id] = c;
      lines[c.id] = c.g.map(seg => {
        const pl = L.polyline(seg, Object.assign({renderer, interactive: true, smoothFactor: 1.2}, styleOf(c, news[c.id])));
        pl.on('click', ev => {
          L.popup(popOpts()).setLatLng(ev.latlng).setContent(popupHtml(c)).openOn(map);
          highlight(c.id);
        });
        pl.addTo(layer);
        return pl;
      });
    });
    shipLayer = L.layerGroup();
  }
  let hiId = null;
  function highlight(id) {
    if (hiId && lines[hiId]) lines[hiId].forEach(pl => pl.setStyle(styleOf(byId[hiId], newsById()[hiId])));
    hiId = id;
    if (lines[id]) lines[id].forEach(pl => { pl.setStyle({weight: 5, opacity: 1}); pl.bringToFront(); });
  }
  map.on('popupclose', () => { if (hiId && lines[hiId]) { lines[hiId].forEach(pl => pl.setStyle(styleOf(byId[hiId], newsById()[hiId]))); hiId = null; } });
  function restyle() {
    if (!data || !layer) return;
    const news = newsById();
    Object.keys(news).forEach(id => { if (lines[id]) lines[id].forEach(pl => { pl.setStyle(styleOf(byId[id], news[id])); pl.bringToFront(); }); });
  }

  // ---------- ships over cables (Baltic live feed)
  const shipIcon = s => L.divIcon({className: 'cbship' + (s.list ? ' cbwatch' : '') + (s.hanging ? ' cbhang' : ''),
    html: '<span>\uD83D\uDEA2</span>', iconSize: [28, 28], iconAnchor: [14, 14]});
  function drawShips() {
    if (!shipLayer) return;
    shipLayer.clearLayers();
    const ships = (watch && watch.ais && watch.ais.ships) || [];
    ships.forEach(s => {
      const mph = Math.round((s.sog || 0) * 1.151);
      const h = `<div class="cbpop"><b class="cbname">\uD83D\uDEA2 ${e(s.name)}</b>` +
        `<div class="cbkind">${e(cap2(s.kind))}${s.flag ? `, flag of ${e(s.flag)}` : ''}${s.list ? ' \u00B7 <b class="cbred">on the watch list</b>' : ''}</div>` +
        `<div class="cbrow"><em>Doing</em> ${s.at_anchor ? 'Anchored' : `Barely moving (${mph} mph)`}${s.mins >= 5 ? ` for ${s.mins} min` : ', just spotted'}, about ${s.mi} miles from ${e(s.cphrase || s.cname)} ${tb('cableships')}</div>` +
        `<div class="cbrow"><em>Where</em> ${e(cap2(s.place))} \u00B7 ${num(s.home_mi)} miles from home</div>` +
        (s.dest ? `<div class="cbrow"><em>Says it\u2019s headed to</em> ${e(s.dest)}</div>` : '') +
        `<div class="cbown">Ships often wait at anchor for a port, so this can be harmless. From Finland\u2019s open ship feed.</div></div>`;
      L.marker([s.lat, s.lon], {icon: shipIcon(s), zIndexOffset: 500}).bindPopup(h, popOpts())
        .on('click', () => highlight(s.cable)).addTo(shipLayer);
    });
  }
  const cap2 = s => s ? s.charAt(0).toUpperCase() + s.slice(1) : '';

  // ---------- toggle button + legend
  function setBtn() { if (btn) { btn.classList.toggle('on', on); btn.setAttribute('aria-pressed', on ? 'true' : 'false'); } }
  function show() {
    load().then(() => {
      if (!layer) build();
      if (on) { layer.addTo(map); shipLayer.addTo(map); drawShips(); if (legend) legend.style.display = ''; restyle(); }
    }).catch(err => { console.error('cables layer', err); if (btn) btn.textContent = '\uD83C\uDF0A CABLES (offline)'; });
  }
  function hide() {
    if (layer) map.removeLayer(layer);
    if (shipLayer) map.removeLayer(shipLayer);
    if (legend) legend.style.display = 'none';
  }
  function toggle() {
    on = !on;
    localStorage.setItem(LS, on ? '1' : '0');
    setBtn();
    on ? show() : hide();
  }
  function addButton() {
    const box = document.querySelector('.ixlayers');
    btn = document.createElement('button');
    btn.className = 'cbbtn';
    btn.innerHTML = '\uD83C\uDF0A CABLES';
    btn.title = 'Show or hide undersea cables';
    btn.addEventListener('click', ev => { ev.preventDefault(); ev.stopPropagation(); toggle(); });
    if (box) box.appendChild(btn);
    else {
      const C = L.Control.extend({options: {position: 'topright'}, onAdd() { const d = L.DomUtil.create('div', 'ixlayers leaflet-bar'); d.appendChild(btn); L.DomEvent.disableClickPropagation(d); return d; }});
      new C().addTo(map);
    }
    const Lg = L.Control.extend({options: {position: 'bottomleft'}, onAdd() {
      const d = L.DomUtil.create('div', 'cblegend');
      d.innerHTML = `<span><i style="background:${COL.net}"></i>Internet</span><span><i style="background:${COL.pw}"></i>Power</span>` +
        `<span><i style="background:${COL.hl}"></i>Israel / Red Sea</span><span><i style="background:${COL.news}"></i>In the news</span>${tb('cables')}`;
      L.DomEvent.disableClickPropagation(d);
      return d;
    }});
    legend = new Lg().addTo(map).getContainer();
    legend.style.display = 'none';
    setBtn();
  }
  // the intel layer buttons are created on page load; wait a moment so ours sits with them
  setTimeout(() => { addButton(); if (on) show(); }, 400);

  // ---------- Cable Watch card on the Alerts page
  function fly(lat, lon, z) { if (WR.showTab) WR.showTab('map'); setTimeout(() => map.flyTo([lat, lon], z || 6, {duration: 1}), 150); }
  WR.showCable = function (id) {
    if (!on) toggle();
    load().then(() => {
      if (!layer) build();
      const c = byId[id];
      if (!c) return;
      if (WR.showTab) WR.showTab('map');
      setTimeout(() => {
        const pts = [].concat(...c.g);
        map.flyToBounds(L.latLngBounds(pts), {padding: [30, 30], maxZoom: 7, duration: 1});
        highlight(id);
        setTimeout(() => L.popup(popOpts()).setLatLng(pts[Math.floor(pts.length / 2)]).setContent(popupHtml(c)).openOn(map), 1100);
      }, 150);
    });
  };
  function drawCard() {
    const host = document.getElementById('cablewatch');
    if (!host) return;
    const ais = (watch && watch.ais) || {};
    const al = cableAlerts(7).slice(0, 4);
    let h = `<div class="ptitle">\uD83C\uDF0A CABLE WATCH ${tb('cablecheck')}</div><div class="cbcard">`;
    if (watch) {
      h += `<div class="cbline">\uD83D\uDDFA\uFE0F ${num(watch.cables || 0)} undersea cables on the map, ${num(watch.zone_cables || 0)} near Israel & the Red Sea</div>`;
      if (ais.ok) {
        const hang = (ais.ships || []).filter(s => s.hanging);
        h += `<div class="cbline">\uD83D\uDEA2 Live ships, Gulf of Finland & northern Baltic: ${num(ais.checked || 0)} checked, ` +
          (hang.length ? `<b class="cbred">${hang.length} hanging over cables</b>` : 'none hanging over cables right now') + ` ${tb('cableships')}</div>`;
        hang.slice(0, 3).forEach(s => {
          h += `<button class="cbitem" data-fly="${s.lat},${s.lon}">\uD83D\uDEA2 <b>${e(s.name)}</b>, ${e(s.kind)}${s.flag ? ' (' + e(s.flag) + ')' : ''}: ${s.at_anchor ? 'anchored' : 'barely moving'}${s.mins >= 5 ? ` ${s.mins} min` : ''} over ${e(s.cphrase || s.cname)}</button>`;
        });
      } else h += `<div class="cbline">\uD83D\uDEA2 The Baltic ship feed didn\u2019t answer on the last check.</div>`;
      h += `<div class="cbline cbsoft">Red Sea & Eastern Med: watched through the news ${tb('cablelive')}</div>`;
    } else h += `<div class="cbline">The first cable check runs within 10 minutes.</div>`;
    if (al.length) {
      h += `<div class="cbsub">Cable news, last 7 days</div>`;
      al.forEach(a => {
        const dist = a.lat != null ? ` \u00B7 ${num(Math.round(miles(HOME[0], HOME[1], a.lat, a.lon)))} mi` : '';
        const tgt = (a.cables && a.cables.length) ? `data-cable="${e(a.cables[0])}"` : (a.lat != null ? `data-fly="${a.lat},${a.lon}"` : '');
        h += `<button class="cbitem" ${tgt}><span class="cbtag">${TAG[a.tier] || ''}</span> <b>${e(whatP(a))}</b><br><span class="cbhl">${e(a.headline || '')}</span><br><small>${agoT(a.ts)}${dist}</small></button>`;
      });
    } else h += `<div class="cbsub">No cable cuts or damage in the news in the last 7 days \uD83D\uDE4F</div>`;
    host.innerHTML = h + '</div>';
  }
  document.addEventListener('click', ev => {
    const b = ev.target.closest && ev.target.closest('[data-cable],.cbitem[data-fly]');
    if (!b || ev.target.closest('.i')) return;
    if (b.dataset.cable) { ev.preventDefault(); WR.showCable(b.dataset.cable); }
    else if (b.classList.contains('cbitem') && b.dataset.fly) { ev.preventDefault(); const [a, o] = b.dataset.fly.split(',').map(Number); if (!on) toggle(); fly(a, o, 8); }
  });

  // ---------- Top Finds: today's cable lines (called from drawTopFinds)
  window.cableTopFinds = function (t) {
    const cf = (t && t.cables) || [];
    let h = `<div class="tfcab"><div class="tfcabt">\uD83C\uDF0A Undersea cables today</div>`;
    if (!cf.length) return h + `<div class="tfcabn">No cable cuts, damage or ships hanging over cables today.</div></div>`;
    cf.slice(0, 3).forEach(f => {
      const tgt = (f.cables && f.cables.length) ? `data-cable="${e(f.cables[0])}"` : '';
      h += `<button class="cbitem" ${tgt}><span class="cbtag">${TAG[f.tier] || ''}</span> <b>${e(whatP(f))}</b>${f.headline ? `<br><span class="cbhl">${e(f.headline)}</span>` : ''}${f.pushed ? '<br><small>Sent to your phone</small>' : ''}</button>`;
    });
    return h + '</div>';
  };

  // ---------- refresh with the rest of the radar
  function refresh() {
    WR.getJSON('cablewatch.json').then(d => { watch = d; drawShips(); drawCard(); }).catch(() => drawCard());
    restyle();
  }
  WR.hooks.push(refresh);
  setTimeout(refresh, 600);
})();
