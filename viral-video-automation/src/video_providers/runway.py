from __future__ import annotations

import time
from pathlib import Path

import requests

from .base import VideoProvider

# Verify this against https://docs.dev.runwayml.com before relying on it --
# generative video APIs change fast and this is a best-effort integration
# matching the general "submit job -> poll -> download" shape Runway (and
# most other text-to-video vendors: Kling, Pika, Luma) use.
RUNWAY_API_BASE = "https://api.dev.runwayml.com/v1"
RUNWAY_API_VERSION = "2024-11-06"
POLL_INTERVAL_SECONDS = 5
POLL_TIMEOUT_SECONDS = 600


class RunwayVideoProvider(VideoProvider):
    """Text-to-video generation via Runway's API.

    To use a different vendor, write a sibling class implementing
    VideoProvider.generate_scene_clip and register it in
    video_providers/__init__.py -- the submit/poll/download shape here is a
    reasonable template for most of them.
    """

    def __init__(self, api_key: str):
        self.session = requests.Session()
        self.session.headers.update(
            {
                "Authorization": f"Bearer {api_key}",
                "X-Runway-Version": RUNWAY_API_VERSION,
                "Content-Type": "application/json",
            }
        )

    def generate_scene_clip(
        self, prompt: str, duration_seconds: float, resolution: str, out_path: Path
    ) -> Path:
        width, height = (int(x) for x in resolution.split("x"))
        submit = self.session.post(
            f"{RUNWAY_API_BASE}/text_to_video",
            json={
                "promptText": prompt,
                "duration": max(round(duration_seconds), 1),
                "ratio": f"{width}:{height}",
                "model": "gen4_turbo",
            },
        )
        submit.raise_for_status()
        task_id = submit.json()["id"]

        elapsed = 0
        while elapsed < POLL_TIMEOUT_SECONDS:
            time.sleep(POLL_INTERVAL_SECONDS)
            elapsed += POLL_INTERVAL_SECONDS
            status = self.session.get(f"{RUNWAY_API_BASE}/tasks/{task_id}")
            status.raise_for_status()
            body = status.json()

            if body["status"] == "SUCCEEDED":
                video_url = body["output"][0]
                video_bytes = requests.get(video_url, timeout=60).content
                out_path.write_bytes(video_bytes)
                return out_path
            if body["status"] == "FAILED":
                raise RuntimeError(f"Runway generation failed for task {task_id}: {body}")

        raise TimeoutError(f"Runway generation for task {task_id} did not finish within {POLL_TIMEOUT_SECONDS}s")
