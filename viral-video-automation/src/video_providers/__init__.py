from __future__ import annotations

from ..config import Settings
from .base import VideoProvider
from .mock import MockVideoProvider


def get_provider(settings: Settings) -> VideoProvider:
    name = settings.video_generation["provider"]

    if name == "mock":
        return MockVideoProvider()

    if name == "runway":
        from .runway import RunwayVideoProvider

        if not settings.runway_api_key:
            raise RuntimeError("VIDEO_PROVIDER=runway but RUNWAY_API_KEY is not set in .env")
        return RunwayVideoProvider(settings.runway_api_key)

    raise ValueError(f"Unknown video provider: {name!r} (expected 'mock' or 'runway')")
