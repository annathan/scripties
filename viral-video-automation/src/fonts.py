"""Best-effort discovery of a real system font file.

ffmpeg's drawtext and subtitles filters fall back to fontconfig's
default-font lookup when no font is given explicitly -- and on plenty of
Windows ffmpeg builds (including the common gyan.dev "full build"),
fontconfig isn't preconfigured, so that lookup crashes with "Fontconfig
error: Cannot load default config file". Passing a font file directly
bypasses fontconfig entirely, on every OS.
"""
from __future__ import annotations

import platform
from pathlib import Path

# (path, family name) -- family name is what libass/force_style needs to
# reference the font by name (drawtext's fontfile= doesn't need it).
_CANDIDATES: dict[str, list[tuple[str, str]]] = {
    "Windows": [
        (r"C:\Windows\Fonts\arial.ttf", "Arial"),
        (r"C:\Windows\Fonts\segoeui.ttf", "Segoe UI"),
    ],
    "Darwin": [
        ("/System/Library/Fonts/Supplemental/Arial.ttf", "Arial"),
        ("/System/Library/Fonts/Helvetica.ttc", "Helvetica"),
    ],
    "Linux": [
        ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", "DejaVu Sans"),
        ("/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf", "Liberation Sans"),
        ("/usr/share/fonts/truetype/noto/NotoSans-Regular.ttf", "Noto Sans"),
    ],
}


def find_font() -> tuple[Path, str] | None:
    """Returns (font_file_path, family_name) for the first candidate that
    actually exists on this machine, or None if none of them do (rare --
    falls back to the old fontconfig-dependent behavior, which may or may
    not work depending on the system)."""
    for path, family in _CANDIDATES.get(platform.system(), []):
        p = Path(path)
        if p.exists():
            return p, family
    return None


def ffmpeg_escape_path(path: Path) -> str:
    """Escape a filesystem path for safe use inside an ffmpeg filtergraph
    string -- backslashes and colons are filtergraph syntax and need
    escaping, which matters most for Windows paths like C:\\Windows\\Fonts."""
    return str(path).replace("\\", "/").replace(":", r"\:")
