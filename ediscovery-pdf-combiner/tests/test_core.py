"""
Unit tests for the pure logic in app/core.py: filename normalization,
duplicate-candidate grouping, and PDF batching/merging.

Deliberately excludes convert_office_to_pdf and app/gui.py - those need
real Windows + Microsoft Office and a display, which this sandbox and CI
runner don't (reliably) have. See README.md for manual QA steps covering
those paths.

Run: pytest tests/ -v
"""
import sys
from pathlib import Path

import pytest
from pypdf import PdfWriter, PdfReader

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.core import (
    Reporter,
    detect_duplicate_candidates,
    final_merge,
    merge_in_batches,
    normalize_name,
)


# ─── normalize_name ─────────────────────────────────────────────────────────

class TestNormalizeName:
    @pytest.mark.parametrize("filename,expected", [
        ("Annual Report.docx", "annual report"),
        ("Annual Report V2.docx", "annual report"),
        ("Annual Report_v2.1.docx", "annual report"),
        ("Annual Report_v3.2_1.docx", "annual report"),
        ("Annual Report Final.docx", "annual report"),
        ("Annual Report - Final Draft.docx", "annual report"),
        ("Annual Report (2).pdf", "annual report"),
        ("Annual Report_2.pdf", "annual report"),
        ("Annual Report-2.pdf", "annual report"),
        ("Annual Report Redline.docx", "annual report"),
        ("Annual Report Tracked Changes.docx", "annual report"),
        ("annual_report.pdf", "annual report"),
    ])
    def test_variants_collapse_to_same_key(self, filename, expected):
        assert normalize_name(filename) == expected

    def test_unrelated_files_produce_different_keys(self):
        assert normalize_name("Annual Report.docx") != normalize_name("Board Minutes.docx")


# ─── detect_duplicate_candidates ────────────────────────────────────────────

class TestDetectDuplicateCandidates:
    def test_groups_likely_duplicates(self, tmp_path):
        (tmp_path / "Annual Report.docx").write_text("a")
        (tmp_path / "Annual Report V2.docx").write_text("b")
        (tmp_path / "Annual Report Final.pdf").write_text("c")
        (tmp_path / "Board Minutes.pdf").write_text("d")

        report = tmp_path / "dup_report.csv"
        groups, extra = detect_duplicate_candidates(tmp_path, report, Reporter())

        assert groups == 1
        assert extra == 2
        assert report.exists()
        contents = report.read_text()
        assert "Annual Report.docx" in contents
        assert "Board Minutes.pdf" not in contents

    def test_no_duplicates_writes_header_only(self, tmp_path):
        (tmp_path / "Annual Report.docx").write_text("a")
        (tmp_path / "Board Minutes.pdf").write_text("b")

        report = tmp_path / "dup_report.csv"
        groups, extra = detect_duplicate_candidates(tmp_path, report, Reporter())

        assert groups == 0
        assert extra == 0
        lines = report.read_text().strip().splitlines()
        assert len(lines) == 1  # header only


# ─── merge_in_batches / final_merge ─────────────────────────────────────────

def _make_pdf(path: Path, num_pages: int) -> None:
    writer = PdfWriter()
    for _ in range(num_pages):
        writer.add_blank_page(width=200, height=200)
    with open(path, "wb") as f:
        writer.write(f)
    writer.close()


class TestMergeInBatches:
    def test_batches_split_correctly_and_preserve_order(self, tmp_path):
        pdf_paths = []
        for i in range(5):
            p = tmp_path / f"{i:05d}.pdf"
            _make_pdf(p, num_pages=i + 1)  # 1,2,3,4,5 pages
            pdf_paths.append((p, f"{i:05d}"))

        work_folder = tmp_path / "work"
        work_folder.mkdir()

        batch_paths = merge_in_batches(pdf_paths, work_folder, batch_size=2, reporter=Reporter(), cancel_event=None)

        assert len(batch_paths) == 3  # ceil(5/2)
        assert len(PdfReader(str(batch_paths[0])).pages) == 1 + 2  # files 0,1
        assert len(PdfReader(str(batch_paths[1])).pages) == 3 + 4  # files 2,3
        assert len(PdfReader(str(batch_paths[2])).pages) == 5      # file 4

    def test_final_merge_combines_all_batches_in_order(self, tmp_path):
        batch1 = tmp_path / "batch_1.pdf"
        batch2 = tmp_path / "batch_2.pdf"
        _make_pdf(batch1, num_pages=2)
        _make_pdf(batch2, num_pages=3)

        final_output = tmp_path / "final.pdf"
        final_merge([batch1, batch2], final_output, Reporter())

        assert len(PdfReader(str(final_output)).pages) == 5
