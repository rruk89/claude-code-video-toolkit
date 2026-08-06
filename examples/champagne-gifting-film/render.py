#!/usr/bin/env python3
"""
"The Gift of Champagne" — a minimal, high-end gifting film with voiceover
for Drinks House 247.

Deliberately quiet: warm ivory ground, thin antique-gold hairlines,
classical serif, generous negative space, slow eased motion. No bubbles,
no glows, no bold fills.

Fully local pipeline: Piper TTS per scene, scene lengths auto-fit the
narration, PIL frames + master audio muxed by a bundled FFmpeg.

    pip install imageio-ffmpeg numpy pillow piper-tts
    PIPER_MODEL=/path/to/en-us-ryan-high.onnx python render.py

Output: output/champagne-gifting-film.mp4  (1080x1920, 30fps, VO-timed)
"""

import math
import os
import subprocess
import wave

import imageio_ffmpeg
import numpy as np
from PIL import Image, ImageDraw, ImageFont

# ---- Config -----------------------------------------------------------------
W, H = 1080, 1920
FPS = 30
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "output", "champagne-gifting-film.mp4")
VO_DIR = os.path.join(HERE, "output", "vo")
MODEL = os.environ.get("PIPER_MODEL", os.path.join(HERE, "en-us-ryan-high.onnx"))
SR = 22050

# Warm ivory ground, antique gold, deep ink — no pure black, no pure white.
BG_TOP = (247, 244, 237)
BG_BOTTOM = (238, 232, 221)
INK = (31, 29, 26)
GOLD = (176, 141, 63)
GOLD_SOFT = (198, 172, 116)
MUTED = (138, 131, 118)
HAIR = (206, 197, 182)

FONT_DIR = "/usr/share/fonts/truetype"


def font(path, size):
    return ImageFont.truetype(os.path.join(FONT_DIR, path), size)


# Classical serif for statements; sans for letterspaced small-caps labels.
F_STATEMENT = font("liberation/LiberationSerif-Regular.ttf", 92)
F_STATEMENT_I = font("liberation/LiberationSerif-Italic.ttf", 92)
F_BIG = font("liberation/LiberationSerif-Regular.ttf", 128)
F_NAME = font("liberation/LiberationSerif-Regular.ttf", 62)
F_SERIF_S = font("liberation/LiberationSerif-Italic.ttf", 46)
F_LABEL = font("dejavu/DejaVuSans.ttf", 30)
F_LABEL_B = font("dejavu/DejaVuSans-Bold.ttf", 30)
F_CAP = font("dejavu/DejaVuSans.ttf", 34)
F_TINY = font("dejavu/DejaVuSans.ttf", 26)
F_LOGO = font("liberation/LiberationSerif-Bold.ttf", 86)
F_MONO = font("dejavu/DejaVuSansMono.ttf", 36)

# ---- Voiceover script -------------------------------------------------------
SCENES = [
    dict(key="open",
         vo="Some gifts are remembered. Champagne is one of them."),
    dict(key="sameday",
         vo="In London, we deliver the same day. Chilled, and at their door "
            "in thirty to forty five minutes."),
    dict(key="ukwide",
         vo="Across the rest of the United Kingdom, next day delivery. "
            "Wherever it needs to arrive."),
    dict(key="presented",
         vo="And every bottle can be presented as a gift. Gift boxes, "
            "gift sets, and a note written in your words."),
    dict(key="names",
         vo="Moet and Chandon. Veuve Clicquot. Dom Perignon. Bollinger. "
            "Krug. Armand de Brignac."),
    dict(key="cta",
         vo="Drinks House two four seven. Champagne gifts, delivered. "
            "Order at any hour, on any day. Please drink responsibly."),
]

VO_LEAD = 0.6
VO_TAIL = 1.0
MIN_SCENE = 4.0


# ---- Easing -----------------------------------------------------------------
def ease_out(t):
    return 1 - (1 - t) ** 3


def ease_in_out(t):
    return 3 * t * t - 2 * t * t * t


def clamp01(x):
    return max(0.0, min(1.0, x))


def seg(t, start, end):
    if end <= start:
        return 1.0 if t >= end else 0.0
    return clamp01((t - start) / (end - start))


