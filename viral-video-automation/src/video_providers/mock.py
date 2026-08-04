from __future__ import annotations

import hashlib
import subprocess
import textwrap
from pathlib import Path

from ..fonts import ffmpeg_escape_path, find_font
from .base import VideoProvider


def _escape_drawtext(text: str) -> str:
    # ffmpeg drawtext needs these escaped or the filter graph parse breaks.
    for char in ("\\", ":", "'", "%"):
        text = text.replace(char, "\\" + char)
    return text


class MockVideoProvider(VideoProvider):
    """Keyless, local placeholder provider.

    Renders a solid-color clip with the scene's visual prompt burned in as
    text, via ffmpeg's lavfi color source. This produces a real, playable
    mp4 for every scene so the *entire* pipeline (concat, captions, music,
    review, upload) can be exercised end-to-end with zero API keys before
    you spend money on a real text-to-video provider.
    """

    def generate_scene_clip(
        self, prompt: str, duration_seconds: float, resolution: str, out_path: Path
    ) -> Path:
        width, height = (int(x) for x in resolution.split("x"))
        # Real providers are asked (via the prompt text) to render mascot
        # "reaction" clips on a solid chroma-key green background so they can
        # be composited over scene content. The mock provider can't actually
        # follow that instruction, but it recognizes the request and uses a
        # real, consistent chroma-key green so the compositing step in
        # video_generator.py is still exercisable end-to-end without keys.
        if "chroma key" in prompt.lower() or "chroma-key" in prompt.lower():
            color = "0x00FF00"
        else:
            color = "0x" + hashlib.md5(prompt.encode()).hexdigest()[:6]

        wrapped = "\n".join(textwrap.wrap(prompt, width=28)[:6])
        text = _escape_drawtext(wrapped)

        # Explicit fontfile= bypasses fontconfig's default-font lookup,
        # which crashes ("Cannot load default config file") on plenty of
        # Windows ffmpeg builds that ship without a working fontconfig setup.
        found = find_font()
        font_clause = f"fontfile='{ffmpeg_escape_path(found[0])}':" if found else ""

        drawtext = (
            f"drawtext={font_clause}text='{text}':fontcolor=white:fontsize=32:"
            "x=(w-text_w)/2:y=(h-text_h)/2:box=1:boxcolor=black@0.5:boxborderw=16"
        )
        cmd = [
            "ffmpeg",
            "-y",
            "-f",
            "lavfi",
            "-i",
            f"color=c={color}:s={width}x{height}:d={duration_seconds}",
            "-f",
            "lavfi",
            "-i",
            f"anullsrc=r=44100:cl=stereo:d={duration_seconds}",
            "-vf",
            drawtext,
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-shortest",
            str(out_path),
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(f"ffmpeg failed generating mock clip: {result.stderr[-4000:]}")
        return out_path
