"""Writes missions.json: what a call sign or a plane type usually means, plus a 'role' the
"Probably doing" line uses (tanker, airlift, heli, trainer ...). Run: python3 tools/build_missions.py"""
import json

# [prefix, mission, unit, one plain sentence, role]
CALLSIGNS = [
    ['AF1', 'Air Force One', '89th Airlift Wing, Joint Base Andrews', 'The President is on board.', 'vip'],
    ['AF2', 'Air Force Two', '89th Airlift Wing, Joint Base Andrews', 'The Vice President is on board.', 'vip'],
    ['SAM', 'Special Air Mission (VIP)', '89th Airlift Wing, Joint Base Andrews', 'Flies cabinet members, top generals and members of Congress.', 'vip'],
    ['VENUS', 'VIP flight', '89th Airlift Wing, Joint Base Andrews', 'A government VIP jet.', 'vip'],
    ['SPAR', 'VIP airlift for generals and admirals', 'US Air Force VIP fleet', 'Carries senior commanders.', 'vip'],
    ['PAT', 'Priority Air Transport', 'US Army operational support airlift', 'Army VIP and priority passenger flights.', 'vip'],
    ['EXEC', 'Executive flight', 'Government VIP transport', 'A VIP passenger flight.', 'vip'],
    ['RCH', 'REACH airlift mission', 'Air Mobility Command', "Cargo, troops or fuel being moved for the Pentagon's global airlift.", 'airlift'],
    ['REACH', 'REACH airlift mission', 'Air Mobility Command', "Cargo, troops or fuel being moved for the Pentagon's global airlift.", 'airlift'],
    ['EVAC', 'Medical evacuation flight', 'Air Force aeromedical evacuation', 'Carries sick or wounded troops with medical crews on board.', 'medevac'],
    ['CNV', 'Navy logistics flight', 'US Navy fleet logistics', 'Moves Navy people and parts to ships and bases.', 'transport'],
    ['NAVY', 'US Navy flight', 'US Navy', 'A Navy plane on a routine flight.', ''],
    ['ARMY', 'US Army flight', 'US Army', 'An Army plane on a routine flight.', ''],
    ['FORTE', 'Global Hawk spy drone', 'RQ-4 out of Sigonella, Italy', 'High-altitude watch flights, often over the Black Sea and Eastern Med.', 'drone'],
    ['OLIVE', 'Rivet Joint signals spy plane', 'RC-135 detachment, RAF Mildenhall', 'Listens to radars and radio traffic.', 'isr'],
    ['JAKE', 'Rivet Joint signals spy plane', 'RC-135, 55th Wing', 'Listens to radars and radio traffic.', 'isr'],
    ['DRAGN', 'U-2 Dragon Lady spy plane', '9th Reconnaissance Wing, Beale AFB', 'Takes pictures and listens from about 70,000 feet.', 'isr'],
    ['SNTRY', 'AWACS radar plane', 'E-3 Sentry', 'A flying radar that watches the whole sky and directs jets.', 'aew'],
    ['NATO', 'NATO AWACS radar plane', 'NATO Airborne Early Warning, Geilenkirchen', "NATO's own flying radar.", 'aew'],
    ['MMF', 'NATO tanker', 'Multinational MRTT Fleet', "NATO's shared refueling and transport jets.", 'tanker'],
    ['QID', 'KC-135 tanker', '100th Air Refueling Wing, RAF Mildenhall', 'The US refueling wing based in England.', 'tanker'],
    ['LAGR', 'KC-135 tanker', '100th Air Refueling Wing, RAF Mildenhall', 'The US refueling wing based in England.', 'tanker'],
    ['SHELL', 'Refueling tanker', 'Tanker call sign', 'A tanker on a refueling track.', 'tanker'],
    ['TEXACO', 'Refueling tanker', 'Tanker call sign', 'A tanker on a refueling track.', 'tanker'],
    ['ARCO', 'Refueling tanker', 'Tanker call sign', 'A tanker on a refueling track.', 'tanker'],
    ['ESSO', 'Refueling tanker', 'Tanker call sign', 'A tanker on a refueling track.', 'tanker'],
    ['EXXON', 'Refueling tanker', 'Tanker call sign', 'A tanker on a refueling track.', 'tanker'],
    ['MOBIL', 'Refueling tanker', 'Tanker call sign', 'A tanker on a refueling track.', 'tanker'],
    ['HOMER', 'Maritime patrol (sub hunter)', 'Maritime patrol squadron', 'Hunts submarines and watches ships.', 'asw'],
    ['TEAL', 'Hurricane Hunter', '53rd Weather Reconnaissance Squadron', 'Flies into storms to measure them.', 'weather'],
    ['KING', 'Rescue tanker', 'Air Force rescue HC-130', 'Search and rescue and helicopter refueling.', 'sar'],
    ['PEDRO', 'Rescue helicopter', 'Air Force rescue HH-60', 'Combat search and rescue.', 'heli_sar'],
    ['JOLLY', 'Rescue helicopter (Jolly Green)', 'Air Force rescue HH-60', 'Combat search and rescue.', 'heli_sar'],
    ['DUSTOFF', 'Army medevac helicopter', 'Army air ambulance', 'Picks up hurt soldiers and flies them to care.', 'heli_sar'],
    ['TEST', 'Test flight', 'Maintenance or test crew', 'Checking a plane after repairs or testing something new.', 'test'],
    ['RRR', 'Royal Air Force airlift (ASCOT)', 'Royal Air Force, UK', 'British military transport.', 'transport'],
    ['ASCOT', 'Royal Air Force airlift', 'Royal Air Force, UK', 'British military transport.', 'transport'],
    ['TARTN', 'Royal Air Force tanker (TARTAN)', 'Royal Air Force Voyager, Brize Norton', 'British air refueling.', 'tanker'],
    ['CFC', 'Canadian Forces flight', 'Royal Canadian Air Force', 'Canadian military flight.', ''],
    ['GAF', 'German Air Force flight', 'Luftwaffe', 'German military flight.', ''],
    ['BAF', 'Belgian Air Force flight', 'Belgian Air Component', 'Belgian military flight.', ''],
    ['NAF', 'Dutch Air Force flight', 'Royal Netherlands Air Force', 'Dutch military flight.', ''],
    ['PLF', 'Polish Air Force flight', 'Polish Air Force', 'Polish military flight.', ''],
    ['IAM', 'Italian Air Force flight', 'Aeronautica Militare', 'Italian military flight.', ''],
    ['CTM', 'French Air Force airlift (COTAM)', 'French Air and Space Force', 'French military transport.', 'transport'],
    ['FAF', 'French Air Force flight', 'French Air and Space Force', 'French military flight.', ''],
    ['FNY', 'French Navy flight', 'French Navy', 'French Navy plane.', ''],
    ['AME', 'Spanish Air Force flight', 'Spanish Air and Space Force', 'Spanish military flight.', ''],
    ['HAF', 'Greek Air Force flight', 'Hellenic Air Force', 'Greek military flight.', ''],
    ['CEF', 'Czech Air Force flight', 'Czech Air Force', 'Czech military flight.', ''],
    ['SVF', 'Swedish Air Force flight', 'Swedish Air Force', 'Swedish military flight.', ''],
    ['NOW', 'Norwegian Air Force flight', 'Royal Norwegian Air Force', 'Norwegian military flight.', ''],
    ['DAF', 'Danish Air Force flight', 'Royal Danish Air Force', 'Danish military flight.', ''],
    ['ASY', 'Australian Air Force flight (AUSSIE)', 'Royal Australian Air Force', 'Australian military flight.', ''],
    ['KIWI', 'New Zealand Air Force flight', 'Royal New Zealand Air Force', 'New Zealand military flight.', ''],
    ['IFC', 'Indian Air Force flight', 'Indian Air Force', 'Indian military flight.', ''],
    ['UAF', 'UAE Air Force flight', 'UAE Air Force', 'Emirati military flight.', ''],
    ['RSF', 'Royal Saudi Air Force flight', 'Royal Saudi Air Force', 'Saudi military flight.', ''],
    ['KAF', 'Kuwait Air Force flight', 'Kuwait Air Force', 'Kuwaiti military flight.', ''],
    ['QAF', 'Qatar Amiri Flight', 'Qatar government', "Qatar's royal and government VIP jets.", 'vip'],
    ['RFF', 'Russian Air Force flight', 'Russian Aerospace Forces', 'A Russian military plane showing on ADS-B.', ''],
    ['RSD', 'Russian government VIP flight', 'Rossiya special flight squadron', 'Flies Russian leaders and officials.', 'vip'],
]

