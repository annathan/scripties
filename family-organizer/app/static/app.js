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

// ── Weather Easter Egg effects ────────────────────────────────────
const WeatherFX = {
  el: null,
  _lightningTimer: null,

  init() { this.el = document.getElementById('weather-fx'); },

  clear() {
    if (this.el) this.el.innerHTML = '';
    clearTimeout(this._lightningTimer);
    this._lightningTimer = null;
    document.body.removeAttribute('data-wx');
  },

  set(condition) {
    this.clear();
    document.body.dataset.wx = condition;
    switch (condition) {
      case 'rainy':            this._rain(55);            break;
      case 'pouring':          this._rain(110);           break;
      case 'lightning-rainy':  this._rain(80); this._lightning(); break;
      case 'snowy':            this._snow(45);            break;
      case 'snowy-rainy':      this._snow(30); this._rain(30);   break;
      case 'hail':             this._hail(65);            break;
      case 'sunny':            this._sun();               break;
      case 'clear-night':      this._stars(35);           break;
      case 'fog':              this._fog();               break;
      case 'windy':
      case 'windy-variant':    this._wind(10);            break;
      case 'partlycloudy':     this._clouds(3);           break;
      case 'cloudy':           this._clouds(6);           break;
    }
  },

  _mk(cls, css) {
    const el = document.createElement('div');
    el.className = cls;
    el.style.cssText = css;
    this.el.appendChild(el);
    return el;
  },

  _rain(n) {
    for (let i = 0; i < n; i++) {
      this._mk('wx-rain', `
        left:${(Math.random() * 105).toFixed(1)}%;
        height:${(14 + Math.random() * 18).toFixed(0)}px;
        animation-duration:${(0.35 + Math.random() * 0.35).toFixed(2)}s;
        animation-delay:${(Math.random() * 2).toFixed(2)}s;
        opacity:${(0.25 + Math.random() * 0.35).toFixed(2)};
      `);
    }
  },

  _hail(n) {
    for (let i = 0; i < n; i++) {
      this._mk('wx-hail', `
        left:${(Math.random() * 100).toFixed(1)}%;
        animation-duration:${(0.45 + Math.random() * 0.4).toFixed(2)}s;
        animation-delay:${(Math.random() * 2).toFixed(2)}s;
        opacity:${(0.35 + Math.random() * 0.4).toFixed(2)};
      `);
    }
  },

  _snow(n) {
    for (let i = 0; i < n; i++) {
      const sz = (4 + Math.random() * 9).toFixed(1);
      this._mk('wx-snow', `
        left:${(Math.random() * 100).toFixed(1)}%;
        width:${sz}px; height:${sz}px;
        --drift:${(-40 + Math.random() * 80).toFixed(0)}px;
        animation-duration:${(3 + Math.random() * 4).toFixed(2)}s;
        animation-delay:${(Math.random() * 5).toFixed(2)}s;
      `);
    }
  },

  _sun() {
    this._mk('wx-sun', '');
    for (let i = 0; i < 7; i++) {
      this._mk('wx-sparkle', `
        top:${(8 + Math.random() * 35).toFixed(0)}%;
        right:${(4 + Math.random() * 28).toFixed(0)}%;
        animation-duration:${(1.8 + Math.random() * 2.4).toFixed(2)}s;
        animation-delay:${(Math.random() * 3).toFixed(2)}s;
      `);
    }
  },

  _stars(n) {
    for (let i = 0; i < n; i++) {
      const sz = (1.5 + Math.random() * 3).toFixed(1);
      this._mk('wx-star', `
        top:${(Math.random() * 85).toFixed(1)}%;
        left:${(Math.random() * 100).toFixed(1)}%;
        width:${sz}px; height:${sz}px;
        animation-duration:${(1.2 + Math.random() * 3.5).toFixed(2)}s;
        animation-delay:${(Math.random() * 5).toFixed(2)}s;
      `);
    }
  },

  _lightning() {
    const flash = this._mk('wx-lightning', '');
    const trigger = () => {
      // double-flash pattern like real lightning
      flash.style.opacity = '1';
      setTimeout(() => { flash.style.opacity = '0';
        setTimeout(() => { flash.style.opacity = '1';
          setTimeout(() => { flash.style.opacity = '0';
            this._lightningTimer = setTimeout(trigger, 4000 + Math.random() * 8000);
          }, 70);
        }, 55);
      }, 80);
    };
    this._lightningTimer = setTimeout(trigger, 800 + Math.random() * 3000);
  },

  _fog() {
    for (let i = 0; i < 4; i++) {
      this._mk('wx-fog', `
        top:${(12 + i * 21).toFixed(0)}%;
        animation-duration:${(18 + i * 6).toFixed(0)}s;
        animation-delay:${(-i * 7).toFixed(0)}s;
        opacity:${(0.14 + i * 0.04).toFixed(2)};
      `);
    }
  },

  _wind(n) {
    for (let i = 0; i < n; i++) {
      this._mk('wx-wind', `
        top:${(8 + Math.random() * 82).toFixed(0)}%;
        width:${(70 + Math.random() * 140).toFixed(0)}px;
        animation-duration:${(1.2 + Math.random() * 2).toFixed(2)}s;
        animation-delay:${(Math.random() * 4).toFixed(2)}s;
        opacity:${(0.14 + Math.random() * 0.22).toFixed(2)};
      `);
    }
  },

  _clouds(n) {
    for (let i = 0; i < n; i++) {
      this._mk('wx-cloud', `
        top:${(4 + Math.random() * 28).toFixed(0)}%;
        animation-duration:${(28 + i * 8).toFixed(0)}s;
        animation-delay:${(-i * 12).toFixed(0)}s;
        opacity:${(0.05 + Math.random() * 0.07).toFixed(2)};
        transform-origin: center;
        transform: scale(${(0.7 + Math.random() * 0.9).toFixed(2)});
      `);
    }
  },
};

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
    WeatherFX.set(d.state);
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
WeatherFX.init();
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
