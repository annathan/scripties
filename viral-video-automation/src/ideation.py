"""Stage 2: turn a trend report into original video concepts.

Feeds the pattern-level signals from stage 1 (what topics/formats/pacing are
currently working, NOT any specific video) into Claude, which returns
wholly original concepts: title, one-line premise, a short script broken
into scenes, a per-scene visual prompt (for stage 3's text-to-video
provider), and upload metadata (description, tags).

The style_guardrails from config.yaml are injected into every request so
originality/safety constraints aren't something each concept has to
remember on its own.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import anthropic

from .config import Settings, load_settings

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
- scenes: a list of {scenes_per_video} scenes, each with:
    - narration: the line(s) spoken/sung during this scene (simple, warm, age-appropriate)
    - visual_prompt: a detailed text-to-video prompt describing the scene \
      (characters, setting, action, animation style — always stylized/cartoon, \
      never photoreal humans)
- description: a YouTube video description (2-3 sentences + relevant hashtags)
- tags: 8-12 relevant search tags

Respond with ONLY a JSON array of concept objects, no prose before or after.
"""


@dataclass
class Concept:
    title: str
    premise: str
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


def generate_concepts(trend_report_path: Path, settings: Settings | None = None) -> Path:
    settings = settings or load_settings()
    if not settings.anthropic_api_key:
        raise RuntimeError(
            "ANTHROPIC_API_KEY is not set. Copy .env.example to .env and add your key."
        )

    trend_report = json.loads(trend_report_path.read_text())
    trend_summary = _summarize_trends(trend_report)

    cfg = settings.ideation
    system_prompt = SYSTEM_PROMPT_TEMPLATE.format(
        guardrails="\n".join(f"- {g}" for g in cfg["style_guardrails"]),
        scenes_per_video=settings.video_generation["scenes_per_video"],
    )

    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
    response = client.messages.create(
        model=cfg["model"],
        max_tokens=4096,
        system=system_prompt,
        messages=[
            {
                "role": "user",
                "content": (
                    f"Trend patterns for niche '{settings.niche}':\n\n{trend_summary}\n\n"
                    f"Generate {cfg['concepts_per_run']} original video concepts."
                ),
            }
        ],
    )

    text = "".join(block.text for block in response.content if block.type == "text")
    concepts_raw = json.loads(text)

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_path = settings.path(f"data/concepts/concepts_{timestamp}.json")
    out_path.write_text(json.dumps({"generated_at": timestamp, "source_trend_report": str(trend_report_path), "concepts": concepts_raw}, indent=2))
    print(f"[ideation] wrote {len(concepts_raw)} concepts to {out_path}")
    return out_path


if __name__ == "__main__":
    import sys

    if len(sys.argv) != 2:
        print("usage: python -m src.ideation <trend_report.json>")
        raise SystemExit(1)
    generate_concepts(Path(sys.argv[1]))
