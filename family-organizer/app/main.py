import os
from datetime import datetime, timedelta, date

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

app = FastAPI(title="Family Organizer")
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

HA_URL = os.getenv("HA_URL", "http://supervisor/core")
HA_TOKEN = os.getenv("SUPERVISOR_TOKEN", os.getenv("HA_TOKEN", ""))
WEATHER_ENTITY = os.getenv("WEATHER_ENTITY", "weather.home")
SCHOOL_CALENDAR = os.getenv("SCHOOL_CALENDAR", "")

_cals_env = os.getenv("CALENDARS", "")
CALENDARS = [c.strip() for c in _cals_env.split(",") if c.strip()] if _cals_env else []

AFFIRMATIONS = [
    "You are doing an amazing job today!",
    "Every day is a fresh start — embrace it.",
    "You are loved more than you know.",
    "Small steps lead to big changes.",
    "Today is going to be a wonderful day!",
    "Your family is your superpower.",
    "Be kind to yourself today.",
    "You've got this — one moment at a time.",
    "Gratitude turns what you have into enough.",
    "Today's challenges are tomorrow's strengths.",
    "You make a difference just by being here.",
    "Choose joy — it's always available to you.",
    "Progress, not perfection.",
    "You are exactly where you need to be.",
    "Good things are coming your way.",
    "Your kindness matters more than you think.",
    "Believe in yourself a little more today.",
    "This moment is a gift — that's why it's called the present.",
    "You are stronger than yesterday.",
    "Love is the most important thing in this home.",
    "Take a deep breath — everything is okay.",
    "You inspire the people around you.",
    "Today, choose happiness.",
    "Your efforts matter even when you can't see the results.",
    "Home is where your story begins.",
    "You are raising amazing human beings.",
    "It's okay to rest — rest is productive too.",
    "Something wonderful is about to happen.",
    "Family makes everything better.",
    "You are appreciated, seen, and valued.",
    "Make today count — even the small moments.",
    "Your smile brightens everyone's day.",
    "Together, your family can handle anything.",
    "Each day is a chance to create beautiful memories.",
    "You are doing your best, and that's enough.",
    "Celebrate the little victories today.",
    "The best is yet to come.",
    "You are enough, exactly as you are.",
]


def _ha_headers() -> dict:
    return {
        "Authorization": f"Bearer {HA_TOKEN}",
        "Content-Type": "application/json",
    }


@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


@app.get("/api/events")
async def get_events():
    now = datetime.now().astimezone()
    start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    end = start + timedelta(days=8)

    all_events: list[dict] = []

    async with httpx.AsyncClient(timeout=10) as client:
        cal_ids = list(CALENDARS)

        if not cal_ids:
            try:
                r = await client.get(f"{HA_URL}/api/calendars", headers=_ha_headers())
                if r.status_code == 200:
                    cal_ids = [c["entity_id"] for c in r.json()]
            except Exception:
                pass

        for cal_id in cal_ids:
            if not cal_id:
                continue
            try:
                r = await client.get(
                    f"{HA_URL}/api/calendars/{cal_id}",
                    params={"start": start.isoformat(), "end": end.isoformat()},
                    headers=_ha_headers(),
                )
                if r.status_code == 200:
                    for ev in r.json():
                        ev["calendar"] = cal_id
                        all_events.append(ev)
            except Exception:
                pass

    return JSONResponse({"events": all_events})


@app.get("/api/weather")
async def get_weather():
    async with httpx.AsyncClient(timeout=10) as client:
        try:
            r = await client.get(
                f"{HA_URL}/api/states/{WEATHER_ENTITY}",
                headers=_ha_headers(),
            )
            if r.status_code == 200:
                return JSONResponse(r.json())
        except Exception:
            pass
    return JSONResponse({})


@app.get("/api/affirmation")
async def get_affirmation():
    day = datetime.now().timetuple().tm_yday
    return {"text": AFFIRMATIONS[day % len(AFFIRMATIONS)]}


