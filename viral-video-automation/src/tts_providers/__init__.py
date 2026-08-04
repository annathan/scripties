from __future__ import annotations

from ..config import Settings
from .base import TTSProvider
from .mock import MockTTSProvider


def get_tts_provider(settings: Settings) -> TTSProvider:
    cfg = settings.narration
    name = cfg["provider"]

    if name == "mock":
        return MockTTSProvider()

    if name == "elevenlabs":
        from .elevenlabs import ElevenLabsTTSProvider

        if not settings.elevenlabs_api_key:
            raise RuntimeError("TTS_PROVIDER=elevenlabs but ELEVENLABS_API_KEY is not set in .env")
        return ElevenLabsTTSProvider(settings.elevenlabs_api_key, cfg["voice_id"], cfg["model_id"])

    raise ValueError(f"Unknown TTS provider: {name!r} (expected 'mock' or 'elevenlabs')")
