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

const DAYS   = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];
const MONTHS = [
  'January', 'February', 'March', 'April', 'May', 'June',
  'July', 'August', 'September', 'October', 'November', 'December',
];

// ── Shared event cache (populated by loadEvents, read by LeaveSoon) ─
let _events = [];
let _config = {};
let _selectedDateStr = null;
let _leaveSoonMinutes = 25;

// ══════════════════════════════════════════════════════════════════
//  Clock & date
// ══════════════════════════════════════════════════════════════════
function tick() {
  const now = new Date();
  const hh = String(now.getHours()).padStart(2, '0');
  const mm = String(now.getMinutes()).padStart(2, '0');
  const timeStr = `${hh}:${mm}`;
  const dateStr = `${DAYS[now.getDay()]}, ${now.getDate()} ${MONTHS[now.getMonth()]} ${now.getFullYear()}`;

  document.getElementById('clock').textContent = timeStr;
  document.getElementById('date').textContent  = dateStr;

  // Mirror into screensaver overlay
  document.getElementById('ssTime').textContent = timeStr;
  document.getElementById('ssDate').textContent =
    `${DAYS[now.getDay()]}, ${now.getDate()} ${MONTHS[now.getMonth()]}`;
}

// ══════════════════════════════════════════════════════════════════
//  Utilities
// ══════════════════════════════════════════════════════════════════
function isoDate(d)  { return d.toISOString().slice(0, 10); }
function evStart(ev) { return ev.start?.dateTime ?? ev.start?.date ?? ''; }
function evDateStr(ev) { return evStart(ev).slice(0, 10); }

function fmtTime(ev) {
  if (ev.start?.date) return 'All day';
  const d = new Date(ev.start.dateTime);
  return `${String(d.getHours()).padStart(2,'0')}:${String(d.getMinutes()).padStart(2,'0')}`;
}

function esc(s) {
  return String(s ?? '')
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

function calLabel(calId) {
  return calId.replace(/^calendar\./, '').replace(/_/g, ' ');
}

function dayLabel(dateStr, todayStr, tomorrowStr) {
  if (dateStr === todayStr) return 'Today';
  if (dateStr === tomorrowStr) return 'Tomorrow';
  const d = new Date(dateStr + 'T00:00:00');
  return `${DAYS[d.getDay()]}, ${d.getDate()} ${MONTHS[d.getMonth()]}`;
}

function emptyMsgFor(dateStr, todayStr, tomorrowStr) {
  if (dateStr === todayStr)    return 'No events today 🎉';
  if (dateStr === tomorrowStr) return 'Nothing scheduled tomorrow';
  return 'Nothing scheduled';
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

function emptyState(msg) { return `<p class="empty-state">${msg}</p>`; }

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
    const pips = sortEvs(events.filter(e => evDateStr(e) === ds))
      .slice(0, 5)
      .map(e => `<div class="pip" style="background:${calColour(e.calendar)}" title="${esc(e.summary)}"></div>`)
      .join('');
    const classes = ['day-col'];
    if (ds === todayStr)         classes.push('is-today');
    if (ds === _selectedDateStr) classes.push('is-selected');
    html += `
      <div class="${classes.join(' ')}" onclick="selectDay('${ds}')">
        <span class="day-name">${DAYS[d.getDay()]}</span>
        <span class="day-num">${d.getDate()}</span>
        <div class="day-pips">${pips}</div>
      </div>`;
  }
  document.getElementById('weekGrid').innerHTML = html;
}

function selectDay(dateStr) {
  _selectedDateStr = dateStr;
  renderWeek(_events, new Date());
  renderDayLists();
}

