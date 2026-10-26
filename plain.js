/* Watchman Radar - plain-English layer + tap-to-learn tips.
   Turns WATCHTOWER's radio-style codes into words anyone can read. Loaded before app.js. */
'use strict';

const TIERW = {FLASH: 'URGENT', IMMEDIATE: 'IMPORTANT', ROUTINE: 'FYI'};
const TIERC = {FLASH: 'fl', IMMEDIATE: 'im', ROUTINE: 'ro'};
const TIERI = {FLASH: '\u{1F7E5}', IMMEDIATE: '\u{1F7E7}', ROUTINE: '\u{1F7E6}'};
function tierTag(t) { return t && TIERW[t] ? `<span class="tag ${TIERC[t]}">${TIERI[t]} ${TIERW[t]}</span>` : ''; }
const tipBtn = k => `<button class="i" data-tip="${k}" aria-label="What is this?">i</button>`;
const escH = s => String(s == null ? '' : s).replace(/[&<>"']/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[c]));
const cap = s => s ? s.charAt(0).toUpperCase() + s.slice(1) : '';
const titleCase = s => String(s || '').toLowerCase().replace(/\b[a-z]/g, c => c.toUpperCase());

const PLACE = {alaska: 'Alaska', conus: 'the US', cuba: 'Cuba & the Caribbean', hawaii: 'Hawaii', europe: 'Europe',
  baltic: 'the Baltic & Scandinavia', ukraine: 'Ukraine & the Black Sea', easternmed: 'Israel & the Eastern Med',
  gulf: 'the Persian Gulf', pacific: 'the West Pacific & Taiwan'};
const SHORTKEY = {'ALASKA': 'alaska', 'US': 'conus', 'CUBA': 'cuba', 'HAWAII': 'hawaii', 'EUROPE': 'europe', 'BALTIC': 'baltic',
  'UKRAINE': 'ukraine', 'E. MED': 'easternmed', 'GULF': 'gulf', 'W. PACIFIC': 'pacific'};
function placeOf(s) { const k = SHORTKEY[String(s || '').trim().toUpperCase()]; return k ? PLACE[k] : titleCase(s); }
const NATN = {RU: 'Russian', CN: 'Chinese', IR: 'Iranian', CU: 'Cuban', KP: 'North Korean'};
const NEWSW = {
  'NUCLEAR / WAR DECLARATION': 'News: a nuclear attack or war declared', 'NUCLEAR DRILL': 'News: a nuclear drill',
  'MISSILE TEST': 'News: a missile test', 'BOMBERS NEAR US/EUROPE': 'News: bombers near the US or Europe',
  'TROOP BUILDUP': 'News: troops building up', 'MAJOR UKRAINE PUSH': 'News: a big push in Ukraine',
  'HORMUZ / GULF': 'News: trouble in the Persian Gulf', 'RUSSIA VS NATO': 'News: Russia testing NATO',
  'SUB WATCH': 'News: a submarine sighting', 'RUSSIA MOVES': 'News: Russia on the move',
  'CARRIER MOVES': 'News: an aircraft carrier on the move'};

// "AIRLIFT SURGE E. MED" -> "Lots of cargo planes over Israel & the Eastern Med"
function plainWhat(what) {
  const w = String(what || '').trim().replace(/\u2026$/, ''), U = w.toUpperCase();
  let m;
  if ((m = U.match(/^AIRLIFT SURGE (.+)$/))) return `Lots of cargo planes over ${placeOf(m[1])}`;
  if ((m = U.match(/^TANKER SURGE (.+)$/))) return `Refueling planes gathering over ${placeOf(m[1])}`;
  if ((m = U.match(/^TANKERS ACTIVE (.+)$/))) return `A few refueling planes over ${placeOf(m[1])}`;
  if ((m = U.match(/^HEAVY AIRLIFT ACTIVE (.+)$/))) return `A few big cargo planes over ${placeOf(m[1])}`;
  if ((m = U.match(/^US BOMBER OVER (.+)$/))) return `US bomber flying over ${placeOf(m[1])}`;
  if ((m = U.match(/^BOMBER AIRBORNE (.+)$/))) return `Bomber in the air over ${placeOf(m[1])}`;
  if (/^E-4B/.test(U)) return '"Doomsday" plane in the air (E-4B)';
  if (/^E-6B/.test(U)) return 'Nuclear command plane in the air (E-6B)';
  if ((m = U.match(/^(RUSSIAN|CHINESE|IRANIAN|CUBAN|NORTH KOREAN) (BOMBER|MIL AIRCRAFT) NEAR (.+)$/)))
    return `${titleCase(m[1])} ${m[2] === 'BOMBER' ? 'bomber' : 'military plane'} near ${placeOf(m[3])}`;
  if ((m = U.match(/^SUB HUNTERS UP (.+)$/))) return `Submarine-hunting planes up over ${placeOf(m[1])}`;
  if ((m = U.match(/^SPY PLANES ACTIVE (.+)$/))) return `Spy planes watching ${placeOf(m[1])}`;
  if ((m = U.match(/^MIL JET SQUAWKING (.+)$/)))
    return {'EMERGENCY': 'Military jet signaling an emergency', 'RADIO FAILURE': 'Military jet with radio trouble',
      'HIJACK CODE': 'Military jet sent the hijack code'}[m[1]] || 'Military jet sent a distress code';
  if (/^TEST/.test(U)) return 'Test alert: WATCHTOWER is online';
  if (/^END-OF-DAY RECAP/.test(U)) return 'Nightly recap of the day' + (/TEST/.test(U) ? ' (test)' : '');
  m = U.match(/^(.+?) - (.+)$/);
  const lab = m ? m[1] : U, rg = m ? m[2] : '';
  const wm = lab.match(/^WARSHIPS NEAR (.+)$/);
  if (wm) return 'News: foreign warships near ' + (wm[1] === 'US/CUBA' ? 'the US or Cuba' : placeOf(wm[1]));
  if (NEWSW[lab]) return NEWSW[lab] + (rg ? ` (${placeOf(rg)})` : '');
  return cap(w.toLowerCase());
}

const COORDS = /\s*\((?:center\s+)?-?\d+(?:\.\d+)?,\s*-?\d+(?:\.\d+)?\)/g;
// "Eastern Med / Israel (center 31.8, 33.1)" -> "Israel & the Eastern Med"
function plainPlace(loc, region) {
  if (region && PLACE[region]) return cap(PLACE[region].replace(/^the /, ''));
  const l = String(loc || '').replace(COORDS, '').trim();
  if (/^global/i.test(l) || /^all theaters/i.test(l)) return 'Worldwide';
  if (!l || /^unknown/i.test(l)) return 'Open water';
  return l.replace(/\s+\/\s+/g, ' & ');
}

const KIND = [
  [/^KC-|^K35|^KC10|MRTT|^A39M/i, 'refueling plane'], [/^C-17|^C-5|^A400M|^C-2\b/i, 'big cargo plane'],
  [/^C-130/i, 'small cargo plane'], [/^B-52|^B-1|^B-2|^TU-|^H-6/i, 'bomber'], [/^E-6|^E-4/i, 'nuclear command plane'],
  [/^E-3|^E-7|AWACS/i, 'flying radar plane'], [/^P-8|^P-3|Poseidon/i, 'sub-hunting plane'],
  [/^RC-135|^RQ-4|^MQ-9|^U-2/i, 'spy plane'], [/^F-\d|^F\/A|Typhoon/i, 'fighter jet'],
  [/Black Hawk|Chinook|helicopter|^H60|^H47/i, 'helicopter'], [/Texan|Goshawk|Talon|Tucano|^T-/i, 'training plane'],
  [/^KC-390/i, 'cargo & refueling plane'], [/^C-27/i, 'small cargo plane'],
  [/Boeing|Airbus|Gulfstream|Global|Citation|Hawker|Falcon|King Air/i, 'transport or VIP plane'],
  [/Cessna|Piper|Twin Otter/i, 'small prop plane'], [/Ground station/i, 'ground station, not a plane']];
function kindOf(type, cat) {
  for (const [rx, k] of KIND) if (rx.test(type || '')) return k;
  return CATK[cat] || 'military plane';
}
const CATK = {tanker: 'refueling plane', bomber: 'bomber', airlift: 'big cargo plane', tactical: 'small cargo plane', isr: 'spy & surveillance plane', c2: 'nuclear command plane', fighter: 'fighter jet', other: 'military plane'};
function plurl(n, w) { return n === 1 ? w : w + 's'; }

// "3x C-17 (RCH1, RCH2, RCH3) | 17,650 ft, 368 kt, hdg 7" -> groups + flight numbers
function parseAssets(s) {
  const [main, fly] = String(s || '').split(' | ');
  const groups = [];
  for (const part of String(main || '').split('; ')) {
    if (!part.trim()) continue;
    const m = part.match(/^(\d+)x (.+?)(?: \((.*)\))?$/);
    if (m) groups.push({n: +m[1], type: m[2], ids: (m[3] || '').split(', ').map(x => x.trim()).filter(Boolean)});
    else groups.push({text: part});
  }
  const f = {};
  if (fly) {
    const a = fly.match(/([\d,]+) ft/), k = fly.match(/(\d+) kt/), h = fly.match(/hdg (\d+)/);
    if (a) f.alt = +a[1].replace(/,/g, '');
    if (k) f.kt = +k[1];
    if (h) f.trk = +h[1];
  }
  return {groups, f};
}
function assetsLine(groups) {
  return groups.map(g => g.text ? g.text.replace(/military aircraft on the scope/, 'military planes on the radar')
    : `${g.n} ${g.type} ${plurl(g.n, kindOf(g.type))}`).join(', ');
}
function idsOf(groups) { return groups.flatMap(g => g.ids || []).map(x => x.replace(/^\+(\d+)$/, '+$1 more')); }
function idsBox(ids) {
  if (!ids.length) return '';
  return `<details class="ids"><summary>Show plane IDs ${tipBtn('planeid')}</summary><div>${ids.map(escH).join(' &middot; ')}</div></details>`;
}

const RAD = Math.PI / 180;
function miles(a1, o1, a2, o2) {
  const d = Math.sin((a2 - a1) * RAD / 2) ** 2 + Math.cos(a1 * RAD) * Math.cos(a2 * RAD) * Math.sin((o2 - o1) * RAD / 2) ** 2;
  return 3958.8 * 2 * Math.asin(Math.sqrt(d));
}
function bearing(a1, o1, a2, o2) {
  const y = Math.sin((o2 - o1) * RAD) * Math.cos(a2 * RAD);
  const x = Math.cos(a1 * RAD) * Math.sin(a2 * RAD) - Math.sin(a1 * RAD) * Math.cos(a2 * RAD) * Math.cos((o2 - o1) * RAD);
  return (Math.atan2(y, x) / RAD + 360) % 360;
}
const compass = d => ['north', 'northeast', 'east', 'southeast', 'south', 'southwest', 'west', 'northwest'][Math.round((((d % 360) + 360) % 360) / 45) % 8];
const HOMEPT = [35.6145, -88.8139];
const TARGETS = [['Israel', 31.78, 35.22], ['home (Jackson)', HOMEPT[0], HOMEPT[1]]];
function headingWords(trk, lat, lon) {
  if (trk == null) return '';
  let s = 'headed ' + compass(trk);
  if (lat != null) for (const [nm, a, b] of TARGETS) {
    const d = miles(lat, lon, a, b);
    if (d < 40 || d > 2500) continue;
    const diff = Math.abs(((bearing(lat, lon, a, b) - trk + 540) % 360) - 180);
    if (diff <= 20) { s += ', toward ' + nm; break; }
  }
  return s;
}
// "Climbing, now at 17,650 feet · 424 mph · headed north, toward Israel"
function flightLine(alt, kt, trk, lat, lon, vr) {
  const bits = [], ground = alt != null && alt <= 0;
  if (alt != null) {
    if (ground) bits.push('On the ground');
    else {
      const ft = Math.round(alt).toLocaleString('en-US') + ' feet';
      bits.push(vr > 500 ? 'Climbing, now at ' + ft : vr < -500 ? 'Coming down, now at ' + ft : 'Flying at ' + ft);
    }
  }
  if (kt && !ground) bits.push(Math.round(kt * 1.15078) + ' mph');
  const h = headingWords(trk, lat, lon);
  if (h && !ground) bits.push(h);
  return cap(bits.join(' \u00B7 '));
}
function fromHome(lat, lon) {
  if (lat == null) return '';
  const d = Math.round(miles(HOMEPT[0], HOMEPT[1], lat, lon) / 10) * 10;
  return d < 20 ? 'right around home' : d.toLocaleString('en-US') + ' miles from home';
}
function plainResponse(r) {
  return String(r || '')
    .replace(/^(\d+) airborne at once vs normal ~([\d.]+)\./, (_, n, b) => `${n} in the air at once. ` +
      (Math.round(+b) ? `Normally there are about ${Math.round(+b)}.` : 'Normally there are almost none here.'))
    .replace('Tankers/airlift often move ahead of fighters or bombers.', 'Refueling and cargo planes often show up before fighters or bombers do.')
    .replace('Logged. Normal activity level so far.', 'Just writing it down. This is a normal amount so far.')
    .replace('Logged. Recon / radar planes watching the area.', 'Just writing it down. Spy and radar planes are keeping an eye on the area.')
    .replace('Bomber task force / presence flight likely. No official statement seen yet.', 'Probably a training or show-of-strength flight. No official word yet.')
    .replace('Often training or VIP travel. Watch for other nuclear-force activity.', 'Usually training or flying officials around. Worth watching if other nuclear planes go up too.')
    .replace('No official response reported yet. Watch for NORAD/NATO intercept news.', 'No official word yet. Watch for news of US or NATO jets going up to meet it.')
    .replace('Several maritime patrol planes at once can mean a submarine is being tracked.', 'Several sub-hunting planes at once can mean someone is tracking a submarine.')
    .replace(/^Squawk (\d+) set by the crew\./, (_, c) => `The crew set code ${c} on the plane's radio box.`)
    .replace(/^Logged\.\s*$/, 'Just writing it down.')
    .replace(/^Developing\. /, 'Still developing. ')
    .replace('No action needed. This is a test.', 'Nothing to do. This was only a test.');
}
const THREATW = {LOW: 'Low', ELEVATED: 'Raised', HIGH: 'High', SEVERE: 'Severe', NONE: 'None (test)'};
const plainSource = s => String(s || '').replace('adsb.lol live ADS-B (military feed)', 'Live plane tracker (adsb.lol)')
  .replace('Watchman Radar backend (GitHub Actions)', 'WATCHTOWER');
function plainHeld(h) {
  const x = String(h || '').replace(/^held: /, '');
  return {'quiet hours': 'Not sent: quiet hours', 'daily cap': 'Not sent: daily limit reached'}[x] || ('Not sent: ' + x.replace('pushes', 'alerts'));
}
function plainAirframes(s) {
  return String(s || '').split(', ').map(x => { const m = x.match(/^(\d+)x (.+)$/); return m ? `${m[1]} ${plurl(+m[1], kindOf(m[2]))} (${m[2]})` : x; }).join(', ');
}
// For text that was sent to the phone as-is (the nightly recap): swap the codes for words.
function plainText(s) {
  return String(s || '').split('\n').map(line => {
    const m = line.match(/^(\u{1F947}|\u{1F948}|\u{1F949}|4|5) (\S+) (.+)$/u);
    if (m) return `${m[1]} ${m[2]} ${plainWhat(m[3])}`;
    return line.replace(COORDS, '')
      .replace(/(\d+) sweeps?\b/gi, (_, n) => `checked ${n} time${n == 1 ? '' : 's'}`)
      .replace(/peak (\d+) mil aircraft/gi, 'most military planes at once: $1')
      .replace(/(\d+) tankers up at once/gi, '$1 refueling planes up at once')
      .replace(/\u25B2 pushed/gi, '\u2714 sent to your phone')
      .replace(/NOTABLE AIRFRAMES: (.+)$/, (_, a) => 'SPECIAL PLANES SPOTTED: ' + plainAirframes(a))
      .replace(/\bFLASH\b/g, 'URGENT').replace(/\bIMMEDIATE\b/g, 'IMPORTANT').replace(/\bROUTINE\b/g, 'FYI')
      .replace(/(\d+)x ([A-Z][A-Z0-9-]+)/g, '$1 $2');
  }).join('\n');
}

const TIPS = {
  threat: 'How stirred up the last 6 hours have been. NORMAL = nothing big. ELEVATED = an Important alert. HIGH = an Urgent alert.',
  lastcheck: 'How long ago WATCHTOWER last looked at the skies and the news. It checks again about every 10 minutes, all by itself.',
  scope: 'Jackson is the dot in the middle. The farther out a blip is, the farther away the plane is. The whole world fits inside the circle.',
  board: 'Green light = calm. Orange = an Important alert there today. Red = an Urgent alert there today. A \u25B2 means more than double the usual.',
  map: 'Every military plane sharing its location right now. Tap a plane to see what it is. Tap the colored buttons to hide or show a kind of plane.',
  cats: 'Refueling = flying gas stations for other jets. Big cargo = haul troops & gear (C-17). Small cargo = C-130s. Spy = planes that watch and listen. Nuclear command = keep the President linked to nuclear forces.',
  topfinds: 'The biggest things the radar noticed today, most important on top. Every night at recap time this list comes to your phone.',
  feed: 'Everything WATCHTOWER noticed, newest first. Tap a card to open it.',
  tiers: 'URGENT (FLASH) = the biggest stuff, like nuclear drills or foreign bombers near the US. IMPORTANT (IMMEDIATE) = unusual buildups. FYI (ROUTINE) = normal activity it writes down.',
  FLASH: 'URGENT (called FLASH on your phone alerts): the biggest stuff, like nuclear drills, missile tests, or foreign bombers or warships near the US or Europe.',
  IMMEDIATE: 'IMPORTANT (called IMMEDIATE on your phone alerts): something unusual building up, like way more refueling or cargo planes than normal.',
  ROUTINE: 'FYI (called ROUTINE on your phone alerts): normal activity the radar writes down. It only buzzes you if you turn that on.',
  kc46: 'The US Air Force\'s KC-46 Pegasus refueling plane is built on the Boeing 767, so a US military 767 is very likely one, a flying gas station for other jets.',
  tanker: 'Refueling planes (like the KC-135) are flying gas stations that top off other jets in midair. A lot at once can mean a big mission.',
  airlift: 'Big cargo planes (like the C-17) carry troops, vehicles and supplies. A bunch in one place can mean a buildup.',
  tactical: 'C-130s are smaller cargo planes for shorter trips, carrying troops and supplies.',
  isr: 'Spy & surveillance planes watch and listen from the sky, like the RC-135 and the P-8 that hunts submarines.',
  c2: 'Nuclear command planes keep the President connected to nuclear forces if the ground is knocked out. The E-6B and the E-4B "doomsday plane" are this kind. They fly for training a lot too.',
  bomber: 'Big long-range planes that carry heavy bombs, like the B-52.',
  fighter: 'Fast combat jets, like the F-35 and F-16.',
  other: 'Military planes that are not in the other groups, like VIP jets and helicopters.',
  total: 'Every military plane sharing its location right now, all over the world.',
  planeid: 'The radio name each plane uses (its call sign). RCH means an Air Force cargo flight. Handy for looking a plane up.',
  checks: 'Each check, WATCHTOWER looks at every military plane sharing its location plus the latest news headlines.',
  peak: 'The most military planes the radar saw in the air at the same time today.',
  sent: 'WATCHTOWER buzzed your phone about this through the ntfy app.',
  threatlvl: 'Low = normal. Raised = worth keeping an eye on. High = something serious.',
  foreign: 'Military planes from Russia, China, Iran, Cuba or North Korea that show up on the tracker.',
  sens: 'LOW = only buzz for big moves. NORMAL = in between. HIGH = buzz for smaller changes too.',
};

// ---------------------------------------------------------------- tap-to-learn (i) bubbles
(function () {
  let tipFor = null;
  const el = () => document.getElementById('tip');
  function hideTip() { const t = el(); if (t) t.classList.remove('on'); tipFor = null; }
  function showTip(btn) {
    if (tipFor === btn) { hideTip(); return; }
    const t = el();
    tipFor = btn;
    t.textContent = TIPS[btn.dataset.tip] || '';
    t.classList.add('on');
    const r = btn.getBoundingClientRect(), vw = window.innerWidth, vh = window.innerHeight;
    const w = Math.min(320, vw - 24);
    t.style.width = w + 'px';
    t.style.left = Math.max(12, Math.min(vw - w - 12, r.left + r.width / 2 - w / 2)) + 'px';
    const h = t.offsetHeight;
    t.style.top = (r.bottom + 8 + h < vh - 70 ? r.bottom + 8 : Math.max(8, r.top - h - 8)) + 'px';
  }
  document.addEventListener('click', e => {
    const b = e.target.closest && e.target.closest('.i');
    if (b) { e.preventDefault(); e.stopPropagation(); showTip(b); return; }
    if (tipFor) hideTip();
  }, true);
  window.addEventListener('scroll', () => tipFor && hideTip(), true);
  window.addEventListener('resize', () => tipFor && hideTip());
})();
