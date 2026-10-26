/* WATCHMAN RADAR // fighter jets: plain-English names, what each one is for, tap-to-learn tips,
   the fighter-jet map icon, and the "refueling with the tanker nearby" check. */
(() => {
'use strict';

// code -> [name, what it's for, tip key]
const F = {
  F35:  ['F-35 Lightning II', 'stealth fighter', 'f35'],
  F22:  ['F-22 Raptor', 'stealth air-to-air fighter', 'f22'],
  F15:  ['F-15 Eagle', 'fighter jet', 'f15'],
  F15E: ['F-15E Strike Eagle', 'fighter & bomber in one', 'f15'],
  F15X: ['F-15EX Eagle II', 'newest F-15 fighter', 'f15'],
  F16:  ['F-16 Fighting Falcon', 'all-around fighter jet', 'f16'],
  F18S: ['F/A-18E/F Super Hornet', 'Navy carrier fighter', 'f18s'],
  E18G: ['EA-18G Growler', 'radar-jamming jet', 'e18g'],
  EA18: ['EA-18G Growler', 'radar-jamming jet', 'e18g'],
  F18H: ['F/A-18 Hornet', 'carrier fighter (older model)', 'f18h'],
  F18:  ['F/A-18 Hornet', 'carrier fighter (older model)', 'f18h'],
  A10:  ['A-10 Thunderbolt II "Warthog"', 'ground-attack jet', 'a10'],
  AV8B: ['AV-8B Harrier', 'jump jet', 'harrier'],
  HAR:  ['Harrier', 'jump jet', 'harrier'],
  EUFI: ['Eurofighter Typhoon', 'European fighter jet', 'eufi'],
  RFAL: ['Dassault Rafale', 'French fighter jet', 'rfal'],
  GRIF: ['Saab Gripen', 'Swedish fighter jet', 'grip'],
  SB39: ['Saab Gripen', 'Swedish fighter jet', 'grip'],
  JAS39:['Saab Gripen', 'Swedish fighter jet', 'grip'],
  TOR:  ['Panavia Tornado', 'strike jet', 'tor'],
  MIR2: ['Mirage 2000', 'French-built fighter jet', 'mirage'],
  M2000:['Mirage 2000', 'French-built fighter jet', 'mirage'],
  MRF1: ['Mirage F1', 'older French-built fighter', 'mirage'],
  F5:   ['F-5 Tiger II', 'light fighter jet', 'f5'],
  F14:  ['F-14 Tomcat', 'fighter jet (only Iran still flies it)', 'fighter'],
  F4:   ['F-4 Phantom II', 'older fighter jet', 'fighter'],
  F104: ['F-104 Starfighter', 'vintage fighter jet', 'fighter'],
  F117: ['F-117 Nighthawk', 'stealth attack jet', 'fighter'],
  KFIR: ['IAI Kfir', 'Israeli-built fighter jet', 'fighter'],
  TEJS: ['HAL Tejas', 'Indian fighter jet', 'fighter'],
  JF17: ['JF-17 Thunder', 'Pakistani-Chinese fighter jet', 'fighter'],
  AMX:  ['AMX', 'ground-attack jet', 'fighter'],
  SU24: ['Su-24 Fencer', 'Russian strike jet', 'rufighter'],
  SU25: ['Su-25 Frogfoot', 'Russian ground-attack jet', 'rufighter'],
  SU27: ['Su-27 Flanker', 'Russian fighter jet', 'rufighter'],
  SU30: ['Su-30 Flanker', 'Russian fighter jet', 'rufighter'],
  SU33: ['Su-33 Flanker', 'Russian carrier fighter', 'rufighter'],
  SU34: ['Su-34 Fullback', 'Russian fighter-bomber', 'rufighter'],
  SU35: ['Su-35 Flanker-E', 'Russian fighter jet', 'rufighter'],
  SU57: ['Su-57 Felon', 'Russian stealth fighter', 'rufighter'],
  MG21: ['MiG-21', 'older Russian-built fighter', 'rufighter'],
  MG23: ['MiG-23', 'older Russian-built fighter', 'rufighter'],
  MG29: ['MiG-29 Fulcrum', 'Russian-built fighter jet', 'rufighter'],
  MG31: ['MiG-31 Foxhound', 'Russian high-speed interceptor', 'rufighter'],
  J10:  ['J-10', 'Chinese fighter jet', 'cnfighter'],
  J11:  ['J-11', 'Chinese fighter jet', 'cnfighter'],
  J15:  ['J-15', 'Chinese carrier fighter', 'cnfighter'],
  J16:  ['J-16', 'Chinese fighter jet', 'cnfighter'],
  J20:  ['J-20', 'Chinese stealth fighter', 'cnfighter'],
};

// Israel's transponder codes run 738000 to 73FFFF
function israeli(hex) {
  const h = parseInt(String(hex || '').replace('~', ''), 16);
  return h >= 0x738000 && h <= 0x73FFFF;
}
// US Air Force tail numbers look like "20-0001" (the first two digits are the order year)
function usafYear(reg) {
  const m = String(reg || '').match(/^(\d{2})-\d{4,5}$/);
  return m ? +m[1] : null;
}

function info(p) {
  const t = String(p.t || '').toUpperCase();
  if (!t || p.fg) return {name: 'Fast jet, type not shared', role: 'probably a fighter jet', tip: 'fighterguess'};
  const base = F[t];
  if (!base) return {name: (window.TYPE_NAMES && TYPE_NAMES[t]) || t, role: 'fighter jet', tip: 'fighter'};
  let [name, role, tip] = base;
  const il = israeli(p.hex), yr = usafYear(p.reg);
  if (t === 'F35') {
    if (il) { name = 'F-35I Adir'; role = 'Israeli stealth fighter'; tip = 'f35i'; }
    else if (yr != null) name = 'F-35A Lightning II';
    else if (/^\d{6}$/.test(p.reg || '')) { name = 'F-35B or F-35C Lightning II'; tip = 'f35bc'; }
  } else if (t === 'F15') {
    if (il) { name = 'Israeli F-15 (Baz or F-15I Ra\'am)'; role = 'Israeli fighter jet'; tip = 'f15i'; }
    else if (yr != null && yr >= 19 && yr <= 40) { name = 'F-15EX Eagle II'; role = 'newest F-15 fighter'; }
    else if (yr != null && yr >= 86 && yr <= 98) { name = 'F-15E Strike Eagle'; role = 'fighter & bomber in one'; }
  } else if (t === 'F16') {
    if (il) { name = 'Israeli F-16 (Barak or F-16I Sufa)'; role = 'Israeli fighter jet'; tip = 'f16i'; }
  }
  return {name, role, tip};
}

function miles(a1, o1, a2, o2) {
  const R = 3958.8, r = Math.PI / 180;
  const x = Math.sin((a2 - a1) * r / 2) ** 2 + Math.cos(a1 * r) * Math.cos(a2 * r) * Math.sin((o2 - o1) * r / 2) ** 2;
  return 2 * R * Math.asin(Math.sqrt(x));
}
// A refueling plane within 25 miles and, when both share a height, within 5,000 feet
function nearTanker(p, planes) {
  if (p.lat == null || !p.alt || p.alt < 5000) return null;
  for (const q of planes || []) {
    const tanker = q.cat === 'tanker' || (q.t === 'B762' && (!q.nat || q.nat === 'US'));
    if (!tanker || q === p || q.lat == null) continue;
    if (q.alt != null && Math.abs(q.alt - p.alt) > 5000) continue;
    const d = miles(p.lat, p.lon, q.lat, q.lon);
    if (d <= 25) return {d: Math.round(d), q};
  }
  return null;
}

function svg(col) {
  const s = 22;
  return `<svg width="${s}" height="${s}" viewBox="0 0 24 24" style="color:${col}"><path fill="${col}" stroke="#000" stroke-width="1.2" stroke-linejoin="round" paint-order="stroke" d="M12 1c.6 0 1 1 1.1 2.3l.3 4.6 8.1 6.6v1.6l-8-2.1.2 3.7 3.3 2.6v1.6l-4.1-.9-.9 1.9-.9-1.9-4.1.9v-1.6l3.3-2.6.2-3.7-8 2.1v-1.6l8.1-6.6.3-4.6C11 2 11.4 1 12 1z"/></svg>`;
}

const TIPS = {
  fighterguess: 'This jet didn\'t share its exact type, but its transponder says it\'s a "high performance" plane (faster than 400 knots and able to pull more than 5 G). That almost always means a fighter.',
  refuelnear: 'A refueling plane is flying close by at about the same height, so this jet may be topping off its fuel in midair. It\'s a guess from where they are, not a sure thing.',
  f35: 'The F-35 Lightning II is a stealth fighter that\'s very hard for radar to see. It comes in three kinds: the F-35A for the Air Force, the F-35B that can land straight down like a helicopter for the Marines, and the F-35C for Navy carriers.',
  f35bc: 'This F-35 has a Navy-style tail number, so it belongs to the Navy or Marines. The F-35B can land straight down like a helicopter (Marines), and the F-35C is built for aircraft carriers (Navy). The tracker can\'t tell which.',
  f35i: 'The F-35I "Adir" (Hebrew for "Mighty One") is Israel\'s own version of the F-35 stealth fighter.',
  f22: 'The F-22 Raptor is America\'s top air-to-air stealth fighter, built to win dogfights. It almost never shares its location, so seeing one here is rare.',
  f15: 'The F-15 is a big, fast twin-engine fighter. The F-15E Strike Eagle can also drop bombs, and the F-15EX Eagle II is the brand-new version the Air Force started getting in 2021.',
  f15i: 'Israel flies two kinds of F-15: the "Baz" (Falcon) fighter and the F-15I "Ra\'am" (Thunder), which can also strike far away targets. The tracker can\'t tell which one this is.',
  f16: 'The F-16 Fighting Falcon is the most common fighter in the world. It can dogfight, drop bombs and fly air defense. Pilots nickname it the "Viper."',
  f16i: 'Israel flies two kinds of F-16: the "Barak" (Lightning) and the F-16I "Sufa" (Storm), which carries extra fuel tanks on its back for long trips. The tracker can\'t tell which one this is.',
  f18s: 'The Super Hornet is the Navy\'s main fighter, flying off aircraft carriers. Its radar-jamming cousin, the EA-18G Growler, uses the same code on the tracker, so this could be either one.',
  e18g: 'The EA-18G Growler is a Navy jet that jams enemy radars and radios so other jets can get through safely.',
  f18h: 'The original F/A-18 Hornet, the older model of the Navy and Marines carrier fighter. Several other countries fly it too.',
  a10: 'The A-10 "Warthog" flies low and slow to protect troops on the ground. It\'s famous for the huge gun in its nose.',
  harrier: 'The Harrier is a "jump jet" that can take off and land straight up and down, so the Marines can fly it from small ships.',
  eufi: 'The Eurofighter Typhoon is a fighter flown by Britain, Germany, Italy, Spain, Saudi Arabia and others.',
  rfal: 'The Rafale is France\'s main fighter jet. Egypt, India, Greece, Qatar and the UAE fly it too.',
  grip: 'The Gripen is a light Swedish fighter jet. Sweden, Hungary, the Czech Republic and others fly it.',
  tor: 'The Tornado is a strike jet flown by Germany and Italy, built to fly fast and low to hit targets.',
  mirage: 'The Mirage is a French-built fighter. France, India, Greece, the UAE and others fly it.',
  f5: 'The F-5 Tiger II is a small, older fighter. In the US it often plays the "enemy" in practice dogfights.',
  rufighter: 'A Russian-built combat jet. Russia, and some countries that buy from Russia, fly it.',
  cnfighter: 'A Chinese combat jet flown by China\'s air force or navy.',
};

// share with the page
window.WRF = {info, nearTanker, svg};
if (window.TIPS_EXTRA) Object.assign(window.TIPS_EXTRA, TIPS); else window.TIPS_EXTRA = TIPS;
})();
