from __future__ import annotations

import subprocess
from pathlib import Path

from .base import SongProvider


class MockSongProvider(SongProvider):
    """Keyless, local placeholder provider.

    Renders a short repeating melodic sweep (not a flat tone, so it's
    audibly distinct from the mock narration placeholder) at the requested
    duration, via ffmpeg's lavfi sine source. Lets the whole song pipeline
    (composing, fitting to actual video duration, mixing) be exercised
    end-to-end without an API key.
    """

    def compose(self, prompt: str, duration_seconds: float, out_path: Path) -> Path:
        cmd = [
            "ffmpeg",
            "-y",
            "-f",
            "lavfi",
            "-i",
            f"sine=frequency=330:duration={duration_seconds}:sample_rate=44100",
            "-af",
            "vibrato=f=4:d=0.3,volume=0.25",
            str(out_path),
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(f"ffmpeg failed generating mock song: {result.stderr[-2000:]}")
        return out_path
