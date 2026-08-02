"""Every stage logs to both the console and data/pipeline.log, so an
unattended run (cron, a scheduled task, whatever ends up kicking this off
twice a week) leaves a trail you can check after the fact instead of
requiring you to babysit a terminal.
"""
from __future__ import annotations

import logging
from pathlib import Path

_configured = False


def configure_logging(log_path: Path) -> None:
    global _configured
    if _configured:
        return
    log_path.parent.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[logging.StreamHandler(), logging.FileHandler(log_path)],
    )
    _configured = True
