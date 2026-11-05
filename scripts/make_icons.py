# Draws dumpling Buddy as SVG, renders with macOS QuickLook (qlmanage), and writes the app's PNGs.
# Usage (macOS only, no installs): python3 scripts/make_icons.py assets/images
# The SVGs and raw renders are written next to this script's working copy; delete them after.
# QuickLook flattens onto white, so the one image that needs transparency (Android's monochrome
# themed icon) is rendered on white AND black and its alpha recovered from the difference.
import os, struct, subprocess, sys, zlib

OUT = sys.argv[1]            # assets/images folder
WORK = os.path.join(os.environ.get("TMPDIR", "/tmp"), "buddy-icons")
os.makedirs(WORK, exist_ok=True)
INK, CREAM, LAV, VIOLET = "#2A2238", "#F2EAE0", "#BDA6CE", "#9B8EC7"
BODY = "M80 14 C121 12 149 32 151 62 C153 91 131 108 82 108 C35 108 9 95 9 64 C9 32 39 16 80 14 Z"
SKETCH = "M82 11 C123 13 147 34 149 60 C151 92 128 110 80 106 C37 106 11 93 12 62 C13 33 41 13 82 11 Z"


def buddy(cx, cy, width, *, shadow=True, mono=False, ink=INK):
    """Buddy's <g>, centred at (cx, cy), `width` px wide. Strokes stay ~10px at icon size."""
    s = width / 160
    sw = 3.2  # in Buddy's own 160-wide units
    tx, ty = cx - 80 * s, cy - 60 * s
    body_fill = "none" if mono else "#FFFFFF"
    parts = []
    if shadow and not mono:
        parts.append(f'<path d="{BODY}" fill="{VIOLET}" transform="translate(5 6)"/>')
    parts.append(f'<path d="{BODY}" fill="{body_fill}" stroke="{ink}" stroke-width="{sw}" stroke-linejoin="round"/>')
    parts.append(f'<path d="{SKETCH}" fill="none" stroke="{ink}" stroke-width="{sw * 0.45}" stroke-opacity="{1 if mono else 0.55}"/>')
    parts.append(f'<circle cx="60" cy="58" r="7.5" fill="{ink}"/><circle cx="102" cy="56" r="7.5" fill="{ink}"/>')
    if not mono:
        parts.append('<circle cx="62.6" cy="54.8" r="2.2" fill="#FFFFFF"/><circle cx="104.6" cy="52.8" r="2.2" fill="#FFFFFF"/>')
    parts.append(f'<path d="M73 74 Q81 81 89 73" fill="none" stroke="{ink}" stroke-width="{sw * 0.95}" stroke-linecap="round"/>')
    return f'<g transform="translate({tx:.1f} {ty:.1f}) scale({s:.4f})">{"".join(parts)}</g>'


def svg(w, h, bg, content):
    rect = f'<rect width="{w}" height="{h}" fill="{bg}"/>' if bg else ""
    return f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}">{rect}{content}</svg>'


def render(name, text, size):
    path = os.path.join(WORK, name + ".svg")
    open(path, "w").write(text)
    subprocess.run(["qlmanage", "-t", "-s", str(size), "-o", WORK, path], check=True, capture_output=True)
    return path + ".png"


