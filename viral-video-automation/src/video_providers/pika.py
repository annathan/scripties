from __future__ import annotations

import time
from pathlib import Path

import requests

from .base import VideoProvider

# Pika's official API access is served through fal.ai (https://fal.ai) using
# a FAL_KEY. Confirmed against fal's own docs for fal-ai/pika/v2.2/text-to-video
# (JS client + REST queue pattern, and the Input/Output schema pages):
#
#   POST https://queue.fal.run/fal-ai/pika/v2.2/text-to-video
#     {"prompt": ..., "negative_prompt": ..., "seed": ...,
#      "aspect_ratio": "16:9"|"9:16"|"1:1"|"4:5"|"5:4"|"3:2"|"2:3",
#      "resolution": "720p"|"1080p", "duration": 5|10}
#   -> {"request_id": ..., "status_url": ..., "response_url": ...}
#   GET  {status_url}   -> {"status": "IN_QUEUE"|"IN_PROGRESS"|"COMPLETED"|...}
#   GET  {response_url} -> {"video": {"url": "..."}}
#
# One thing this schema forces on us: `duration` is an enum of exactly 5 or
# 10 seconds, not a free-form number. generate_scene_clip rounds whatever
# scene_duration video_generator.py asks for to the nearest allowed value --
# the actual rendered clip can therefore be shorter/longer than requested.
# video_generator.py accounts for this by measuring each clip's real
# duration (ffprobe) after generation rather than assuming the requested
# one, so captions/mascot timing stay in sync regardless. If you tune
# video_generation.scenes_per_video / target_duration_seconds, note that
# whatever scene length you land on will get pulled to 5s or 10s here.
FAL_QUEUE_BASE = "https://queue.fal.run"
FAL_MODEL_ID = "fal-ai/pika/v2.2/text-to-video"
POLL_INTERVAL_SECONDS = 5
POLL_TIMEOUT_SECONDS = 600

_ASPECT_RATIOS = {
    "16:9": 16 / 9,
    "9:16": 9 / 16,
    "1:1": 1.0,
    "4:5": 4 / 5,
    "5:4": 5 / 4,
    "3:2": 3 / 2,
    "2:3": 2 / 3,
}
_ALLOWED_DURATIONS = (5, 10)


def _closest_aspect_ratio(width: int, height: int) -> str:
    target = width / height
    return min(_ASPECT_RATIOS, key=lambda k: abs(_ASPECT_RATIOS[k] - target))


def _resolution_tier(width: int, height: int) -> str:
    return "1080p" if max(width, height) >= 1080 else "720p"


def _closest_duration(duration_seconds: float) -> int:
    return min(_ALLOWED_DURATIONS, key=lambda d: abs(d - duration_seconds))


class PikaVideoProvider(VideoProvider):
    """Text-to-video generation via Pika, accessed through fal.ai's queue API."""

    def __init__(self, api_key: str):
        self.session = requests.Session()
        self.session.headers.update(
            {
                "Authorization": f"Key {api_key}",
                "Content-Type": "application/json",
            }
        )

    def generate_scene_clip(
        self, prompt: str, duration_seconds: float, resolution: str, out_path: Path
    ) -> Path:
        width, height = (int(x) for x in resolution.split("x"))

        submit = self.session.post(
            f"{FAL_QUEUE_BASE}/{FAL_MODEL_ID}",
            json={
                "prompt": prompt,
                "aspect_ratio": _closest_aspect_ratio(width, height),
                "resolution": _resolution_tier(width, height),
                "duration": _closest_duration(duration_seconds),
            },
        )
        submit.raise_for_status()
        submitted = submit.json()
        request_id = submitted["request_id"]
        status_url = submitted.get("status_url") or f"{FAL_QUEUE_BASE}/{FAL_MODEL_ID}/requests/{request_id}/status"
        response_url = submitted.get("response_url") or f"{FAL_QUEUE_BASE}/{FAL_MODEL_ID}/requests/{request_id}"

        elapsed = 0
        while elapsed < POLL_TIMEOUT_SECONDS:
            time.sleep(POLL_INTERVAL_SECONDS)
            elapsed += POLL_INTERVAL_SECONDS
            status_resp = self.session.get(status_url)
            status_resp.raise_for_status()
            status = status_resp.json().get("status")

            if status == "COMPLETED":
                result = self.session.get(response_url)
                result.raise_for_status()
                video_url = result.json()["video"]["url"]
                video_bytes = requests.get(video_url, timeout=60).content
                out_path.write_bytes(video_bytes)
                return out_path
            if status in ("ERROR", "FAILED"):
                raise RuntimeError(f"Pika (fal.ai) generation failed for request {request_id}: {status_resp.text}")

        raise TimeoutError(f"Pika (fal.ai) generation for request {request_id} did not finish within {POLL_TIMEOUT_SECONDS}s")
