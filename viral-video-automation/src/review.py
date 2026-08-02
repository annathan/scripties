"""Stage 4: human review gate.

Nothing in the pipeline auto-progresses past here -- approve() must be
called explicitly, per item, before stage 5 (upload) will touch it. This is
the safety valve for both quality and YouTube policy compliance.
"""
from __future__ import annotations

import json
import logging
import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .config import PROJECT_ROOT, Settings, load_settings

logger = logging.getLogger(__name__)


def list_pending(settings: Settings | None = None) -> list[dict]:
    settings = settings or load_settings()
    queue_dir = PROJECT_ROOT / settings.review["queue_dir"]
    if not queue_dir.exists():
        return []
    items = []
    for item_dir in sorted(queue_dir.iterdir()):
        metadata_path = item_dir / "metadata.json"
        if metadata_path.exists():
            metadata = json.loads(metadata_path.read_text())
            if metadata.get("status") == "pending_review":
                items.append(metadata)
    return items


def approve(slug: str, settings: Settings | None = None) -> Path:
    settings = settings or load_settings()
    queue_dir = PROJECT_ROOT / settings.review["queue_dir"]
    approved_dir = PROJECT_ROOT / settings.review["approved_dir"]
    src_dir = queue_dir / slug
    if not src_dir.exists():
        raise FileNotFoundError(f"No such item in review queue: {slug}")

    metadata_path = src_dir / "metadata.json"
    metadata = json.loads(metadata_path.read_text())
    metadata["status"] = "approved"

    dest_dir = approved_dir / slug
    dest_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src_dir / "final.mp4", dest_dir / "final.mp4")
    (dest_dir / "metadata.json").write_text(json.dumps(metadata, indent=2))
    metadata_path.write_text(json.dumps(metadata, indent=2))
    logger.info(f"approved {slug} -> {dest_dir}")
    return dest_dir


def reject(slug: str, reason: str = "", settings: Settings | None = None) -> None:
    settings = settings or load_settings()
    queue_dir = PROJECT_ROOT / settings.review["queue_dir"]
    src_dir = queue_dir / slug
    metadata_path = src_dir / "metadata.json"
    if not metadata_path.exists():
        raise FileNotFoundError(f"No such item in review queue: {slug}")
    metadata = json.loads(metadata_path.read_text())
    metadata["status"] = "rejected"
    metadata["rejection_reason"] = reason
    metadata_path.write_text(json.dumps(metadata, indent=2))
    logger.info(f"rejected {slug}" + (f" ({reason})" if reason else ""))


def build_gallery(settings: Settings | None = None) -> Path:
    """Writes an index.html into the review queue dir so pending videos can
    be eyeballed in a browser (open the file directly from disk)."""
    settings = settings or load_settings()
    queue_dir = PROJECT_ROOT / settings.review["queue_dir"]
    pending = list_pending(settings)

    cards = []
    for metadata in pending:
        video_path = PROJECT_ROOT / metadata["video_path"]
        rel_to_queue = video_path.relative_to(queue_dir)
        cards.append(f"""
        <div class="card">
          <video controls src="{rel_to_queue.as_posix()}"></video>
          <h3>{metadata['title']}</h3>
          <p>{metadata['premise']}</p>
          <p><b>Tags:</b> {', '.join(metadata['tags'])}</p>
          <p><code>python -m src.review approve {metadata['slug']}</code> &nbsp;
             <code>python -m src.review reject {metadata['slug']}</code></p>
        </div>""")

    html = f"""<!doctype html>
<html><head><meta charset="utf-8"><title>Review queue</title>
<style>
body {{ font-family: sans-serif; background: #111; color: #eee; padding: 2rem; }}
.card {{ background: #1c1c1c; border-radius: 12px; padding: 1rem; margin-bottom: 2rem; max-width: 480px; }}
video {{ width: 100%; border-radius: 8px; }}
code {{ background: #000; padding: 2px 6px; border-radius: 4px; }}
</style></head>
<body>
<h1>Pending review ({len(cards)})</h1>
{''.join(cards) if cards else '<p>Nothing pending.</p>'}
</body></html>
"""
    out_path = queue_dir / "index.html"
    out_path.write_text(html)
    logger.info(f"wrote gallery to {out_path}")
    return out_path


def prune(older_than_days: int = 14, settings: Settings | None = None) -> list[str]:
    """Deletes the generated video (final.mp4 + work/) for rejected items
    older than older_than_days, keeping metadata.json (including the
    rejection reason) for an audit trail. Keeps the review queue from
    growing forever across an unattended, twice-a-week cadence."""
    settings = settings or load_settings()
    queue_dir = PROJECT_ROOT / settings.review["queue_dir"]
    if not queue_dir.exists():
        return []

    cutoff = datetime.now(timezone.utc) - timedelta(days=older_than_days)
    pruned = []
    for item_dir in sorted(queue_dir.iterdir()):
        metadata_path = item_dir / "metadata.json"
        if not metadata_path.exists():
            continue
        metadata = json.loads(metadata_path.read_text())
        if metadata.get("status") != "rejected":
            continue

        generated_at = metadata.get("generated_at")
        if not generated_at:
            continue
        generated_dt = datetime.strptime(generated_at, "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)
        if generated_dt > cutoff:
            continue

        final_video = item_dir / "final.mp4"
        work_dir = item_dir / "work"
        if final_video.exists():
            final_video.unlink()
        if work_dir.exists():
            shutil.rmtree(work_dir)
        pruned.append(metadata["slug"])
        logger.info(f"pruned rejected item {metadata['slug']} (generated {generated_at})")

    return pruned


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("usage: python -m src.review [list|gallery|approve <slug>|reject <slug> [reason]|prune [days]]")
        raise SystemExit(1)

    cmd = sys.argv[1]
    if cmd == "list":
        for m in list_pending():
            print(f"- {m['slug']}: {m['title']}")
    elif cmd == "gallery":
        build_gallery()
    elif cmd == "approve":
        approve(sys.argv[2])
    elif cmd == "reject":
        reject(sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else "")
    elif cmd == "prune":
        days = int(sys.argv[2]) if len(sys.argv) > 2 else 14
        pruned = prune(days)
        print(f"pruned {len(pruned)} rejected item(s) older than {days} days")
    else:
        print(f"unknown command {cmd!r}")
        raise SystemExit(1)
