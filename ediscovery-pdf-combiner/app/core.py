r"""
Core pipeline for combining an eDiscovery export into a single PDF.

Converts Word, Excel, and PowerPoint files to PDF using Office (COM),
then merges everything in batches to keep memory use low.

This module has no UI code in it. It is used by both app/cli.py (a thin
terminal wrapper) and app/gui.py (the packaged desktop app), so all
progress/log output goes through the Reporter callback instead of being
printed directly - callers decide whether that becomes a progress bar,
a log pane, or plain stdout.
"""

from __future__ import annotations

import os
import gc
import re
import shutil
import csv
import logging
import threading
import warnings
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from pypdf import PdfWriter, PdfReader
from pypdf.errors import PdfReadWarning

warnings.filterwarnings("ignore", category=PdfReadWarning)
logging.getLogger("pypdf").setLevel(logging.ERROR)

log = logging.getLogger(__name__)

BATCH_SIZE = 10

WORD_EXT = {".doc", ".docx"}
EXCEL_EXT = {".xls", ".xlsx"}
PPT_EXT = {".ppt", ".pptx"}


VERSION_COMPOUND_PATTERN = re.compile(r"(?:^|[_\s-])v\d+(?:\.\d+)?(?:_\d+)?(?=$|[_\s-])")

WORD_TOKENS = [
    r"\bfinal\b",
    r"\bfinal\s*version\b",
    r"\bfinal\s*draft\b",
    r"\bdraft\b",
    r"\bcopy\b",
    r"\brevised\b",
    r"\bupdated\b",
    r"\breview\b",
    r"\bclean\b",
    r"\bredline\b",
    r"\btracked\s*changes\b",
    r"\bdigital\b",
    r"\(\d+\)",
    r"_\d+$",
    r"-\d+$",
]


# --------------------------------------------------------------------------
# Errors - typed so callers (the GUI in particular) can show a specific,
# friendly message instead of a raw traceback.
# --------------------------------------------------------------------------

class CombineError(Exception):
    """Base class for expected, user-facing failures."""


class SourceNotFoundError(CombineError):
    pass


class OutputPathInvalidError(CombineError):
    pass


class NoConvertibleFilesError(CombineError):
    pass


class OfficeNotAvailableError(CombineError):
    pass


class Cancelled(CombineError):
    """Raised internally when the user cancels a run; callers can catch
    this to distinguish a deliberate stop from a real failure."""


# --------------------------------------------------------------------------
# Reporter - progress/log callback bundle. Defaults to plain `logging`
# so CLI behavior matches the original script.
# --------------------------------------------------------------------------

class Reporter:
    def __init__(self, progress_cb=None, log_cb=None):
        self._progress_cb = progress_cb
        self._log_cb = log_cb

    def progress(self, current: int, total: int, message: str = "") -> None:
        if self._progress_cb:
            self._progress_cb(current, total, message)

    def info(self, message: str) -> None:
        log.info(message)
        if self._log_cb:
            self._log_cb("info", message)

    def warning(self, message: str) -> None:
        log.warning(message)
        if self._log_cb:
            self._log_cb("warning", message)

    def error(self, message: str) -> None:
        log.error(message)
        if self._log_cb:
            self._log_cb("error", message)


def _check_cancelled(cancel_event: threading.Event | None) -> None:
    if cancel_event is not None and cancel_event.is_set():
        raise Cancelled("Run cancelled by user.")


@dataclass
class RunResult:
    files_found: int = 0
    files_converted: int = 0
    files_skipped: int = 0
    duplicate_groups: int = 0
    duplicate_extra_files: int = 0
    dup_report_path: Path | None = None
    page_report_path: Path | None = None
    final_output: Path | None = None
    work_folder: Path | None = None
    skipped_files: list[str] = field(default_factory=list)


def normalize_name(filename: str) -> str:
    """Strip version/status words and numbering from a filename so different
    versions of the same document collapse to the same key. Handles both
    space-separated versions ('Report V2') and underscore/hyphen-separated
    versions ('Report_v2.1', 'Report_v3.2_1'), since a plain \\b boundary
    never fires between an underscore and a letter."""
    name = Path(filename).stem.lower()
    name = VERSION_COMPOUND_PATTERN.sub("", name)
    for pattern in WORD_TOKENS:
        name = re.sub(pattern, "", name)
    name = re.sub(r"[^a-z0-9]+", " ", name).strip()
    return name


