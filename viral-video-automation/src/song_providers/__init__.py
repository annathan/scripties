from __future__ import annotations

from ..config import Settings
from .base import SongProvider
from .mock import MockSongProvider


def get_song_provider(settings: Settings) -> SongProvider:
    cfg = settings.song
    name = cfg["provider"]

    if name == "mock":
        return MockSongProvider()

    if name == "elevenlabs":
        from .elevenlabs import ElevenLabsSongProvider

        if not settings.elevenlabs_api_key:
            raise RuntimeError("SONG_PROVIDER=elevenlabs but ELEVENLABS_API_KEY is not set in .env")
        return ElevenLabsSongProvider(settings.elevenlabs_api_key, cfg["model_id"])

    raise ValueError(f"Unknown song provider: {name!r} (expected 'mock' or 'elevenlabs')")
