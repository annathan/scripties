from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

load_dotenv()

from db import get_result, init_db, store_result
from lookup import run_lookup
from synthesize import synthesize_threat

STATIC_DIR = Path(__file__).parent / "static"


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(title="ThreatPlain", lifespan=lifespan)


class LookupRequest(BaseModel):
    value: str


@app.post("/api/lookup")
async def api_lookup(req: LookupRequest):
    value = req.value.strip()
    if not value:
        raise HTTPException(status_code=400, detail="Input cannot be empty")

    raw = await run_lookup(value)

    if raw.get("input_type") == "unknown" or "error" in raw:
        if raw.get("input_type") == "unknown":
            raise HTTPException(
                status_code=422,
                detail=raw.get(
                    "error",
                    "Could not identify this input. Please enter a URL, IP address, file hash, or email headers.",
                ),
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