# code: [name, unit, one plain sentence, role]
T = {}


def add(codes, name, unit, desc, role):
    for c in codes.split():
        T[c] = [name, unit, desc, role]


# nuclear command
add('E4B E4', 'NIGHTWATCH, the doomsday plane', '595th Command and Control Group, Offutt AFB', 'Flying Pentagon for the President and Defense Secretary if the ground is lost. Also flies for training and VIP trips.', 'c2')
add('E6', 'Looking Glass / TACAMO nuclear relay', 'Strategic Communications Wing One, Tinker AFB', 'Keeps the line open to nuclear submarines and missile crews.', 'c2')
# spy / radar
add('R135', 'RC-135 signals spy plane', '55th Wing, Offutt AFB', 'Listens to radars and radio traffic. Cousins sniff the air for nuclear tests or fly Open Skies.', 'isr')
add('E3TF E3CF E3', 'AWACS radar plane', 'E-3 Sentry', 'A flying radar that watches the whole sky.', 'aew')
add('E737 E7WW', 'E-7 Wedgetail radar plane', 'Airborne early warning', 'A 737 with a big radar on its back that watches the sky.', 'aew')
add('E2', 'E-2 Hawkeye radar plane', 'Navy carrier air wing', "The carrier's flying radar.", 'aew')
add('A50', 'A-50 Russian radar plane', 'Russian Aerospace Forces', "Russia's flying radar.", 'aew')
add('E8', 'JSTARS ground radar plane', 'E-8 Joint STARS', 'Tracks vehicles moving on the ground.', 'isr')
add('U2', 'U-2 Dragon Lady spy plane', '9th Reconnaissance Wing', 'Takes pictures and listens from about 70,000 feet.', 'isr')
add('IL20', 'Il-20 Russian spy plane', 'Russian Aerospace Forces', 'Russian signals spy plane.', 'isr')
add('GLEX', 'Global Express spy or relay jet', 'Special mission business jet', 'Militaries use these as flying radio relays (E-11A) or ground-watching radar jets.', 'isr')
add('CL60', 'Challenger special-mission jet', 'Military business jet', 'Used for VIPs or as a small spy and radar jet.', 'isr')
add('DH8A DH8B DH8C', 'Dash 8 special-mission plane', 'Surveillance or transport', 'Some carry cameras and radar for border or ocean watch.', 'isr')
# drones
add('RQ4 GLHK', 'RQ-4 Global Hawk spy drone', 'High-altitude drone', 'Flies about 55,000 feet up for a day or more, taking pictures and listening.', 'drone')
add('Q4 MQ4', 'MQ-4C Triton ocean-watch drone', 'Navy drone squadron', 'A Navy Global Hawk that watches ships over the ocean.', 'drone')
add('MQ9 Q9', 'MQ-9 Reaper drone', 'Air Force drone squadron', 'Watches the ground with cameras for many hours and can carry missiles.', 'drone')
add('MQ1 Q1', 'MQ-1 Predator drone', 'Drone squadron', 'Watches the ground with cameras.', 'drone')
add('HRON', 'Heron drone', 'Drone squadron', 'An Israeli-built watch drone.', 'drone')
# sub hunters
add('P8', 'P-8 Poseidon sub hunter', 'Navy / allied maritime patrol', 'A 737 that hunts submarines and watches ships.', 'asw')
add('P3 EP3', 'P-3 Orion patrol plane', 'Maritime patrol', 'Hunts submarines and watches ships.', 'asw')
add('P1', 'Kawasaki P-1 sub hunter', 'Japan Maritime Self-Defense Force', "Japan's submarine hunter.", 'asw')
add('ATL2', 'Atlantique 2 sub hunter', 'French Navy', 'French sub hunter.', 'asw')
add('IL38', 'Il-38 Russian sub hunter', 'Russian Navy', 'Russian maritime patrol plane.', 'asw')
# tankers
add('K35R K35E', 'KC-135 refueling tanker', 'Air Mobility Command / Air National Guard', 'Gas station in the sky for fighters and bombers.', 'tanker')
add('KC46 K46', 'KC-46 Pegasus tanker', 'Air Mobility Command', 'Newest US refueling tanker.', 'tanker')
add('KC10 DC10', 'KC-10 Extender tanker', 'Air Mobility Command', 'Large refueling tanker.', 'tanker')
add('A332 A339', 'Airbus tanker or transport', 'Military A330', 'Often a refueling tanker (MRTT/Voyager).', 'tanker')
add('IL78', 'Il-78 tanker', 'Russian / Indian air force', 'Russian-built refueling tanker.', 'tanker')
add('A310', 'A310 tanker or transport', 'Military A310', 'Used for troops, VIPs or refueling.', 'transport')
# big cargo
add('C17', 'C-17 Globemaster heavy airlift', 'Air Mobility Command', 'Carries tanks, troops and supplies anywhere in the world.', 'airlift')
add('C5M C5', 'C-5 Galaxy, the biggest US cargo jet', 'Air Mobility Command', 'Moves the heaviest loads.', 'airlift')
add('IL76', 'Il-76 heavy cargo plane', 'Military transport', 'Russian-built heavy airlifter.', 'airlift')
add('A400', 'A400M Atlas cargo plane', 'European air forces', 'Big four-propeller cargo and troop carrier.', 'airlift')
add('KC2', 'Kawasaki C-2 cargo plane', 'Japan Air Self-Defense Force', "Japan's big cargo jet.", 'airlift')
add('Y20', 'Y-20 heavy cargo plane', 'Chinese Air Force', "China's big cargo jet.", 'airlift')
add('A124 AN22 AN12', 'Antonov cargo plane', 'Military transport', 'Russian/Ukrainian-built cargo plane.', 'airlift')
# smaller cargo
add('C130 C30J', 'C-130 Hercules cargo plane', 'Tactical airlift', 'Short-runway cargo and troop carrier.', 'tactical')
add('C27J', 'C-27J Spartan cargo plane', 'Tactical airlift / Coast Guard', 'Small twin-propeller cargo plane.', 'tactical')
add('CN35 C295', 'CASA cargo plane', 'Tactical airlift', 'Small cargo and patrol plane.', 'tactical')
add('E390', 'KC-390 Millennium', 'Cargo and tanker jet', 'Brazilian-built cargo jet that can also refuel.', 'tactical')
add('AN26 AN32 AN72', 'Antonov small cargo plane', 'Military transport', 'Twin-engine cargo and troop plane.', 'tactical')
add('C160', 'Transall cargo plane', 'Military transport', 'Older twin-propeller cargo plane.', 'tactical')
add('C212', 'CASA C-212 Aviocar', 'Light transport', 'Small cargo, parachute and patrol plane.', 'tactical')
# bombers
add('B52', 'B-52 Stratofortress bomber', 'Air Force Global Strike Command', 'Long-range heavy bomber that can carry nuclear weapons.', 'bomber')
add('B1', 'B-1B Lancer bomber', 'Air Force Global Strike Command', 'Fast long-range bomber.', 'bomber')
add('B2', 'B-2 Spirit stealth bomber', '509th Bomb Wing, Whiteman AFB', 'Stealth bomber that can carry nuclear weapons.', 'bomber')
add('TU95 T95', 'Tu-95 Bear bomber', 'Russian Long-Range Aviation', 'Russian long-range bomber.', 'bomber')
add('T160 TU60', 'Tu-160 Blackjack bomber', 'Russian Long-Range Aviation', 'Russian supersonic bomber.', 'bomber')
add('TU22', 'Tu-22M Backfire bomber', 'Russian Long-Range Aviation', 'Russian strike bomber.', 'bomber')
add('H6', 'H-6 bomber', 'Chinese Air Force', "China's long-range bomber.", 'bomber')
# fighters & attack
add('F16', 'F-16 fighter', 'Fighter squadron', 'Fighter jet.', 'fighter')
add('F15 F15E F15X', 'F-15 fighter', 'Fighter squadron', 'Fighter jet.', 'fighter')
add('F35', 'F-35 stealth fighter', 'Fighter squadron', 'Stealth fighter jet.', 'fighter')
add('F18S', 'Super Hornet (or Growler)', 'Navy strike fighter squadron', 'Carrier fighter jet.', 'fighter')
add('F18H', 'F/A-18 Hornet', 'Fighter squadron', 'Carrier fighter jet (older model).', 'fighter')
add('F18', 'F/A-18 fighter', 'Navy / Marine fighter squadron', 'Carrier fighter jet.', 'fighter')
add('E18G EA18', 'EA-18G Growler', 'Navy electronic attack squadron', 'Jams enemy radars.', 'fighter')
add('F22', 'F-22 Raptor', 'Fighter squadron', 'Stealth air-superiority fighter.', 'fighter')
add('EUFI', 'Eurofighter Typhoon', 'Allied fighter squadron', 'European fighter jet.', 'fighter')
add('RFAL', 'Rafale', 'Allied fighter squadron', 'French fighter jet.', 'fighter')
add('SB39 GRIF JAS39', 'Gripen', 'Allied fighter squadron', 'Swedish fighter jet.', 'fighter')
add('TOR', 'Tornado', 'Allied strike squadron', 'Strike jet.', 'fighter')
add('MIR2 M2000', 'Mirage 2000', 'Fighter squadron', 'French-built fighter jet.', 'fighter')
add('F5', 'F-5 Tiger II', 'Adversary / training squadron', 'Light fighter, often the enemy in practice dogfights.', 'fighter')
add('A10', 'A-10 Warthog', 'Attack squadron', 'Protects troops on the ground.', 'attack')
add('AV8B HAR', 'AV-8B Harrier', 'Marine attack squadron', 'Jump jet that can take off straight up.', 'attack')
add('SU25', 'Su-25 Frogfoot', 'Attack squadron', 'Russian-built ground-attack jet.', 'attack')
add('E314 T27', 'Super Tucano', 'Light attack / training', 'Propeller plane for training and light attack.', 'trainer')
add('AT8T AT6T', 'Air Tractor patrol plane', 'Border patrol / light attack', 'A tough crop-duster design some militaries arm for border patrol.', 'patrol')
# VIP & passengers
add('C32 B752', 'C-32 VIP jet (757)', '89th Airlift Wing', 'A government VIP 757.', 'vip')
add('VC25 B742 B748', 'Air Force One jet (VC-25)', '89th Airlift Wing', "The President's 747.", 'vip')
add('C40 B737 B738 B739 B734 B38M B733', 'Military 737', 'VIP, troop or logistics transport', 'A 737 used for officials, troops or Navy logistics.', 'transport')
add('A319 A320 A321 A20N A21N', 'Military Airbus jet', 'Government transport', 'Carries officials or troops.', 'transport')
add('B763 B772 B77L B788 B789 A359 A343', 'Military widebody jet', 'Government transport', 'A big jet for leaders or troops.', 'transport')
add('GLF5 GLF6 GLF4 GL5T GL7T', 'Gulfstream VIP jet (C-37 / C-20)', 'Military VIP squadron', 'Flies generals, officials and small teams.', 'vip')
add('FA7X F900 F2TH FA50 FA8X', 'Falcon VIP jet', 'Military VIP squadron', 'A business jet for officials.', 'vip')
add('LJ35 LJ45 LJ60', 'Learjet (C-21)', 'Operational support airlift', 'Small fast jet for a few passengers or parts.', 'utility')
add('C560 C56X C680 C68A C700', 'Cessna Citation (UC-35 / UC-41)', 'Operational support airlift', 'Small jet for a few passengers.', 'utility')
add('T154 IL62 IL96', 'Russian government jet', 'Government transport', 'Russian-built passenger jet for officials.', 'vip')
# small utility planes
add('BE20 B350 BE30', 'King Air (C-12 Huron)', 'Utility / special mission', 'Moves a few people or parts. Some versions carry spy sensors (MC-12 / RC-12).', 'utility')
add('BE9L', 'King Air 90 (T-44)', 'Navy multi-engine training', 'Teaches Navy pilots to fly twin-engine planes.', 'trainer')
add('BE40', 'T-1 Jayhawk', 'Air Force pilot training', 'Trains pilots headed for tankers and cargo planes.', 'trainer')
add('C208', 'Cessna Caravan', 'Utility', 'Small single-propeller utility plane.', 'utility')
add('PC12', 'PC-12 (U-28A)', 'Special operations / utility', 'Small plane used for special-ops spying or moving people.', 'isr')
add('DHC6', 'Twin Otter', 'Utility', 'Small rugged plane for short runways and parachuting.', 'utility')
add('E120 E135 E145 E35L', 'Embraer jet', 'Government transport', 'Moves officials or small groups.', 'utility')
add('C26 SW4', 'C-26 Metroliner', 'National Guard / special mission', 'Small plane, sometimes with cameras for counter-drug work.', 'utility')
# trainers
add('TEX2 T6', 'T-6 Texan II trainer', 'Pilot training', 'Where new military pilots learn to fly.', 'trainer')
add('T38', 'T-38 Talon jet trainer', 'Pilot training', 'Supersonic trainer for future fighter and bomber pilots.', 'trainer')
add('HAWK T45', 'Hawk jet trainer', 'Advanced pilot training', 'Jet trainer for future fighter pilots.', 'trainer')
add('PC7 PC9 PC21', 'Pilatus trainer', 'Pilot training', 'Propeller trainer for new military pilots.', 'trainer')
add('KT1', 'KT-1 Woongbi trainer', 'Pilot training', 'Korean-built propeller trainer.', 'trainer')
add('CT4 DA40 DA42 G120 G115 SR22 P28A C172', 'Basic trainer', 'Flight school', 'Small plane where cadets take their first flights.', 'trainer')
add('M346 L39 L159 AJET M339 T50 T7', 'Jet trainer', 'Advanced pilot training', 'Jet trainer for future fighter pilots.', 'trainer')
# helicopters
add('H60 S70 UH60 MH60', 'Black Hawk / Seahawk helicopter', 'Army / Navy / Air Force', 'The workhorse helicopter: troops, rescue, medevac and sub hunting.', 'heli')
add('H47 CH47', 'CH-47 Chinook helicopter', 'Army heavy-lift helicopter', 'Two-rotor helicopter that carries troops and big loads.', 'heli_cargo')
add('H53 H53S', 'CH-53 Super Stallion helicopter', 'Marine heavy-lift helicopter', 'The biggest US helicopter, for Marines and heavy loads.', 'heli_cargo')
add('H64 AH64', 'AH-64 Apache attack helicopter', 'Army attack helicopter', 'Gunship helicopter.', 'heli_attack')
add('AH1 H1 UH1Y UH1', 'Huey / Cobra helicopter', 'Marine or Army helicopter', 'Utility or attack helicopter.', 'heli')
add('TIGR MI24 MI28', 'Attack helicopter', 'Army aviation', 'Gunship helicopter.', 'heli_attack')
add('EC45 H145', 'UH-72 Lakota helicopter', 'Army / National Guard', 'Light helicopter for training, medevac and border work.', 'heli')
add('EC35 H135', 'EC135 helicopter', 'Military helicopter training', 'Light twin-engine helicopter many militaries train on.', 'heli')
add('AS65', 'MH-65 Dolphin helicopter', 'US Coast Guard', 'The Coast Guard rescue helicopter.', 'heli_sar')
add('EC25 AS32 AS3B PUMA EC55', 'Super Puma helicopter', 'Military transport helicopter', 'Medium helicopter for troops and rescue.', 'heli')
add('A139 A169 A189', 'AW139 helicopter (MH-139)', 'Military / government helicopter', 'Medium helicopter for rescue, VIPs and missile-field security.', 'heli')
add('NH90 EH10 LYNX WILD', 'Navy / army helicopter', 'Military helicopter', 'Used for troops, rescue and sub hunting.', 'heli')
add('MI8 MI17', 'Mi-8/17 helicopter', 'Military transport helicopter', 'Russian-built transport helicopter.', 'heli')
add('B06 B407 B429 A109 A119 EC30 AS50 H500', 'Light helicopter', 'Training or utility', 'Small helicopter for training or quick trips.', 'heli')
add('S92', 'VH-92 / S-92 helicopter', 'Marine One fleet or rescue', 'Can be a presidential helicopter or a rescue helicopter.', 'heli')
add('V22', 'V-22 Osprey tiltrotor', 'Marines / Air Force special ops', 'Takes off like a helicopter, flies like a plane.', 'tiltrotor')
add('B762 K767 E767', 'Military 767 (KC-46 / KC-767)', 'Air refueling', 'Almost always a refueling tanker. Japan also flies an E-767 radar version.', 'tanker')
# odd ones
add('TWR', 'Ground radio station', 'Not a plane', 'A ground transmitter that shows up on the tracker.', 'ground')

CATS = {
    'tanker': ['Air refueling tanker', '', 'Gas station in the sky.', 'tanker'],
    'bomber': ['Bomber', '', 'Long-range strike plane.', 'bomber'],
    'airlift': ['Heavy airlift', '', 'Moving troops and equipment.', 'airlift'],
    'tactical': ['Tactical airlift', '', 'Smaller cargo and troop carrier.', 'tactical'],
    'isr': ['Spy / surveillance flight', '', 'Watching and listening.', 'isr'],
    'c2': ['Nuclear command flight', '', 'Part of the chain that carries nuclear orders.', 'c2'],
    'fighter': ['Fighter jet', '', 'Fighter.', 'fighter'],
    'other': ['Military flight', '', 'A military plane.', ''],
}

out = {
    '_about': 'Watchman Radar mission decoder. callsigns: [prefix, mission, unit, sentence, role]. types: code -> [name, unit, sentence, role]. '
              'role feeds the "Probably doing" line in doing.js. Public knowledge, best guesses.',
    'callsigns': CALLSIGNS, 'types': T, 'cats': CATS,
}
json.dump(out, open('missions.json', 'w'), indent=0, ensure_ascii=False)
print(len(CALLSIGNS), 'callsigns', len(T), 'types')
