/* MIDEAST NEWS: live Iran / Israel / Middle East news desk (mideast.json from the watcher, every sweep). */
(() => {
'use strict';
const WR = window.WR;
if (!WR) return;
const $ = s => document.querySelector(s);
const esc = s => String(s == null ? '' : s).replace(/[&<>"']/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[c]));
const tb = k => (typeof tipBtn === 'function' ? tipBtn(k) : '');
const CHIPS = [
  ['all', 'All'], ['iran', 'Iran'], ['israel', 'Israel'], ['lebanon', 'Lebanon / Hezbollah'],
  ['syria', 'Syria'], ['yemen', 'Yemen / Houthis'], ['gulf', 'Gulf'],
];
const TAGNAME = {iran: 'IRAN', israel: 'ISRAEL', lebanon: 'LEBANON', syria: 'SYRIA', yemen: 'YEMEN', gulf: 'GULF'};
const SEEN_KEY = 'wr_me_seen';
let data = null, isOpen = false, chip = 'all', milOnly = false, shownSince = 0;
try { chip = localStorage.getItem('wr_me_chip') || 'all'; milOnly = localStorage.getItem('wr_me_mil') === '1'; } catch (e) { /* ignore */ }
if (!CHIPS.some(c => c[0] === chip)) chip = 'all';
const seen = () => { try { return +localStorage.getItem(SEEN_KEY) || 0; } catch (e) { return 0; } };

Object.assign(window.TIPS_EXTRA = window.TIPS_EXTRA || {}, {
  mideast: 'Live news about Iran, Israel and the rest of the Middle East. The watchtower reads free news feeds about every 10 minutes (Times of Israel, Jerusalem Post, Iran International, Al Jazeera, Al-Monitor, i24NEWS, Reuters, AP, The War Zone, BBC and more), keeps the last two days, takes out repeats and puts the newest on top. Tap a story to read the whole article. A red MILITARY tag means the headline is about strikes, troops moving, warships or carriers, aircraft deployments, missile or drone launches, or air defense; the words after it say which.',
});

function ago(ts) {
  const s = Math.max(0, Date.now() / 1000 - ts);
  if (s < 90) return 'just now';
  if (s < 3600) return Math.round(s / 60) + ' min ago';
  if (s < 86400) return Math.round(s / 3600) + ' hr ago';
  const d = Math.round(s / 86400);
  return d + (d === 1 ? ' day ago' : ' days ago');
}
function ct(ts) {
  const d = new Date(ts * 1000), now = new Date();
  const day = x => x.toLocaleDateString([], {timeZone: 'America/Chicago'});
  const t = d.toLocaleTimeString([], {hour: 'numeric', minute: '2-digit', timeZone: 'America/Chicago'});
  return (day(d) === day(now) ? t : d.toLocaleDateString([], {weekday: 'short', timeZone: 'America/Chicago'}) + ' ' + t) + ' CT';
}

function stories() {
  let s = (data && data.stories) || [];
  if (chip !== 'all') s = s.filter(x => (x.tags || []).includes(chip));
  if (milOnly) s = s.filter(x => x.mil && x.mil.length);
  return s;
}
function card(s) {
  const mil = s.mil && s.mil.length;
  const fresh = shownSince && (s.seen || s.t) > shownSince;
  return `<a class="mecard${mil ? ' mil' : ''}" href="${esc(s.link)}" target="_blank" rel="noopener">` +
    `<div class="metop"><b class="mesrc">${esc(s.src)}</b><span class="meago">${esc(ago(s.t))} &middot; ${esc(ct(s.t))}</span></div>` +
    `<div class="mebadges">${fresh ? '<i class="menew">NEW</i>' : ''}` +
    (mil ? `<i class="memil">&#9876; MILITARY &middot; ${esc(s.mil.join(' \u00B7 '))}</i>` : '') +
    (s.tags || []).map(t => `<i class="metag">${TAGNAME[t] || esc(t)}</i>`).join('') + '</div>' +
    `<h4>${esc(s.title)}</h4>` + (s.snip ? `<p>${esc(s.snip)}</p>` : '') + '</a>';
}
function render() {
  const body = $('#mebody');
  if (!body) return;
  const c = (data && data.counts) || {}, all = (data && data.stories) || [];
  $('#mechips').innerHTML = CHIPS.map(([k, n]) => {
    const num = k === 'all' ? all.length : (c[k] || 0);
    return `<button data-me="${k}" class="${chip === k ? 'on' : ''}">${esc(n)} <small>${num}</small></button>`;
  }).join('') + `<button data-memil="1" class="memilchip${milOnly ? ' on' : ''}">&#9876; Military only <small>${c.mil || 0}</small></button>`;
  $('#mesub').textContent = data ? `Updated ${ago(data.updated)} \u00B7 ${data.count} stories, last ${data.keep_hours || 48} hrs` : 'Linking to the watchtower\u2026';
  if (!data) { body.innerHTML = '<div class="meempty">Loading the Middle East news&hellip;</div>'; return; }
  const list = stories();
  body.innerHTML = list.length ? list.map(card).join('') + `<div class="mefoot">Newest first &middot; refreshes about every 10 minutes &middot; free news feeds ${tb('mideast')}</div>`
    : `<div class="meempty">No ${milOnly ? 'military ' : ''}stories for ${esc((CHIPS.find(x => x[0] === chip) || CHIPS[0])[1])} in the last ${data.keep_hours || 48} hours.</div>`;
}
function badge() {
  const dot = $('#meBadge');
  if (!dot || !data) return;
  const since = seen();
  dot.classList.toggle('on', !isOpen && (data.stories || []).some(s => s.mil && s.mil.length && (s.seen || s.t) > since));
}

function open() {
  isOpen = true;
  shownSince = seen();
  const el = $('#mes'); el.classList.add('open'); el.setAttribute('aria-hidden', 'false');
  document.querySelectorAll('.tabs button').forEach(b => b.classList.toggle('on', b.dataset.go === 'mideast'));
  if (location.hash !== '#mideast') history.replaceState(null, '', '#mideast');
  render(); $('#mebody').scrollTop = 0;
  markSeen(); badge();
}
function markSeen() {
  if (!data) return;
  try { localStorage.setItem(SEEN_KEY, String(Math.max(seen(), ...(data.stories || []).map(s => s.seen || s.t)))); } catch (e) { /* ignore */ }
}
function close(keepTab) {
  if (!isOpen) return;
  isOpen = false;
  const el = $('#mes'); el.classList.remove('open'); el.setAttribute('aria-hidden', 'true');
  if (location.hash === '#mideast') history.replaceState(null, '', location.pathname + location.search);
  if (!keepTab) WR.showTab(WR.lastTab || 'map');
  badge();
}
$('#closeMe').onclick = () => close();
const ob = $('#openMe'); if (ob) ob.onclick = () => (isOpen ? close() : open());
document.querySelectorAll('.tabs button').forEach(b => {
  if (b.dataset.go === 'mideast') b.onclick = () => { if (!isOpen) open(); };
  else b.addEventListener('click', () => { if (isOpen) close(true); }, true);
});
// the header buttons for INTEL / SQUAWKS / COMMAND open their own screens: step aside for them
['#openIx', '#openSq', '#openCmd'].forEach(id => { const b = $(id); if (b) b.addEventListener('click', () => { if (isOpen) close(true); }, true); });
document.addEventListener('keydown', ev => { if (ev.key === 'Escape' && isOpen) close(); });
$('#mechips').addEventListener('click', ev => {
  const b = ev.target.closest('button');
  if (!b) return;
  if (b.dataset.memil) milOnly = !milOnly; else chip = b.dataset.me;
  try { localStorage.setItem('wr_me_chip', chip); localStorage.setItem('wr_me_mil', milOnly ? '1' : '0'); } catch (e) { /* ignore */ }
  render(); $('#mebody').scrollTop = 0;
});
window.addEventListener('hashchange', () => { if (location.hash === '#mideast') open(); });

async function refresh() {
  let d = null;
  try { d = await WR.getJSON('mideast.json'); } catch (e) { d = null; } // WR.getJSON adds the data-branch address
  if (d && d.stories) {
    data = d;
    if (isOpen) { const top = $('#mebody').scrollTop; render(); $('#mebody').scrollTop = top; markSeen(); }
    badge();
  }
}
(async () => {
  await refresh();
  if (location.hash === '#mideast') open();
  setInterval(refresh, 60000);
  setInterval(() => { if (isOpen && data) $('#mesub').textContent = `Updated ${ago(data.updated)} \u00B7 ${data.count} stories, last ${data.keep_hours || 48} hrs`; }, 30000);
})();
WR.mideast = {open, close, refresh, get data() { return data; }};
})();
