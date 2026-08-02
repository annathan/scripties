"""Stage 3: turn one concept (title + scenes) into an assembled video file.

For each scene, calls the configured VideoProvider to produce a raw clip,
then uses ffmpeg to: concatenate scenes, burn in narration captions, and mix
in background music. Requires ffmpeg on PATH.

Nothing here uploads or publishes anything -- output lands in
data/review_queue/<slug>/ for stage 4 (human review).
"""
from __future__ import annotations

import json
import random
import re
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .config import PROJECT_ROOT, Settings, load_settings
from .video_providers import get_provider


def _slugify(title: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
    return slug[:60] or "untitled"


def _srt_timestamp(seconds: float) -> str:
    total_ms = int(timedelta(seconds=seconds).total_seconds() * 1000)
    hours, rem = divmod(total_ms, 3_600_000)
    minutes, rem = divmod(rem, 60_000)
    secs, ms = divmod(rem, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{ms:03d}"


def _build_srt(scenes: list[dict], scene_duration: float, out_path: Path) -> Path:
    lines = []
    for i, scene in enumerate(scenes):
        start, end = i * scene_duration, (i + 1) * scene_duration
        lines += [str(i + 1), f"{_srt_timestamp(start)} --> {_srt_timestamp(end)}", scene["narration"], ""]
    out_path.write_text("\n".join(lines))
    return out_path


def _run_ffmpeg(args: list[str], cwd: Path | None = None) -> None:
    result = subprocess.run(["ffmpeg", "-y", *args], capture_output=True, text=True, cwd=cwd)
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg failed: {result.stderr[-4000:]}")


def _pick_music_track(settings: Settings) -> Path | None:
    music_dir = PROJECT_ROOT / settings.video_generation["music"]["dir"]
    if not music_dir.exists():
        return None
    tracks = [p for p in music_dir.iterdir() if p.suffix.lower() in (".mp3", ".wav", ".m4a")]
    return random.choice(tracks) if tracks else None


def generate_video_for_concept(concept: dict, settings: Settings | None = None) -> Path:
    settings = settings or load_settings()
    provider = get_provider(settings)
    vgcfg = settings.video_generation
    scenes = concept["scenes"]
    scene_duration = vgcfg["target_duration_seconds"] / len(scenes)

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    slug = f"{_slugify(concept['title'])}-{timestamp}"
    item_dir = settings.path(f"data/review_queue/{slug}/placeholder").parent
    work_dir = item_dir / "work"
    work_dir.mkdir(parents=True, exist_ok=True)

    print(f"[video_generator] generating '{concept['title']}' ({len(scenes)} scenes) via {vgcfg['provider']}")
    clip_paths = []
    for i, scene in enumerate(scenes):
        clip_path = work_dir / f"scene_{i:02d}.mp4"
        provider.generate_scene_clip(
            prompt=scene["visual_prompt"],
            duration_seconds=scene_duration,
            resolution=vgcfg["resolution"],
            out_path=clip_path,
        )
        clip_paths.append(clip_path)

    concat_list = work_dir / "concat_list.txt"
    concat_list.write_text("\n".join(f"file '{p.name}'" for p in clip_paths))
    combined = work_dir / "combined.mp4"
    _run_ffmpeg(["-f", "concat", "-safe", "0", "-i", "concat_list.txt", "-c", "copy", "combined.mp4"], cwd=work_dir)

    srt_path = work_dir / "captions.srt"
    _build_srt(scenes, scene_duration, srt_path)
    captioned = work_dir / "captioned.mp4"
    _run_ffmpeg(
        [
            "-i", "combined.mp4",
            "-vf", "subtitles=captions.srt:force_style='FontName=Arial,FontSize=18,"
            "PrimaryColour=&HFFFFFF&,OutlineColour=&H000000&,BorderStyle=3'",
            "-c:a", "copy",
            "captioned.mp4",
        ],
        cwd=work_dir,
    )

    final_path = item_dir / "final.mp4"
    music_track = _pick_music_track(settings)
    if music_track is None:
        (work_dir / "captioned.mp4").replace(final_path)
        print("[video_generator] no music track found in assets/music/, shipping without background music")
    else:
        _run_ffmpeg(
            [
                "-i", str(work_dir / "captioned.mp4"),
                "-stream_loop", "-1", "-i", str(music_track),
                "-filter_complex",
                "[1:a]volume=0.25[music];[0:a][music]amix=inputs=2:duration=first:dropout_transition=2[aout]",
                "-map", "0:v", "-map", "[aout]",
                "-shortest",
                "-c:v", "copy",
                str(final_path),
            ]
        )

    metadata = {
        "slug": slug,
        "title": concept["title"],
        "premise": concept.get("premise", ""),
        "description": concept.get("description", ""),
        "tags": concept.get("tags", []),
        "made_for_kids": settings.upload["made_for_kids"],
        "privacy_status": settings.upload["privacy_status"],
        "category_id": settings.upload["category_id"],
        "video_path": str(final_path.relative_to(PROJECT_ROOT)),
        "status": "pending_review",
        "generated_at": timestamp,
    }
    (item_dir / "metadata.json").write_text(json.dumps(metadata, indent=2))
    print(f"[video_generator] wrote {final_path}")
    return final_path


def generate_videos_from_concepts_file(concepts_path: Path, settings: Settings | None = None) -> list[Path]:
    settings = settings or load_settings()
    data = json.loads(concepts_path.read_text())
    outputs = []
    for concept in data["concepts"]:
        outputs.append(generate_video_for_concept(concept, settings))
    return outputs


if __name__ == "__main__":
    import sys

    if len(sys.argv) != 2:
        print("usage: python -m src.video_generator <concepts.json>")
        raise SystemExit(1)
    generate_videos_from_concepts_file(Path(sys.argv[1]))
