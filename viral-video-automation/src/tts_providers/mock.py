from __future__ import annotations

import subprocess
from pathlib import Path

from .base import TTSProvider

_WORDS_PER_SECOND = 2.5  # ~150 words/minute, a reasonable narration pace


class MockTTSProvider(TTSProvider):
    """Keyless, local placeholder provider.

    Renders a short tone (not silence) whose length roughly matches how
    long the text would take to actually speak, via ffmpeg's lavfi sine
    source. This lets the whole narration pipeline (per-scene duration
    fitting, trimming/padding, mixing with music) be exercised end-to-end
    without an API key -- and it's audible, not silent, so it's obvious
    during review that a real voice belongs there, not that TTS is broken.
    """

    def synthesize(self, text: str, out_path: Path) -> Path:
        word_count = max(len(text.split()), 1)
        estimated_seconds = max(word_count / _WORDS_PER_SECOND, 1.0)

        cmd = [
            "ffmpeg",
            "-y",
            "-f",
            "lavfi",
            "-i",
            f"sine=frequency=440:duration={estimated_seconds}",
            "-af",
            "volume=0.3",
            str(out_path),
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(f"ffmpeg failed generating mock narration: {result.stderr[-2000:]}")
        return out_path