// ══════════════════════════════════════════════════════════════════
//  Photo Screensaver
// ══════════════════════════════════════════════════════════════════
const Screensaver = {
  photos:      [],
  idx:         0,
  idleTimer:   null,
  slideTimer:  null,
  IDLE_MS:     3 * 60 * 1000,   // show after 3 min idle
  SLIDE_MS:    30 * 1000,       // rotate every 30 s

  async init() {
    try {
      const r = await fetch('/api/photos');
      this.photos = (await r.json()).photos ?? [];
    } catch {}

    if (this.photos.length === 0) return;

    const ss = document.getElementById('screensaver');
    ss.addEventListener('click',      () => this.hide());
    ss.addEventListener('touchstart', () => this.hide(), { passive: true });

    const resetEvents = ['touchstart', 'mousedown', 'keydown', 'mousemove'];
    resetEvents.forEach(ev =>
      document.addEventListener(ev, () => this._resetIdle(), { passive: true })
    );

    this._resetIdle();
  },

  _resetIdle() {
    clearTimeout(this.idleTimer);
    this.idleTimer = setTimeout(() => this._show(), this.IDLE_MS);
  },

  _show() {
    const ss = document.getElementById('screensaver');
    ss.style.display = '';
    this._displayPhoto();
    this.slideTimer = setInterval(() => this._advance(), this.SLIDE_MS);
  },

  hide() {
    document.getElementById('screensaver').style.display = 'none';
    clearInterval(this.slideTimer);
    this._resetIdle();
  },

  _displayPhoto() {
    const url = this.photos[this.idx % this.photos.length];
    const el  = document.getElementById('ssPhoto');
    el.style.backgroundImage = `url('${encodeURI(url)}')`;
    el.classList.remove('fade-out');
  },

  _advance() {
    const el = document.getElementById('ssPhoto');
    el.classList.add('fade-out');
    setTimeout(() => {
      this.idx = (this.idx + 1) % this.photos.length;
      this._displayPhoto();
    }, 1500);
  },
};

// ══════════════════════════════════════════════════════════════════
//  Leaving Soon Banner
// ══════════════════════════════════════════════════════════════════
function checkLeavingSoon() {
  const now     = Date.now();
  const warnMs  = _leaveSoonMinutes * 60 * 1000;
  const banner  = document.getElementById('leaveBanner');

  const candidate = _events
    .filter(ev => {
      if (!ev.location || !ev.start?.dateTime) return false;
      const ms = new Date(ev.start.dateTime).getTime() - now;
      return ms > 0 && ms <= warnMs;
    })
    .sort((a, b) =>
      new Date(a.start.dateTime).getTime() - new Date(b.start.dateTime).getTime()
    )[0];

  if (!candidate) {
    banner.style.display = 'none';
    return;
  }

  const minsLeft = Math.ceil((new Date(candidate.start.dateTime).getTime() - now) / 60000);
  banner.style.display = '';
  document.getElementById('lbEvent').textContent = candidate.summary ?? 'Event';
  document.getElementById('lbLoc').textContent   = `📍 ${candidate.location}`;
  document.getElementById('lbTimer').textContent  = `${minsLeft}m`;
}

// ══════════════════════════════════════════════════════════════════
//  Weather Easter Egg Effects
// ══════════════════════════════════════════════════════════════════
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
      this._mk('wx-rain', `left:${(Math.random()*105).toFixed(1)}%;height:${(14+Math.random()*18).toFixed(0)}px;animation-duration:${(0.35+Math.random()*0.35).toFixed(2)}s;animation-delay:${(Math.random()*2).toFixed(2)}s;opacity:${(0.25+Math.random()*0.35).toFixed(2)};`);
    }
  },
  _hail(n) {
    for (let i = 0; i < n; i++) {
      this._mk('wx-hail', `left:${(Math.random()*100).toFixed(1)}%;animation-duration:${(0.45+Math.random()*0.4).toFixed(2)}s;animation-delay:${(Math.random()*2).toFixed(2)}s;opacity:${(0.35+Math.random()*0.4).toFixed(2)};`);
    }
  },
  _snow(n) {
    for (let i = 0; i < n; i++) {
      const sz = (4+Math.random()*9).toFixed(1);
      this._mk('wx-snow', `left:${(Math.random()*100).toFixed(1)}%;width:${sz}px;height:${sz}px;--drift:${(-40+Math.random()*80).toFixed(0)}px;animation-duration:${(3+Math.random()*4).toFixed(2)}s;animation-delay:${(Math.random()*5).toFixed(2)}s;`);
    }
  },
  _sun() {
    this._mk('wx-sun', '');
    for (let i = 0; i < 7; i++) {
      this._mk('wx-sparkle', `top:${(8+Math.random()*35).toFixed(0)}%;right:${(4+Math.random()*28).toFixed(0)}%;animation-duration:${(1.8+Math.random()*2.4).toFixed(2)}s;animation-delay:${(Math.random()*3).toFixed(2)}s;`);
    }
  },
  _stars(n) {
    for (let i = 0; i < n; i++) {
      const sz = (1.5+Math.random()*3).toFixed(1);
      this._mk('wx-star', `top:${(Math.random()*85).toFixed(1)}%;left:${(Math.random()*100).toFixed(1)}%;width:${sz}px;height:${sz}px;animation-duration:${(1.2+Math.random()*3.5).toFixed(2)}s;animation-delay:${(Math.random()*5).toFixed(2)}s;`);
    }
  },
  _lightning() {
    const flash = this._mk('wx-lightning', '');
    const trigger = () => {
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
      this._mk('wx-fog', `top:${(12+i*21).toFixed(0)}%;animation-duration:${(18+i*6).toFixed(0)}s;animation-delay:${(-i*7).toFixed(0)}s;opacity:${(0.14+i*0.04).toFixed(2)};`);
    }
  },
  _wind(n) {
    for (let i = 0; i < n; i++) {
      this._mk('wx-wind', `top:${(8+Math.random()*82).toFixed(0)}%;width:${(70+Math.random()*140).toFixed(0)}px;animation-duration:${(1.2+Math.random()*2).toFixed(2)}s;animation-delay:${(Math.random()*4).toFixed(2)}s;opacity:${(0.14+Math.random()*0.22).toFixed(2)};`);
    }
  },
  _clouds(n) {
    for (let i = 0; i < n; i++) {
      this._mk('wx-cloud', `top:${(4+Math.random()*28).toFixed(0)}%;animation-duration:${(28+i*8).toFixed(0)}s;animation-delay:${(-i*12).toFixed(0)}s;opacity:${(0.05+Math.random()*0.07).toFixed(2)};transform:scale(${(0.7+Math.random()*0.9).toFixed(2)});`);
    }
  },
};

