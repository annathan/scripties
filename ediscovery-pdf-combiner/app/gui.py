r"""
Desktop GUI for the eDiscovery PDF combiner - the actual "product".

Packaged with PyInstaller (see build/pdf_combiner.spec) into a single
.exe that a non-technical reviewer can double-click. No Python install
required on their machine; Microsoft Office IS required, since Word/
Excel/PowerPoint conversion goes through Office COM automation.

This module intentionally has no business logic in it - everything it
calls lives in app/core.py, which is unit-testable without a GUI.
"""

from __future__ import annotations

import os
import queue
import threading
import tkinter as tk
from datetime import date
from pathlib import Path
from tkinter import filedialog, messagebox, scrolledtext, ttk

from app.core import (
    CombineError,
    Cancelled,
    Reporter,
    RunResult,
    run_combine,
)

APP_TITLE = "eDiscovery PDF Combiner"


def _default_output_path(source_folder: str) -> str:
    name = Path(source_folder).name or "export"
    stamp = date.today().strftime("%Y%m%d")
    desktop = Path.home() / "Desktop"
    base = desktop if desktop.exists() else Path.home()
    return str(base / f"Combined_{name}_{stamp}.pdf")


class CombinerApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title(APP_TITLE)
        self.root.geometry("720x520")
        self.root.minsize(640, 480)

        self._events: queue.Queue = queue.Queue()
        self._cancel_event: threading.Event | None = None
        self._worker: threading.Thread | None = None

        self.source_var = tk.StringVar()
        self.output_var = tk.StringVar()
        self.status_var = tk.StringVar(value="Choose a source folder to begin.")

        self._build_widgets()
        self.root.after(100, self._drain_events)

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_widgets(self) -> None:
        pad = {"padx": 10, "pady": 6}

        intro = tk.Label(
            self.root,
            text=(
                "Combine an eDiscovery export folder into a single PDF.\n"
                "Point this at your OneDrive or SharePoint folder as it appears in "
                "File Explorer on this PC (it must already be synced - look for the "
                "green checkmark)."
            ),
            justify="left",
            wraplength=680,
        )
        intro.pack(fill="x", **pad)

        src_frame = tk.Frame(self.root)
        src_frame.pack(fill="x", **pad)
        tk.Label(src_frame, text="Source folder:", width=14, anchor="w").pack(side="left")
        tk.Entry(src_frame, textvariable=self.source_var).pack(side="left", fill="x", expand=True, padx=(0, 6))
        tk.Button(src_frame, text="Browse...", command=self._browse_source).pack(side="left")

        out_frame = tk.Frame(self.root)
        out_frame.pack(fill="x", **pad)
        tk.Label(out_frame, text="Output PDF:", width=14, anchor="w").pack(side="left")
        tk.Entry(out_frame, textvariable=self.output_var).pack(side="left", fill="x", expand=True, padx=(0, 6))
        tk.Button(out_frame, text="Browse...", command=self._browse_output).pack(side="left")

        btn_frame = tk.Frame(self.root)
        btn_frame.pack(fill="x", **pad)
        self.dup_btn = tk.Button(btn_frame, text="Check for duplicate versions", command=self._start_duplicate_check)
        self.dup_btn.pack(side="left")
        self.combine_btn = tk.Button(
            btn_frame, text="Combine into one PDF", command=self._start_combine, bg="#2e7d32", fg="white"
        )
        self.combine_btn.pack(side="left", padx=(8, 0))
        self.cancel_btn = tk.Button(btn_frame, text="Cancel", command=self._cancel, state="disabled")
        self.cancel_btn.pack(side="left", padx=(8, 0))

        self.progress = ttk.Progressbar(self.root, mode="determinate")
        self.progress.pack(fill="x", **pad)

        tk.Label(self.root, textvariable=self.status_var, anchor="w").pack(fill="x", padx=10)

        log_frame = tk.Frame(self.root)
        log_frame.pack(fill="both", expand=True, **pad)
        self.log_text = scrolledtext.ScrolledText(log_frame, height=14, state="disabled", wrap="word")
        self.log_text.pack(fill="both", expand=True)

    # ------------------------------------------------------------------
    # Field helpers
    # ------------------------------------------------------------------

    def _browse_source(self) -> None:
        folder = filedialog.askdirectory(title="Choose the eDiscovery export folder")
        if folder:
            self.source_var.set(folder)
            if not self.output_var.get():
                self.output_var.set(_default_output_path(folder))

    def _browse_output(self) -> None:
        initial = self.output_var.get() or _default_output_path(self.source_var.get() or "export")
        path = filedialog.asksaveasfilename(
            title="Save combined PDF as",
            defaultextension=".pdf",
            filetypes=[("PDF files", "*.pdf")],
            initialfile=Path(initial).name,
            initialdir=str(Path(initial).parent),
        )
        if path:
            self.output_var.set(path)

    # ------------------------------------------------------------------
    # Run orchestration
    # ------------------------------------------------------------------

    def _validate_inputs(self) -> tuple[Path, Path] | None:
        source = self.source_var.get().strip()
        output = self.output_var.get().strip()
        if not source:
            messagebox.showerror(APP_TITLE, "Choose a source folder first.")
            return None
        if not output:
            output = _default_output_path(source)
            self.output_var.set(output)
        return Path(source), Path(output)

    def _set_running(self, running: bool) -> None:
        state = "disabled" if running else "normal"
        self.dup_btn.config(state=state)
        self.combine_btn.config(state=state)
        self.cancel_btn.config(state=("normal" if running else "disabled"))

    def _start_duplicate_check(self) -> None:
        paths = self._validate_inputs()
        if not paths:
            return
        source, output = paths
        self._run_in_background(source, output, check_duplicates_only=True)

    def _start_combine(self) -> None:
        paths = self._validate_inputs()
        if not paths:
            return
        source, output = paths
        if output.exists():
            if not messagebox.askyesno(APP_TITLE, f"{output.name} already exists. Overwrite it?"):
                return
        self._run_in_background(source, output, check_duplicates_only=False)

    def _run_in_background(self, source: Path, output: Path, *, check_duplicates_only: bool) -> None:
        self._cancel_event = threading.Event()
        self._set_running(True)
        self.progress.config(value=0, maximum=100)
        self._clear_log()
        self.status_var.set("Working...")

        def progress_cb(current, total, message):
            self._events.put(("progress", current, total, message))

        def log_cb(level, message):
            self._events.put(("log", level, message))

        def worker():
            # COM objects are being created on this thread, not the main
            # thread, so it must initialize its own COM apartment.
            try:
                import pythoncom

                pythoncom.CoInitialize()
            except ImportError:
                pythoncom = None

            reporter = Reporter(progress_cb=progress_cb, log_cb=log_cb)
            try:
                result = run_combine(
                    source,
                    output,
                    check_duplicates_only=check_duplicates_only,
                    reporter=reporter,
                    cancel_event=self._cancel_event,
                )
                self._events.put(("done", result, check_duplicates_only))
            except Cancelled:
                self._events.put(("cancelled", None, None))
            except CombineError as e:
                self._events.put(("error", str(e), None))
            except Exception as e:  # noqa: BLE001 - surfaced to the user, not swallowed
                self._events.put(("crash", str(e), None))
            finally:
                if pythoncom is not None:
                    pythoncom.CoUninitialize()

        self._worker = threading.Thread(target=worker, daemon=True)
        self._worker.start()

    def _cancel(self) -> None:
        if self._cancel_event is not None:
            self._cancel_event.set()
            self.status_var.set("Cancelling...")

    # ------------------------------------------------------------------
    # Event pump (background thread -> UI thread)
    # ------------------------------------------------------------------

    def _drain_events(self) -> None:
        try:
            while True:
                event = self._events.get_nowait()
                kind = event[0]
                if kind == "progress":
                    _, current, total, message = event
                    self.progress.config(maximum=max(total, 1), value=current)
                    self.status_var.set(message or f"{current}/{total}")
                elif kind == "log":
                    _, level, message = event
                    self._append_log(f"[{level.upper()}] {message}")
                elif kind == "done":
                    _, result, was_dup_check = event
                    self._on_done(result, was_dup_check)
                elif kind == "cancelled":
                    self._set_running(False)
                    self.status_var.set("Cancelled.")
                    messagebox.showinfo(APP_TITLE, "Run cancelled.")
                elif kind == "error":
                    _, message, _ = event
                    self._set_running(False)
                    self.status_var.set("Failed.")
                    messagebox.showerror(APP_TITLE, message)
                elif kind == "crash":
                    _, message, _ = event
                    self._set_running(False)
                    self.status_var.set("Something went wrong.")
                    messagebox.showerror(
                        APP_TITLE,
                        "Something unexpected went wrong.\n\n"
                        f"{message}\n\n"
                        "See combine_log.txt next to this program for details.",
                    )
        except queue.Empty:
            pass
        self.root.after(100, self._drain_events)

    def _on_done(self, result: RunResult, was_dup_check: bool) -> None:
        self._set_running(False)
        self.progress.config(value=self.progress["maximum"])

        if was_dup_check:
            self.status_var.set("Duplicate check complete.")
            if result.duplicate_groups:
                msg = (
                    f"Found {result.duplicate_groups} groups of possibly duplicate files "
                    f"({result.duplicate_extra_files} extra files). Nothing was changed.\n\n"
                    f"Report: {result.dup_report_path}"
                )
            else:
                msg = "No likely duplicate/version files found by name. Nothing was changed."
            if messagebox.askyesno(APP_TITLE, msg + "\n\nOpen the report now?"):
                self._open_path(result.dup_report_path)
            return

        self.status_var.set("Done.")
        summary = (
            f"Combined PDF created:\n{result.final_output}\n\n"
            f"Files converted: {result.files_converted}\n"
            f"Files skipped: {result.files_skipped}"
        )
        if messagebox.askyesno(APP_TITLE, summary + "\n\nOpen the PDF now?"):
            self._open_path(result.final_output)

    @staticmethod
    def _open_path(path: Path | None) -> None:
        if path is None:
            return
        try:
            os.startfile(str(path))  # type: ignore[attr-defined]
        except AttributeError:
            pass  # non-Windows dev environment; nothing to do

    # ------------------------------------------------------------------
    # Log pane helpers
    # ------------------------------------------------------------------

    def _clear_log(self) -> None:
        self.log_text.config(state="normal")
        self.log_text.delete("1.0", tk.END)
        self.log_text.config(state="disabled")

    def _append_log(self, line: str) -> None:
        self.log_text.config(state="normal")
        self.log_text.insert(tk.END, line + "\n")
        self.log_text.see(tk.END)
        self.log_text.config(state="disabled")


def main() -> None:
    root = tk.Tk()
    CombinerApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