# ---- TTS --------------------------------------------------------------------
def synthesize():
    from piper import PiperVoice
    os.makedirs(VO_DIR, exist_ok=True)
    voice = PiperVoice.load(MODEL)
    for i, sc in enumerate(SCENES):
        path = os.path.join(VO_DIR, f"vo_{i}_{sc['key']}.wav")
        with wave.open(path, "wb") as w:
            voice.synthesize_wav(sc["vo"], w)
        with wave.open(path, "rb") as w:
            sc["vo_dur"] = w.getnframes() / w.getframerate()
            sc["vo_path"] = path
        print(f"  VO {sc['key']}: {sc['vo_dur']:.2f}s")


def layout_scenes():
    t = 0.0
    for sc in SCENES:
        sc["len"] = max(sc["vo_dur"] + VO_LEAD + VO_TAIL, MIN_SCENE)
        sc["start"] = t
        t += sc["len"]
    return t + 0.6


def build_master_audio(total):
    master = np.zeros(int(total * SR), dtype=np.float32)
    for sc in SCENES:
        with wave.open(sc["vo_path"], "rb") as w:
            data = np.frombuffer(w.readframes(w.getnframes()),
                                 dtype=np.int16).astype(np.float32) / 32768
        off = int((sc["start"] + VO_LEAD) * SR)
        master[off:off + len(data)] += data * 0.92
    peak = np.abs(master).max()
    if peak > 0.98:
        master *= 0.98 / peak
    path = os.path.join(VO_DIR, "master.wav")
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes((master * 32767).astype(np.int16).tobytes())
    return path


# ---- Ground -----------------------------------------------------------------
def make_gradient():
    top = np.array(BG_TOP, dtype=np.float32)
    bot = np.array(BG_BOTTOM, dtype=np.float32)
    ramp = np.linspace(0, 1, H, dtype=np.float32)[:, None]
    grad = (top[None, :] * (1 - ramp) + bot[None, :] * ramp)
    return np.repeat(grad[:, None, :], W, axis=1).astype(np.uint8)


BG = make_gradient()


# ---- Type helpers -----------------------------------------------------------
def ctext(d, y, text, fnt, color, alpha, dy=0):
    if alpha <= 0.004:
        return
    tw = d.textlength(text, font=fnt)
    d.text(((W - tw) / 2, y + dy), text, font=fnt,
           fill=(*color, int(255 * alpha)))


def ls_width(d, text, fnt, sp):
    return sum(d.textlength(c, font=fnt) for c in text) + sp * (len(text) - 1)


def ls_ctext(d, y, text, fnt, color, alpha, sp=10, dy=0):
    """Centered, letterspaced — the quiet-luxury label treatment."""
    if alpha <= 0.004:
        return
    x = (W - ls_width(d, text, fnt, sp)) / 2
    col = (*color, int(255 * alpha))
    for c in text:
        d.text((x, y + dy), c, font=fnt, fill=col)
        x += d.textlength(c, font=fnt) + sp


def hairline(d, y, half, alpha, color=None):
    if alpha <= 0.004 or half < 1:
        return
    d.line([(W / 2 - half, y), (W / 2 + half, y)],
           fill=(*(color or GOLD), int(255 * alpha)), width=2)


def wrap(d, text, fnt, maxw):
    words, lines, cur = text.split(), [], ""
    for wd in words:
        trial = (cur + " " + wd).strip()
        if d.textlength(trial, font=fnt) <= maxw:
            cur = trial
        else:
            lines.append(cur)
            cur = wd
    if cur:
        lines.append(cur)
    return lines


def caption(d, lt, sc, alpha):
    p = ease_out(seg(lt, VO_LEAD, VO_LEAD + 0.6))
    lines = wrap(d, sc["vo"], F_CAP, 820)
    y = 1620 - (len(lines) - 1) * 24
    for ln in lines:
        ctext(d, y, ln, F_CAP, MUTED, alpha * p * 0.85)
        y += 48


def corner_rules(d, alpha):
    """Thin margin rules — a framed, editorial feel."""
    a = int(60 * alpha)
    if a <= 1:
        return
    d.line([(96, 132), (W - 96, 132)], fill=(*HAIR, a), width=2)
    d.line([(96, H - 132), (W - 96, H - 132)], fill=(*HAIR, a), width=2)


