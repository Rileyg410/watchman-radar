// Plain-English names for plane types the radar didn't know yet, so a tap never just says "Military plane".
// code: [name, what kind of plane (a short noun), optional one-line note shown in the popup]
(function () {
  const T = {
    // small jets & VIP planes
    PC24: ['Pilatus PC-24', 'small Swiss business jet', 'Militaries use it to fly VIPs and staff, or as an air ambulance.'],
    PC12: ['Pilatus PC-12', 'single-engine turboprop', 'Used for troop and staff trips, special missions and air ambulance flights.'],
    GLEX: ['Bombardier Global Express', 'long-range business jet', 'Militaries use it for VIP trips, and some carry spy and radar gear.'],
    GL7T: ['Bombardier Global 7500', 'long-range VIP jet'], GL5T: ['Bombardier Global 5000', 'long-range business jet'],
    CL60: ['Bombardier Challenger', 'business jet', 'Used for VIP trips, and some are fitted out for patrol or spy work.'],
    CL30: ['Bombardier Challenger 300', 'business jet'], CL35: ['Bombardier Challenger 350', 'business jet'],
    GLF4: ['Gulfstream IV (C-20)', 'VIP transport jet'], GLF5: ['Gulfstream V (C-37)', 'VIP transport jet'],
    GLF6: ['Gulfstream G650', 'VIP transport jet'], GA6C: ['Gulfstream G600', 'VIP transport jet'], G280: ['Gulfstream G280', 'business jet'],
    GALX: ['Gulfstream G200', 'business jet'], FA7X: ['Dassault Falcon 7X', 'VIP transport jet'], F900: ['Dassault Falcon 900', 'VIP transport jet'],
    FA50: ['Dassault Falcon 50', 'VIP transport jet'], FA8X: ['Dassault Falcon 8X', 'VIP transport jet'], F2TH: ['Dassault Falcon 2000', 'VIP transport jet'],
    FA20: ['Dassault Falcon 20', 'small jet', 'Militaries use it for transport, training radar crews and pretending to be an enemy jet in drills.'],
    LJ35: ['Learjet 35 (C-21)', 'small transport jet'], LJ45: ['Learjet 45', 'small transport jet'], LJ60: ['Learjet 60', 'small transport jet'],
    C560: ['Cessna Citation (UC-35)', 'small transport jet'], C56X: ['Cessna Citation Excel', 'small transport jet'], C680: ['Cessna Citation Sovereign', 'small transport jet'],
    C68A: ['Cessna Citation Latitude', 'small transport jet'], C700: ['Cessna Citation Longitude', 'small transport jet'], C550: ['Cessna Citation II', 'small transport jet'],
    C25A: ['Cessna Citation CJ2', 'small transport jet'], C25B: ['Cessna Citation CJ3', 'small transport jet'], C25C: ['Cessna Citation CJ4', 'small transport jet'],
    C510: ['Cessna Citation Mustang', 'small jet'], E35L: ['Embraer Legacy 600', 'VIP jet'], E55P: ['Embraer Phenom 300', 'small transport jet'], E50P: ['Embraer Phenom 100', 'small jet'],
    BE40: ['Beechjet (T-1 Jayhawk)', 'training jet', 'The US Air Force uses it to train tanker and cargo pilots.'],
    P180: ['Piaggio Avanti', 'small VIP plane'], H25B: ['Hawker 800', 'small transport jet'],
    // airliners used as government / VIP / troop planes
    C32: ['Boeing 757 (C-32)', 'VIP transport jet', 'Often flies the Vice President, the First Lady or cabinet members.'], B752: ['Boeing 757', 'transport or VIP plane'],
    VC25: ['Air Force One (VC-25)', 'presidential jet'], B742: ['Boeing 747', 'VIP or cargo jet'], B748: ['Boeing 747-8', 'VIP or cargo jet'],
    C40: ['Boeing 737 (C-40 Clipper)', 'transport or VIP plane'], B733: ['Boeing 737', 'transport or VIP plane'], B734: ['Boeing 737', 'transport or VIP plane'],
    B737: ['Boeing 737', 'transport or VIP plane'], B738: ['Boeing 737', 'transport or VIP plane'], B739: ['Boeing 737', 'transport or VIP plane'],
    B38M: ['Boeing 737 MAX', 'transport or VIP plane'], B39M: ['Boeing 737 MAX', 'transport or VIP plane'],
    A318: ['Airbus A318', 'transport or VIP plane'], A319: ['Airbus A319', 'transport or VIP plane'], A320: ['Airbus A320', 'transport or VIP plane'],
    A321: ['Airbus A321', 'transport or VIP plane'], A20N: ['Airbus A320neo', 'transport or VIP plane'], A21N: ['Airbus A321neo', 'transport or VIP plane'],
    A310: ['Airbus A310', 'transport or refueling plane'], A332: ['Airbus A330', 'transport or refueling plane', 'Many air forces fly it as the A330 MRTT, a flying gas station that also carries troops.'],
    A333: ['Airbus A330', 'transport or VIP plane'], A339: ['Airbus A330neo', 'transport or VIP plane'], A343: ['Airbus A340', 'VIP transport jet'], A359: ['Airbus A350', 'VIP transport jet'],
    B762: ['Boeing 767', 'transport or refueling plane'], B763: ['Boeing 767', 'transport or VIP plane'], B772: ['Boeing 777', 'transport or VIP plane'],
    B77L: ['Boeing 777', 'transport or VIP plane'], B77W: ['Boeing 777-300ER', 'VIP transport jet', 'Japan flies two of these as its own “Air Force One.”'],
    B788: ['Boeing 787', 'transport or VIP plane'], B789: ['Boeing 787', 'transport or VIP plane'],
    T134: ['Tupolev Tu-134', 'Russian transport plane'], T154: ['Tupolev Tu-154', 'Russian transport or VIP plane'], IL62: ['Ilyushin Il-62', 'Russian VIP jet'],
    IL96: ['Ilyushin Il-96', 'Russian VIP jet', 'Russia’s president flies on one.'],
    // refueling
    KC10: ['KC-10 Extender', 'refueling plane'], DC10: ['KC-10 Extender', 'refueling plane'], IL78: ['Ilyushin Il-78', 'refueling plane'],
    K767: ['KC-767', 'refueling plane'], A39M: ['A330 MRTT', 'refueling plane'],
    // cargo
    IL76: ['Ilyushin Il-76', 'big cargo plane'], Y20: ['Xian Y-20', 'big cargo plane'], A124: ['Antonov An-124 Ruslan', 'big cargo plane'],
    AN22: ['Antonov An-22', 'big cargo plane'], AN12: ['Antonov An-12', 'cargo plane'], KC2: ['Kawasaki C-2', 'big cargo plane'],
    CN35: ['CASA CN-235', 'small cargo plane'], C295: ['Airbus C295', 'small cargo plane', 'Also flown as a sea patrol and search-and-rescue plane.'],
    AN26: ['Antonov An-26', 'small cargo plane'], AN24: ['Antonov An-24', 'small cargo plane'], AN32: ['Antonov An-32', 'small cargo plane'],
    AN72: ['Antonov An-72', 'small cargo plane'], AN30: ['Antonov An-30', 'photo-mapping plane'], C160: ['Transall C-160', 'small cargo plane'],
    C212: ['CASA C-212', 'small cargo plane'], C130: ['C-130 Hercules', 'small cargo plane'], C30J: ['C-130J Super Hercules', 'small cargo plane'],
    // smaller transport, patrol & spy turboprops
    D228: ['Dornier 228', 'small patrol or transport plane'], AT72: ['ATR 72', 'patrol or transport plane'], AT76: ['ATR 72', 'patrol or transport plane'],
    AT45: ['ATR 42', 'patrol or transport plane'], AT75: ['ATR 72', 'patrol or transport plane'],
    DH8A: ['Dash 8', 'transport or spy plane', 'The US Army flies Dash 8s as spy planes that listen and take radar pictures.'], DH8B: ['Dash 8', 'transport or spy plane'],
    DH8C: ['Dash 8', 'transport or spy plane'], DH8D: ['Dash 8 Q400', 'transport or patrol plane'],
    C26: ['Metroliner (C-26)', 'small surveillance or transport plane'], SW4: ['Metroliner', 'small surveillance or transport plane'],
    E120: ['Embraer Brasilia', 'small transport plane'], E135: ['Embraer ERJ-135', 'transport jet'], E145: ['Embraer ERJ-145', 'transport or radar jet'],
    SF34: ['Saab 340', 'transport or radar plane'], SB20: ['Saab 2000', 'transport or radar plane'], B190: ['Beech 1900', 'small transport plane'],
    B350: ['King Air 350', 'transport or spy plane', 'The US flies these as MC-12 spy planes, and many militaries use them for transport.'],
    BE30: ['King Air 300', 'transport or spy plane'], BE20: ['King Air (C-12)', 'small transport plane'], BE9L: ['King Air 90', 'small transport plane'],
    A748: ['Hawker Siddeley 748', 'small transport plane'], C208: ['Cessna Caravan', 'small prop plane'], BN2P: ['Britten-Norman Islander', 'small prop plane'], DHC6: ['Twin Otter', 'small prop plane'],
    // radar, spy, sub-hunting & drones
    E737: ['E-7 Wedgetail', 'flying radar plane'], E7WW: ['E-7 Wedgetail', 'flying radar plane'], E2: ['E-2 Hawkeye', 'flying radar plane'],
    E767: ['E-767 AWACS', 'flying radar plane'], E3: ['E-3 AWACS', 'flying radar plane'], E4: ['E-4B Nightwatch', 'nuclear command plane'], A50: ['Beriev A-50', 'flying radar plane'], E8: ['E-8 JSTARS', 'spy plane'], U2: ['U-2 Dragon Lady', 'spy plane'],
    IL20: ['Ilyushin Il-20', 'spy plane'], EP3: ['EP-3 Aries', 'spy plane'], P3: ['P-3 Orion', 'sub-hunting plane'], P1: ['Kawasaki P-1', 'sub-hunting plane'],
    ATL2: ['Atlantique 2', 'sub-hunting plane'], IL38: ['Ilyushin Il-38', 'sub-hunting plane'],
    MQ4: ['MQ-4C Triton', 'drone'], Q9: ['MQ-9 Reaper', 'drone'], MQ9: ['MQ-9 Reaper', 'drone'], MQ1: ['MQ-1 Predator', 'drone'], Q1: ['MQ-1 Predator', 'drone'],
    HRON: ['Heron', 'drone'], TB2: ['Bayraktar TB2', 'drone'], RQ4: ['RQ-4 Global Hawk', 'spy drone'], Q4: ['RQ-4 Global Hawk', 'spy drone'], GLHK: ['RQ-4 Global Hawk', 'spy drone'],
    // bombers
    TU95: ['Tu-95 Bear', 'bomber'], T95: ['Tu-95 Bear', 'bomber'], T160: ['Tu-160 Blackjack', 'bomber'], TU60: ['Tu-160 Blackjack', 'bomber'],
    TU22: ['Tu-22M Backfire', 'bomber'], H6: ['Xian H-6', 'bomber'],
    // fighters & attack jets
    F15E: ['F-15E Strike Eagle', 'fighter jet'], F15X: ['F-15EX Eagle II', 'fighter jet'], F18: ['F/A-18 Hornet', 'fighter jet'],
    E18G: ['EA-18G Growler', 'radar-jamming jet'], EA18: ['EA-18G Growler', 'radar-jamming jet'], JAS39: ['Gripen', 'fighter jet'], M2000: ['Mirage 2000', 'fighter jet'],
    AV8B: ['AV-8B Harrier', 'jump jet'], HAR: ['Harrier', 'jump jet'], SU25: ['Su-25 Frogfoot', 'attack jet'],
    // trainers & light attack
    E314: ['Tucano', 'training plane'], T27: ['Tucano', 'training plane'], AT6T: ['AT-6 Wolverine', 'light attack plane'], AT8T: ['Air Tractor AT-802', 'light attack or firefighting plane'],
    T45: ['T-45 Goshawk', 'training jet'], HAWK: ['BAE Hawk', 'training jet'], KT1: ['KT-1 Woongbi', 'training plane'], CT4: ['CT-4 Airtrainer', 'training plane'],
    DA40: ['Diamond DA40', 'training plane'], DA42: ['Diamond DA42', 'training plane'], DA20: ['Diamond DA20', 'training plane'], G120: ['Grob G120', 'training plane'],
    G115: ['Grob Tutor', 'training plane'], SR22: ['Cirrus SR22', 'small prop plane'], L159: ['L-159 ALCA', 'light attack & training jet'], AJET: ['Alpha Jet', 'training jet'],
    M339: ['MB-339', 'training jet'], M346: ['M-346 Master', 'training jet'], T50: ['T-50 Golden Eagle', 'training jet'], T7: ['T-7 Red Hawk', 'training jet'],
    L39: ['L-39 Albatros', 'training jet'], PC21: ['Pilatus PC-21', 'training plane'], PC7: ['Pilatus PC-7', 'training plane'], PC9: ['Pilatus PC-9', 'training plane'],
    SIRA: ['SIAI-Marchetti SF.260', 'training plane'], TUCA: ['Tucano', 'training plane'],
    // helicopters & tiltrotors
    V22: ['V-22 Osprey', 'tiltrotor', 'Takes off like a helicopter, then tilts its rotors forward and flies like a plane.'],
    S70: ['Black Hawk', 'helicopter'], UH60: ['Black Hawk', 'helicopter'], MH60: ['MH-60 Seahawk', 'helicopter'], H60: ['Black Hawk', 'helicopter'],
    CH47: ['Chinook', 'helicopter'], H47: ['Chinook', 'helicopter'], H53: ['CH-53 Sea Stallion', 'helicopter'], H53S: ['CH-53E Super Stallion', 'helicopter'],
    H64: ['AH-64 Apache', 'attack helicopter'], AH64: ['AH-64 Apache', 'attack helicopter'], AH1: ['AH-1Z Viper', 'attack helicopter'],
    H1: ['UH-1Y Venom', 'helicopter'], UH1Y: ['UH-1Y Venom', 'helicopter'], UH1: ['UH-1 Huey', 'helicopter'], TIGR: ['Tiger', 'attack helicopter'],
    MI24: ['Mi-24 Hind', 'attack helicopter'], MI28: ['Mi-28 Havoc', 'attack helicopter'], KA52: ['Ka-52 Alligator', 'attack helicopter'],
    H145: ['H145', 'helicopter'], EC35: ['H135', 'helicopter'], H135: ['H135', 'helicopter'], EC25: ['H225 Super Puma', 'helicopter'],
    AS32: ['Super Puma', 'helicopter'], AS3B: ['Cougar', 'helicopter'], PUMA: ['Puma', 'helicopter'], EC55: ['H155', 'helicopter'],
    A139: ['AW139', 'helicopter'], A169: ['AW169', 'helicopter'], A189: ['AW189', 'helicopter'], NH90: ['NH90', 'helicopter'], EH10: ['AW101 Merlin', 'helicopter'],
    LYNX: ['Lynx', 'helicopter'], WILD: ['Wildcat', 'helicopter'], MI8: ['Mi-8', 'helicopter'], MI17: ['Mi-17', 'helicopter'], MI26: ['Mi-26', 'heavy-lift helicopter'],
    B06: ['Bell 206', 'helicopter'], B407: ['Bell 407', 'helicopter'], B429: ['Bell 429', 'helicopter'], B412: ['Bell 412', 'helicopter'], A109: ['AW109', 'helicopter'],
    EC30: ['H130', 'helicopter'], AS50: ['AS350 Squirrel', 'helicopter'], H500: ['MD 500', 'helicopter'], S92: ['S-92', 'helicopter'],
    AS65: ['MH-65 Dolphin', 'helicopter'], EC45: ['UH-72 Lakota', 'helicopter'], A119: ['AW119 Koala', 'helicopter'],
  };
  const N = window.TYPE_NAMES = window.TYPE_NAMES || {};
  const KIND = {}, BYNAME = {}, NOTE = {};
  // names the radar already had keep winning, except these two that were wrong or vague
  const FIX = new Set(['HAWK', 'PC24']);
  const had = name => typeof kindOf === 'function' && kindOf(name, 'other') !== 'military plane';
  for (const [code, row] of Object.entries(T)) {
    if (N[code] && !FIX.has(code) && had(N[code])) continue; // already named well: leave it exactly as it was
    if (!N[code] || FIX.has(code)) N[code] = row[0];
    KIND[code] = row[1];
    if (row[2]) NOTE[code] = row[2];
    BYNAME[String(N[code]).toLowerCase()] = BYNAME[String(N[code]).toLowerCase()] || row[1];
    BYNAME[row[0].toLowerCase()] = BYNAME[row[0].toLowerCase()] || row[1];
  }
  window.TYPE_NOTE = NOTE;
  // kindOf() in plain.js asks this first (by code "PC24" or by name "Pilatus PC-24")
  window.TYPE_KIND_OF = function (type) {
    const s = String(type || '').trim(); if (!s) return null;
    return KIND[s.toUpperCase()] || BYNAME[s.toLowerCase()] || null;
  };
})();
