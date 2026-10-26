// Which country each plane belongs to, with its flag.
// 1) The plane's ICAO transponder address (every country gets its own block of addresses; table in country-data.js)
// 2) For US planes: which branch, from the call sign and the tail number's pattern
// 3) Known military call signs (RCH = US Air Force, RRR = Royal Air Force, IAM = Italian Air Force ...)
// "Unknown country" only when none of these can tell.
(function () {
  const D = window.WR_CC_DATA || {ranges: [], names: {}};
  const SHORT = {AE: 'UAE', GB: 'United Kingdom', US: 'United States', KP: 'North Korea', KR: 'South Korea',
    CD: 'DR Congo', CG: 'Congo', CZ: 'Czechia', NL: 'Netherlands', BA: 'Bosnia', MK: 'North Macedonia'};
  const DEM = {GB: 'British', FR: 'French', DE: 'German', IT: 'Italian', ES: 'Spanish', NL: 'Dutch', BE: 'Belgian', PL: 'Polish',
    GR: 'Greek', TR: 'Turkish', SE: 'Swedish', NO: 'Norwegian', DK: 'Danish', FI: 'Finnish', CA: 'Canadian', AU: 'Australian',
    JP: 'Japanese', KR: 'South Korean', KP: 'North Korean', CN: 'Chinese', TW: 'Taiwanese', IN: 'Indian', PK: 'Pakistani',
    IL: 'Israeli', IR: 'Iranian', IQ: 'Iraqi', SY: 'Syrian', JO: 'Jordanian', SA: 'Saudi', AE: 'UAE', QA: 'Qatari', KW: 'Kuwaiti',
    BH: 'Bahraini', OM: 'Omani', EG: 'Egyptian', RU: 'Russian', UA: 'Ukrainian', BY: 'Belarusian', CU: 'Cuban', BR: 'Brazilian',
    MX: 'Mexican', TH: 'Thai', SG: 'Singapore', MY: 'Malaysian', ID: 'Indonesian', PH: 'Philippine', CH: 'Swiss', AT: 'Austrian',
    CZ: 'Czech', HU: 'Hungarian', RO: 'Romanian', BG: 'Bulgarian', PT: 'Portuguese', IE: 'Irish', ZA: 'South African', NZ: 'New Zealand',
    LT: 'Lithuanian', LV: 'Latvian', EE: 'Estonian', SK: 'Slovak', HR: 'Croatian', RS: 'Serbian', LB: 'Lebanese', YE: 'Yemeni',
    LY: 'Libyan', DZ: 'Algerian', MA: 'Moroccan', AZ: 'Azerbaijani', AM: 'Armenian', GE: 'Georgian', KZ: 'Kazakh', AF: 'Afghan',
    VN: 'Vietnamese', AR: 'Argentine', CL: 'Chilean', CO: 'Colombian', VE: 'Venezuelan', NG: 'Nigerian', ET: 'Ethiopian', PE: 'Peruvian',
    EC: 'Ecuadorian', BO: 'Bolivian', UY: 'Uruguayan', PY: 'Paraguayan', KE: 'Kenyan', BD: 'Bangladeshi', LK: 'Sri Lankan', NP: 'Nepalese',
    SD: 'Sudanese', TN: 'Tunisian', IS: 'Icelandic', SI: 'Slovenian', AL: 'Albanian', CY: 'Cypriot', MT: 'Maltese', LU: 'Luxembourg'};
  // Military call sign prefixes (ICAO telephony designators) -> [country, force]
  const CALLS = [
    ['RCH', 'US', 'United States Air Force'], ['REACH', 'US', 'United States Air Force'], ['SAM', 'US', 'United States Air Force'],
    ['SPAR', 'US', 'United States Air Force'], ['PAT', 'US', 'United States Army'], ['CNV', 'US', 'United States Navy'],
    ['NAVY', 'US', 'United States Navy'], ['ARMY', 'US', 'United States Army'], ['MARINE', 'US', 'United States Marine Corps'],
    ['RRR', 'GB', 'Royal Air Force'], ['ASCOT', 'GB', 'Royal Air Force'], ['TARTN', 'GB', 'Royal Air Force'], ['RFR', 'GB', 'Royal Air Force'],
    ['IAM', 'IT', 'Italian Air Force'], ['GAF', 'DE', 'German Air Force'], ['GAM', 'DE', 'German Army'], ['GNY', 'DE', 'German Navy'],
    ['CTM', 'FR', 'French Air and Space Force'], ['FAF', 'FR', 'French Air and Space Force'], ['FNY', 'FR', 'French Navy'],
    ['AME', 'ES', 'Spanish Air Force'], ['CFC', 'CA', 'Royal Canadian Air Force'], ['CANFORCE', 'CA', 'Royal Canadian Air Force'],
    ['ASY', 'AU', 'Royal Australian Air Force'], ['KIWI', 'NZ', 'Royal New Zealand Air Force'], ['UAF', 'AE', 'UAE Air Force'],
    ['QAF', 'QA', 'Qatar Emiri Air Force'], ['RSF', 'SA', 'Royal Saudi Air Force'], ['NAF', 'NL', 'Royal Netherlands Air Force'],
    ['BAF', 'BE', 'Belgian Air Force'], ['PLF', 'PL', 'Polish Air Force'], ['HAF', 'GR', 'Hellenic (Greek) Air Force'],
    ['TUAF', 'TR', 'Turkish Air Force'], ['SVF', 'SE', 'Swedish Air Force'], ['NOW', 'NO', 'Royal Norwegian Air Force'],
    ['DAF', 'DK', 'Royal Danish Air Force'], ['HUF', 'HU', 'Hungarian Air Force'], ['CEF', 'CZ', 'Czech Air Force'],
    ['IFC', 'IN', 'Indian Air Force'], ['RFF', 'RU', 'Russian Air Force'], ['NATO', 'LU', 'NATO'], ['MAGIC', 'LU', 'NATO'],
  ];
  // US branch hints from the plane type
  const USCG_T = new Set(['AS65', 'H65', 'EC65', 'H60', 'C30J', 'C130', 'C27J', 'CN35', 'GLF5', 'GLF4']);
  const USMC_T = new Set(['V22', 'AV8B', 'H1', 'UH1Y', 'AH1Z', 'H53S', 'H53', 'C30J']);
  const USAF5_T = new Set(['R135', 'K35R', 'K35E', 'C135', 'E3TF', 'E3CF', 'B52', 'C5', 'C5M', 'E8', 'U2', 'B762', 'K46', 'KC46',
    'MQ9', 'RQ4', 'Q4', 'GLHK', 'E4', 'E4B', 'B1', 'B2', 'F15', 'F16', 'F22', 'F35', 'A10', 'T38', 'T6', 'TEX2']);

  function hexCC(hex) {
    const s = String(hex || '').trim();
    if (!s || s[0] === '~') return null; // "~" = not a real transponder address (relayed by a ground station)
    const x = parseInt(s, 16);
    if (isNaN(x)) return null;
    for (const r of D.ranges) if (x >= r[0] && x <= r[1]) return r[2];
    return null;
  }
  function flag(cc) {
    if (!cc || cc.length !== 2) return '\u{1F3F3}\uFE0F';
    return String.fromCodePoint(...[...cc.toUpperCase()].map(c => 0x1F1E6 + c.charCodeAt(0) - 65));
  }
  function name(cc) { return cc ? (SHORT[cc] || D.names[cc] || cc) : 'Unknown country'; }
  function byCall(cs) {
    cs = String(cs || '').toUpperCase().trim();
    if (!cs) return null;
    for (const [pre, cc, force] of CALLS) {
      if (cs.startsWith(pre) && (cs.length === pre.length || /[0-9]/.test(cs[pre.length]) || pre.length >= 4)) return {cc, force};
    }
    return null;
  }
  function usBranch(p) {
    const cs = String(p.cs || '').toUpperCase().trim(), reg = String(p.reg || '').trim(), t = String(p.t || '').toUpperCase();
    if (/^N[1-9][0-9A-Z]{0,4}$/.test(reg)) return 'United States (civil-registered)';
    if (/^C\d{4}$/.test(cs) || /^CG\d/.test(cs) || (/^\d{4}$/.test(reg) && USCG_T.has(t))) return 'United States Coast Guard';
    const c = byCall(cs);
    if (c && c.cc === 'US') return c.force;
    if (/^\d{6}$/.test(reg)) return USMC_T.has(t) ? 'United States Marine Corps' : 'United States Navy'; // Navy/Marine bureau number
    if (/^\d{2}-\d{5}$/.test(reg)) return USAF5_T.has(t) ? 'United States Air Force' : 'United States Army';
    if (/^\d{2}-\d{4}$/.test(reg)) return 'United States Air Force';
    return 'United States military';
  }
  // {cc, flag, country, force, label, by}
  function of(p) {
    if (!p) return {cc: null, flag: flag(null), country: 'Unknown country', force: '', label: 'Unknown country', by: ''};
    const t = String(p.t || p.type || '').toUpperCase(), cs = String(p.cs || '').toUpperCase();
    if (t === 'TWR' || cs.startsWith('TEST')) return {cc: null, flag: '\u{1F4E1}', country: 'Ground test signal', force: '', label: 'Ground test signal, not a plane', by: 'its transponder'};
    let cc = hexCC(p.hex), by = cc ? 'its transponder address' : '';
    const c = byCall(cs);
    if (!cc && c) { cc = c.cc; by = 'its call sign'; }
    if (!cc && /^\d{2}-\d{4,5}$/.test(String(p.reg || '')) && /^(RCH|SAM|PAT|CNV)/.test(cs)) { cc = 'US'; by = 'its tail number'; }
    if (!cc) return {cc: null, flag: flag(null), country: 'Unknown country', force: '', label: 'Unknown country', by: ''};
    let force = '';
    if (cc === 'US') force = usBranch({cs, reg: p.reg, t});
    else if (c && c.cc === cc) force = c.force;
    else if (cc === 'AU' && /^N\d\d-/.test(String(p.reg || ''))) force = 'Royal Australian Navy';
    const country = name(cc);
    let label;
    if (!force) label = (DEM[cc] || country) + ' military';
    else if (force.includes(country) || (cc === 'US' && force.startsWith('United States'))) label = force;
    else label = country + ' \u00B7 ' + force;
    return {cc, flag: flag(cc), country, force, label, by};
  }
  // countries for a list of plane IDs (call signs / tail numbers) from an alert, matched to planes on the radar
  function forIds(ids, planes) {
    const out = new Map();
    for (const raw of ids || []) {
      const id = String(raw).trim(); if (!id || id[0] === '+') continue;
      const p = (planes || []).find(q => q.cs === id || q.reg === id || String(q.hex) === id);
      const o = p ? of(p) : (() => { const c = byCall(id); return c ? of({cs: id}) : (hexCC(id) && /^[0-9a-f]{6}$/i.test(id) ? of({hex: id}) : null); })();
      if (o && o.cc) out.set(o.cc, (out.get(o.cc) || 0) + 1);
    }
    return out;
  }
  function line(m) { // Map(cc -> n) -> "🇺🇸 United States · 🇬🇧 United Kingdom"
    return [...m.keys()].map(cc => flag(cc) + ' ' + name(cc)).join(' \u00B7 ');
  }
  window.WRC = {of, flag, name, hexCC, forIds, line};
})();
