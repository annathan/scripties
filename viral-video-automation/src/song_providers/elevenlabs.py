from __future__ import annotations

from pathlib import Path

from elevenlabs.client import ElevenLabs

from .base import SongProvider


class ElevenLabsSongProvider(SongProvider):
    """Song generation via ElevenLabs Music.

    Confirmed against a docs example pulled directly from ElevenLabs'
    support chat: client.music.compose(prompt=, music_length_ms=,
    model_id="music_v2") -> Iterator[bytes], same chunk-to-file pattern as
    text_to_speech.convert(). Uses the same ELEVENLABS_API_KEY as
    narration -- same account, different product.
    """

    def __init__(self, api_key: str, model_id: str):
        self.client = ElevenLabs(api_key=api_key)
        self.model_id = model_id

    def compose(self, prompt: str, duration_seconds: float, out_path: Path) -> Path:
        track_chunks = self.client.music.compose(
            prompt=prompt,
            music_length_ms=round(duration_seconds * 1000),
            model_id=self.model_id,
        )
        with open(out_path, "wb") as f:
            for chunk in track_chunks:
                f.write(chunk)
        return out_path
