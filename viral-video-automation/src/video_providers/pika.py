from __future__ import annotations

import time
from pathlib import Path

import requests

from .base import VideoProvider

# Pika doesn't run its own separate public REST API -- its official API
# access is served through fal.ai (https://fal.ai) using a FAL_KEY. fal.ai
# uses one generic async "queue" pattern across all the models it hosts:
# POST to submit, GET to poll status, GET to fetch the result once done.
#
# IMPORTANT: the model id and field names below (fal-ai/pika/v2.2/text-to-video,
# aspect_ratio, duration, ...) reflect fal's Pika model catalog as described
# in fal's own documentation/search results at the time this was written --
# doc-site fetches were blocked (403) while building this, so it could not
# be verified against a live page. Before relying on this for real spend:
# log into https://fal.ai/models (search "pika"), open the specific model's
# page, and use its "API" tab's auto-generated code sample -- that sample is
# generated against your actual key and the current model version, and is a
# more reliable source of truth than any static doc scrape.
FAL_QUEUE_BASE = "https://queue.fal.run"
FAL_MODEL_ID = "fal-ai/pika/v2.2/text-to-video"
POLL_INTERVAL_SECONDS = 5
POLL_TIMEOUT_SECONDS = 600


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
        if height > width:
            aspect_ratio = "9:16"
        elif width > height:
            aspect_ratio = "16:9"
        else:
            aspect_ratio = "1:1"

        submit = self.session.post(
            f"{FAL_QUEUE_BASE}/{FAL_MODEL_ID}",
            json={
                "prompt": prompt,
                "aspect_ratio": aspect_ratio,
                "duration": max(round(duration_seconds), 1),
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
