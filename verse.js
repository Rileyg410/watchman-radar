/* WATCHMAN RADAR // verse card: a watchman's verse for today on the RADAR tab (KJV).
   A new verse each day, browse with the arrows, a short prayer, share.
   When the threat gauge reads HIGH, today's card turns to a shelter verse. */
(() => {
'use strict';
const WR = window.WR;
const $ = s => document.querySelector(s);
const esc = s => String(s == null ? '' : s).replace(/[&<>"']/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[c]));
const KEY = 'wr_vcard';
const prefs = Object.assign({on: true}, JSON.parse(localStorage.getItem(KEY) || '{}'));
const save = () => localStorage.setItem(KEY, JSON.stringify(prefs));

// [reference, text, watch note, shelter verse?]
const V = [
  ['Habakkuk 2:1', 'I will stand upon my watch, and set me upon the tower, and will watch to see what he will say unto me, and what I shall answer when I am reproved.', 'The watchman\u2019s post: eyes on the sky, ears on the Lord.'],
  ['Isaiah 62:6', 'I have set watchmen upon thy walls, O Jerusalem, which shall never hold their peace day nor night: ye that make mention of the LORD, keep not silence,', 'Watchmen on the walls of Jerusalem, day and night.'],
  ['Ezekiel 33:7', 'So thou, O son of man, I have set thee a watchman unto the house of Israel; therefore thou shalt hear the word at my mouth, and warn them from me.', 'A watchman hears first, then warns.'],
  ['Luke 21:28', 'And when these things begin to come to pass, then look up, and lift up your heads; for your redemption draweth nigh.', 'Every blip on the scope is a reason to look up.'],
  ['Mark 13:37', 'And what I say unto you I say unto all, Watch.', 'One word for every believer: Watch.'],
  ['Luke 21:36', 'Watch ye therefore, and pray always, that ye may be accounted worthy to escape all these things that shall come to pass, and to stand before the Son of man.', 'Watch and pray go together.'],
  ['Psalm 121:4', 'Behold, he that keepeth Israel shall neither slumber nor sleep.', 'The radar sleeps between checks. He never does.', 1],
  ['Psalm 91:1', 'He that dwelleth in the secret place of the most High shall abide under the shadow of the Almighty.', 'The safest place on the map.', 1],
  ['Psalm 91:5', 'Thou shalt not be afraid for the terror by night; nor for the arrow that flieth by day;', 'For the night watch, and for anything that flies.', 1],
  ['Isaiah 21:11', 'He calleth to me out of Seir, Watchman, what of the night? Watchman, what of the night?', 'The question every night watch answers.'],
  ['1 Thessalonians 5:6', 'Therefore let us not sleep, as do others; but let us watch and be sober.', 'Awake and clear-eyed.'],
  ['Revelation 16:15', 'Behold, I come as a thief. Blessed is he that watcheth, and keepeth his garments, lest he walk naked, and they see his shame.', 'A blessing for the one who watches.'],
  ['Zechariah 12:3', 'And in that day will I make Jerusalem a burdensome stone for all people: all that burden themselves with it shall be cut in pieces, though all the people of the earth be gathered together against it.', 'Why so many eyes, and so many jets, turn toward Jerusalem.'],
  ['Psalm 122:6', 'Pray for the peace of Jerusalem: they shall prosper that love thee.', 'When the map lights up over Israel, pray this one.'],
  ['Ezekiel 38:16', 'And thou shalt come up against my people of Israel, as a cloud to cover the land; it shall be in the latter days, and I will bring thee against my land, that the heathen may know me, when I shall be sanctified in thee, O Gog, before their eyes.', 'The northern alliance, and the God who ends it.'],
  ['Psalm 83:4', 'They have said, Come, and let us cut them off from being a nation; that the name of Israel may be no more in remembrance.', 'The plan of the nations around Israel, written long ago.'],
  ['Isaiah 26:20', 'Come, my people, enter thou into thy chambers, and shut thy doors about thee: hide thyself as it were for a little moment, until the indignation be overpast.', 'A door shut by God, like Noah\u2019s.', 1],
  ['2 Chronicles 20:15', 'Be not afraid nor dismayed by reason of this great multitude; for the battle is not yours, but God\u2019s.', 'However many planes are up, the battle is His.', 1],
  ['Joel 2:1', 'Blow ye the trumpet in Zion, and sound an alarm in my holy mountain: let all the inhabitants of the land tremble: for the day of the LORD cometh, for it is nigh at hand;', 'The shofar alarm, the oldest alert there is.'],
  ['Titus 2:13', 'Looking for that blessed hope, and the glorious appearing of the great God and our Saviour Jesus Christ;', 'What the watchman is really looking for.'],
  ['1 Thessalonians 4:17', 'Then we which are alive and remain shall be caught up together with them in the clouds, to meet the Lord in the air: and so shall we ever be with the Lord.', 'The flight no radar will track.'],
  ['Psalm 46:1', 'God is our refuge and strength, a very present help in trouble.', 'A refuge closer than any base.', 1],
  ['Psalm 46:10', 'Be still, and know that I am God: I will be exalted among the heathen, I will be exalted in the earth.', 'Between alerts: be still.'],
  ['Isaiah 40:31', 'But they that wait upon the LORD shall renew their strength; they shall mount up with wings as eagles; they shall run, and not be weary; and they shall walk, and not faint.', 'Wings that never need a tanker.'],
  ['Psalm 18:10', 'And he rode upon a cherub, and did fly: yea, he did fly upon the wings of the wind.', 'The Lord in flight.'],
  ['Isaiah 31:5', 'As birds flying, so will the LORD of hosts defend Jerusalem; defending also he will deliver it; and passing over he will preserve it.', 'The LORD\u2019s own air cover over Jerusalem.', 1],
  ['Psalm 127:1', 'Except the LORD build the house, they labour in vain that build it: except the LORD keep the city, the watchman waketh but in vain.', 'The watchman watches. The Lord keeps.', 1],
  ['Zechariah 2:5', 'For I, saith the LORD, will be unto her a wall of fire round about, and will be the glory in the midst of her.', 'A wall of fire around Jerusalem.', 1],
  ['Revelation 22:20', 'He which testifieth these things saith, Surely I come quickly. Amen. Even so, come, Lord Jesus.', 'The last prayer in the Bible.'],
  ['Amos 3:7', 'Surely the Lord GOD will do nothing, but he revealeth his secret unto his servants the prophets.', 'He tells His watchmen ahead of time.'],
  ['Daniel 12:4', 'But thou, O Daniel, shut up the words, and seal the book, even to the time of the end: many shall run to and fro, and knowledge shall be increased.', 'Thousands of planes running to and fro on one map.'],
];
const SHELTER = V.map((v, i) => v[3] ? i : -1).filter(i => i >= 0);
const PRAY = [
  'Lord, make me a faithful watchman. Open my eyes to what You are doing, and keep my heart ready for Your coming. Cover Israel, cover my family, and give me Your peace while I watch. In Jesus\u2019 name, Amen.',
  'Father, You neither slumber nor sleep. Guard Jerusalem, guard the people I love, and keep me awake to Your voice. Let me look up, not in fear, but in hope. In Jesus\u2019 name, Amen.',
];

const dayNum = () => Math.floor((Date.now() - new Date().getTimezoneOffset() * 60000) / 86400000);
const lvNow = () => { const g = document.querySelector('.gauge'); return g ? g.dataset.lv : ''; };
function todayIdx() {
  if (lvNow() === 'HIGH') return SHELTER[dayNum() % SHELTER.length];
  return dayNum() % V.length;
}
let idx = todayIdx(), browsing = false, lastLv = lvNow();

const card = document.createElement('div');
card.className = 'vcard';
card.innerHTML = `
<div class="vtop"><span class="vk" id="vKicker"></span><span class="vdate" id="vDate"></span></div>
<div class="vtxt" id="vTxt"></div>
<div class="vref" id="vRef"></div>
<div class="vnote" id="vNote"></div>
<div class="vpray" id="vPray" hidden></div>
<div class="vact">
  <button class="vnav" id="vPrev" aria-label="Previous verse">&#8249;</button>
  <button class="vbtn" id="vPrayBtn">&#128591; Pray</button>
  <button class="vbtn" id="vShare">&#10148; Share</button>
  <button class="vnav" id="vNext" aria-label="Next verse">&#8250;</button>
</div>`;
const title = document.createElement('div');
title.className = 'ptitle';
title.innerHTML = 'WATCHMAN&rsquo;S VERSE <span>// a new one every day</span> <button class="i" data-tip="vcard" aria-label="What is this?">i</button>';
(window.TIPS_EXTRA = window.TIPS_EXTRA || {}).vcard = 'A Bible verse for today\u2019s watch, a new one every day (King James). Tap the arrows to read more. Pray shows a short prayer to pray with it, and Share sends it to someone. When the threat gauge reads HIGH, the card switches to a shelter verse like Psalm 91. You can hide it in Sounds & Effects.';

// it sits right under the threat gauge on the RADAR tab
const anchor = $('.scopepanel .gauge') || $('.scopewrap');
anchor.after(title); title.after(card);

function paint() {
  const [ref, txt, note] = V[idx];
  const high = lvNow() === 'HIGH' && !browsing;
  $('#vKicker').innerHTML = browsing ? '&#10022; MORE VERSES' : (high ? '&#128737; SHELTER VERSE \u00B7 HIGH DAY' : '&#10022; TODAY\u2019S WATCH');
  $('#vDate').textContent = new Date().toLocaleDateString('en-US', {timeZone: 'America/Chicago', weekday: 'short', month: 'short', day: 'numeric'}).toUpperCase();
  $('#vTxt').innerHTML = '&ldquo;' + esc(txt) + '&rdquo;';
  $('#vRef').textContent = ref.toUpperCase();
  $('#vNote').textContent = note;
  card.classList.toggle('high', high);
  const pr = $('#vPray');
  if (!pr.hidden) pr.textContent = PRAY[idx % PRAY.length];
}
function go(step) {
  idx = (idx + step + V.length) % V.length;
  browsing = idx !== todayIdx();
  card.classList.remove('flip'); void card.offsetWidth; card.classList.add('flip');
  paint();
}
$('#vPrev').onclick = () => go(-1);
$('#vNext').onclick = () => go(1);
$('#vPrayBtn').onclick = () => {
  const pr = $('#vPray');
  pr.hidden = !pr.hidden;
  if (!pr.hidden) pr.textContent = PRAY[idx % PRAY.length];
  $('#vPrayBtn').classList.toggle('on', !pr.hidden);
  $('#vPrayBtn').innerHTML = pr.hidden ? '&#128591; Pray' : '&#128591; Amen';
};
$('#vShare').onclick = async () => {
  const [ref, txt] = V[idx];
  const msg = '\u201C' + txt + '\u201D ' + ref + ' (KJV)\n\nWatchman\u2019s verse from my radar';
  try {
    if (navigator.share) { await navigator.share({text: msg}); return; }
    await navigator.clipboard.writeText(msg); WR.toast('\u{1F4DC} Verse copied');
  } catch (e) { if (e && e.name !== 'AbortError') WR.toast('Could not share this one'); }
};
// swipe left or right on the card to browse
let sx = null;
card.addEventListener('touchstart', e => { sx = e.touches[0].clientX; }, {passive: true});
card.addEventListener('touchend', e => { if (sx == null) return; const dx = e.changedTouches[0].clientX - sx; sx = null; if (Math.abs(dx) > 60) go(dx < 0 ? 1 : -1); }, {passive: true});

// a new day, or the gauge turning HIGH, brings a fresh card (unless he is browsing)
let lastDay = dayNum();
function check() {
  const lv = lvNow(), d = dayNum();
  if (!browsing && (lv !== lastLv || d !== lastDay)) { idx = todayIdx(); paint(); }
  lastLv = lv; lastDay = d;
}
WR.hooks.push(() => setTimeout(check, 50));
setInterval(check, 60000);

// show or hide it from Sounds & Effects
function apply() { card.hidden = !prefs.on; title.hidden = !prefs.on; }
const fxb = $('.fxbox');
if (fxb) {
  const row = document.createElement('div');
  row.className = 'fxrow';
  row.innerHTML = '<span><b>&#10022; Verse card</b><small>The verse of the day on this tab</small></span><label class="tog"><input type="checkbox" id="vToggle"><i></i></label>';
  const glitchBtn = fxb.querySelector('.fxglitch');
  fxb.insertBefore(row, glitchBtn);
  const t = row.querySelector('input'); t.checked = prefs.on;
  t.onchange = () => { prefs.on = t.checked; save(); apply(); };
}
paint(); apply();
})();
