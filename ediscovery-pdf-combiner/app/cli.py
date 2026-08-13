r"""
Terminal entry point for the eDiscovery PDF combiner.

Kept for whoever is comfortable at a command line (e.g. Andrew); the
double-clickable product for everyone else is app/gui.py, packaged as
a single .exe (see build/pdf_combiner.spec).

Usage:
    python -m app.cli "C:/path/to/export_folder" "C:/path/to/final_combined.pdf" [--check-duplicates-only]
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

from app.core import CombineError, Reporter, run_combine

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler("combine_log.txt"),
        logging.StreamHandler(),
    ],
)


def main() -> None:
    if len(sys.argv) < 3:
        print("Usage: python -m app.cli <source_folder> <final_output.pdf> [--check-duplicates-only]")
        sys.exit(1)

    source_folder = Path(sys.argv[1])
    final_output = Path(sys.argv[2])
    check_duplicates_only = "--check-duplicates-only" in sys.argv[3:]

    try:
        run_combine(
            source_folder,
            final_output,
            check_duplicates_only=check_duplicates_only,
            reporter=Reporter(),
        )
    except CombineError as e:
        logging.getLogger(__name__).error(str(e))
        sys.exit(1)


if __name__ == "__main__":
    main()