# ---- Line-art motifs --------------------------------------------------------
def draw_bow(d, cx, cy, s, alpha, p):
    """A thin ribbon bow that draws itself; p in 0..1."""
    a = int(255 * alpha)
    if a <= 1:
        return
    # ribbon tails grow first
    tp = ease_out(seg(p, 0.0, 0.45))
    if tp > 0:
        for sgn in (-1, 1):
            d.line([(cx, cy), (cx + sgn * 46 * s * tp, cy + 150 * s * tp)],
                   fill=(*GOLD, a), width=3)
            # tail notch
            if tp > 0.85:
                ex, ey = cx + sgn * 46 * s, cy + 150 * s
                d.line([(ex, ey), (ex + sgn * 20 * s, ey - 22 * s)],
                       fill=(*GOLD, a), width=3)
    # loops sweep open
    lp = ease_out(seg(p, 0.3, 1.0))
    if lp > 0:
        for sgn in (-1, 1):
            rx = 92 * s * lp
            ry = 60 * s * lp
            box = [cx + sgn * 6 * s - (rx if sgn < 0 else 0),
                   cy - ry,
                   cx + sgn * 6 * s + (rx if sgn > 0 else 0),
                   cy + ry]
            d.arc([min(box[0], box[2]), box[1], max(box[0], box[2]), box[3]],
                  0, 360, fill=(*GOLD, a), width=3)
    # knot last
    kp = ease_out(seg(p, 0.75, 1.0))
    if kp > 0:
        r = 13 * s * kp
        d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(*GOLD, a))


def draw_clock(d, cx, cy, r, alpha, p):
    """Hairline dial with a single sweeping hand."""
    a = int(255 * alpha)
    if a <= 1:
        return
    d.ellipse([cx - r, cy - r, cx + r, cy + r], outline=(*HAIR, a), width=2)
    for k in range(12):
        ang = k * math.pi / 6
        o = 14 if k % 3 else 24
        d.line([(cx + (r - 4) * math.sin(ang), cy - (r - 4) * math.cos(ang)),
                (cx + (r - o) * math.sin(ang), cy - (r - o) * math.cos(ang))],
               fill=(*(GOLD if k % 3 == 0 else HAIR), a), width=2)
    sweep = 360 * ease_in_out(p)
    if sweep > 2:
        d.arc([cx - r, cy - r, cx + r, cy + r], -90, -90 + sweep,
              fill=(*GOLD, a), width=3)
    ang = math.radians(-90 + sweep)
    d.line([(cx, cy), (cx + (r - 46) * math.cos(ang),
                       cy + (r - 46) * math.sin(ang))],
           fill=(*INK, a), width=3)
    d.ellipse([cx - 5, cy - 5, cx + 5, cy + 5], fill=(*INK, a))


