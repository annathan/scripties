from __future__ import annotations

from pathlib import Path

import requests

from .base import TTSProvider

# ElevenLabs' text-to-speech endpoint has been stable in this exact shape
# (POST .../v1/text-to-speech/{voice_id}, xi-api-key header, raw audio
# bytes back) for years across a huge number of third-party integrations.
# That said, doc-site fetches were blocked (bot detection on elevenlabs.io
# itself, not a network policy) while building this, so it wasn't verified
# against a live page this session. Before spending real money on it, a
# quick sanity check against your account's own API reference/dashboard is
# worthwhile -- adjust field names here if anything's drifted.
ELEVENLABS_API_BASE = "https://api.elevenlabs.io/v1"


class ElevenLabsTTSProvider(TTSProvider):
    """Text-to-speech via ElevenLabs."""

    def __init__(self, api_key: str, voice_id: str, model_id: str):
        self.voice_id = voice_id
        self.model_id = model_id
        self.session = requests.Session()
        self.session.headers.update(
            {
                "xi-api-key": api_key,
                "Content-Type": "application/json",
                "Accept": "audio/mpeg",
            }
        )

    def synthesize(self, text: str, out_path: Path) -> Path:
        response = self.session.post(
            f"{ELEVENLABS_API_BASE}/text-to-speech/{self.voice_id}",
            json={
                "text": text,
                "model_id": self.model_id,
                "voice_settings": {"stability": 0.5, "similarity_boost": 0.75},
            },
        )
        response.raise_for_status()
        out_path.write_bytes(response.content)
        return out_path
