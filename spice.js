/* WATCHMAN RADAR // round two spice-ups: silver over satellite, threat gauge, world clock,
   custom plane icons, alert sounds, verse ticker, scan lines + glitch */
(() => {
'use strict';
const WR = window.WR;
const $ = s => document.querySelector(s);
const FX_KEY = 'wr_fx';
const fx = Object.assign({sound: true, shofar: true, scan: true, ticker: true}, JSON.parse(localStorage.getItem(FX_KEY) || '{}'));
const saveFx = () => localStorage.setItem(FX_KEY, JSON.stringify(fx));
const el = (tag, cls, html) => { const e = document.createElement(tag); if (cls) e.className = cls; if (html != null) e.innerHTML = html; return e; };

const TIPS = {
  icons: 'Each kind of plane has its own shape on the map, so you can tell them apart at a glance. A plane from another country\'s military shows in red.',
  sounds: 'When a new alert comes in while the radar is open, it plays a sound: a ping for FYI, a double beep for Important, a klaxon for Urgent, and a shofar for anything over Israel. iPhone needs one tap on the radar first before it can play sound, and the ringer switch has to be on.',
  wclock: 'The time right now at home in Jackson, in Jerusalem, in Tehran, and Zulu (the time pilots and the military use).',
};
if (window.TIPS_EXTRA) Object.assign(window.TIPS_EXTRA, TIPS); else window.TIPS_EXTRA = TIPS;

// ---------------------------------------------------------------- satellite background (see-through panels sit on it)
document.body.classList.add('th-silver');
document.body.prepend(el('div', 'satbg'));

// ---------------------------------------------------------------- world clock
const CLOCKS = [['JACKSON', 'America/Chicago', 1], ['JERUSALEM', 'Asia/Jerusalem'], ['TEHRAN', 'Asia/Tehran'], ['ZULU', 'UTC']];
const wc = el('div', 'wclock', CLOCKS.map(([n, tz, home]) => `<span class="${home ? 'home' : ''}"><i>${n}</i><b data-tz="${tz}">--:--</b></span>`).join('') +
  `<button class="sndbtn" id="sndBtn" aria-label="Alert sounds on or off"></button>`);
$('.top').appendChild(wc);
function tickClocks() {
  const d = new Date();
  wc.querySelectorAll('b[data-tz]').forEach(b => {
    const tz = b.dataset.tz;
    b.textContent = tz === 'UTC' ? d.toISOString().substr(11, 5).replace(':', '') + 'Z'
      : d.toLocaleTimeString('en-US', {timeZone: tz, hour: 'numeric', minute: '2-digit'});
  });
}
setInterval(tickClocks, 1000); tickClocks();

// ---------------------------------------------------------------- big threat gauge
const GA = {NORMAL: -60, ELEVATED: 0, HIGH: 60};
const gauge = el('div', 'gauge', `
<svg viewBox="0 0 300 172" aria-hidden="true">
  <defs><filter id="gglow" x="-30%" y="-30%" width="160%" height="160%"><feGaussianBlur stdDeviation="3" result="b"/><feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge></filter></defs>
  <path class="gz n" d="M40 150 A110 110 0 0 1 95 54.7"/>
  <path class="gz e" d="M97.5 53.4 A110 110 0 0 1 202.5 53.4"/>
  <path class="gz h" d="M205 54.7 A110 110 0 0 1 260 150"/>
  ${Array.from({length: 13}, (_, i) => `<line class="gt" data-a="${-90 + i * 15}" data-r1="124" data-r2="${i % 2 ? 130 : 134}"/>`).join('')}
  <text class="gl" x="34" y="168">NORMAL</text><text class="gl" x="150" y="22" text-anchor="middle">ELEVATED</text><text class="gl" x="266" y="168" text-anchor="end">HIGH</text>
  <text class="gv" id="gVal" x="150" y="118" text-anchor="middle">----</text>
  <g class="gneedle" id="gNeedle"><line x1="150" y1="150" x2="150" y2="52"/><circle cx="150" cy="150" r="10"/><circle class="hub" cx="150" cy="150" r="4"/></g>
</svg>
<div class="gcap" id="gCap">Waiting for the first check&hellip;</div>`);
// place tick marks around the dial
gauge.querySelectorAll('.gt').forEach(t => { const a = +t.dataset.a * Math.PI / 180, r1 = +t.dataset.r1, r2 = +t.dataset.r2;
  t.setAttribute('x1', 150 + r1 * Math.sin(a)); t.setAttribute('y1', 150 - r1 * Math.cos(a)); t.setAttribute('x2', 150 + r2 * Math.sin(a)); t.setAttribute('y2', 150 - r2 * Math.cos(a)); });
const gp = el('div', 'ptitle', 'THREAT GAUGE <span>// last 6 hours of alerts</span> <button class="i" data-tip="threat" aria-label="What is this?">i</button>');
const scopeP = $('.scopepanel'), sw = $('.scopewrap');
sw.after(gp); gp.after(gauge);
let gLevel = null, gBase = -88;
const needle = $('#gNeedle');
function setNeedle(deg, swing) { needle.style.transition = swing ? 'transform 1.6s cubic-bezier(.34,1.56,.64,1)' : 'transform .9s ease-in-out'; needle.style.transform = `rotate(${deg}deg)`; }
setNeedle(gBase, false);
function updateGauge() {
  const b = $('#threatcon b'); const lv = b ? b.textContent.trim() : '';
  if (!GA.hasOwnProperty(lv)) return;
  const cap = {NORMAL: 'All quiet. No important or urgent alerts in the last 6 hours.', ELEVATED: 'At least one Important alert in the last 6 hours.', HIGH: 'An Urgent alert came in within the last 6 hours.'}[lv];
  if (lv !== gLevel) { gLevel = lv; gBase = GA[lv]; setNeedle(gBase, true); }
  $('#gVal').textContent = lv; gauge.dataset.lv = lv; $('#gCap').textContent = cap;
}
// the needle trembles a hair, like a real gauge
setInterval(() => { if (gLevel && !document.hidden) setNeedle(gBase + (Math.random() * 3 - 1.5), false); }, 2200);

// ---------------------------------------------------------------- custom plane icons (shapes from the preview)
const fus = (w = 4, l0 = 6, l1 = 94) => `<path d="M50 ${l0} C${50 + w} ${l0 + 5} ${50 + w} ${l0 + 12} ${50 + w} ${l0 + 18} L${50 + w} ${l1 - 10} C${50 + w} ${l1 - 4} ${50 + w / 2} ${l1 - 1} 50 ${l1} C${50 - w / 2} ${l1 - 1} ${50 - w} ${l1 - 4} ${50 - w} ${l1 - 10} L${50 - w} ${l0 + 18} C${50 - w} ${l0 + 12} ${50 - w} ${l0 + 5} 50 ${l0}Z"/>`;
const mir = d => `<path d="${d}"/><path d="${d}" transform="translate(100 0) scale(-1 1)"/>`;
const SHAPES = {
  tanker: fus(4) + mir('M54 38 L92 60 L92 64 L54 52Z') + mir('M54 80 L68 89 L68 92 L54 88Z') + mir('M64 47 h5 v9 h-5z') + mir('M78 55 h5 v8 h-5z') + '<path d="M49 92 L46 100 L48 100 L51 93Z"/>',
  airlift: fus(6.5, 8, 90) + mir('M56 34 L95 49 L95 54 L56 46Z') + mir('M56 84 L76 82 L76 87 L56 90Z') + mir('M66 40 h5 v9 h-5z') + mir('M80 45 h5 v8 h-5z'),
  tactical: fus(5.5, 10, 88) + mir('M55 36 L92 40 L92 46 L55 45Z') + mir('M55 80 L72 80 L72 85 L55 86Z') + mir('M64 33 h5 v9 h-5z') + mir('M78 35 h5 v8 h-5z'),
  isr: fus(4) + '<circle cx="50" cy="10" r="5.5"/>' + mir('M54 38 L92 60 L92 64 L54 52Z') + mir('M54 80 L68 89 L68 92 L54 88Z') + mir('M54 20 h3 v14 h-3z') + mir('M64 47 h5 v9 h-5z'),
  awacs: fus(4) + '<ellipse cx="50" cy="60" rx="17" ry="6" fill-opacity=".9"/>' + mir('M54 38 L92 60 L92 64 L54 52Z') + mir('M54 80 L68 89 L68 92 L54 88Z') + mir('M64 47 h5 v9 h-5z'),
  b2: '<path d="M50 26 L97 60 L89 67 L79 61 L69 69 L59 63 L50 69 L41 63 L31 69 L21 61 L11 67 L3 60Z"/>',
  bomber: fus(4.5, 4, 94) + mir('M54 34 L94 70 L94 75 L54 56Z') + mir('M54 82 L70 92 L70 95 L54 91Z') + mir('M70 50 h5 v9 h-5z') + mir('M82 60 h5 v8 h-5z'),
  c2: fus(5.5) + '<ellipse cx="50" cy="22" rx="5.5" ry="10" opacity=".55" fill="#fff"/>' + mir('M55 38 L94 60 L94 64 L55 52Z') + mir('M55 80 L70 89 L70 92 L55 88Z') + mir('M64 47 h5 v9 h-5z') + mir('M79 55 h5 v8 h-5z'),
  drone: fus(2.5, 18, 92) + mir('M52 44 L98 47 L98 50 L52 50Z') + mir('M52 86 L64 96 L62 98 L51 90Z'),
};
const DRONES = new Set(['Q4', 'RQ4', 'GLHK', 'MQ9', 'Q9', 'MQ1', 'MQ1C', 'MQ4', 'MQ4C', 'MQ25', 'RQ7', 'RQ170', 'HRON', 'HERN', 'TB2', 'BAYK', 'AKNC', 'WK45', 'SKYG', 'MQ9B']);
const AWACS = new Set(['E3TF', 'E3CF', 'E767', 'E7WW', 'E737', 'E2', 'E2C', 'E2D', 'A50', 'KJ2K', 'SB20']);
const BOMBERS = new Set(['B52', 'B1', 'B1B', 'TU95', 'T95', 'TU22', 'T22M', 'TU60', 'T160', 'H6']);
// which picture a plane gets
function kindOf(p) {
  const t = String(p.t || '').toUpperCase();
  if (t === 'B2') return 'b2';
  if (DRONES.has(t)) return 'drone';
  if (p.cat === 'fighter') return 'fighter';
  if (p.cat === 'bomber' || BOMBERS.has(t)) return 'bomber';
  if (p.cat === 'c2') return 'c2';
  if (p.cat === 'tanker' || (t === 'B762' && (!p.nat || p.nat === 'US'))) return 'tanker';
  if (AWACS.has(t)) return 'awacs';
  if (p.cat === 'isr') return 'isr';
  if (p.cat === 'airlift') return 'airlift';
  if (p.cat === 'tactical') return 'tactical';
  return null;
}
const ICON_COL = {tanker: '#ffb000', airlift: '#38bdf8', tactical: '#7dd3fc', isr: '#c084fc', awacs: '#c084fc', fighter: '#a3ff3b', b2: '#ff3b3b', bomber: '#ff3b3b', c2: '#ff4fd8', drone: '#e6f57a'};
const ICON_SIZE = {tanker: 30, airlift: 30, tactical: 26, isr: 28, awacs: 28, fighter: 24, b2: 32, bomber: 32, c2: 30, drone: 28};
function shapeSvg(k, col, s) {
  return `<svg width="${s}" height="${s}" viewBox="0 0 100 100"><g fill="${col}" stroke="#000" stroke-width="5" stroke-linejoin="round" paint-order="stroke">${SHAPES[k]}</g></svg>`;
}
// app.js asks this for each plane on the map; null = keep the normal plane shape
window.WRI = {
  kindOf,
  icon(p, foreign) {
    const k = kindOf(p); if (!k) return null;
    const col = foreign ? '#ff3b3b' : ICON_COL[k], s = ICON_SIZE[k];
    if (k === 'fighter') return window.WRF ? {html: WRF.svg(col), size: s} : null;
    return {html: shapeSvg(k, col, s), size: s};
  },
};
// legend on the RADAR tab
const LEG = [['tanker', 'Refueling'], ['airlift', 'Big cargo'], ['isr', 'Spy'], ['fighter', 'Fighter'], ['b2', 'B-2 bomber'], ['c2', 'Nuclear command'], ['drone', 'Drone']];
const leg = el('div', 'legend', LEG.map(([k, n]) => `<div><span>${k === 'fighter' && window.WRF ? WRF.svg(ICON_COL[k]) : shapeSvg(k, ICON_COL[k], 40)}</span><b>${n}</b></div>`).join(''));
const stats = $('#stats');
const lt = el('div', 'ptitle', 'PLANE ICONS <span>// what each shape means on the map</span> <button class="i" data-tip="icons" aria-label="What is this?">i</button>');
stats.after(lt); lt.after(leg);

// ---------------------------------------------------------------- sounds (Web Audio, made on the fly, nothing to download)
let ac = null, unlocked = false;
function ctx() {
  if (!ac) { const C = window.AudioContext || window.webkitAudioContext; if (!C) return null; ac = new C(); }
  return ac;
}
function unlock() {
  // iPhone only lets a page make sound after a tap. The first tap anywhere wakes the speaker.
  try { if (navigator.audioSession) navigator.audioSession.type = 'playback'; } catch (e) {}
  const c = ctx(); if (!c) return;
  if (c.state !== 'running') c.resume();
  const b = c.createBuffer(1, 1, 22050), s = c.createBufferSource(); s.buffer = b; s.connect(c.destination); s.start(0);
  unlocked = true; paintSnd();
}
['pointerdown', 'touchend', 'keydown'].forEach(ev => document.addEventListener(ev, unlock, {passive: true}));
function out(c, vol) { const g = c.createGain(); g.gain.value = vol; const comp = c.createDynamicsCompressor(); g.connect(comp); comp.connect(c.destination); return g; }
function env(g, t, a, peak, hold, rel) { g.gain.setValueAtTime(0.0001, t); g.gain.exponentialRampToValueAtTime(peak, t + a); g.gain.setValueAtTime(peak, t + a + hold); g.gain.exponentialRampToValueAtTime(0.0001, t + a + hold + rel); }
const SOUNDS = {
  // FYI: a soft sonar ping with an echo
  ping(c, t) {
    const o = out(c, 1.3), dl = c.createDelay(1), fb = c.createGain(), wet = c.createGain();
    dl.delayTime.value = .32; fb.gain.value = .35; wet.gain.value = .5; dl.connect(fb); fb.connect(dl); dl.connect(wet); wet.connect(o);
    const osc = c.createOscillator(), g = c.createGain(); osc.type = 'sine'; osc.frequency.setValueAtTime(1480, t); osc.frequency.exponentialRampToValueAtTime(1180, t + 1.4);
    env(g, t, .006, .7, .02, 1.6); osc.connect(g); g.connect(o); g.connect(dl); osc.start(t); osc.stop(t + 2.4);
    return 2.6;
  },
  // IMPORTANT: double beep
  beep(c, t) {
    const o = out(c, 1.05);
    [0, .22].forEach(d => { const osc = c.createOscillator(), g = c.createGain(); osc.type = 'square'; osc.frequency.value = 1046; const f = c.createBiquadFilter(); f.type = 'lowpass'; f.frequency.value = 3200;
      env(g, t + d, .005, .45, .11, .03); osc.connect(f); f.connect(g); g.connect(o); osc.start(t + d); osc.stop(t + d + .2); });
    return .6;
  },
  // URGENT: klaxon, three rising whoops
  klaxon(c, t) {
    const o = out(c, .55);
    for (let i = 0; i < 3; i++) {
      const s = t + i * .62, a = c.createOscillator(), b = c.createOscillator(), g = c.createGain(), f = c.createBiquadFilter();
      a.type = 'sawtooth'; b.type = 'square'; f.type = 'lowpass'; f.frequency.value = 2400;
      a.frequency.setValueAtTime(330, s); a.frequency.linearRampToValueAtTime(660, s + .48); b.frequency.setValueAtTime(333, s); b.frequency.linearRampToValueAtTime(664, s + .48);
      env(g, s, .02, .5, .42, .06); a.connect(f); b.connect(f); f.connect(g); g.connect(o); a.start(s); b.start(s); a.stop(s + .56); b.stop(s + .56);
    }
    return 2;
  },
  // ISRAEL: shofar blast (tekiah): breathy horn that bends up into a long note and rises at the end
  shofar(c, t) {
    const o = out(c, .8), dur = 2.6, base = 233;
    const osc = c.createOscillator(), osc2 = c.createOscillator(), g = c.createGain();
    osc.type = 'sawtooth'; osc2.type = 'sawtooth';
    const fr = osc.frequency; fr.setValueAtTime(base * .78, t); fr.exponentialRampToValueAtTime(base, t + .28); fr.setValueAtTime(base, t + dur - .55); fr.exponentialRampToValueAtTime(base * 1.5, t + dur - .25); fr.setValueAtTime(base * 1.5, t + dur);
    const f2 = osc2.frequency; f2.setValueAtTime(base * .78 * 1.004, t); f2.exponentialRampToValueAtTime(base * 1.004, t + .28); f2.setValueAtTime(base * 1.004, t + dur - .55); f2.exponentialRampToValueAtTime(base * 1.5 * 1.004, t + dur - .25);
    const vib = c.createOscillator(), vg = c.createGain(); vib.frequency.value = 5.2; vg.gain.value = 2.2; vib.connect(vg); vg.connect(fr); vg.connect(f2);
    // horn body: two formant peaks plus a gentle top cut
    const f1 = c.createBiquadFilter(); f1.type = 'peaking'; f1.frequency.value = 700; f1.Q.value = 2; f1.gain.value = 9;
    const fb = c.createBiquadFilter(); fb.type = 'peaking'; fb.frequency.value = 1500; fb.Q.value = 3; fb.gain.value = 6;
    const lp = c.createBiquadFilter(); lp.type = 'lowpass'; lp.frequency.setValueAtTime(900, t); lp.frequency.linearRampToValueAtTime(2600, t + .35); lp.frequency.setValueAtTime(2600, t + dur - .3); lp.frequency.linearRampToValueAtTime(1200, t + dur);
    osc.connect(f1); osc2.connect(f1); f1.connect(fb); fb.connect(lp); lp.connect(g); g.connect(o);
    g.gain.setValueAtTime(0.0001, t); g.gain.exponentialRampToValueAtTime(.42, t + .12); g.gain.linearRampToValueAtTime(.36, t + dur - .5); g.gain.linearRampToValueAtTime(.46, t + dur - .2); g.gain.exponentialRampToValueAtTime(0.0001, t + dur + .15);
    // breath
    const n = c.createBuffer(1, c.sampleRate * (dur + .2), c.sampleRate), nd = n.getChannelData(0); for (let i = 0; i < nd.length; i++) nd[i] = Math.random() * 2 - 1;
    const ns = c.createBufferSource(), nf = c.createBiquadFilter(), ng = c.createGain(); ns.buffer = n; nf.type = 'bandpass'; nf.frequency.value = 1800; nf.Q.value = .8;
    ng.gain.setValueAtTime(0.0001, t); ng.gain.exponentialRampToValueAtTime(.09, t + .05); ng.gain.exponentialRampToValueAtTime(.025, t + .4); ng.gain.exponentialRampToValueAtTime(0.0001, t + dur + .1);
    ns.connect(nf); nf.connect(ng); ng.connect(o);
    [osc, osc2, vib, ns].forEach(x => { x.start(t); x.stop(t + dur + .25); });
    return dur + .4;
  },
};
function play(names, force) {
  if (!force && !fx.sound) return;
  const c = ctx(); if (!c) return;
  if (c.state !== 'running') c.resume();
  let t = c.currentTime + .05;
  for (const n of names) t += SOUNDS[n](c, t);
}
const sndBtn = $('#sndBtn');
function paintSnd() {
  sndBtn.classList.toggle('off', !fx.sound);
  sndBtn.innerHTML = fx.sound ? '&#128266;' : '&#128263;';
  sndBtn.title = fx.sound ? 'Alert sounds on' : 'Alert sounds off';
  document.querySelectorAll('[data-fx]').forEach(i => { i.checked = !!fx[i.dataset.fx]; });
}
sndBtn.onclick = e => { e.stopPropagation(); unlock(); fx.sound = !fx.sound; saveFx(); paintSnd(); WR.toast(fx.sound ? '\u{1F50A} Alert sounds ON' : '\u{1F507} Alert sounds OFF'); if (fx.sound) play(['ping']); };

// sounds + effects panel on the RADAR tab
const sp = el('div', 'fxbox', `
<div class="fxrow"><span><b>&#128266; Sound on new alerts</b><small>Plays while the radar is open</small></span><label class="tog"><input type="checkbox" data-fx="sound"><i></i></label></div>
<div class="fxsnd">
  <button data-play="ping" class="ro">&#9673; Sonar ping<small>FYI</small></button>
  <button data-play="beep" class="im">&#9835; Double beep<small>Important</small></button>
  <button data-play="klaxon" class="fl">&#9888; Klaxon<small>Urgent</small></button>
  <button data-play="shofar" class="go">&#10022; Shofar<small>Over Israel</small></button>
</div>
<div class="fxrow"><span><b>&#10022; Shofar for anything over Israel</b></span><label class="tog"><input type="checkbox" data-fx="shofar"><i></i></label></div>
<div class="fxrow"><span><b>&#128250; Scan lines</b><small>Old-monitor look, glitch on Urgent alerts</small></span><label class="tog"><input type="checkbox" data-fx="scan"><i></i></label></div>
<div class="fxrow"><span><b>&#128220; Verse ticker</b></span><label class="tog"><input type="checkbox" data-fx="ticker"><i></i></label></div>
<button class="fxglitch" id="fxGlitch">&#9889; Try the Urgent glitch</button>`);
const spt = el('div', 'ptitle', 'SOUNDS &amp; EFFECTS <span>// tap a sound to hear it</span> <button class="i" data-tip="sounds" aria-label="What is this?">i</button>');
leg.after(spt); spt.after(sp);
sp.querySelectorAll('[data-play]').forEach(b => b.onclick = () => { unlock(); play([b.dataset.play], true); });
sp.querySelectorAll('[data-fx]').forEach(i => i.onchange = () => { fx[i.dataset.fx] = i.checked; saveFx(); paintSnd(); applyFx(); if (i.dataset.fx === 'sound' && i.checked) { unlock(); play(['ping']); } });
$('#fxGlitch').onclick = () => glitch(true);

// ---------------------------------------------------------------- verse ticker
const tk = el('div', 'ticker', `<div class="tlab">VERSE</div><div class="tview"><div class="trun" id="trun"></div></div>`);
const VERSES = `<span>&ldquo;And when these things begin to come to pass, then look up, and lift up your heads; for your redemption draweth nigh.&rdquo; <em>LUKE 21:28</em></span><span class="dot">&#9670;</span>` +
  `<span>&ldquo;And what I say unto you I say unto all, Watch.&rdquo; <em>MARK 13:37</em></span><span class="dot">&#9670;</span>` +
  `<span class="gold">&ldquo;I have set watchmen upon thy walls, O Jerusalem, which shall never hold their peace day nor night.&rdquo; <em>ISAIAH 62:6</em></span><span class="dot">&#9670;</span>`;
const trun = tk.querySelector('#trun');
// a different verse leads each day
const parts = VERSES.split('<span class="dot">&#9670;</span>').filter(Boolean).map(s => s + '<span class="dot">&#9670;</span>');
const day = Math.floor((Date.now() - new Date().getTimezoneOffset() * 60000) / 86400000);
const lead = day % parts.length, ordered = parts.slice(lead).concat(parts.slice(0, lead)).join('');
trun.innerHTML = `<div class="tseg">${ordered}</div><div class="tseg" aria-hidden="true">${ordered}</div>`;
document.body.appendChild(tk);
tk.onclick = () => tk.classList.toggle('paused');

// ---------------------------------------------------------------- scan lines + glitch
const roll = el('div', 'scanroll'); document.body.appendChild(roll);
const gl = el('div', 'glitchfx', '<i></i><i></i><i></i><i></i>'); document.body.appendChild(gl);
function applyFx() {
  document.body.classList.toggle('noscan', !fx.scan);
  document.body.classList.toggle('noticker', !fx.ticker);
  setTimeout(() => window.dispatchEvent(new Event('resize')), 30);
}
function glitch(force) {
  if (!force && !fx.scan) return;
  document.body.classList.remove('glitching'); void document.body.offsetWidth;
  document.body.classList.add('glitching');
  clearTimeout(glitch._t); glitch._t = setTimeout(() => document.body.classList.remove('glitching'), 1100);
}

// ---------------------------------------------------------------- watch for new alerts (sound + glitch)
let known = null;
const overIsrael = a => a.region === 'easternmed' || /israel|jerusalem|tel aviv|gaza|west bank|golan|haifa/i.test([a.location, a.title, a.what].join(' ')) ||
  (a.lat != null && a.lat >= 29.4 && a.lat <= 33.4 && a.lon >= 34.2 && a.lon <= 35.95);
function onRefresh() {
  updateGauge();
  const list = (WR.alerts || []).filter(a => a.id && a.watch !== 'test');
  if (known === null) { known = new Set(list.map(a => a.id)); return; }
  const fresh = list.filter(a => !known.has(a.id)); fresh.forEach(a => known.add(a.id));
  if (!fresh.length) return;
  const tiers = new Set(fresh.map(a => a.tier));
  const seq = [tiers.has('FLASH') ? 'klaxon' : tiers.has('IMMEDIATE') ? 'beep' : 'ping'];
  if (fx.shofar && fresh.some(overIsrael)) seq.push('shofar');
  play(seq);
  if (tiers.has('FLASH')) glitch();
}
WR.hooks.push(onRefresh);
WR.fx = {play, glitch, overIsrael, updateGauge};

paintSnd(); applyFx();
if (WR.live) { onRefresh(); if (WR.drawPlanes) WR.drawPlanes(); }
})();