# Great Britain coastline, from Natural Earth 1:50m admin-0 boundaries:
# largest ring of the United Kingdom feature, projected equirectangular
# with a cos(lat) correction, simplified (Douglas-Peucker) and normalised
# so that height = 1.0. Baked in so the render stays offline.
GB = [
    (0.2356, 0.8157), (0.1931, 0.8427), (0.1748, 0.84), (0.1525, 0.8193),
    (0.1291, 0.8219), (0.1388, 0.8114), (0.1188, 0.8019), (0.0837, 0.8153),
    (0.0592, 0.7857), (0.1349, 0.7339), (0.1464, 0.7088), (0.1381, 0.6653),
    (0.0986, 0.678), (0.1268, 0.6387), (0.1611, 0.6197), (0.1909, 0.6151),
    (0.2064, 0.6252), (0.2018, 0.6096), (0.2086, 0.6058), (0.2186, 0.62),
    (0.2301, 0.6194), (0.2086, 0.5958), (0.222, 0.5185), (0.2018, 0.5243),
    (0.1728, 0.4735), (0.1814, 0.4492), (0.2106, 0.4283), (0.1756, 0.4289),
    (0.1479, 0.4483), (0.1278, 0.4406), (0.1098, 0.4509), (0.0894, 0.4407),
    (0.0831, 0.459), (0.0678, 0.4394), (0.0653, 0.4245), (0.0732, 0.4242),
    (0.099, 0.3645), (0.0844, 0.3415), (0.0858, 0.3212), (0.1053, 0.3136),
    (0.0876, 0.3005), (0.0906, 0.2881), (0.0615, 0.3197), (0.0619, 0.2988),
    (0.0772, 0.2794), (0.0491, 0.307), (0.0392, 0.3775), (0.0331, 0.3848),
    (0.0248, 0.3806), (0.0427, 0.3295), (0.0347, 0.3282), (0.0407, 0.2773),
    (0.0642, 0.2183), (0.0327, 0.2446), (0.0, 0.223), (0.0273, 0.2073),
    (0.0185, 0.2015), (0.0388, 0.1631), (0.0214, 0.1394), (0.0375, 0.1266),
    (0.0265, 0.1153), (0.0298, 0.0996), (0.0357, 0.0876), (0.0663, 0.0876),
    (0.0489, 0.0657), (0.054, 0.0461), (0.0765, 0.0433), (0.0719, 0.0169),
    (0.0822, 0.0054), (0.1156, 0.0142), (0.2094, 0.0), (0.1986, 0.0365),
    (0.1457, 0.0786), (0.1426, 0.0911), (0.1548, 0.095), (0.1359, 0.123),
    (0.193, 0.1076), (0.276, 0.1085), (0.2901, 0.1189), (0.296, 0.135),
    (0.247, 0.2324), (0.2347, 0.2467), (0.192, 0.2642), (0.2209, 0.2603),
    (0.2367, 0.2695), (0.2352, 0.277), (0.1884, 0.3033), (0.1594, 0.2954),
    (0.2097, 0.3121), (0.2403, 0.3033), (0.271, 0.3178), (0.3045, 0.3565),
    (0.3332, 0.4573), (0.3714, 0.4805), (0.4113, 0.5254), (0.4031, 0.5366),
    (0.4249, 0.5846), (0.3987, 0.5698), (0.3722, 0.5713), (0.3971, 0.5749),
    (0.4355, 0.6165), (0.4412, 0.6369), (0.4202, 0.6665), (0.4361, 0.6777),
    (0.4551, 0.6593), (0.4888, 0.6603), (0.511, 0.6679), (0.5338, 0.693),
    (0.5231, 0.7617), (0.5009, 0.7752), (0.4979, 0.7947), (0.4682, 0.8033),
    (0.4781, 0.8079), (0.4776, 0.8217), (0.4459, 0.834), (0.4775, 0.8463),
    (0.5133, 0.8459), (0.5121, 0.867), (0.4881, 0.8826), (0.4823, 0.8968),
    (0.431, 0.9157), (0.4032, 0.9097), (0.3637, 0.9154), (0.3207, 0.9001),
    (0.3263, 0.909), (0.3139, 0.9175), (0.2789, 0.9201), (0.2786, 0.9343),
    (0.2131, 0.9211), (0.1855, 0.9309), (0.1668, 0.9765), (0.1318, 0.9587),
    (0.0955, 0.9707), (0.069, 1.0), (0.0475, 0.9923), (0.0347, 0.9986),
    (0.0324, 0.9891), (0.0843, 0.9424), (0.1054, 0.9141), (0.1095, 0.8908),
    (0.1249, 0.885), (0.1322, 0.8662), (0.2038, 0.8643), (0.2516, 0.802),
    (0.2356, 0.8157),
]
LONDON = (0.4084, 0.8291)


def _chaikin(pts, iterations=1):
    """Corner-cutting on a closed ring (unused: the baked outline is real)."""
    ring = pts[:-1] if pts[0] == pts[-1] else pts[:]
    for _ in range(iterations):
        out = []
        n = len(ring)
        for i in range(n):
            x0, y0 = ring[i]
            x1, y1 = ring[(i + 1) % n]
            out.append((0.75 * x0 + 0.25 * x1, 0.75 * y0 + 0.25 * y1))
            out.append((0.25 * x0 + 0.75 * x1, 0.25 * y0 + 0.75 * y1))
        ring = out
    return ring + [ring[0]]


_gxs = [p[0] for p in GB]
_gys = [p[1] for p in GB]
GB_BOX = (min(_gxs), min(_gys), max(_gxs), max(_gys))


def _gb_project(cx, cy, size):
    """Fit the outline into a `size`-tall box, centred, aspect preserved."""
    x0, y0, x1, y1 = GB_BOX
    k = size / (y1 - y0)
    ox = cx - (x0 + x1) / 2 * k
    oy = cy - (y0 + y1) / 2 * k
    return lambda x, y: (ox + x * k, oy + y * k)


