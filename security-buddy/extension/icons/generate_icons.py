"""
Generate Safety Buddy shield icons (buddy-16.png, buddy-48.png, buddy-128.png).
No external dependencies — uses only Python stdlib (struct + zlib).

Run once from this directory:
    python generate_icons.py
"""
import os
import struct
import zlib


def _make_png(width: int, height: int, pixels: list[tuple[int, int, int, int]]) -> bytes:
    """Encode a list of RGBA tuples as a valid PNG byte string."""
    def chunk(tag: bytes, data: bytes) -> bytes:
        crc = zlib.crc32(tag + data) & 0xFFFFFFFF
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", crc)

    ihdr = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)
    raw = b""
    for y in range(height):
        raw += b"\x00"  # filter: None
        for x in range(width):
            r, g, b, a = pixels[y * width + x]
            raw += bytes([r, g, b, a])

    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", ihdr)
        + chunk(b"IDAT", zlib.compress(raw, 9))
        + chunk(b"IEND", b"")
    )


def _draw_shield(size: int) -> list[tuple[int, int, int, int]]:
    """Return RGBA pixels for a shield shape on a transparent background."""
    BLUE = (21, 101, 192, 255)   # #1565c0
    WHITE = (255, 255, 255, 255)
    TRANSPARENT = (0, 0, 0, 0)

    half = size / 2
    radius = size * 0.42          # circular top radius
    pixels: list[tuple[int, int, int, int]] = []

    for y in range(size):
        for x in range(size):
            cx = x - half + 0.5   # offset to centre
            cy = y - half + 0.5

            # Shield shape: semicircle on top, tapered to a point at bottom.
            if cy <= 0:
                inside = (cx * cx + cy * cy) <= radius * radius
            else:
                # Width tapers linearly from radius at the equator to 0 at the bottom.
                taper = max(0.0, 1.0 - cy / half)
                inside = abs(cx) <= radius * taper

            if not inside:
                pixels.append(TRANSPARENT)
                continue

            # White checkmark in the lower-centre of the shield (skip for 16 px).
            if size >= 48:
                nx = (x + 0.5) / size   # normalised 0..1
                ny = (y + 0.5) / size

                stroke = max(0.05, 5 / size)

                # Left leg: (0.28, 0.60) → (0.44, 0.75)
                # Right leg: (0.44, 0.75) → (0.72, 0.38)
                def seg_dist(px, py, x1, y1, x2, y2):
                    dx, dy = x2 - x1, y2 - y1
                    if dx == 0 and dy == 0:
                        return ((px - x1) ** 2 + (py - y1) ** 2) ** 0.5
                    t = max(0.0, min(1.0, ((px - x1) * dx + (py - y1) * dy) / (dx * dx + dy * dy)))
                    return ((px - x1 - t * dx) ** 2 + (py - y1 - t * dy) ** 2) ** 0.5

                d1 = seg_dist(nx, ny, 0.28, 0.60, 0.44, 0.74)
                d2 = seg_dist(nx, ny, 0.44, 0.74, 0.72, 0.38)
                pixels.append(WHITE if (d1 < stroke or d2 < stroke) else BLUE)
            else:
                pixels.append(BLUE)

    return pixels


def main():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    for size in (16, 48, 128):
        pixels = _draw_shield(size)
        png = _make_png(size, size, pixels)
        path = os.path.join(script_dir, f"buddy-{size}.png")
        with open(path, "wb") as fh:
            fh.write(png)
        print(f"  {path}  ({size}×{size}, {len(png)} bytes)")


if __name__ == "__main__":
    main()