// ══════════════════════════════════════════════════════════════════
//  Data loaders
// ══════════════════════════════════════════════════════════════════
async function loadWeather() {
  try {
    const r = await fetch('/api/weather');
    const d = await r.json();
    if (!d.state) return;
    const emoji = WEATHER_EMOJI[d.state] ?? '🌤️';
    const temp  = d.attributes?.temperature;
    const unit  = d.attributes?.temperature_unit ?? '°C';
    const cond  = d.state.replace(/-/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
    document.getElementById('wi').textContent   = emoji;
    document.getElementById('wtemp').textContent = temp != null ? `${Math.round(temp)}${unit}` : '—';
    document.getElementById('wcond').textContent = cond;
    WeatherFX.set(d.state);
  } catch {}
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

  _events = evRes.status === 'fulfilled'
    ? ((await evRes.value.json()).events ?? [])
    : [];

  _config = cfgRes.status === 'fulfilled'
    ? await cfgRes.value.json()
    : {};

  _events.forEach(e => calColour(e.calendar));

  if (!_selectedDateStr) _selectedDateStr = isoDate(new Date());

  renderWeek(_events, new Date());
  renderDayLists();
  checkLeavingSoon();
}

function renderDayLists() {
  const today       = new Date();
  const todayStr    = isoDate(today);
  const tomorrow    = new Date(today);
  tomorrow.setDate(tomorrow.getDate() + 1);
  const tomorrowStr = isoDate(tomorrow);

  const selectedStr = _selectedDateStr ?? todayStr;
  const nextDate     = new Date(selectedStr + 'T00:00:00');
  nextDate.setDate(nextDate.getDate() + 1);
  const nextStr = isoDate(nextDate);

  const schoolCal = _config.school_calendar ?? '';

  const primaryEvs   = sortEvs(_events.filter(e => evDateStr(e) === selectedStr && e.calendar !== schoolCal));
  const secondaryEvs = sortEvs(_events.filter(e => evDateStr(e) === nextStr      && e.calendar !== schoolCal));
  const schoolEvs    = schoolCal
    ? sortEvs(_events.filter(e => evDateStr(e) === selectedStr && e.calendar === schoolCal))
    : [];

  document.getElementById('todayLabel').textContent    = dayLabel(selectedStr, todayStr, tomorrowStr);
  document.getElementById('tomorrowLabel').textContent = dayLabel(nextStr, todayStr, tomorrowStr);

  setList('todayList',    primaryEvs,   emptyMsgFor(selectedStr, todayStr, tomorrowStr));
  setList('tomorrowList', secondaryEvs, emptyMsgFor(nextStr, todayStr, tomorrowStr));

  const schoolSection = document.getElementById('schoolSection');
  if (schoolEvs.length > 0) {
    schoolSection.style.display = '';
    document.getElementById('schoolList').innerHTML = schoolEvs.map(eventCard).join('');
    if (schoolCal) {
      document.getElementById('schoolLabel').textContent =
        `School ${dayLabel(selectedStr, todayStr, tomorrowStr)} — ${calLabel(schoolCal)}`;
    }
  } else {
    schoolSection.style.display = 'none';
  }
}

async function loadCountdown() {
  try {
    const r = await fetch('/api/countdown');
    const d = await r.json();
    if (!d.status || d.status === 'unknown') return;

    const card = document.getElementById('countdownCard');
    card.style.display = '';
    card.className = 'countdown-card';

    const isSummer = d.label?.includes('Summer');
    const isHols   = d.status === 'holidays' || d.status === 'break';
    if (isHols && isSummer) card.classList.add('is-summer');
    else if (isHols)        card.classList.add('is-hols');

    const icons = { term: '📚', holidays: '🌴', break: '🏖️' };
    document.getElementById('cdIcon').textContent  = icons[d.status] ?? '📅';
    document.getElementById('cdLabel').textContent = d.label ?? '—';
    document.getElementById('cdNum').textContent   = d.days_left ?? '—';
    document.getElementById('cdBarFill').style.width = `${Math.round((d.progress ?? 0) * 100)}%`;

    const n = d.days_left ?? 0;
    document.getElementById('cdUnit').textContent =
      d.status === 'term'
        ? (n === 1 ? 'day until holidays' : 'days until holidays')
        : (n === 1 ? 'day until school'   : 'days until school');

    const footer = document.getElementById('cdFooter');
    footer.textContent = (d.next_label && d.next_start)
      ? `Then: ${d.next_label} · ${d.next_start}`
      : '';
  } catch {}
}

async function loadChores() {
  try {
    const r = await fetch('/api/chores');
    const { lists = [] } = await r.json();

    const section   = document.getElementById('choresSection');
    const container = document.getElementById('choresList');

    const hasItems = lists.some(l => l.items.length > 0);
    if (!hasItems) { section.style.display = 'none'; return; }

    section.style.display = '';
    let html = '';

    for (const list of lists) {
      if (!list.items.length) continue;
      if (lists.length > 1) {
        html += `<p class="chore-group-name">${esc(list.name)}</p>`;
      }
      // Pending first, completed at the end
      const pending   = list.items.filter(i => i.status !== 'completed');
      const completed = list.items.filter(i => i.status === 'completed');
      for (const item of [...pending, ...completed]) {
        const done = item.status === 'completed';
        html += `
          <div class="chore-item${done ? ' is-done' : ''}"
               data-entity="${esc(list.entity_id)}"
               data-uid="${esc(item.uid)}"
               onclick="toggleChore(this)">
            <div class="chore-check">${done ? '✓' : ''}</div>
            <div class="chore-text">${esc(item.summary)}</div>
          </div>`;
      }
    }

    container.innerHTML = html;
  } catch {}
}

async function toggleChore(el) {
  if (el.classList.contains('is-done')) return;

  // Optimistic UI update
  el.classList.add('is-done');
  el.querySelector('.chore-check').textContent = '✓';

  try {
    await fetch('/api/chores/complete', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        entity_id: el.dataset.entity,
        uid:       el.dataset.uid,
      }),
    });
  } catch {}

  // Re-sync after a short delay so HA state catches up
  setTimeout(loadChores, 1500);
}

