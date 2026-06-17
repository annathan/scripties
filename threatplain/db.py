import sqlite3
import json
import secrets
import time
from pathlib import Path

DB_PATH = Path("threatplain.db")

CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS lookups (
    id          TEXT PRIMARY KEY,
    input       TEXT NOT NULL,
    input_type  TEXT NOT NULL,
    raw_results TEXT NOT NULL,
    synthesis   TEXT NOT NULL,
    created_at  INTEGER NOT NULL
)
"""


def init_db() -> None:
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(CREATE_TABLE)
        conn.commit()


def store_result(input_value: str, raw_results: dict, synthesis: dict) -> str:
    result_id = secrets.token_urlsafe(12)  # 96-bit entropy → 16-char URL-safe IDs
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            "INSERT INTO lookups (id, input, input_type, raw_results, synthesis, created_at) VALUES (?,?,?,?,?,?)",
            (
                result_id,
                input_value,
                raw_results.get("input_type", "unknown"),
                json.dumps(raw_results),
                json.dumps(synthesis),
                int(time.time()),
            ),
        )
        conn.commit()
    return result_id


def get_result(result_id: str) -> dict | None:
    with sqlite3.connect(DB_PATH) as conn:
        row = conn.execute(
            "SELECT id, input, input_type, raw_results, synthesis, created_at FROM lookups WHERE id = ?",
            (result_id,),
        ).fetchone()
    if not row:
        return None
    return {
        "id": row[0],
        "input": row[1],
        "input_type": row[2],
        "raw_results": json.loads(row[3]),
        "synthesis": json.loads(row[4]),
        "created_at": row[5],
    }
