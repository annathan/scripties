from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path


class VideoProvider(ABC):
    """Interface every text-to-video backend implements. Swap providers by
    setting VIDEO_PROVIDER in .env -- the rest of the pipeline doesn't care
    which one is behind it."""

    @abstractmethod
    def generate_scene_clip(
        self, prompt: str, duration_seconds: float, resolution: str, out_path: Path
    ) -> Path:
        """Generate a single scene clip and write it to out_path (mp4). Must
        return out_path."""
        raise NotImplementedError
