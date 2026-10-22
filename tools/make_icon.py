"""Generate assets/icon.png and assets/icon.ico without external dependencies.

Run from anywhere with:

    python tools/make_icon.py
"""

import struct
import zlib
from pathlib import Path

SIZE = 256
SS = 4  # supersampling factor
BIG = SIZE * SS

ROOT = Path(__file__).resolve().parent.parent


def rounded_rect_contains(x, y, x0, y0, x1, y1, radius):
    if x < x0 or x > x1 or y < y0 or y > y1:
        return False
    cx = min(max(x, x0 + radius), x1 - radius)
    cy = min(max(y, y0 + radius), y1 - radius)
    return (x - cx) ** 2 + (y - cy) ** 2 <= radius ** 2


def blend(img, x, y, color, alpha=1.0):
    if alpha <= 0:
        return
    i = (y * BIG + x) * 4
    sr, sg, sb = color
    da = img[i + 3] / 255.0
    out_a = alpha + da * (1 - alpha)
    if out_a <= 0:
        return
    for j, sc in enumerate((sr, sg, sb)):
        dc = img[i + j]
        img[i + j] = int(round((sc * alpha + dc * da * (1 - alpha)) / out_a))
    img[i + 3] = int(round(out_a * 255))


def lerp(a, b, t):
    return tuple(int(round(a[k] + (b[k] - a[k]) * t)) for k in range(3))


# ── Render at BIG resolution ───────────────────────────────────────

img = bytearray(BIG * BIG * 4)

# Rounded square background with a subtle border and vertical gradient.
margin = 6 * SS
radius = 52 * SS
top = (48, 48, 54)
bottom = (18, 18, 22)
border = (74, 74, 84)

for y in range(BIG):
    for x in range(BIG):
        if rounded_rect_contains(
            x + 0.5, y + 0.5, margin, margin, BIG - margin, BIG - margin, radius
        ):
            blend(img, x, y, lerp(top, bottom, y / BIG))

border_width = 2.2 * SS
for y in range(BIG):
    for x in range(BIG):
        px, py = x + 0.5, y + 0.5
        if rounded_rect_contains(
            px, py, margin, margin, BIG - margin, BIG - margin, radius
        ):
            if not rounded_rect_contains(
                px,
                py,
                margin + border_width,
                margin + border_width,
                BIG - margin - border_width,
                BIG - margin - border_width,
                radius - border_width,
            ):
                blend(img, x, y, border)

# Soft shadow behind the red circle.
shadow_cx, shadow_cy, shadow_r = 128 * SS, 122 * SS, 79 * SS
for y in range(int(shadow_cy - shadow_r), int(shadow_cy + shadow_r) + 1):
    for x in range(int(shadow_cx - shadow_r), int(shadow_cx + shadow_r) + 1):
        if 0 <= x < BIG and 0 <= y < BIG:
            if (
                (x + 0.5 - shadow_cx) ** 2 + (y + 0.5 - shadow_cy) ** 2
                <= shadow_r ** 2
            ):
                blend(img, x, y, (0, 0, 0), 0.30)

# Red circle with a vertical gradient.
cx, cy, r = 128 * SS, 116 * SS, 74 * SS
red_top = (255, 59, 78)
red_bottom = (194, 0, 28)
for y in range(int(cy - r), int(cy + r) + 1):
    for x in range(int(cx - r), int(cx + r) + 1):
        if (x + 0.5 - cx) ** 2 + (y + 0.5 - cy) ** 2 <= r ** 2:
            t = (y - (cy - r)) / (2 * r)
            blend(img, x, y, lerp(red_top, red_bottom, t))

white = (255, 255, 255)


def fill_rect(x0, y0, x1, y1, color):
    for y in range(int(y0), int(y1) + 1):
        for x in range(int(x0), int(x1) + 1):
            if 0 <= x < BIG and 0 <= y < BIG:
                blend(img, x, y, color)


