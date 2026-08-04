from __future__ import annotations

from pathlib import Path

from elevenlabs.client import ElevenLabs

from .base import TTSProvider


class ElevenLabsTTSProvider(TTSProvider):
    """Text-to-speech via ElevenLabs' official Python SDK.

    Confirmed against ElevenLabs' own "Make your first request" docs
    example (client.text_to_speech.convert(text=, voice_id=, model_id=,
    output_format=)) rather than guessed -- the earlier raw-REST version of
    this file was replaced once the real usage was verified.
    """

    def __init__(self, api_key: str, voice_id: str, model_id: str):
        self.client = ElevenLabs(api_key=api_key)
        self.voice_id = voice_id
        self.model_id = model_id

    def synthesize(self, text: str, out_path: Path) -> Path:
        audio_chunks = self.client.text_to_speech.convert(
            text=text,
            voice_id=self.voice_id,
            model_id=self.model_id,
            output_format="mp3_44100_128",
        )
        with open(out_path, "wb") as f:
            for chunk in audio_chunks:
                f.write(chunk)
        return out_path