def draw_uk(d, cx, cy, size, alpha, p, pulse=0.0):
    """Progressively strokes the coastline, then marks London."""
    a = int(255 * alpha)
    if a <= 1:
        return
    proj = _gb_project(cx, cy, size)
    pts = [proj(x, y) for x, y in GB]
    segs = len(pts) - 1
    drawn = p * segs
    for i in range(segs):
        if drawn <= i:
            break
        f = clamp01(drawn - i)
        x0, y0 = pts[i]
        x1, y1 = pts[i + 1]
        d.line([(x0, y0), (x0 + (x1 - x0) * f, y0 + (y1 - y0) * f)],
               fill=(*INK, int(a * 0.7)), width=3)
    if p > 0.94:
        lx, ly = proj(*LONDON)
        d.ellipse([lx - 6, ly - 6, lx + 6, ly + 6], fill=(*GOLD, a))
        rr = 12 + 30 * pulse
        d.ellipse([lx - rr, ly - rr, lx + rr, ly + rr],
                  outline=(*GOLD, int(a * (1 - pulse) * 0.75)), width=2)


def draw_giftbox(d, cx, cy, s, alpha, p):
    """Hairline box; the ribbon crosses it, then the bow settles on top."""
    a = int(255 * alpha)
    if a <= 1:
        return
    w, h = 210 * s, 150 * s
    x0, y0, x1, y1 = cx - w, cy - h * 0.2, cx + w, cy + h * 1.25
    bp = ease_out(seg(p, 0.0, 0.5))
    if bp > 0:
        d.rectangle([x0, y0 + (y1 - y0) * (1 - bp), x1, y1],
                    outline=(*INK, int(a * 0.8)), width=3)
    # lid
    if p > 0.35:
        lp = ease_out(seg(p, 0.35, 0.7))
        d.rectangle([x0 - 16 * s, y0 - 44 * s * lp, x1 + 16 * s, y0],
                    outline=(*INK, int(a * 0.8)), width=3)
    # vertical ribbon
    rp = ease_out(seg(p, 0.5, 0.85))
    if rp > 0:
        d.line([(cx, y0 - 44 * s), (cx, y0 - 44 * s + (y1 - y0 + 44 * s) * rp)],
               fill=(*GOLD, a), width=3)
    if p > 0.75:
        draw_bow(d, cx, y0 - 52 * s, s * 0.5, alpha, seg(p, 0.75, 1.0))


def draw_note(d, cx, cy, s, alpha, p):
    """A small card with ruled 'handwriting' that writes itself."""
    a = int(255 * alpha)
    if a <= 1:
        return
    w, h = 150 * s, 105 * s
    d.rectangle([cx - w, cy - h, cx + w, cy + h],
                outline=(*INK, int(a * 0.7)), width=3)
    rows = [0.78, 0.5, 0.22, 0.55]
    for i, frac in enumerate(rows):
        rp = ease_out(seg(p, 0.15 + i * 0.16, 0.5 + i * 0.16))
        if rp <= 0:
            continue
        y = cy - h + (i + 1) * (2 * h / (len(rows) + 1))
        d.line([(cx - w * 0.72, y),
                (cx - w * 0.72 + 2 * w * 0.72 * frac * rp, y)],
               fill=(*MUTED, int(a * 0.8)), width=3)


def draw_flute_pair(d, cx, cy, s, alpha, p):
    """Two hairline flutes, lightly toasting."""
    a = int(255 * alpha)
    if a <= 1:
        return
    lean = 7 * math.sin(p * math.pi)
    for sgn in (-1, 1):
        ox = sgn * 74 * s
        tilt = sgn * lean
        top, bowl, stem = cy - 128 * s, 132 * s, 108 * s
        bt, bb = 34 * s, 13 * s
        d.polygon([(cx + ox - bt + tilt, top),
                   (cx + ox + bt + tilt, top),
                   (cx + ox + bb, top + bowl),
                   (cx + ox - bb, top + bowl)],
                  outline=(*GOLD, a), width=3)
        d.line([(cx + ox, top + bowl), (cx + ox, top + bowl + stem)],
               fill=(*GOLD, a), width=3)
        d.line([(cx + ox - 30 * s, top + bowl + stem),
                (cx + ox + 30 * s, top + bowl + stem)],
               fill=(*GOLD, a), width=3)


