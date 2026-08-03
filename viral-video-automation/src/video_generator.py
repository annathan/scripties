"""Stage 3: turn one concept (title + scenes) into an assembled video file.

For each scene, calls the configured VideoProvider to produce a raw clip,
then uses ffmpeg to: concatenate scenes, burn in narration captions, and mix
in background music. Requires ffmpeg on PATH.

Nothing here uploads or publishes anything -- output lands in
data/review_queue/<slug>/ for stage 4 (human review).
"""
from __future__ import annotations

import json
import logging
import random
import re
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .config import PROJECT_ROOT, Settings, load_settings
from .retry import with_retry
from .video_providers import get_provider
from .video_providers.base import VideoProvider

logger = logging.getLogger(__name__)


def _slugify(title: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
    return slug[:60] or "untitled"


def _srt_timestamp(seconds: float) -> str:
    total_ms = int(timedelta(seconds=seconds).total_seconds() * 1000)
    hours, rem = divmod(total_ms, 3_600_000)
    minutes, rem = divmod(rem, 60_000)
    secs, ms = divmod(rem, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{ms:03d}"


def _build_srt(scenes: list[dict], scene_durations: list[float], out_path: Path) -> Path:
    lines = []
    t = 0.0
    for i, scene in enumerate(scenes):
        start, end = t, t + scene_durations[i]
        lines += [str(i + 1), f"{_srt_timestamp(start)} --> {_srt_timestamp(end)}", scene["narration"], ""]
        t = end
    out_path.write_text("\n".join(lines))
    return out_path


def _run_ffmpeg(args: list[str], cwd: Path | None = None) -> None:
    result = subprocess.run(["ffmpeg", "-y", *args], capture_output=True, text=True, cwd=cwd)
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg failed: {result.stderr[-4000:]}")


def _probe_duration(path: Path) -> float:
    """Actual clip duration, not the one we asked the provider for. Some
    providers only support fixed-length outputs (e.g. Pika's 5s/10s enum),
    so the requested and rendered durations can differ -- captions and
    mascot-transition timing need to match reality, not the request."""
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
        capture_output=True,
        text=True,
    )
    return float(result.stdout.strip())


def _pick_music_track(settings: Settings) -> Path | None:
    music_dir = PROJECT_ROOT / settings.video_generation["music"]["dir"]
    if not music_dir.exists():
        return None
    tracks = [p for p in music_dir.iterdir() if p.suffix.lower() in (".mp3", ".wav", ".m4a")]
    return random.choice(tracks) if tracks else None


_REACTION_POSITIONS = {
    "top_right": ("W-w-{m}", "{m}"),
    "top_left": ("{m}", "{m}"),
    "bottom_right": ("W-w-{m}", "H-h-{m}"),
    "bottom_left": ("{m}", "H-h-{m}"),
}


def _composite_mascot_reactions(
    combined_path: Path, work_dir: Path, settings: Settings, scene_durations: list[float]
) -> Path:
    """Overlays the mascot's pre-rendered 'reaction' clip (chroma-keyed) at
    each scene transition, in a corner, on top of the ongoing scene content.
    Transition points are the actual (ffprobe-measured) scene boundaries,
    not the theoretical ones -- a provider that doesn't honor the requested
    duration exactly shouldn't desync the pop-in. Falls back to returning
    combined_path unchanged if the mascot is disabled, there's only one
    scene (no transitions), or the asset hasn't been generated yet."""
    mascot = settings.mascot
    if not mascot.get("enabled") or len(scene_durations) < 2:
        return combined_path

    assets_dir = PROJECT_ROOT / mascot["assets_dir"]
    reaction_clip = assets_dir / "reaction.mp4"
    if not reaction_clip.exists():
        logger.warning(f"mascot reaction clip not found at {reaction_clip}, skipping pop-ins "
                        "(run scripts/generate_mascot_assets.py)")
        return combined_path

    reaction_duration = mascot["clips"]["reaction"]["duration_seconds"]
    size_frac = mascot.get("reaction_size_pct", 30) / 100
    margin = 24
    x_expr, y_expr = (
        v.format(m=margin) for v in _REACTION_POSITIONS[mascot.get("reaction_position", "top_right")]
    )

    boundaries = []
    cumulative = 0.0
    for d in scene_durations[:-1]:
        cumulative += d
        boundaries.append(cumulative)

    inputs = ["-i", str(combined_path)]
    for _ in boundaries:
        inputs += ["-i", str(reaction_clip)]

    filter_parts = []
    labels = []
    for i in range(len(boundaries)):
        label = f"r{i}"
        filter_parts.append(
            f"[{i + 1}:v]scale=iw*{size_frac}:-1,colorkey={mascot['chroma_key_color']}:0.3:0.1[{label}]"
        )
        labels.append(label)

    current = "0:v"
    for i, label in enumerate(labels):
        t_start = boundaries[i] - reaction_duration / 2
        t_end = t_start + reaction_duration
        out_label = f"v{i}"
        filter_parts.append(
            f"[{current}][{label}]overlay=x={x_expr}:y={y_expr}:enable='between(t,{t_start:.2f},{t_end:.2f})'[{out_label}]"
        )
        current = out_label

    out_path = work_dir / "with_mascot.mp4"
    _run_ffmpeg(
        [*inputs, "-filter_complex", ";".join(filter_parts), "-map", f"[{current}]", "-map", "0:a", "-c:a", "copy", str(out_path)]
    )
    return out_path


def _add_bumpers(core_path: Path, work_dir: Path, settings: Settings) -> Path:
    """Prepends bounce_in and appends bounce_out (the mascot's standalone
    intro/outro clips) around the finished scene content. Falls back to
    returning core_path unchanged if the mascot is disabled or the bumper
    assets haven't been generated yet."""
    mascot = settings.mascot
    if not mascot.get("enabled"):
        return core_path

    assets_dir = PROJECT_ROOT / mascot["assets_dir"]
    bounce_in, bounce_out = assets_dir / "bounce_in.mp4", assets_dir / "bounce_out.mp4"
    if not bounce_in.exists() or not bounce_out.exists():
        logger.warning(f"mascot bumper clips not found in {assets_dir}, skipping intro/outro "
                        "(run scripts/generate_mascot_assets.py)")
        return core_path

    out_path = work_dir / "with_bumpers.mp4"
    _run_ffmpeg(
        [
            "-i", str(bounce_in), "-i", str(core_path), "-i", str(bounce_out),
            "-filter_complex", "[0:v][0:a][1:v][1:a][2:v][2:a]concat=n=3:v=1:a=1[v][a]",
            "-map", "[v]", "-map", "[a]",
            str(out_path),
        ]
    )
    return out_path


@with_retry(attempts=3, base_delay=10.0, exceptions=(Exception,))
def _generate_scene_clip(provider: VideoProvider, **kwargs) -> Path:
    # Broad Exception on purpose: this is a pluggable interface to arbitrary
    # third-party text-to-video vendors with wildly different failure modes
    # (requests errors, timeouts, provider-specific RuntimeErrors, ...) --
    # the goal is "don't die on a transient hiccup," not to distinguish them.
    return provider.generate_scene_clip(**kwargs)


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

    logger.info(f"generating '{concept['title']}' ({len(scenes)} scenes) via {vgcfg['provider']}")
    clip_paths = []
    for i, scene in enumerate(scenes):
        clip_path = work_dir / f"scene_{i:02d}.mp4"
        _generate_scene_clip(
            provider,
            prompt=scene["visual_prompt"],
            duration_seconds=scene_duration,
            resolution=vgcfg["resolution"],
            out_path=clip_path,
        )
        clip_paths.append(clip_path)

    # Measure what was actually rendered rather than trusting the requested
    # duration -- some providers only support fixed-length clips (e.g.
    # Pika's 5s/10s enum) and will silently round, which would otherwise
    # desync captions and mascot pop-ins from the real scene boundaries.
    scene_durations = [_probe_duration(p) for p in clip_paths]

    concat_list = work_dir / "concat_list.txt"
    concat_list.write_text("\n".join(f"file '{p.name}'" for p in clip_paths))
    combined = work_dir / "combined.mp4"
    _run_ffmpeg(["-f", "concat", "-safe", "0", "-i", "concat_list.txt", "-c", "copy", "combined.mp4"], cwd=work_dir)

    with_mascot = _composite_mascot_reactions(combined, work_dir, settings, scene_durations)

    srt_path = work_dir / "captions.srt"
    _build_srt(scenes, scene_durations, srt_path)
    captioned = work_dir / "captioned.mp4"
    _run_ffmpeg(
        [
            "-i", str(with_mascot),
            "-vf", "subtitles=captions.srt:force_style='FontName=Arial,FontSize=18,"
            "PrimaryColour=&HFFFFFF&,OutlineColour=&H000000&,BorderStyle=3'",
            "-c:a", "copy",
            "captioned.mp4",
        ],
        cwd=work_dir,
    )

    core_path = work_dir / "core.mp4"
    music_track = _pick_music_track(settings)
    if music_track is None:
        captioned.replace(core_path)
        logger.info("no music track found in assets/music/, shipping without background music")
    else:
        _run_ffmpeg(
            [
                "-i", str(captioned),
                "-stream_loop", "-1", "-i", str(music_track),
                "-filter_complex",
                "[1:a]volume=0.25[music];[0:a][music]amix=inputs=2:duration=first:dropout_transition=2[aout]",
                "-map", "0:v", "-map", "[aout]",
                "-shortest",
                "-c:v", "copy",
                str(core_path),
            ]
        )

    final_path = item_dir / "final.mp4"
    _add_bumpers(core_path, work_dir, settings).replace(final_path)

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
    logger.info(f"wrote {final_path}")
    return final_path


def generate_videos_from_concepts_file(concepts_path: Path, settings: Settings | None = None) -> list[Path]:
    """Generates a video per concept. A failure on one concept (provider
    outage, a bad prompt, whatever) is logged and skipped rather than
    aborting the whole batch -- for an unattended run, three good videos and
    one logged failure beats zero videos because #2 of 4 blew up."""
    settings = settings or load_settings()
    data = json.loads(concepts_path.read_text())
    concepts = data["concepts"]

    cap = settings.video_generation.get("max_videos_per_run")
    if cap and len(concepts) > cap:
        logger.info(f"capping this run at max_videos_per_run={cap} (ideation produced {len(concepts)} concepts)")
        concepts = concepts[:cap]

    outputs: list[Path] = []
    failures: list[dict] = []
    for concept in concepts:
        try:
            outputs.append(generate_video_for_concept(concept, settings))
        except Exception as exc:
            logger.error(f"failed to generate video for {concept.get('title', '<untitled>')!r}: {exc}")
            failures.append({"title": concept.get("title"), "error": str(exc)})

    logger.info(f"generated {len(outputs)}/{len(concepts)} videos" + (f", {len(failures)} failed" if failures else ""))
    for f in failures:
        logger.warning(f"  failed: {f['title']!r} -- {f['error']}")
    return outputs


if __name__ == "__main__":
    import sys

    if len(sys.argv) != 2:
        print("usage: python -m src.video_generator <concepts.json>")
        raise SystemExit(1)
    generate_videos_from_concepts_file(Path(sys.argv[1]))
