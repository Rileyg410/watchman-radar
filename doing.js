/* WATCHMAN RADAR // "Probably doing": a plain-English best guess of what every plane is up to right now.
   Uses the call sign + plane type (missions.json roles), where it is and which way it's going, height,
   speed, climbing or coming down, circling (from the radar's last checks, the "bh" box the watcher adds),
   the time of day there, and other planes flying with it. Needs plain.js (miles, bearing, compass, cap). */
(() => {
'use strict';

const STRAT = [['Israel', 31.78, 35.22], ['the Persian Gulf', 26.6, 52.0], ['Iran', 32.4, 53.7], ['Ukraine', 49.0, 32.0],
  ['Taiwan', 23.7, 121.0], ['Korea', 37.5, 127.5], ['the Red Sea', 20.0, 38.5], ['home (Jackson)', 35.6145, -88.8139]];
const WATCH_LAND = {'Iran': 'Iran', 'Russia': 'Russia', 'China': 'China', 'North Korea': 'North Korea', 'Syria': 'Syria',
  'Lebanon': 'Lebanon and Hezbollah', 'Yemen': 'Yemen and the Houthis', 'Venezuela': 'Venezuela', 'Cuba': 'Cuba',
  'Belarus': 'Belarus and Russia', 'Ukraine': 'the war in Ukraine', 'Iraq': 'Iraq', 'Israel': 'Israel and its neighbors',
  'Jordan': 'Israel and its neighbors', 'the West Bank & Gaza': 'Gaza and Israel', 'Taiwan': 'China and Taiwan', 'Kaliningrad': 'Russia'};
const WATCH_SEA = [[/Black Sea|Sea of Azov/, 'Russia and Ukraine'], [/Baltic|Gulf of Finland/, 'Russia'], [/Persian Gulf|Gulf of Oman|Strait of Hormuz|Arabian Sea/, 'Iran'],
  [/Red Sea|Gulf of Aden|Bab/, 'Yemen and the Houthis'], [/Yellow Sea|Korea Bay|Sea of Japan/, 'North Korea and China'],
  [/South China Sea|East China Sea|Taiwan Strait|Philippine Sea/, 'China'], [/Barents|Norwegian Sea/, 'Russia'], [/Caribbean/, 'Venezuela and Cuba']];
const FIGHTERISH = new Set(['fighter', 'attack', 'bomber']);
const GROUPNOUN = {tanker: 'refueling plane', airlift: 'cargo plane', tactical: 'cargo plane', trainer: 'training plane', fighter: 'jet',
  attack: 'jet', bomber: 'bomber', heli: 'helicopter', heli_cargo: 'helicopter', heli_attack: 'helicopter', heli_sar: 'helicopter', tiltrotor: 'Osprey',
  isr: 'spy plane', aew: 'radar plane', asw: 'patrol plane', drone: 'drone', utility: 'small plane', vip: 'VIP jet', transport: 'transport jet'};
const HELI = r => /^heli/.test(r) || r === 'tiltrotor';
const pl = (n, w) => n === 1 ? w : w + 's';
const NUMW = ['no', 'one', 'two', 'three', 'four', 'five', 'six', 'seven', 'eight', 'nine', 'ten'];
const num = n => NUMW[n] || String(n);
const ft = a => (a >= 10000 ? Math.round(a / 500) * 500 : Math.round(a / 100) * 100).toLocaleString('en-US') + ' ft';
const mins = m => m >= 90 ? `${Math.floor(m / 60)} hr ${m % 60 >= 10 ? (Math.round(m % 60 / 5) * 5) + ' min' : ''}`.trim() : m >= 55 ? 'an hour' : `${Math.max(5, Math.round(m / 5) * 5)} min`;
const sea = s => String(s || '').replace(/\b(North|South) (Pacific|Atlantic) Ocean/, '$2 Ocean');

function roleOf(p, M) {
  const cs = String(p.cs || '').toUpperCase().replace(/\s/g, ''), t = String(p.t || '').toUpperCase();
  const word = (cs.match(/^[A-Z]+/) || [''])[0];
  let best = null;
  for (const row of (M && M.callsigns) || []) {
    const pre = row[0];
    if (word === pre || (pre.length >= 3 && word.startsWith(pre) && word.length <= pre.length + 1))
      if (!best || pre.length > best[0].length) best = row;
  }
  const ti = M && M.types ? M.types[t] : null;
  const csRole = best ? best[4] || '' : '', tRole = ti ? ti[3] || '' : '';
  let role;
  if (['vip', 'medevac', 'sar', 'heli_sar', 'weather', 'test', 'c2', 'isr', 'aew', 'drone', 'asw'].includes(csRole) && !(csRole === 'vip' && tRole === 'tanker')) role = csRole;
  else if (tRole) role = tRole;
  else if (csRole) role = csRole;
  else if (p.cat === 'fighter') role = 'fighter';
  else role = (M && M.cats && M.cats[p.cat] && M.cats[p.cat][3]) || '';
  if (t === 'B762' && (!p.nat || p.nat === 'US')) role = csRole === 'airlift' ? 'tanker' : role || 'tanker';
  // US Coast Guard flights use C + the tail number (C6591)
  const uscg = /^C\d{4}$/.test(cs) && (HELI(role) || ['tactical', 'sar', 'utility', ''].includes(role));
  if (uscg && HELI(role)) role = 'heli_sar';
  else if (uscg && role === 'tactical') role = 'sar';
  return {role, cs: best ? best[0] : '', csRole, tRole, uscg, ferry: csRole === 'airlift' && tRole === 'tanker'};
}

function place(bh, preferNear) {
  if (!bh) return '';
  if (preferNear && bh.near && bh.near[1] <= 12) return 'near ' + bh.near[0];
  if (bh.over) return 'over ' + bh.over;
  if (bh.sea && bh.coast) return `over ${sea(bh.sea)} off ${bh.coast}`;
  if (bh.sea) return 'over ' + sea(bh.sea);
  if (bh.coast) return 'off the coast of ' + bh.coast;
  return 'far out over the ocean';
}
function watchOn(bh) {
  if (!bh) return '';
  for (const k of [bh.over, bh.coast]) if (k && WATCH_LAND[k]) return WATCH_LAND[k];
  if (bh.sea) for (const [rx, w] of WATCH_SEA) if (rx.test(bh.sea)) return w;
  return '';
}
function toward(p) {
  if (p.trk == null || p.lat == null || p.alt == null || p.alt < 15000) return '';
  for (const [nm, a, b] of STRAT) {
    const d = miles(p.lat, p.lon, a, b);
    if (d < 150 || d > 1300) continue;
    const off = Math.abs(((bearing(p.lat, p.lon, a, b) - p.trk + 540) % 360) - 180);
    if (off <= 12) return nm;
  }
  return '';
}
function localHour(lon, ts) {
  const d = new Date((ts || Date.now() / 1000) * 1000);
  return ((d.getUTCHours() + d.getUTCMinutes() / 60 + lon / 15) % 24 + 24) % 24;
}
function hourWords(h) {
  const hh = Math.round(h) % 24, ap = hh >= 12 ? 'PM' : 'AM', x = hh % 12 || 12;
  return hh === 0 ? 'about midnight' : hh === 12 ? 'about noon' : `about ${x} ${ap}`;
}

function neighbors(p, planes, roleFn, myRole) {
  const out = {same: [], tankers: [], jets: [], role: []};
  if (p.lat == null) return out;
  for (const q of planes || []) {
    if (q === p || q.hex === p.hex || q.lat == null) continue;
    const d = miles(p.lat, p.lon, q.lat, q.lon);
    if (d > 150) continue;
    const altOk = p.alt != null && q.alt != null && Math.abs(p.alt - q.alt) <= 4000 && p.alt > 0 && q.alt > 0;
    const qr = roleFn(q).role;
    if (d <= 25 && altOk && qr === 'tanker') out.tankers.push(q);
    if (d <= 25 && altOk && FIGHTERISH.has(qr)) out.jets.push(q);
    if (d <= 20 && altOk && q.t && q.t === p.t) { out.same.push(q); out.closest = Math.min(out.closest || 99, d); }
    // a stream: same job, same direction, within 150 mi
    if (qr === myRole && p.trk != null && q.trk != null && Math.abs(((q.trk - p.trk + 540) % 360) - 180) <= 30 && q.alt > 8000 && p.alt > 8000) out.role.push(q);
  }
  return out;
}

function doing(p, planes, M, ts) {
  const R = roleOf(p, M), role = R.role;
  let bh = p.bh || {};
  // no map lookup on this plane yet (older data or a lookup hiccup): use the radar's region name, never guess "ocean"
  if (!bh.over && !bh.sea && !bh.coast && !bh.near && (!p.bh || bh.err)) {
    const RG = (window.WR && WR.REGIONS) || {};
    const rg = RG[p.rg] ? String(RG[p.rg][0]).replace(/^Mainland US$/, 'the mainland US') : '';
    bh = Object.assign({}, bh, {over: rg || 'the area'});
  }
  const roleFn = q => roleOf(q, M);
  const alt = p.alt, gs = p.gs, trk = p.trk;
  const vr = p.vr != null ? p.vr : bh.climb ? bh.climb : bh.sink ? -bh.sink : null;
  const nodata = gs == null && trk == null;
  const heli = HELI(role);
  const ground = alt != null && (alt <= 0 || (alt < 300 && gs != null && gs < 40 && !heli));
  const nearB = bh.near && bh.near[1] <= 25 ? bh.near : null;
  const where = place(bh, true), wide = place(bh, false);
  const water = !bh.over && (bh.sea || bh.coast || true);
  const nb = neighbors(p, planes, roleFn, role);
  const tw = toward(p);
  const dir = trk != null ? 'headed ' + compass(trk) : '';
  const lh = p.lon != null ? localHour(p.lon, ts) : 12, night = lh < 5.5 || lh >= 19.5;
  const orb = bh.orb >= 20 && !ground ? bh.orb : 0, circling = orb && (bh.turn || 0) >= 150;
  const why = [];
  let used = {spot: p.lat != null, path: !nodata, checks: (bh.up || 0) >= 10};

  // ---- phase
  let phase = 'cruise', landB = null;
  // a field only counts as 'ahead' when it's a sensible glide away for the height (about 300 ft per mile, with room to spare)
  const ahead = bh.ahead && (alt == null || bh.ahead[1] <= Math.max(10, alt / 100)) && (vr != null && vr < -300 ? bh.ahead[1] <= 80 : alt != null && alt < 5000 && bh.ahead[1] <= 20) ? bh.ahead : null;
  if (['7700', '7600', '7500'].includes(p.sq)) phase = 'sq';
  else if (role === 'ground') phase = 'station';
  else if (ground) phase = 'ground';
  else if (alt != null && alt < 14000 && ((vr != null && vr < -400 && (ahead || (nearB && nearB[1] <= 30) || alt < 5000)) || (ahead && (vr == null || vr <= 0) && alt < 4000))) { phase = 'landing'; landB = ahead ? ahead[0] : nearB ? nearB[0] : ''; }
  else if (alt != null && alt < 14000 && vr != null && vr > 400 && (nearB && nearB[1] <= 30 || (bh.frm && bh.frm[1] <= 25))) phase = 'takeoff';
  else if (orb) phase = 'orbit';
  else if (alt != null && alt < 3000) phase = 'low';

  const at = nearB ? nearB[0] : wide;
  const fromB = bh.frm ? bh.frm[0] : nearB ? nearB[0] : '';
  const toLine = tw ? `toward ${tw}` : dir;
  let line = '';
  if (phase === 'landing' && !landB) line = `coming down ${wide}, likely to land soon`;

  // ---- shared phases
  if (phase === 'sq') {
    line = {'7700': 'dealing with an emergency and looking for the closest place to land', '7600': 'flying with a radio problem and following the standard steps to land safely',
      '7500': 'sending the hijack code, though crews sometimes set it by mistake'}[p.sq];
    why.push(`Its transponder is set to ${p.sq}`);
  } else if (phase === 'station') {
    line = `not a plane at all. It's a ground radio station ${nearB ? 'at ' + nearB[0] : wide}, so it stays put`;
  } else if (phase === 'ground') {
    const atB = nearB ? 'at ' + nearB[0] : wide;
    line = ({airlift: `loading or unloading cargo ${atB}`, tactical: `loading or unloading ${atB}`, tanker: `parked or getting ready for a refueling flight ${atB}`,
      vip: `waiting on VIP passengers ${atB}`, transport: `boarding or dropping off passengers ${atB}`, trainer: `a student pilot taxiing out or just landed ${atB}`,
      fighter: `taxiing out or just landed ${atB}`, bomber: `taxiing out or just landed ${atB}`}[role]) ||
      (heli ? `on the pad ${atB}, starting up or just landed` : `on the ground ${atB}, taxiing or parked`);
  } else if (phase === 'landing' && !line) {
    const to = landB ? 'at ' + landB : wide;
    line = ({airlift: `bringing cargo or troops in to land ${to}`, tactical: `coming in to land ${to} with troops or supplies`,
      tanker: (bh.up || 0) >= 60 ? `heading home to land ${to} after a refueling flight` : `coming in to land ${to}`,
      trainer: alt != null && alt < 4000 ? `a student practicing landings ${to}` : `a student heading back to land ${to}`, vip: `bringing VIPs in to land ${to}`, transport: `bringing passengers in to land ${to}`,
      asw: `coming home to land ${to} after an ocean patrol`, isr: `coming home to land ${to} after a watch flight`, aew: `coming home to land ${to} after a radar watch`,
      fighter: `coming home to land ${to}`, medevac: `bringing patients in to land ${to}`}[role]) || `coming in to land ${to}`;
    if (alt != null) why.push(`Coming down through ${ft(alt)}`);
    if (ahead) why.push(`pointed right at ${ahead[0]}, ${ahead[1]} mi ahead`);
  } else if (phase === 'takeoff') {
    line = ({airlift: `just took off from ${fromB} with cargo or troops, ${toLine}`, tanker: `just took off from ${fromB}, heading out to a refueling track`,
      trainer: `just took off from ${fromB} on a training flight`, fighter: `just took off from ${fromB} for a training flight or a patrol`,
      tactical: `just took off from ${fromB} with troops or supplies, ${toLine}`, vip: `just took off from ${fromB} with VIPs on board, ${toLine}`}[role]) ||
      (heli ? `just lifted off from ${fromB}` : `just took off from ${fromB}, ${toLine}`);
    if (alt != null) why.push(`Climbing through ${ft(alt)}`);
  }

  // ---- job-specific guesses while flying
  if (!line) {
    const ww = watchOn(bh);
    const highFast = alt >= 25000 && gs >= 350;
    const lowNear = alt != null && alt < 5000 && nearB && nearB[1] <= 15;
    const grp = nb.same.length, stream = nb.role.length;
    switch (role) {
      case 'tanker':
        if (R.ferry) line = `moving to a new base or carrying cargo, not refueling right now ${wide}`;
        else if (nb.jets.length) { line = `refueling the ${num(nb.jets.length)} ${pl(nb.jets.length, 'jet')} flying right next to it ${wide}`; why.push(`${cap(num(nb.jets.length))} ${pl(nb.jets.length, 'jet')} within 25 mi at about the same height`); }
        else if (orb) line = `refueling jets on a set refueling track ${wide}`;
        else if (stream >= 2) line = `part of a group of ${num(stream + 1)} refueling planes moving the same way ${wide}, which often means a deployment or a big operation`;
        else if (tw && tw !== 'home (Jackson)') line = `flying out to set up a refueling track toward ${tw}`;
        else if (lowNear) line = `practicing approaches and landings at ${nearB[0]}`;
        else line = `heading to or from a refueling track ${wide}`;
        break;
      case 'airlift':
        if (stream >= 2) line = `part of a stream of ${num(stream + 1)} cargo planes heading ${compass(trk)}, moving troops or gear somewhere`;
        else if (tw && tw !== 'home (Jackson)') line = `hauling cargo or troops toward ${tw}`;
        else if (lowNear) line = `practicing takeoffs and landings at ${nearB[0]}`;
        else if (orb) line = `practicing airdrops or waiting its turn to land ${wide}`;
        else line = (R.csRole === 'airlift' ? `on a Pentagon cargo run ${wide}` : `hauling cargo or troops ${wide}`) + (dir ? ', ' + dir : '');
        break;
      case 'tactical':
        if (alt != null && alt < 3000 && night) line = `practicing low flying at night with night-vision goggles ${where}`;
        else if (alt != null && alt < 3000) line = `practicing low-level flying or a parachute or cargo drop ${where}`;
        else if (orb) line = `circling a drop zone or a practice area ${wide}`;
        else if (lowNear) line = `practicing takeoffs and landings at ${nearB[0]}`;
        else line = `moving troops or supplies ${wide}` + (dir ? ', ' + dir : '');
        break;
      case 'isr':
        if (orb) line = ww ? `listening in on radars and radio traffic ${wide}, keeping an ear on ${ww}` : `listening in on radars and radio traffic ${wide}`;
        else if (bh.cc === 'US' && !ww) line = `on a training flight over ${bh.over}`;
        else line = ww ? `heading out to (or back from) a watch area, keeping an eye on ${ww}` : `heading out to (or back from) a watch area ${wide}`;
        break;
      case 'aew':
        line = orb ? `watching the sky with its big radar and directing other jets ${wide}` : ww ? `on radar watch, keeping an eye on the skies around ${ww}` : `heading out to a radar watch station ${wide}`;
        break;
      case 'asw':
        if (water && alt != null && alt < 6000) line = `hunting a submarine or checking out a ship up close ${wide}`;
        else if (orb && !water) line = `on a training flight, circling ${wide}`;
        else if (water && orb) line = `searching a patch of ocean for submarines or ships ${wide}`;
        else if (bh.sea || (!bh.over && bh.coast)) line = `on an ocean patrol ${wide}, watching ships and submarines` + (ww ? `, likely ${ww}'s` : '');
        else line = `heading out to (or home from) an ocean patrol ${wide}`;
        break;
      case 'drone':
        if (alt >= 40000) line = `taking pictures and listening from very high up ${wide}` + (ww ? `, watching ${ww}` : '');
        else if (orb) line = `keeping watch over one spot ${wide}`;
        else line = `on a long watch flight ${wide}` + (ww ? `, watching ${ww}` : '');
        break;
      case 'c2':
        line = orb ? `keeping the radio link open to nuclear forces, circling ${wide} like it's built to do` : `on a routine practice flight ${wide}. These fly every day`;
        break;
      case 'bomber':
        if (nb.tankers.length) line = `refueling from the tanker flying next to it ${wide}`;
        else if (ww) line = `on a show-of-strength flight near ${ww}`;
        else if (tw && tw !== 'home (Jackson)') line = `on a long-range flight toward ${tw}`;
        else if (lowNear) line = `practicing landings at ${nearB[0]}`;
        else line = `on a long training flight ${wide}`;
        break;
      case 'fighter':
        if (nb.tankers.length) line = `refueling from the tanker flying next to it ${wide}`;
        else if (orb) line = `patrolling or practicing dogfights in one area ${wide}`;
        else if (grp) line = `flying in a group of ${num(grp + 1)} jets ${wide}, most likely training together`;
        else if (ww) line = `on patrol ${wide}, near ${ww}`;
        else if (alt != null && alt < 3000) line = `practicing low flying ${where}`;
        else line = `on a training flight ${wide}`;
        break;
      case 'attack':
        line = orb ? `practicing protecting troops on the ground, circling a bombing range ${wide}` : `on a training flight ${wide}`;
        break;
      case 'vip':
        line = (R.csRole === 'vip' ? `flying government VIPs ${wide}` : `flying officials or senior officers ${wide}`) + (tw ? `, toward ${tw}` : dir ? ', ' + dir : '');
        break;
      case 'transport':
        line = (stream >= 2 ? `moving troops along with ${num(stream)} other ${pl(stream, 'jet')} heading the same way` : `flying passengers, most likely troops or officials, ${wide}`) + (tw ? `, toward ${tw}` : '');
        break;
      case 'medevac':
        line = `carrying sick or hurt troops with a medical crew on board ${wide}` + (dir ? ', ' + dir : '');
        break;
      case 'utility':
        if (orb) line = `on a small watch or photo flight, circling ${wide}`;
        else if (lowNear) line = `making a short hop near ${nearB[0]}`;
        else if (bh.sea && !bh.over) line = `on a sea patrol or carrying a few people between islands ${wide}`;
        else line = `moving a few people or parts between bases ${wide}`;
        break;
      case 'patrol':
        line = orb ? `watching the border, circling ${wide}` : `on a border patrol flight ${wide}`;
        break;
      case 'trainer':
        if (grp && nb.closest <= 3) line = `flying in formation with ${num(grp)} other training ${pl(grp, 'plane')} ${where}`;
        else if (grp) line = `training alongside ${num(grp)} other training ${pl(grp, 'plane')} nearby ${where}`;
        else if (night) line = `a night training flight ${where}`;
        else if (lowNear) line = `a student practicing takeoffs and landings at ${nearB[0]}`;
        else if (orb || (bh.near && bh.near[1] <= 45)) line = `a student practicing loops, stalls and turns in a training area ${bh.near ? 'near ' + bh.near[0] : wide}`;
        else if (highFast) line = `a training flight, or chasing other jets as a practice target, ${wide}`;
        else line = `a student pilot training flight ${wide}`;
        break;
      case 'heli': case 'heli_cargo': case 'heli_attack': case 'heli_sar': case 'tiltrotor': {
        const n = num(grp), many = grp ? ` with ${n} other ${pl(grp, role === 'tiltrotor' ? 'Osprey' : 'helicopter')}` : '';
        if (gs != null && gs < 20 && alt > 0) line = role === 'heli_sar' || R.uscg ? `hovering, likely pulling someone up on a hoist or practicing a rescue ${where}` : `hovering ${where}, likely practicing a hoist, a rescue or a tricky landing`;
        else if (role === 'heli_sar' || R.uscg) line = (bh.sea || (!bh.over && bh.coast)) ? `a Coast Guard or rescue patrol ${wide}` : `on a rescue or medical flight ${where}`;
        else if (role === 'heli_attack') line = `gunnery or flight training${many} ${where}`;
        else if (role === 'heli_cargo') line = grp ? `moving troops or gear${many} ${where}` : `hauling troops or a load hanging underneath ${where}`;
        else if (role === 'tiltrotor') line = `moving Marines or special forces${many} ${where}`;
        else if (night) line = `night-vision training${many} ${where}`;
        else if (grp) line = `moving troops or training${many} ${where}`;
        else if (bh.sea && !bh.over) line = `working with a ship nearby or practicing sub hunting ${wide}`;
        else if (nearB && nearB[1] <= 30) line = `training around ${nearB[0]}`;
        else line = `moving people or training ${wide}`;
        break;
      }
      case 'sar':
        line = orb ? `searching for someone or something ${wide}` : `on a search-and-rescue patrol ${wide}`;
        break;
      case 'weather':
        line = orb ? `measuring a storm or the weather ${wide}` : `heading out to measure the weather ${wide}`;
        break;
      case 'test':
        line = `a test flight after repairs, checking that the plane is good to go, ${where}`;
        break;
      default: // nothing to go on but how it's flying
        if (nodata && alt == null) line = `a routine military flight ${wide}. It's only sharing a rough spot right now`;
        else if (orb) line = `on a watch or training mission, circling ${wide}`;
        else if (alt >= 28000 && gs >= 380) line = `on a long trip moving people or cargo ${wide}` + (tw ? `, toward ${tw}` : dir ? ', ' + dir : '');
        else if (alt != null && alt < 3000 && (gs == null || gs < 140)) line = `a helicopter or small plane training or patrolling ${where}`;
        else if (gs >= 350 && alt != null && alt < 15000) line = `a fast jet on a training flight ${where}`;
        else if (lowNear) line = `training around ${nearB[0]}`;
        else line = `a routine military flight ${wide}` + (dir ? ', ' + dir : '');
    }
  }

  // ---- why (the clues), at most three
  if (phase !== 'landing' && phase !== 'takeoff' && phase !== 'ground' && phase !== 'station' && alt != null && alt > 0) {
    if (circling) why.push(`It's been circling at ${ft(alt)} for about ${mins(orb)}`);
    else if (orb) why.push(`It's stayed in the same ${Math.max(10, bh.orbr || 0)}-mile area at ${ft(alt)} for about ${mins(orb)}`);
    else if (vr != null && vr > 400) why.push(`Climbing through ${ft(alt)}`);
    else if (vr != null && vr < -400) why.push(`Coming down through ${ft(alt)}`);
    else if (gs != null && gs < 20 && heli) why.push(`Hardly moving at ${ft(alt)}`);
    else why.push(`Flying at ${ft(alt)}${gs ? ', ' + Math.round(gs * 1.15078) + ' mph' : ''}`);
  }
  if (nb.same.length && !/formation|group of|with (one|two|three|four|five|\d+) other/.test(line)) why.push(`${cap(num(nb.same.length))} more of the same type within 20 mi`);
  if (nb.role.length >= 2 && /stream|group of/.test(line)) why.push(`${cap(num(nb.role.length))} others like it within 150 mi going the same way`);
  if (bh.frm && phase !== 'takeoff' && phase !== 'ground' && bh.frm[1] <= 120 && !(landB && landB === bh.frm[0])) why.push(`It first showed up near ${bh.frm[0]} about ${mins(bh.frm[1])} ago, so it likely took off there`);
  else if ((bh.up || 0) >= 30 && !orb) why.push(`On the radar for about ${mins(bh.up)}`);
  if (tw && !line.includes(tw)) why.push(`Pointed toward ${tw}`);
  if ((night && (heli || role === 'trainer' || role === 'tactical')) || (nodata && alt == null)) why.push(night ? `It's ${hourWords(lh)} there` : 'No speed or direction shared, so this is a looser guess');
  if (nodata && alt != null && why.length < 3 && phase !== 'station') why.push('No speed or direction shared yet');

  const clues = [R.cs ? `call sign (${R.cs})` : '', p.t ? 'plane type' : '', used.spot ? 'location' : '',
    used.path ? 'flight path' : alt != null ? 'height' : '', used.checks ? "the radar's last few checks" : ''].filter(Boolean);
  const by = clues.length > 1 ? clues.slice(0, -1).join(', ') + ' and ' + clues[clues.length - 1] : clues[0] || 'where it is';
  line = line.replace(/\s+,/g, ',').replace(/\s{2,}/g, ' ').replace(/,\s*$/, '').trim();
  return {line: cap(line), why: why.slice(0, 3).map(w => cap(w) + '.').join(' '), by, role};
}

const TIPS = {
  doing: "The radar's best guess at what this plane is up to right now. It's worked out from the call sign, the plane type, where it is and which way it's going, its height and speed, whether it's climbing or coming down, if it's been circling, the time of day there, and other planes flying with it. It's a smart guess, not a confirmed mission."
};
window.WRD = {doing, roleOf};
if (window.TIPS_EXTRA) Object.assign(window.TIPS_EXTRA, TIPS); else window.TIPS_EXTRA = TIPS;
})();
