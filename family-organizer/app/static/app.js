'use strict';

// ── Colour palette (one per calendar) ────────────────────────────
const PALETTE = [
  '#4C6EF5', '#F03E3E', '#12B886', '#F59F00',
  '#7950F2', '#E64980', '#0CA678', '#FD7E14',
];
const colourMap = new Map();
let colourIdx = 0;

function calColour(calId) {
  if (!colourMap.has(calId)) {
    colourMap.set(calId, PALETTE[colourIdx++ % PALETTE.length]);
  }
  return colourMap.get(calId);
}

// ── Weather emoji map ─────────────────────────────────────────────
const WEATHER_EMOJI = {
  sunny: '☀️', 'clear-night': '🌙',
  partlycloudy: '⛅', cloudy: '☁️',
  fog: '🌫️', rainy: '🌦️', pouring: '🌧️',
  snowy: '❄️', 'snowy-rainy': '🌨️',
  lightning: '⚡', 'lightning-rainy': '⛈️',
  windy: '💨', 'windy-variant': '🌬️', hail: '🌨️',
};

const DAYS = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];
const MONTHS = [
  'January', 'February', 'March', 'April', 'May', 'June',
  'July', 'August', 'September', 'October', 'November', 'December',
];

// ── Clock & date ──────────────────────────────────────────────────
function tick() {
  const now = new Date();
  const hh = String(now.getHours()).padStart(2, '0');
  const mm = String(now.getMinutes()).padStart(2, '0');
  document.getElementById('clock').textContent = `${hh}:${mm}`;
  document.getElementById('date').textContent =
    `${DAYS[now.getDay()]}, ${now.getDate()} ${MONTHS[now.getMonth()]} ${now.getFullYear()}`;
}

// ── Utility helpers ───────────────────────────────────────────────
function isoDate(d) {
  return d.toISOString().slice(0, 10);
}

function evStart(ev) {
  return ev.start?.dateTime ?? ev.start?.date ?? '';
}

function evDateStr(ev) {
  return evStart(ev).slice(0, 10);
}

function fmtTime(ev) {
  if (ev.start?.date) return 'All day';
  const d = new Date(ev.start.dateTime);
  return `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`;
}

function esc(s) {
  return String(s ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;');
}

function calLabel(calId) {
  return calId.replace(/^calendar\./, '').replace(/_/g, ' ');
}

function sortEvs(arr) {
  return [...arr].sort((a, b) => evStart(a).localeCompare(evStart(b)));
}

// ── Render helpers ────────────────────────────────────────────────
function eventCard(ev) {
  const colour = calColour(ev.calendar);
  return `
    <div class="event-card" style="border-left-color:${colour}">
      <div class="ev-time">${fmtTime(ev)}</div>
      <div class="ev-info">
        <div class="ev-title">${esc(ev.summary)}</div>
        <div class="ev-cal">${esc(calLabel(ev.calendar))}</div>
      </div>
    </div>`;
}

function emptyState(msg) {
  return `<p class="empty-state">${msg}</p>`;
}

function setList(id, evs, emptyMsg) {
  document.getElementById(id).innerHTML =
    evs.length ? evs.map(eventCard).join('') : emptyState(emptyMsg);
}

// ── Week grid ─────────────────────────────────────────────────────
function renderWeek(events, today) {
  const todayStr = isoDate(today);
  let html = '';
  for (let i = 0; i < 7; i++) {
    const d = new Date(today);
    d.setDate(d.getDate() + i);
    const ds = isoDate(d);
    const isToday = ds === todayStr;
    const pips = sortEvs(events.filter(e => evDateStr(e) === ds))
      .slice(0, 5)
      .map(e => `<div class="pip" style="background:${calColour(e.calendar)}" title="${esc(e.summary)}"></div>`)
      .join('');
    html += `
      <div class="day-col${isToday ? ' is-today' : ''}">
        <span class="day-name">${DAYS[d.getDay()]}</span>
        <span class="day-num">${d.getDate()}</span>
        <div class="day-pips">${pips}</div>
      </div>`;
  }
  document.getElementById('weekGrid').innerHTML = html;
}

// ── Data loading ──────────────────────────────────────────────────
async function loadWeather() {
  try {
    const r = await fetch('/api/weather');
    const d = await r.json();
    if (!d.state) return;
    const emoji = WEATHER_EMOJI[d.state] ?? '🌤️';
    const temp = d.attributes?.temperature;
    const unit = d.attributes?.temperature_unit ?? '°C';
    const cond = d.state.replace(/-/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
    document.getElementById('wi').textContent = emoji;
    document.getElementById('wtemp').textContent = temp != null ? `${Math.round(temp)}${unit}` : '—';
    document.getElementById('wcond').textContent = cond;
  } catch {
    // silently ignore; weather not critical
  }
}

async function loadAffirmation() {
  try {
    const r = await fetch('/api/affirmation');
    const d = await r.json();
    document.getElementById('affirmationText').textContent = `"${d.text}"`;
  } catch {}
}

async function loadEvents() {
  const [evRes, cfgRes] = await Promise.allSettled([
    fetch('/api/events'),
    fetch('/api/config'),
  ]);

  const events = evRes.status === 'fulfilled'
    ? ((await evRes.value.json()).events ?? [])
    : [];

  const cfg = cfgRes.status === 'fulfilled'
    ? await cfgRes.value.json()
    : {};

  // Pre-register colours for stable assignment across renders
  events.forEach(e => calColour(e.calendar));

  const today = new Date();
  const tomorrow = new Date(today);
  tomorrow.setDate(tomorrow.getDate() + 1);

  const todayStr    = isoDate(today);
  const tomorrowStr = isoDate(tomorrow);
  const schoolCal   = cfg.school_calendar ?? '';

  const todayEvs    = sortEvs(events.filter(e => evDateStr(e) === todayStr && e.calendar !== schoolCal));
  const tomorrowEvs = sortEvs(events.filter(e => evDateStr(e) === tomorrowStr && e.calendar !== schoolCal));
  const schoolEvs   = schoolCal
    ? sortEvs(events.filter(e => evDateStr(e) === todayStr && e.calendar === schoolCal))
    : [];

  setList('todayList',    todayEvs,    'No events today 🎉');
  setList('tomorrowList', tomorrowEvs, 'Nothing scheduled tomorrow');

  const schoolSection = document.getElementById('schoolSection');
  if (schoolEvs.length > 0) {
    schoolSection.style.display = '';
    document.getElementById('schoolList').innerHTML = schoolEvs.map(eventCard).join('');
    // Label the section with the calendar name
    if (schoolCal) {
      document.getElementById('schoolLabel').textContent =
        `School Today — ${calLabel(schoolCal)}`;
    }
  } else {
    schoolSection.style.display = 'none';
  }

  renderWeek(events, today);
}

// ── Bootstrap ─────────────────────────────────────────────────────
tick();
setInterval(tick, 1000);

loadWeather();
loadAffirmation();
loadEvents();

// Refresh data every 5 minutes
setInterval(loadWeather, 5 * 60 * 1000);
setInterval(loadEvents,  5 * 60 * 1000);
// Affirmation rotates daily; re-check hourly near midnight
setInterval(loadAffirmation, 60 * 60 * 1000);
