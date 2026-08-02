"""Stage 1: find currently-performing kids-content videos on YouTube.

Uses the official YouTube Data API v3 (search.list + videos.list) — no
scraping. This is read-only and only needs an API key (no OAuth), so it's
safe to run frequently.

Output is a "trend report": for each search query, the top-scoring videos
with normalized signals (view velocity, engagement rate, title/tag patterns).
It intentionally does NOT store or forward video content itself — only
metadata used to spot *patterns* (topics, pacing, title structure) that
stage 2 uses as inspiration, never a specific video to copy.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from .config import Settings, load_settings


@dataclass
class VideoSignal:
    video_id: str
    title: str
    channel_title: str
    published_at: str
    view_count: int
    like_count: int
    comment_count: int
    duration_iso: str
    tags: list[str]
    made_for_kids: bool | None
    view_velocity: float  # views per day since published
    engagement_rate: float  # (likes + comments) / views

    @property
    def url(self) -> str:
        return f"https://www.youtube.com/watch?v={self.video_id}"


def _view_velocity(view_count: int, published_at: str) -> float:
    published = datetime.fromisoformat(published_at.replace("Z", "+00:00"))
    age_days = max((datetime.now(timezone.utc) - published).total_seconds() / 86400, 0.5)
    return view_count / age_days


def _engagement_rate(view_count: int, like_count: int, comment_count: int) -> float:
    if view_count == 0:
        return 0.0
    return (like_count + comment_count) / view_count


def scan_query(youtube, query: str, settings: Settings) -> list[VideoSignal]:
    cfg = settings.trend_scanner
    published_after = (
        datetime.now(timezone.utc) - timedelta(days=cfg["published_within_days"])
    ).strftime("%Y-%m-%dT%H:%M:%SZ")

    search_resp = (
        youtube.search()
        .list(
            q=query,
            part="id",
            type="video",
            order="viewCount",
            publishedAfter=published_after,
            maxResults=min(cfg["max_results_per_query"], 50),
            safeSearch="strict",
        )
        .execute()
    )
    video_ids = [item["id"]["videoId"] for item in search_resp.get("items", [])]
    if not video_ids:
        return []

    videos_resp = (
        youtube.videos()
        .list(part="snippet,statistics,contentDetails,status", id=",".join(video_ids))
        .execute()
    )

    signals = []
    for item in videos_resp.get("items", []):
        snippet = item["snippet"]
        stats = item.get("statistics", {})
        status = item.get("status", {})
        made_for_kids = status.get("madeForKids")

        if cfg.get("restrict_to_made_for_kids") and made_for_kids is False:
            continue

        view_count = int(stats.get("viewCount", 0))
        like_count = int(stats.get("likeCount", 0))
        comment_count = int(stats.get("commentCount", 0))
        published_at = snippet["publishedAt"]
        velocity = _view_velocity(view_count, published_at)

        if velocity < cfg["min_view_velocity"]:
            continue

        signals.append(
            VideoSignal(
                video_id=item["id"],
                title=snippet["title"],
                channel_title=snippet["channelTitle"],
                published_at=published_at,
                view_count=view_count,
                like_count=like_count,
                comment_count=comment_count,
                duration_iso=item.get("contentDetails", {}).get("duration", ""),
                tags=snippet.get("tags", []) or [],
                made_for_kids=made_for_kids,
                view_velocity=round(velocity, 1),
                engagement_rate=round(_engagement_rate(view_count, like_count, comment_count), 4),
            )
        )

    signals.sort(key=lambda s: s.view_velocity, reverse=True)
    return signals


def run_trend_scan(settings: Settings | None = None) -> Path:
    settings = settings or load_settings()
    if not settings.youtube_api_key:
        raise RuntimeError(
            "YOUTUBE_API_KEY is not set. Copy .env.example to .env and add a "
            "YouTube Data API v3 key (Google Cloud Console -> Credentials)."
        )

    youtube = build("youtube", "v3", developerKey=settings.youtube_api_key)

    report: dict[str, list[dict]] = {}
    for query in settings.trend_scanner["search_queries"]:
        try:
            signals = scan_query(youtube, query, settings)
        except HttpError as e:
            print(f"[trend_scanner] query {query!r} failed: {e}")
            continue
        report[query] = [asdict(s) for s in signals]
        print(f"[trend_scanner] {query!r}: {len(signals)} qualifying videos")

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_path = settings.path(f"data/trends/trend_report_{timestamp}.json")
    out_path.write_text(json.dumps({"generated_at": timestamp, "niche": settings.niche, "results": report}, indent=2))
    print(f"[trend_scanner] wrote {out_path}")
    return out_path


if __name__ == "__main__":
    run_trend_scan()
