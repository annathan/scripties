from __future__ import annotations

import logging
import os
from pathlib import Path

import fal_client
import requests

from .base import VideoProvider

logger = logging.getLogger(__name__)

# Pika's official API access is served through fal.ai using a FAL_KEY.
# Uses fal.ai's official Python SDK (fal_client.subscribe(), which handles
# the submit -> poll -> result flow internally) rather than hand-rolled
# REST calls -- confirmed directly against fal.ai's own docs example for
# fal-ai/pika/v2.2/text-to-video, pulled from the live model page's API tab.
FAL_MODEL_ID = "fal-ai/pika/v2.2/text-to-video"

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


def _log_queue_update(update) -> None:
    if isinstance(update, fal_client.InProgress):
        for log in update.logs:
            logger.info(f"[pika] {log['message']}")


class PikaVideoProvider(VideoProvider):
    """Text-to-video generation via Pika, through fal.ai's official SDK."""

    def __init__(self, api_key: str):
        # fal_client reads FAL_KEY from the environment rather than taking
        # a key in its constructor -- set it explicitly here instead of
        # relying on it already being set, so this provider doesn't depend
        # on load order elsewhere.
        os.environ["FAL_KEY"] = api_key

    def generate_scene_clip(
        self, prompt: str, duration_seconds: float, resolution: str, out_path: Path
    ) -> Path:
        width, height = (int(x) for x in resolution.split("x"))

        result = fal_client.subscribe(
            FAL_MODEL_ID,
            arguments={
                "prompt": prompt,
                "aspect_ratio": _closest_aspect_ratio(width, height),
                "resolution": _resolution_tier(width, height),
                "duration": _closest_duration(duration_seconds),
            },
            with_logs=True,
            on_queue_update=_log_queue_update,
        )

        video_url = result["video"]["url"]
        video_bytes = requests.get(video_url, timeout=60).content
        out_path.write_bytes(video_bytes)
        return out_path