def detect_duplicate_candidates(
    source_folder: Path, report_path: Path, reporter: Reporter
) -> tuple[int, int]:
    """Group files by normalized name to surface likely duplicate versions
    (e.g. 'Annual Report V2.docx', 'Annual Report Final.docx',
    'Annual Report.pdf'). Writes a CSV for manual review. Does not exclude
    anything automatically, since picking the authoritative version is a
    judgment call. Returns (number_of_duplicate_groups, number_of_extra_files)."""
    files = sorted(p for p in source_folder.rglob("*") if p.is_file())

    groups: dict[str, list[Path]] = {}
    for f in files:
        key = normalize_name(f.name)
        if not key:
            continue
        groups.setdefault(key, []).append(f)

    dup_groups = {k: v for k, v in groups.items() if len(v) > 1}
    extra_count = sum(len(v) - 1 for v in dup_groups.values())

    with open(report_path, "w", newline="", encoding="utf-8") as rf:
        writer = csv.writer(rf)
        writer.writerow(["group_key", "file_name", "extension", "size_bytes", "full_path"])
        for key, paths in sorted(dup_groups.items()):
            for p in paths:
                writer.writerow([key, p.name, p.suffix.lower(), p.stat().st_size, str(p)])

    if dup_groups:
        reporter.warning(
            f"Found {len(dup_groups)} groups of likely duplicate/version files "
            f"({extra_count} extra files beyond one-per-group). "
            f"Review before converting: {report_path}"
        )
        for key, paths in sorted(dup_groups.items()):
            names = ", ".join(p.name for p in paths)
            reporter.warning(f"  Possible duplicate set '{key}': {names}")
    else:
        reporter.info("No likely duplicate/version groups found by filename.")

    return len(dup_groups), extra_count


def check_office_available() -> None:
    """Raise OfficeNotAvailableError up front if pywin32/Office automation
    isn't usable on this machine, instead of failing on the first file."""
    try:
        import win32com.client  # noqa: F401
    except ImportError as e:
        raise OfficeNotAvailableError(
            "Microsoft Office automation isn't available on this PC. "
            "This tool needs Word, Excel, and PowerPoint installed to convert "
            "those file types to PDF."
        ) from e


def convert_office_to_pdf(input_path: Path, output_path: Path, reporter: Reporter) -> bool:
    """Convert a single Office file to PDF using COM automation.
    Opens and closes the app for each file to avoid memory buildup."""
    ext = input_path.suffix.lower()
    try:
        import win32com.client as win32

        if ext in WORD_EXT:
            app = win32.Dispatch("Word.Application")
            app.Visible = False
            doc = app.Documents.Open(str(input_path))
            doc.SaveAs(str(output_path), FileFormat=17)  # 17 = PDF
            doc.Close()
            app.Quit()

        elif ext in EXCEL_EXT:
            app = win32.Dispatch("Excel.Application")
            app.Visible = False
            wb = app.Workbooks.Open(str(input_path))
            wb.ExportAsFixedFormat(0, str(output_path))  # 0 = PDF
            wb.Close(False)
            app.Quit()

        elif ext in PPT_EXT:
            app = win32.Dispatch("PowerPoint.Application")
            pres = app.Presentations.Open(str(input_path), WithWindow=False)
            pres.SaveAs(str(output_path), 32)  # 32 = PDF
            pres.Close()
            app.Quit()

        else:
            return False

        return True

    except Exception as e:
        reporter.error(f"Failed to convert {input_path.name}: {e}")
        return False
    finally:
        gc.collect()


WINDOWS_LONG_PATH_PREFIX = r"\\?" + "\\"


def long_path(p: Path) -> str:
    """Return a Windows extended-length path (\\?\\...) for paths that may
    exceed 260 characters, so reads don't fail before flattening even runs."""
    resolved = str(p.resolve())
    if os.name == "nt" and not resolved.startswith(WINDOWS_LONG_PATH_PREFIX):
        return WINDOWS_LONG_PATH_PREFIX + resolved
    return resolved


def flatten_source(
    source_folder: Path, flat_folder: Path, reporter: Reporter, cancel_event: threading.Event | None
) -> dict[str, str]:
    """Copy every file into a flat folder with short sequential names.
    Avoids the Windows 260-character path limit, which breaks Word/Excel/
    PowerPoint COM automation even when Python itself can handle long paths.
    Writes manifest.csv mapping short name back to original path, for
    traceability. Returns a dict of {short_stem: original_path}."""
    flat_folder.mkdir(exist_ok=True)
    manifest_path = flat_folder / "manifest.csv"
    manifest: dict[str, str] = {}

    files = sorted(p for p in source_folder.rglob("*") if p.is_file())
    total = len(files)
    reporter.info(f"Flattening {total} files into short paths to avoid path length errors.")

    with open(manifest_path, "w", newline="", encoding="utf-8") as mf:
        writer = csv.writer(mf)
        writer.writerow(["short_name", "original_path"])

        for i, f in enumerate(files, 1):
            _check_cancelled(cancel_event)
            ext = f.suffix.lower()
            short_stem = f"{i:05d}"
            short_name = f"{short_stem}{ext}"
            dest = flat_folder / short_name
            try:
                shutil.copy2(long_path(f), str(dest))
                writer.writerow([short_name, str(f)])
                manifest[short_stem] = str(f)
            except Exception as e:
                reporter.error(f"Failed to copy {f}: {e}")

    reporter.info(f"Flatten complete. Manifest written to {manifest_path}")
    return manifest