@app.get("/api/config")
async def get_config():
    return {
        "school_calendar": SCHOOL_CALENDAR,
        "weather_entity": WEATHER_ENTITY,
    }


# ── NSW DoE public school term dates ─────────────────────────────
# Source: https://education.nsw.gov.au/public-schools/going-to-a-public-school/calendars-and-school-terms
# Each entry: (short_label, full_label, term_start, term_end)
_NSW_TERMS: list[tuple[str, str, date, date]] = [
    ("Term 1",        "Term 1 · 2025",        date(2025, 1, 29),  date(2025, 4, 11)),
    ("Term 2",        "Term 2 · 2025",        date(2025, 4, 29),  date(2025, 7, 4)),
    ("Term 3",        "Term 3 · 2025",        date(2025, 7, 22),  date(2025, 9, 26)),
    ("Term 4",        "Term 4 · 2025",        date(2025, 10, 13), date(2025, 12, 19)),
    ("Term 1",        "Term 1 · 2026",        date(2026, 1, 28),  date(2026, 4, 9)),
    ("Term 2",        "Term 2 · 2026",        date(2026, 4, 28),  date(2026, 7, 3)),
    ("Term 3",        "Term 3 · 2026",        date(2026, 7, 21),  date(2026, 9, 25)),
    ("Term 4",        "Term 4 · 2026",        date(2026, 10, 12), date(2026, 12, 18)),
    ("Term 1",        "Term 1 · 2027",        date(2027, 1, 27),  date(2027, 4, 8)),
    ("Term 2",        "Term 2 · 2027",        date(2027, 4, 27),  date(2027, 7, 2)),
    ("Term 3",        "Term 3 · 2027",        date(2027, 7, 20),  date(2027, 9, 24)),
    ("Term 4",        "Term 4 · 2027",        date(2027, 10, 11), date(2027, 12, 17)),
]

_HOL_NAMES = {
    "Term 1": "Easter Holidays",
    "Term 2": "Winter Holidays",
    "Term 3": "Spring Holidays",
    "Term 4": "Summer Holidays",
}


def _build_timeline() -> list[dict]:
    """Expand term list into alternating term / holiday periods."""
    periods: list[dict] = []
    for i, (short, full, t_start, t_end) in enumerate(_NSW_TERMS):
        periods.append({
            "type": "term",
            "label": full,
            "short": short,
            "start": t_start,
            "end": t_end,
        })
        if i + 1 < len(_NSW_TERMS):
            hol_start = t_end + timedelta(days=1)
            hol_end = _NSW_TERMS[i + 1][2] - timedelta(days=1)
            if hol_start <= hol_end:
                hol_name = _HOL_NAMES.get(short, "School Holidays")
                periods.append({
                    "type": "holidays",
                    "label": hol_name,
                    "short": hol_name,
                    "start": hol_start,
                    "end": hol_end,
                })
    return periods


@app.get("/api/countdown")
async def get_countdown():
    today = date.today()
    timeline = _build_timeline()

    current = next((p for p in timeline if p["start"] <= today <= p["end"]), None)
    upcoming = [p for p in timeline if p["start"] > today]
    nxt = upcoming[0] if upcoming else None

    def _fmt(d: date) -> str:
        return d.strftime("%-d %b")

    if current:
        span = (current["end"] - current["start"]).days or 1
        progress = (today - current["start"]).days / span
        days_left = (current["end"] - today).days
        return {
            "status": current["type"],
            "label": current["label"],
            "short": current["short"],
            "days_left": days_left,
            "progress": round(progress, 3),
            "next_label": nxt["label"] if nxt else None,
            "next_start": _fmt(nxt["start"]) if nxt else None,
        }

    if nxt:
        # Between data ranges (e.g. very start of year before Term 1)
        return {
            "status": "break",
            "label": "School Break",
            "short": "Break",
            "days_left": (nxt["start"] - today).days,
            "progress": 0.0,
            "next_label": nxt["label"],
            "next_start": _fmt(nxt["start"]),
        }

    return {"status": "unknown"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", "7123")))
