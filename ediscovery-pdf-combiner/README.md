# eDiscovery PDF Combiner

Combines a folder of eDiscovery export files (e.g. from a Microsoft Purview
eDiscovery search) — Word, Excel, PowerPoint, and PDF — into a single PDF.
Converts Office files to PDF using Microsoft Office itself, flags likely
duplicate/version files by filename before converting anything, and merges
everything in memory-safe batches.

This folder contains both the double-clickable desktop app (the actual
product, for non-technical reviewers) and the underlying Python code
(for whoever maintains it).

## For reviewers (no technical setup needed)

**Before you start:**

1. **Microsoft Office must be installed** on this PC (Word, Excel, PowerPoint) —
   it's used to convert those files to PDF.
2. **The source folder must already be synced to this PC.** If you access the
   eDiscovery export through OneDrive or SharePoint, open it in the OneDrive
   app or File Explorer first and confirm you see a green checkmark or a
   solid cloud icon (not just a browser tab) — that means it's actually on
   this computer, not just online. If you only see the files in a web
   browser, sync the folder first (right-click it on the SharePoint/OneDrive
   web page → **Sync**), wait for it to finish downloading, then continue.

**Using the tool:**

1. Download `eDiscovery PDF Combiner.exe` from the project's Releases page
   (a link will be shared with you) and double-click it. No installation
   step — it just runs.
2. Click **Browse...** next to *Source folder* and pick the synced export
   folder.
3. (Optional but recommended) Click **Check for duplicate versions** first.
   This scans filenames for things like `Report V2.docx` / `Report Final.docx`
   and writes a report — it does **not** delete or change anything. Review
   the report and remove any extra versions from the source folder yourself
   if you want them excluded, then continue.
4. Click **Combine into one PDF**. A progress bar and log will show what's
   happening. This can take a while for large exports — Office has to open
   and convert every Word/Excel/PowerPoint file one at a time.
5. When it finishes, you'll be offered a button to open the combined PDF
   directly.

**Where things go:**

- The combined PDF is saved wherever you chose (defaults to your Desktop).
- Two report CSVs (duplicate candidates, page counts per file) and a working
  copy of the converted files are kept in a folder under
  `<same drive as your output file>\EdiscoveryCombinerTemp\<timestamp>` for
  traceability — safe to delete once you've confirmed the combined PDF looks
  right.
- A log file (`combine_log.txt`) is written next to the program if something
  needs troubleshooting.

**If something goes wrong:** the app shows a plain-language message for
common problems (Office not installed, output file already open elsewhere,
empty source folder). For anything else, check `combine_log.txt` and pass it
along to whoever maintains this tool.

## For maintainers

### Project layout

```
app/
  core.py   pure pipeline logic (no UI) - conversion, dedup detection, batching/merging
  cli.py    thin terminal wrapper around core.py, for command-line use
  gui.py    Tkinter desktop app - the packaged product's entry point
build/
  pdf_combiner.spec   PyInstaller spec used to build the .exe
tests/
  test_core.py        unit tests for the logic that doesn't need Windows/Office
.github/workflows/build-windows-exe.yml   builds + releases the .exe (repo root)
```

### Running from source

```
pip install -r requirements.txt
python -m app.gui                     # desktop app
python -m app.cli SOURCE_FOLDER OUT.pdf [--check-duplicates-only]   # terminal
```

`app.core.check_office_available()` and `convert_office_to_pdf()` require
Windows with Microsoft Office installed and `pywin32`. On any other platform
you can still run the tests and the duplicate-check path, but full conversion
will fail.

### Running tests

```
pip install -r requirements.txt pytest
pytest tests/
```

These tests cover filename normalization/dedup grouping and PDF batching/
merging (using blank in-memory PDFs), and run fine without Windows or Office.
`convert_office_to_pdf` and the GUI itself are **not** covered by automated
tests — they need real Office COM automation and a display. Treat a build
from a fresh Windows+Office VM as the manual QA step before shipping a new
`.exe` to reviewers: run a real export folder through both the duplicate
check and the full combine, and confirm the resulting PDF opens and looks
right.

### Building the .exe locally

On a Windows machine with Office installed (for testing) or any Windows
machine (for just building):

```
pip install -r requirements.txt pyinstaller
pyinstaller build/pdf_combiner.spec
```

The output is `dist/eDiscovery PDF Combiner.exe`.

### Releasing

The GitHub Actions workflow (`.github/workflows/build-windows-exe.yml`)
builds the `.exe` on every push that touches this folder and uploads it as a
build artifact. To publish a version reviewers can download from the
Releases page, push a tag matching `ediscovery-pdf-combiner-v*`, e.g.:

```
git tag ediscovery-pdf-combiner-v1.0.0
git push origin ediscovery-pdf-combiner-v1.0.0
```

The workflow will attach the built `.exe` to the corresponding GitHub
Release automatically.