def collect_pdfs(
    source_folder: Path, work_folder: Path, reporter: Reporter, cancel_event: threading.Event | None
) -> tuple[list[tuple[Path, str]], list[str]]:
    """Walk the source folder, convert non-PDFs, and return
    (pdf_paths, skipped_file_names). pdf_paths is a list of
    (pdf_path, short_stem) pairs in order. short_stem is the 5-digit
    flattened file identifier, used later to trace page counts back to
    the original file via the manifest."""
    pdf_paths: list[tuple[Path, str]] = []
    skipped: list[str] = []
    files = sorted(source_folder.rglob("*"))
    files = [f for f in files if f.is_file() and f.name != "manifest.csv"]

    total = len(files)
    reporter.info(f"Found {total} files to process.")

    for i, f in enumerate(files, 1):
        _check_cancelled(cancel_event)
        ext = f.suffix.lower()
        short_stem = f.stem
        reporter.progress(i, total, f"Processing {f.name}")

        if ext == ".pdf":
            pdf_paths.append((f, short_stem))

        elif ext in WORD_EXT | EXCEL_EXT | PPT_EXT:
            out_path = work_folder / f"{short_stem}.pdf"
            reporter.info(f"[{i}/{total}] Converting {f.name}")
            if convert_office_to_pdf(f, out_path, reporter):
                pdf_paths.append((out_path, short_stem))
            else:
                reporter.warning(f"Skipped (conversion failed): {f.name}")
                skipped.append(f.name)

        else:
            reporter.info(f"[{i}/{total}] Skipping unsupported file type: {f.name}")
            skipped.append(f.name)

    return pdf_paths, skipped


def write_page_count_report(
    pdf_paths: list[tuple[Path, str]], manifest: dict[str, str], report_path: Path, reporter: Reporter
):
    """Count pages in each converted/native PDF and write a report sorted
    descending by page count, with the original file name attached, so
    outliers are obvious at a glance."""
    rows = []
    for pdf_path, short_stem in pdf_paths:
        try:
            reader = PdfReader(str(pdf_path))
            page_count = len(reader.pages)
        except Exception as e:
            reporter.error(f"Could not read page count for {pdf_path.name}: {e}")
            page_count = -1

        original = manifest.get(short_stem, "(unknown)")
        rows.append((original, page_count))

    rows.sort(key=lambda r: r[1], reverse=True)

    with open(report_path, "w", newline="", encoding="utf-8") as rf:
        writer = csv.writer(rf)
        writer.writerow(["original_path", "page_count"])
        writer.writerows(rows)

    reporter.info(f"Page count report written to {report_path}")
    reporter.info("Top 10 files by page count:")
    for original, count in rows[:10]:
        reporter.info(f"  {count:>5} pages  -  {original}")


def merge_in_batches(
    pdf_paths: list[tuple[Path, str]],
    work_folder: Path,
    batch_size: int,
    reporter: Reporter,
    cancel_event: threading.Event | None,
) -> list[Path]:
    """Merge PDFs in small batches to keep memory use low. Returns list of batch PDF paths."""
    batch_paths = []
    total_batches = (len(pdf_paths) + batch_size - 1) // batch_size

    for batch_num in range(total_batches):
        _check_cancelled(cancel_event)
        chunk = pdf_paths[batch_num * batch_size: (batch_num + 1) * batch_size]
        batch_out = work_folder / f"batch_{batch_num + 1}.pdf"
        reporter.info(f"Merging batch {batch_num + 1}/{total_batches} ({len(chunk)} files)")
        reporter.progress(batch_num + 1, total_batches, "Merging batches")

        writer = PdfWriter()
        for p, _short_stem in chunk:
            try:
                writer.append(str(p))
            except Exception as e:
                reporter.error(f"Failed to add {p.name} to batch: {e}")

        with open(batch_out, "wb") as f:
            writer.write(f)
        writer.close()

        batch_paths.append(batch_out)
        gc.collect()

    return batch_paths