# ---- Frame ------------------------------------------------------------------
def scene_alpha(t, sc, fade=0.6):
    s0, s1 = sc["start"], sc["start"] + sc["len"]
    if t < s0 or t >= s1:
        return 0.0, 0.0
    a_in = ease_out(seg(t, s0, s0 + fade))
    a_out = 1.0 - ease_in_out(seg(t, s1 - fade, s1))
    return a_in * a_out, t - s0


def render_frame(i, total):
    t = i / FPS
    img = Image.fromarray(BG.copy())
    d = ImageDraw.Draw(img, "RGBA")
    cx = W // 2

    for sc in SCENES:
        a, lt = scene_alpha(t, sc)
        if a <= 0:
            continue
        key = sc["key"]
        corner_rules(d, a)

        if key == "open":
            ls_ctext(d, 196, "DRINKS HOUSE 247", F_LABEL, MUTED, a * 0.85,
                     sp=11)
            draw_bow(d, cx, 660, 1.0, a, seg(lt, 0.3, 1.9))
            p1 = ease_out(seg(lt, 1.2, 2.0))
            ctext(d, 940, "Some gifts", F_STATEMENT, INK, a * p1,
                  dy=int(20 * (1 - p1)))
            p2 = ease_out(seg(lt, 1.6, 2.4))
            ctext(d, 1050, "are remembered.", F_STATEMENT, INK, a * p2,
                  dy=int(20 * (1 - p2)))
            hairline(d, 1220, int(120 * ease_in_out(seg(lt, 2.2, 3.0))), a)

        elif key == "sameday":
            ls_ctext(d, 196, "SAME DAY  ·  LONDON", F_LABEL, GOLD, a * 0.95,
                     sp=11)
            draw_clock(d, cx, 660, 190, a * ease_out(seg(lt, 0.2, 1.0)),
                       seg(lt, 0.5, 2.6))
            p1 = ease_out(seg(lt, 1.0, 1.8))
            ctext(d, 960, "30–45", F_BIG, INK, a * p1, dy=int(18 * (1 - p1)))
            p2 = ease_out(seg(lt, 1.4, 2.2))
            ls_ctext(d, 1120, "MINUTES", F_LABEL, MUTED, a * p2, sp=14)
            hairline(d, 1210, int(120 * ease_in_out(seg(lt, 1.8, 2.6))), a)
            p3 = ease_out(seg(lt, 2.0, 2.8))
            ctext(d, 1260, "chilled, to their door", F_SERIF_S, MUTED, a * p3)

        elif key == "ukwide":
            ls_ctext(d, 196, "UK-WIDE  ·  NEXT DAY", F_LABEL, GOLD, a * 0.95,
                     sp=11)
            draw_uk(d, cx, 700, 620, a, seg(lt, 0.2, 2.2),
                    pulse=((lt - 2.2) * 0.7) % 1.0 if lt > 2.2 else 0.0)
            p1 = ease_out(seg(lt, 1.8, 2.6))
            ctext(d, 1090, "Anywhere in Britain,", F_STATEMENT, INK, a * p1,
                  dy=int(18 * (1 - p1)))
            p2 = ease_out(seg(lt, 2.2, 3.0))
            ctext(d, 1200, "by tomorrow.", F_STATEMENT_I, INK, a * p2,
                  dy=int(18 * (1 - p2)))

        elif key == "presented":
            ls_ctext(d, 196, "PRESENTED, NOT POSTED", F_LABEL, GOLD, a * 0.95,
                     sp=11)
            draw_giftbox(d, cx - 150, 620, 1.0,
                         a * ease_out(seg(lt, 0.2, 0.9)), seg(lt, 0.3, 2.0))
            draw_note(d, cx + 250, 760, 1.0,
                      a * ease_out(seg(lt, 1.1, 1.8)), seg(lt, 1.2, 2.8))
            items = ["Gift boxes & gift sets",
                     "A note in your words",
                     "Wrapped, then delivered"]
            y = 1030
            for k, it in enumerate(items):
                pk = ease_out(seg(lt, 1.6 + k * 0.34, 2.3 + k * 0.34))
                if pk <= 0:
                    continue
                ctext(d, y, it, F_NAME, INK, a * pk, dy=int(14 * (1 - pk)))
                y += 118

        elif key == "names":
            ls_ctext(d, 196, "THE HOUSES", F_LABEL, GOLD, a * 0.95, sp=13)
            draw_flute_pair(d, cx, 470, 0.82,
                            a * ease_out(seg(lt, 0.1, 0.9)),
                            seg(lt, 0.4, 1.4))
            names = ["Moët & Chandon", "Veuve Clicquot", "Dom Pérignon",
                     "Bollinger", "Krug", "Armand de Brignac"]
            y = 800
            for k, nm in enumerate(names):
                pk = ease_out(seg(lt, 0.7 + k * 0.3, 1.4 + k * 0.3))
                if pk <= 0:
                    continue
                ctext(d, y, nm, F_NAME, INK, a * pk, dy=int(12 * (1 - pk)))
                y += 96
            hairline(d, y + 24, int(120 * ease_in_out(seg(lt, 2.8, 3.6))), a)

        elif key == "cta":
            p1 = ease_out(seg(lt, 0.2, 1.0))
            draw_bow(d, cx, 460, 0.62, a * p1, seg(lt, 0.2, 1.4))
            p2 = ease_out(seg(lt, 0.8, 1.6))
            ctext(d, 700, "DRINKS HOUSE", F_LOGO, INK, a * p2,
                  dy=int(16 * (1 - p2)))
            ctext(d, 810, "247", F_LOGO, GOLD, a * p2, dy=int(16 * (1 - p2)))
            hairline(d, 960, int(150 * ease_in_out(seg(lt, 1.3, 2.0))), a)
            p3 = ease_out(seg(lt, 1.5, 2.3))
            ctext(d, 1010, "Champagne gifts, delivered.", F_SERIF_S, MUTED,
                  a * p3)
            p4 = ease_out(seg(lt, 1.9, 2.7))
            ctext(d, 1140, "drinkshouse247.co.uk", F_MONO, INK, a * p4)
            ctext(d, 1210, "+44 20 3488 3266", F_MONO, MUTED, a * p4)
            p5 = ease_out(seg(lt, 2.3, 3.1))
            ls_ctext(d, 1330, "SAME DAY LONDON  ·  NEXT DAY UK", F_LABEL,
                     GOLD, a * p5, sp=9)
            ls_ctext(d, 1400, "OPEN 24/7", F_LABEL_B, INK, a * p5, sp=12)

        if key != "cta":
            caption(d, lt, sc, a)
        ctext(d, H - 118, "18+ · Please drink responsibly", F_TINY, MUTED,
              a * 0.6)

    total_s = total / FPS
    fade = ease_out(seg(t, 0.0, 0.6)) * (
        1.0 - ease_in_out(seg(t, total_s - 0.8, total_s)))
    if fade < 1.0:
        ov = Image.new("RGBA", (W, H), (*BG_BOTTOM, int(255 * (1 - fade))))
        img = Image.alpha_composite(img.convert("RGBA"), ov)

    return np.asarray(img.convert("RGB"))


def main():
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    if not os.path.exists(MODEL):
        raise SystemExit(f"Piper model not found: {MODEL}")
    print("Synthesizing voiceover...")
    synthesize()
    total_s = layout_scenes()
    total = int(total_s * FPS)
    print(f"Total: {total_s:.1f}s ({total} frames)")
    audio = build_master_audio(total_s)

    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    cmd = [
        ffmpeg, "-y",
        "-f", "rawvideo", "-pix_fmt", "rgb24",
        "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-",
        "-i", audio,
        "-map", "0:v", "-map", "1:a",
        "-c:v", "libx264", "-preset", "medium", "-crf", "18",
        "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "128k",
        "-movflags", "+faststart",
        "-t", f"{total_s:.3f}",
        OUT,
    ]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE,
                            stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL)
    for i in range(total):
        proc.stdin.write(render_frame(i, total).tobytes())
        if i % 90 == 0:
            print(f"  frame {i}/{total}")
    proc.stdin.close()
    rc = proc.wait()
    if rc != 0:
        raise SystemExit(f"ffmpeg failed with code {rc}")
    print("Done:", OUT)


if __name__ == "__main__":
    main()
