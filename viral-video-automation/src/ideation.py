"""Stage 2: turn a trend report into original video concepts.

Feeds the pattern-level signals from stage 1 (what topics/formats/pacing are
currently working, NOT any specific video) into Claude, which returns
wholly original concepts: title, one-line premise, a short script broken
into scenes, a per-scene visual prompt (for stage 3's text-to-video
provider), and upload metadata (description, tags).

The style_guardrails from config.yaml are injected into every request so
originality/safety constraints aren't something each concept has to
remember on its own. Recently-used titles are also injected so repeated
runs don't quietly fill the review queue with near-duplicates.
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import anthropic

from .config import PROJECT_ROOT, Settings, load_settings
from .retry import with_retry

logger = logging.getLogger(__name__)

SYSTEM_PROMPT_TEMPLATE = """\
You are a creative director for an original kids' animated video channel.

You will be given a summary of *patterns* currently performing well on \
YouTube in this niche (topics, pacing, title style, typical length) — \
never a specific video to imitate. Your job is to invent brand-new, \
wholly original video concepts inspired by those patterns.

Hard rules (non-negotiable):
{guardrails}

For each concept produce:
- title: a catchy, original YouTube title (not copied from any example)
- premise: one sentence describing the story/idea
- format: either "song" (a nursery rhyme, counting song, silly song, or \
  anything meant to be SUNG) or "narration" (a narrated story or \
  informational video meant to be SPOKEN). Pick whichever this concept \
  naturally is — don't force every concept into one or the other.
- scenes: a list of exactly {scenes_per_video} scenes, each with:
    - narration: for format "song", write this as actual singable lyrics \
      (simple rhythm and rhyme) for this scene's portion of the song; for \
      format "narration", write it as spoken narration (simple, warm, \
      age-appropriate). Either way this doubles as the on-screen caption.
    - visual_prompt: a detailed text-to-video prompt describing the scene \
      (characters, setting, action, animation style — always stylized/cartoon, \
      never photoreal humans)
- description: a YouTube video description (2-3 sentences + relevant hashtags)
- tags: 8-12 relevant search tags