def final_merge(batch_paths: list[Path], final_output: Path, reporter: Reporter):
    reporter.info(f"Merging {len(batch_paths)} batches into final file.")
    writer = PdfWriter()
    for p in batch_paths:
        try:
            writer.append(str(p))
        except Exception as e:
            reporter.error(f"Failed to add batch {p.name} to final file: {e}")

    with open(final_output, "wb") as f:
        writer.write(f)
    writer.close()
    reporter.info(f"Done. Final file: {final_output}")


def default_work_root(output_path: Path) -> Path:
    """Short, drive-root-adjacent temp location, preserving the original
    script's workaround for the Windows 260-character path limit."""
    drive = output_path.resolve().drive or "C:"
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return Path(f"{drive}\\EdiscoveryCombinerTemp\\{stamp}")


def run_combine(
    source_folder: Path,
    final_output: Path,
    *,
    check_duplicates_only: bool = False,
    work_root: Path | None = None,
    reporter: Reporter | None = None,
    cancel_event: threading.Event | None = None,
    batch_size: int = BATCH_SIZE,
) -> RunResult:
    """Single entry point for the whole pipeline. Raises a CombineError
    subclass on expected failures instead of exiting the process, so
    callers (GUI or CLI) can decide how to present the failure."""
    reporter = reporter or Reporter()
    source_folder = Path(source_folder)
    final_output = Path(final_output)

    if not source_folder.exists():
        raise SourceNotFoundError(f"Source folder does not exist: {source_folder}")

    if not source_folder.is_dir():
        raise SourceNotFoundError(
            f"Source path is not a folder: {source_folder}\n"
            "If your path contains spaces (common with OneDrive folder names), "
            "make sure it's wrapped in double quotes."
        )

    if final_output.exists() and final_output.is_dir():
        raise OutputPathInvalidError(
            f"Output path is a folder, not a file: {final_output}\n"
            "This usually means the path got cut off at a space because it wasn't "
            'quoted. Wrap the FULL output path in double quotes, e.g.\n'
            '"C:/Users/you/OneDrive - Company Name/Documents/final_combined.pdf"'
        )

    if final_output.suffix.lower() != ".pdf":
        reporter.warning(f"Output file doesn't end in .pdf: {final_output}")

    work_root = Path(work_root) if work_root else default_work_root(final_output)
    flat_folder = work_root / "flat"
    work_folder = work_root / "work"

    result = RunResult(work_folder=work_folder)

    if check_duplicates_only:
        work_folder.mkdir(parents=True, exist_ok=True)
        dup_report = work_folder / "duplicate_candidates.csv"
        groups, extra = detect_duplicate_candidates(source_folder, dup_report, reporter)
        result.duplicate_groups = groups
        result.duplicate_extra_files = extra
        result.dup_report_path = dup_report
        reporter.info(
            f"Duplicate check only. Review {dup_report}, clean up the source folder, "
            "then run the full combine."
        )
        return result

    check_office_available()

    for folder in (flat_folder, work_folder):
        if folder.exists():
            reporter.info(f"Clearing previous run's folder: {folder}")
            shutil.rmtree(folder)
        folder.mkdir(parents=True, exist_ok=True)

    dup_report = work_folder / "duplicate_candidates.csv"
    groups, extra = detect_duplicate_candidates(source_folder, dup_report, reporter)
    result.duplicate_groups = groups
    result.duplicate_extra_files = extra
    result.dup_report_path = dup_report

    _check_cancelled(cancel_event)
    manifest = flatten_source(source_folder, flat_folder, reporter, cancel_event)
    result.files_found = len(manifest)

    _check_cancelled(cancel_event)
    pdf_paths, skipped = collect_pdfs(flat_folder, work_folder, reporter, cancel_event)
    result.files_converted = len(pdf_paths)
    result.files_skipped = len(skipped)
    result.skipped_files = skipped

    if not pdf_paths:
        raise NoConvertibleFilesError("No convertible files found. Nothing to merge.")

    page_report = work_folder / "page_count_report.csv"
    write_page_count_report(pdf_paths, manifest, page_report, reporter)
    result.page_report_path = page_report

    _check_cancelled(cancel_event)
    batch_paths = merge_in_batches(pdf_paths, work_folder, batch_size, reporter, cancel_event)

    _check_cancelled(cancel_event)
    final_merge(batch_paths, final_output, reporter)
    result.final_output = final_output

    reporter.info("Cleanup: batch and conversion files are kept in the work folder for reference.")
    reporter.info(f"Review {dup_report} for possible duplicate versions.")
    reporter.info(f"Review {page_report} for the page count breakdown by file.")

    return result
