#!/usr/bin/env python3
"""One-time (or per-redesign) render of the channel mascot's clip library.

Generates bounce_in.mp4, reaction.mp4, and bounce_out.mp4 into
assets/mascot/ from the description in config/config.yaml's `mascot:`
section, using whichever VIDEO_PROVIDER is configured. Every video the
pipeline produces afterwards composites these same clips in via ffmpeg
(see src/video_generator.py) rather than asking the model to redraw the
character fresh each time -- see assets/mascot/DESIGN_BRIEF.md for why.

Run again any time you change the mascot's design in config.yaml. This
overwrites the existing clips; already-generated videos are unaffected.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.config import PROJECT_ROOT, load_settings
from src.video_providers import get_provider


def _has_audio_stream(path: Path) -> bool:
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "a", "-show_entries", "stream=index", "-of", "csv=p=0", str(path)],
        capture_output=True,
        text=True,
    )
    return bool(result.stdout.strip())


def _ensure_audio(path: Path) -> None:
    """Compositing later assumes every mascot clip has an audio stream (even
    if silent), so bumper-concat and reaction-overlay don't need per-clip
    special-casing. Add one if the provider didn't include it."""
    if _has_audio_stream(path):
        return
    tmp = path.with_suffix(".tmp.mp4")
    result = subprocess.run(
        [
            "ffmpeg", "-y",
            "-i", str(path),
            "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo",
            "-c:v", "copy", "-c:a", "aac", "-shortest",
            str(tmp),
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg failed adding silent audio to {path}: {result.stderr[-2000:]}")
    tmp.replace(path)


def generate_mascot_assets() -> None:
    settings = load_settings()
    mascot = settings.mascot
    if not mascot.get("enabled"):
        print("[mascot] mascot.enabled is false in config.yaml, nothing to do")
        return

    provider = get_provider(settings)
    resolution = settings.video_generation["resolution"]
    assets_dir = PROJECT_ROOT / mascot["assets_dir"]
    assets_dir.mkdir(parents=True, exist_ok=True)

    for clip_name, spec in mascot["clips"].items():
        if spec.get("composited"):
            background = (
                f"Background: solid chroma key green ({mascot['chroma_key_color']}), "
                "no other elements, so this clip can be composited over other footage."
            )
        else:
            background = f"Background: {mascot['bumper_background']}."

        prompt = f"{mascot['visual_description'].strip()} {spec['prompt_suffix']} {background}"
        out_path = assets_dir / f"{clip_name}.mp4"

        print(f"[mascot] generating {clip_name}.mp4 ({spec['duration_seconds']}s)...")
        provider.generate_scene_clip(
            prompt=prompt,
            duration_seconds=spec["duration_seconds"],
            resolution=resolution,
            out_path=out_path,
        )
        _ensure_audio(out_path)
        print(f"[mascot] wrote {out_path}")

    print(f"[mascot] done. Assets in {assets_dir}/")


if __name__ == "__main__":
    generate_mascot_assets()