def fill_triangle(p0, p1, p2, color):
    xs = [p[0] for p in (p0, p1, p2)]
    ys = [p[1] for p in (p0, p1, p2)]
    x_min, x_max = int(min(xs)), int(max(xs)) + 1
    y_min, y_max = int(min(ys)), int(max(ys)) + 1

    def sign(ax, ay, bx, by, px, py):
        return (px - bx) * (ay - by) - (ax - bx) * (py - by)

    for y in range(max(y_min, 0), min(y_max, BIG)):
        for x in range(max(x_min, 0), min(x_max, BIG)):
            px, py = x + 0.5, y + 0.5
            d1 = sign(px, py, p0[0], p0[1], p1[0], p1[1])
            d2 = sign(px, py, p1[0], p1[1], p2[0], p2[1])
            d3 = sign(px, py, p2[0], p2[1], p0[0], p0[1])
            has_neg = d1 < 0 or d2 < 0 or d3 < 0
            has_pos = d1 > 0 or d2 > 0 or d3 > 0
            if not (has_neg and has_pos):
                blend(img, x, y, color)


# Download arrow: shaft + head.
fill_rect(115 * SS, 62 * SS, 141 * SS, 116 * SS, white)
fill_triangle(
    (128 * SS, 160 * SS),
    (86 * SS, 104 * SS),
    (170 * SS, 104 * SS),
    white,
)

# Tray bar under the arrow.
fill_rect(94 * SS, 174 * SS, 162 * SS, 186 * SS, white)


# ── Downsample with premultiplied alpha ────────────────────────────


def downsample(target):
    scale = BIG // target
    out = bytearray(target * target * 4)
    block = scale * scale
    for oy in range(target):
        for ox in range(target):
            r_sum = g_sum = b_sum = a_sum = 0
            for sy in range(oy * scale, (oy + 1) * scale):
                row = sy * BIG
                for sx in range(ox * scale, (ox + 1) * scale):
                    i = (row + sx) * 4
                    a = img[i + 3]
                    r_sum += img[i] * a
                    g_sum += img[i + 1] * a
                    b_sum += img[i + 2] * a
                    a_sum += a
            o = (oy * target + ox) * 4
            if a_sum:
                out[o] = int(round(r_sum / a_sum))
                out[o + 1] = int(round(g_sum / a_sum))
                out[o + 2] = int(round(b_sum / a_sum))
                out[o + 3] = int(round(a_sum / block))
            else:
                out[o + 3] = 0
    return bytes(out)


def png_bytes(width, height, rgba):
    raw = bytearray()
    stride = width * 4
    for y in range(height):
        raw.append(0)
        raw.extend(rgba[y * stride:(y + 1) * stride])

    def chunk(kind, data):
        return (
            struct.pack(">I", len(data))
            + kind
            + data
            + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)
        )

    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(bytes(raw), 9))
        + chunk(b"IEND", b"")
    )


def dib_bytes(width, height, rgba):
    """32-bit bottom-up DIB + AND mask, the classic ICO image format."""
    header = struct.pack(
        "<IiiHHIIiiII",
        40,  # biSize
        width,
        height * 2,  # XOR + AND masks
        1,  # biPlanes
        32,  # biBitCount
        0,  # BI_RGB
        width * height * 4,
        0,
        0,
        0,
        0,
    )
    rows = []
    for y in range(height - 1, -1, -1):
        row = bytearray()
        for x in range(width):
            i = (y * width + x) * 4
            r, g, b, a = rgba[i:i + 4]
            row.extend((b, g, r, a))
        rows.append(bytes(row))
    xor = b"".join(rows)
    mask_stride = ((width + 31) // 32) * 4
    mask = b"\x00" * (mask_stride * height)
    return header + xor + mask


assets = ROOT / "assets"
assets.mkdir(parents=True, exist_ok=True)
sizes = [16, 24, 32, 48, 64, 128, 256]
images = {size: downsample(size) for size in sizes}
(assets / "icon.png").write_bytes(png_bytes(256, 256, images[256]))

# ICO directory must contain every entry first, followed by the image data.
entries = []
blobs = []
offset = 6 + 16 * len(sizes)
for size in sizes:
    blob = dib_bytes(size, size, images[size])
    dim = 0 if size == 256 else size
    entries.append(
        struct.pack("<BBBBHHII", dim, dim, 0, 0, 1, 32, len(blob), offset)
    )
    blobs.append(blob)
    offset += len(blob)

ico = (
    struct.pack("<HHH", 0, 1, len(sizes))
    + b"".join(entries)
    + b"".join(blobs)
)
(assets / "icon.ico").write_bytes(ico)
print(f"Wrote {assets / 'icon.png'} and {assets / 'icon.ico'}")
