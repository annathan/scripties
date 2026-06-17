import re
import time
from collections import defaultdict
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

load_dotenv()

from db import get_result, init_db, store_result
from lookup import run_lookup
from synthesize import synthesize_threat

STATIC_DIR = Path(__file__).parent / "static"

# ─── Rate limiting (sliding window, in-memory) ─────────────────────────────────

RATE_LIMIT = 10   # requests per window per IP
RATE_WINDOW = 60  # seconds
_rate_store: dict[str, list[float]] = defaultdict(list)


def _allow_request(ip: str) -> bool:
    now = time.time()
    cutoff = now - RATE_WINDOW
    _rate_store[ip] = [t for t in _rate_store[ip] if t > cutoff]
    if len(_rate_store[ip]) >= RATE_LIMIT:
        return False
    _rate_store[ip].append(now)
    return True


# ─── Result ID allow-list format ───────────────────────────────────────────────

_RESULT_ID_RE = re.compile(r"^[A-Za-z0-9_-]{6,24}$")


# ─── App ───────────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(title="ThreatPlain", lifespan=lifespan)


@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; "
        "img-src 'self' https://urlscan.io https://screenshotapi.net data:; "
        "style-src 'self' 'unsafe-inline'; "
        "script-src 'self' 'unsafe-inline'"
    )
    return response


class LookupRequest(BaseModel):
    value: str = Field(..., min_length=1, max_length=100_000)


@app.post("/api/lookup")
async def api_lookup(req: LookupRequest, request: Request):
    ip = request.client.host if request.client else "unknown"
    if not _allow_request(ip):
        raise HTTPException(status_code=429, detail="Too many requests — please wait a minute.")

    value = req.value.strip()
    if not value:
        raise HTTPException(status_code=400, detail="Input cannot be empty")

    raw = await run_lookup(value)

    if raw.get("input_type") == "unknown":
        raise HTTPException(
            status_code=422,
            detail="Could not identify this input. Please enter a URL, IP address, file hash, or email headers.",
        )

    synthesis = await synthesize_threat(value, raw)
    result_id = store_result(value, raw, synthesis)

    return {
        "id": result_id,
        "input": value,
        "input_type": raw.get("input_type", "unknown"),
        "synthesis": synthesis,
        "sources": raw.get("sources", {}),
        "screenshot_url": raw.get("screenshot_url"),
    }


@app.get("/api/result/{result_id}")
async def api_get_result(result_id: str):
    if not _RESULT_ID_RE.match(result_id):
        raise HTTPException(status_code=404, detail="Result not found")
    result = get_result(result_id)
    if not result:
        raise HTTPException(status_code=404, detail="Result not found")
    raw = result["raw_results"]
    return {
        "id": result["id"],
        "input": result["input"],
        "input_type": result["input_type"],
        "synthesis": result["synthesis"],
        "sources": raw.get("sources", {}),
        "screenshot_url": raw.get("screenshot_url"),
    }


@app.get("/result/{result_id}")
async def result_page(result_id: str):
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/")
async def index():
    return FileResponse(STATIC_DIR / "index.html")


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
