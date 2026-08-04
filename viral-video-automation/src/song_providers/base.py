from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path


class SongProvider(ABC):
    """Interface every song-generation backend implements. Unlike TTSProvider
    (per-scene spoken lines), a SongProvider composes ONE continuous track
    for a whole video, from a style/lyrics prompt and a target duration."""

    @abstractmethod
    def compose(self, prompt: str, duration_seconds: float, out_path: Path) -> Path:
        """Compose a song and write it to out_path (mp3). Must return out_path."""
        raise NotImplementedError