// ══════════════════════════════════════════════════════════════════
//  Quick launch — try the native app, fall back to the website
// ══════════════════════════════════════════════════════════════════
function openAppOrWeb(appUri, webUrl, evt) {
  if (evt) evt.preventDefault();

  let didHide = false;
  const onVisibility = () => { if (document.hidden) didHide = true; };
  document.addEventListener('visibilitychange', onVisibility);

  window.location.href = appUri;

  setTimeout(() => {
    document.removeEventListener('visibilitychange', onVisibility);
    if (!didHide) window.location.href = webUrl;
  }, 1200);

  return false;
}

// ══════════════════════════════════════════════════════════════════
//  Bootstrap
// ══════════════════════════════════════════════════════════════════
WeatherFX.init();
Screensaver.init();

// Fetch leave-soon threshold from backend config
fetch('/api/leave-soon-config')
  .then(r => r.json())
  .then(d => { _leaveSoonMinutes = d.minutes ?? 25; })
  .catch(() => {});

tick();
setInterval(tick, 1000);

// Check leaving soon every minute
setInterval(checkLeavingSoon, 60 * 1000);

// Initial data load
loadWeather();
loadAffirmation();
loadEvents();
loadCountdown();
loadChores();

// Recurring refreshes
setInterval(loadWeather,     5  * 60 * 1000);   // weather  every 5 min
setInterval(loadEvents,      5  * 60 * 1000);   // events   every 5 min
setInterval(loadChores,      2  * 60 * 1000);   // chores   every 2 min (fast turnaround after ticking)
setInterval(loadCountdown,   60 * 60 * 1000);   // countdown hourly
setInterval(loadAffirmation, 60 * 60 * 1000);   // affirmation hourly