Respond with ONLY a JSON array of concept objects — no prose, no markdown code fences, before or after.
"""

REQUIRED_CONCEPT_KEYS = ("title", "premise", "format", "scenes", "description", "tags")
VALID_FORMATS = ("song", "narration")
REQUIRED_SCENE_KEYS = ("narration", "visual_prompt")
MAX_IDEATION_ATTEMPTS = 3


@dataclass
class Concept:
    title: str
    premise: str
    format: str
    scenes: list[dict]
    description: str
    tags: list[str]


def _summarize_trends(trend_report: dict) -> str:
    """Reduce a raw trend report to pattern-level signals only (titles/tags/
    stats), so the LLM sees "what's working" without being handed a specific
    video to reproduce."""
    lines = []
    for query, videos in trend_report.get("results", {}).items():
        if not videos:
            continue
        lines.append(f"Search theme: {query}")
        for v in videos[:5]:
            lines.append(
                f"  - title pattern: {v['title']!r} | view_velocity/day={v['view_velocity']} "
                f"| engagement_rate={v['engagement_rate']} | tags_sample={v['tags'][:5]}"
            )
    return "\n".join(lines) if lines else "No qualifying trend data this run."


def _recent_titles(settings: Settings, limit: int) -> list[str]:
    """Titles from the most recently-generated concept files, so the
    ideation prompt can tell the model what's already been made and steer
    it away from repeating itself run after run."""
    if limit <= 0:
        return []
    concepts_dir = PROJECT_ROOT / "data" / "concepts"
    if not concepts_dir.exists():
        return []

    titles: list[str] = []
    for path in sorted(concepts_dir.glob("concepts_*.json"), reverse=True):
        try:
            data = json.loads(path.read_text())
        except (json.JSONDecodeError, OSError):
            continue
        for concept in data.get("concepts", []):
            if title := concept.get("title"):
                titles.append(title)
        if len(titles) >= limit:
            break
    return titles[:limit]


def _extract_json_text(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    return text.strip()


def _parse_and_validate(text: str, expected_scene_count: int) -> list[dict]:
    concepts = json.loads(_extract_json_text(text))
    if not isinstance(concepts, list) or not concepts:
        raise ValueError("expected a non-empty JSON array of concepts")

    for concept in concepts:
        missing = [k for k in REQUIRED_CONCEPT_KEYS if k not in concept]
        if missing:
            raise ValueError(f"concept {concept.get('title', '<untitled>')!r} missing key(s): {missing}")
        if concept["format"] not in VALID_FORMATS:
            raise ValueError(f"concept {concept['title']!r} has invalid format {concept['format']!r}, expected one of {VALID_FORMATS}")
        if len(concept["scenes"]) != expected_scene_count:
            raise ValueError(
                f"concept {concept['title']!r} has {len(concept['scenes'])} scenes, expected {expected_scene_count}"
            )
        for scene in concept["scenes"]:
            missing_scene_keys = [k for k in REQUIRED_SCENE_KEYS if k not in scene]
            if missing_scene_keys:
                raise ValueError(f"concept {concept['title']!r} has a scene missing key(s): {missing_scene_keys}")

    return concepts


@with_retry(
    attempts=3,
    base_delay=5.0,
    exceptions=(
        anthropic.APIConnectionError,
        anthropic.APITimeoutError,
        anthropic.RateLimitError,
        anthropic.InternalServerError,
        anthropic.OverloadedError,
    ),
)
def _create_message(client: anthropic.Anthropic, **kwargs):
    return client.messages.create(**kwargs)


def generate_concepts(trend_report_path: Path, settings: Settings | None = None) -> Path:
    settings = settings or load_settings()
    if not settings.anthropic_api_key:
        raise RuntimeError(
            "ANTHROPIC_API_KEY is not set. Copy .env.example to .env and add your key."
        )

    trend_report = json.loads(trend_report_path.read_text())
    trend_summary = _summarize_trends(trend_report)

    cfg = settings.ideation
    scenes_per_video = settings.video_generation["scenes_per_video"]
    system_prompt = SYSTEM_PROMPT_TEMPLATE.format(
        guardrails="\n".join(f"- {g}" for g in cfg["style_guardrails"]),
        scenes_per_video=scenes_per_video,
    )

    recent_titles = _recent_titles(settings, cfg.get("avoid_repeating_last_n_titles", 0))
    user_message = (
        f"Trend patterns for niche '{settings.niche}':\n\n{trend_summary}\n\n"
        f"Generate {cfg['concepts_per_run']} original video concepts."
    )
    if recent_titles:
        user_message += (
            "\n\nAlready-used titles this channel has published or generated recently — "
            "invent something distinct from all of these, not a variation on any of them:\n"
            + "\n".join(f"- {t}" for t in recent_titles)
        )

    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
    last_error: Exception | None = None
    concepts_raw: list[dict] | None = None

    max_tokens = cfg.get("max_tokens", 8192)
    for attempt in range(1, MAX_IDEATION_ATTEMPTS + 1):
        response = _create_message(
            client,
            model=cfg["model"],
            max_tokens=max_tokens,
            system=system_prompt,
            messages=[{"role": "user", "content": user_message}],
        )
        text = "".join(block.text for block in response.content if block.type == "text")

        if response.stop_reason == "max_tokens":
            last_error = ValueError(
                f"response was truncated (hit max_tokens={max_tokens} before finishing) -- this is a token "
                "budget problem, not a formatting one. Raise ideation.max_tokens in config.yaml, or lower "
                "concepts_per_run/scenes_per_video, if this keeps happening."
            )
            logger.warning(f"ideation response truncated at max_tokens (attempt {attempt}/{MAX_IDEATION_ATTEMPTS})")
            user_message += (
                "\n\nYour previous response was cut off before it finished (ran out of output budget) -- "
                f"generate fewer/shorter concepts if needed so the full JSON array fits within {max_tokens} tokens."
            )
            continue

        try:
            concepts_raw = _parse_and_validate(text, scenes_per_video)
            break
        except (json.JSONDecodeError, ValueError) as exc:
            last_error = exc
            logger.warning(f"ideation response failed validation (attempt {attempt}/{MAX_IDEATION_ATTEMPTS}): {exc}")
            user_message += (
                "\n\nYour previous response could not be used: "
                f"{exc}. Respond again with ONLY a valid JSON array matching the required schema exactly, "
                "no prose or markdown fences."
            )

    if concepts_raw is None:
        raise RuntimeError(f"ideation failed to produce valid concepts after {MAX_IDEATION_ATTEMPTS} attempts: {last_error}")

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_path = settings.path(f"data/concepts/concepts_{timestamp}.json")
    out_path.write_text(json.dumps({"generated_at": timestamp, "source_trend_report": str(trend_report_path), "concepts": concepts_raw}, indent=2))
    logger.info(f"wrote {len(concepts_raw)} concepts to {out_path}")
    return out_path


if __name__ == "__main__":
    import sys

    if len(sys.argv) != 2:
        print("usage: python -m src.ideation <trend_report.json>")
        raise SystemExit(1)
    generate_concepts(Path(sys.argv[1]))
