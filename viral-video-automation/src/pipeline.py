#!/usr/bin/env python3
"""Orchestrator CLI for the pipeline.

    python -m src.pipeline scan                 # stage 1: find trends
    python -m src.pipeline ideate <trend.json>   # stage 2: generate concepts
    python -m src.pipeline generate <concepts.json>  # stage 3: build videos
    python -m src.pipeline review list           # stage 4: see what's pending
    python -m src.pipeline review gallery        # stage 4: build browsable HTML
    python -m src.pipeline review approve <slug> # stage 4: approve one
    python -m src.pipeline review reject <slug>  # stage 4: reject one
    python -m src.pipeline upload <slug>         # stage 5: publish an approved video
    python -m src.pipeline run                   # stages 1-3 back to back, stops at review

`run` deliberately stops before upload -- nothing publishes to YouTube
without an explicit `review approve` + `upload` for that specific item.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import ideation, review, trend_scanner, uploader, video_generator
from .config import load_settings


def cmd_scan(args: argparse.Namespace) -> None:
    trend_scanner.run_trend_scan()


def cmd_ideate(args: argparse.Namespace) -> None:
    ideation.generate_concepts(Path(args.trend_report))


def cmd_generate(args: argparse.Namespace) -> None:
    video_generator.generate_videos_from_concepts_file(Path(args.concepts))


def cmd_review(args: argparse.Namespace) -> None:
    if args.action == "list":
        for m in review.list_pending():
            print(f"- {m['slug']}: {m['title']}")
    elif args.action == "gallery":
        review.build_gallery()
    elif args.action == "approve":
        review.approve(args.slug)
    elif args.action == "reject":
        review.reject(args.slug, args.reason or "")


def cmd_upload(args: argparse.Namespace) -> None:
    uploader.upload_video(args.slug)


def cmd_run(args: argparse.Namespace) -> None:
    settings = load_settings()
    print("=== Stage 1: scanning trends ===")
    trend_report = trend_scanner.run_trend_scan(settings)

    print("\n=== Stage 2: generating concepts ===")
    concepts_path = ideation.generate_concepts(trend_report, settings)

    print("\n=== Stage 3: generating videos ===")
    video_generator.generate_videos_from_concepts_file(concepts_path, settings)

    print("\n=== Stage 4: review queue ===")
    gallery = review.build_gallery(settings)
    print(f"Open {gallery} to review, then approve/reject each item:")
    print("  python -m src.pipeline review list")
    print("  python -m src.pipeline review approve <slug>")
    print("  python -m src.pipeline upload <slug>")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("scan").set_defaults(func=cmd_scan)

    p = sub.add_parser("ideate")
    p.add_argument("trend_report")
    p.set_defaults(func=cmd_ideate)

    p = sub.add_parser("generate")
    p.add_argument("concepts")
    p.set_defaults(func=cmd_generate)

    p = sub.add_parser("review")
    p.add_argument("action", choices=["list", "gallery", "approve", "reject"])
    p.add_argument("slug", nargs="?")
    p.add_argument("reason", nargs="?")
    p.set_defaults(func=cmd_review)

    p = sub.add_parser("upload")
    p.add_argument("slug")
    p.set_defaults(func=cmd_upload)

    sub.add_parser("run").set_defaults(func=cmd_run)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
