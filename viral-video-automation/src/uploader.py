"""Stage 5: upload an approved video to YouTube.

Requires a one-time OAuth authorization (see scripts/setup_youtube_oauth.py)
-- this uploads to whichever channel you authorize, on your behalf. Only
touches items that have been explicitly approved in stage 4 (data/approved);
it never reads straight from the review queue.
"""
from __future__ import annotations

import json
import logging
import time
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload

from .config import PROJECT_ROOT, Settings, load_settings

logger = logging.getLogger(__name__)

SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]
_RETRYABLE_HTTP_STATUSES = {429, 500, 502, 503, 504}
MAX_CHUNK_RETRIES = 5


def _get_credentials(settings: Settings) -> Credentials:
    token_file = settings.youtube_token_file
    if not token_file.exists():
        raise RuntimeError(
            f"No YouTube OAuth token at {token_file}. Run "
            "`python scripts/setup_youtube_oauth.py` once first."
        )
    creds = Credentials.from_authorized_user_file(str(token_file), SCOPES)
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
        token_file.write_text(creds.to_json())
    return creds


def upload_video(slug: str, settings: Settings | None = None) -> str:
    settings = settings or load_settings()
    approved_dir = PROJECT_ROOT / settings.review["approved_dir"] / slug
    metadata_path = approved_dir / "metadata.json"
    video_path = approved_dir / "final.mp4"
    if not metadata_path.exists() or not video_path.exists():
        raise FileNotFoundError(f"{slug} is not in the approved queue ({approved_dir})")

    metadata = json.loads(metadata_path.read_text())
    if metadata.get("status") != "approved":
        raise RuntimeError(
            f"{slug} has status {metadata.get('status')!r}, expected 'approved'. "
            "Run stage 4 review (approve) first."
        )

    creds = _get_credentials(settings)
    youtube = build("youtube", "v3", credentials=creds)

    body = {
        "snippet": {
            "title": metadata["title"],
            "description": metadata["description"],
            "tags": metadata["tags"],
            "categoryId": metadata["category_id"],
        },
        "status": {
            "privacyStatus": metadata["privacy_status"],
            # YouTube's actual COPPA/"made for kids" designation -- this
            # disables personalized ads and comments on the video regardless
            # of any other setting here.
            "selfDeclaredMadeForKids": metadata["made_for_kids"],
        },
    }

    media = MediaFileUpload(str(video_path), chunksize=-1, resumable=True, mimetype="video/mp4")
    request = youtube.videos().insert(part="snippet,status", body=body, media_body=media)

    logger.info(f"uploading '{metadata['title']}'...")
    response = None
    retries = 0
    while response is None:
        try:
            status, response = request.next_chunk()
        except HttpError as exc:
            status_code = getattr(exc, "status_code", None) or getattr(exc.resp, "status", None)
            if status_code not in _RETRYABLE_HTTP_STATUSES or retries >= MAX_CHUNK_RETRIES:
                raise
            retries += 1
            delay = 5.0 * retries
            logger.warning(
                f"upload chunk failed (status {status_code}, retry {retries}/{MAX_CHUNK_RETRIES}): {exc}. "
                f"Retrying in {delay:.0f}s..."
            )
            time.sleep(delay)
            continue
        if status:
            logger.info(f"  {int(status.progress() * 100)}%")

    video_id = response["id"]
    uploaded_dir = PROJECT_ROOT / settings.upload["uploaded_dir"]
    uploaded_dir.mkdir(parents=True, exist_ok=True)
    metadata["status"] = "uploaded"
    metadata["youtube_video_id"] = video_id
    metadata["youtube_url"] = f"https://youtube.com/watch?v={video_id}"
    (uploaded_dir / f"{slug}.json").write_text(json.dumps(metadata, indent=2))

    logger.info(f"done: {metadata['youtube_url']}")
    return video_id


if __name__ == "__main__":
    import sys

    if len(sys.argv) != 2:
        print("usage: python -m src.uploader <slug>")
        raise SystemExit(1)
    upload_video(sys.argv[1])
