from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path


class TTSProvider(ABC):
    """Interface every text-to-speech backend implements. Swap providers by
    setting TTS_PROVIDER in .env -- the rest of the pipeline doesn't care
    which one is behind it."""

    @abstractmethod
    def synthesize(self, text: str, out_path: Path) -> Path:
        """Synthesize spoken audio for text and write it to out_path (mp3).
        Must return out_path."""
        raise NotImplementedError