# ── tiny PNG reader/writer (stdlib only) ─────────────────────────────────────────────
def read_png(path):
    d = open(path, "rb").read()
    w, h, bd, ct = struct.unpack(">IIBB", d[16:26])
    assert bd == 8 and ct in (2, 6), (bd, ct)
    bpp = 4 if ct == 6 else 3
    i, idat = 8, b""
    while i < len(d):
        ln = struct.unpack(">I", d[i:i + 4])[0]
        if d[i + 4:i + 8] == b"IDAT":
            idat += d[i + 8:i + 8 + ln]
        i += 12 + ln
    raw, stride = zlib.decompress(idat), w * bpp
    rows, prev = [], bytearray(stride)
    for y in range(h):
        f = raw[y * (stride + 1)]
        line = bytearray(raw[y * (stride + 1) + 1:(y + 1) * (stride + 1)])
        for x in range(stride):
            a = line[x - bpp] if x >= bpp else 0
            b = prev[x]
            c = prev[x - bpp] if x >= bpp else 0
            if f == 1: line[x] = (line[x] + a) & 255
            elif f == 2: line[x] = (line[x] + b) & 255
            elif f == 3: line[x] = (line[x] + (a + b) // 2) & 255
            elif f == 4:
                p = a + b - c
                pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
                line[x] = (line[x] + (a if pa <= pb and pa <= pc else b if pb <= pc else c)) & 255
        rows.append(line)
        prev = line
    return w, h, bpp, rows


def write_png(path, w, h, rows, rgba):
    raw = b"".join(b"\x00" + bytes(r) for r in rows)
    chunk = lambda t, data: struct.pack(">I", len(data)) + t + data + struct.pack(">I", zlib.crc32(t + data) & 0xffffffff)
    ihdr = struct.pack(">IIBBBBB", w, h, 8, 6 if rgba else 2, 0, 0, 0)
    open(path, "wb").write(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b""))


def opaque(src, dest):
    """Re-save QuickLook's output as plain RGB (drops its useless alpha)."""
    w, h, bpp, rows = read_png(src)
    out = [bytearray(b for x in range(w) for b in r[x * bpp:x * bpp + 3]) for r in rows]
    write_png(dest, w, h, out, rgba=False)
    print("wrote", dest, w, h)


def with_alpha(on_white, on_black, dest):
    """alpha = 1 - (white - black); colour = black / alpha (exact for normal compositing)."""
    w, h, bw, rw = read_png(on_white)
    _, _, bb, rb = read_png(on_black)
    out = []
    for yw, yb in zip(rw, rb):
        line = bytearray()
        for x in range(w):
            pw, pb = yw[x * bw:x * bw + 3], yb[x * bb:x * bb + 3]
            a = 255 - round(sum(pw[i] - pb[i] for i in range(3)) / 3)
            a = max(0, min(255, a))
            col = [0, 0, 0] if a == 0 else [min(255, round(pb[i] * 255 / a)) for i in range(3)]
            line += bytes(col + [a])
        out.append(line)
    write_png(dest, w, h, out, rgba=True)
    print("wrote", dest, w, h, "(with transparency)")


# ── the images ───────────────────────────────────────────────────────────────────────
S = 1024
# App icon (iOS / legacy Android): white Buddy on lavender.
opaque(render("icon", svg(S, S, LAV, buddy(S / 2, S / 2 + 10, 720)), S), os.path.join(OUT, "icon.png"))
# Android adaptive icon: Buddy inside the centre safe zone (66%), on lavender; background plain lavender.
opaque(render("fg", svg(S, S, LAV, buddy(S / 2, S / 2 + 8, 560)), S), os.path.join(OUT, "android-icon-foreground.png"))
opaque(render("bg", svg(S, S, LAV, ""), S), os.path.join(OUT, "android-icon-background.png"))
# Android 13+ themed icon: line-art Buddy, transparent everywhere else.
mono = lambda bg, ink: svg(S, S, bg, buddy(S / 2, S / 2 + 8, 560, mono=True, ink=ink))
with_alpha(render("mono_w", mono("#FFFFFF", "#000000"), S), render("mono_b", mono("#000000", "#000000").replace(
    '<rect width="1024" height="1024" fill="#000000"/>', '<rect width="1024" height="1024" fill="#000000"/>'), S),
    os.path.join(OUT, "android-icon-monochrome.png"))
# Splash: Buddy on the splash screen's own cream, so the square blends in.
opaque(render("splash", svg(800, 800, CREAM, buddy(400, 400, 600)), 800), os.path.join(OUT, "splash-icon.png"))
# Favicon (web).
opaque(render("favicon", svg(256, 256, LAV, buddy(128, 132, 200, shadow=False)), 48), os.path.join(OUT, "favicon.png"))
