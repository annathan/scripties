import os
from datetime import datetime, timedelta

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


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", "7123")))
