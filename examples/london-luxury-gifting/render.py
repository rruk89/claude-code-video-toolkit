#!/usr/bin/env python3
"""
"London's Champagne" — an opulent, monument-led gifting film with
voiceover for Drinks House 247.

Rich rather than restrained: midnight sky, real gold-foil gradients
(text and artwork are masked and filled with a metallic ramp), an
illustrated London skyline — The Shard, the Gherkin, St Paul's, the
London Eye, Elizabeth Tower, Tower Bridge — ornate framing, light
shafts, sparkle and drifting gold bubbles.

Fully local pipeline: Piper TTS per scene, scene lengths auto-fit the
narration, PIL frames + master audio muxed by a bundled FFmpeg.

    pip install imageio-ffmpeg numpy pillow piper-tts
    PIPER_MODEL=/path/to/en-us-ryan-high.onnx python render.py

Output: output/london-luxury-gifting.mp4  (1080x1920, 30fps, VO-timed)
"""

import math
import os
import subprocess
import wave
from functools import lru_cache

import imageio_ffmpeg
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter

# ---- Config -----------------------------------------------------------------
W, H = 1080, 1920
FPS = 30
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "output", "london-luxury-gifting.mp4")
VO_DIR = os.path.join(HERE, "output", "vo")
MODEL = os.environ.get("PIPER_MODEL", os.path.join(HERE, "en-us-ryan-high.onnx"))
SR = 22050

SKY_TOP = (7, 9, 20)
SKY_MID = (20, 17, 30)
SKY_LOW = (44, 30, 26)
CREAM = (246, 240, 226)
MUTED = (163, 150, 128)
GOLD = (206, 168, 88)
GOLD_DEEP = (140, 102, 38)
GOLD_LIGHT = (250, 236, 190)

FONT_DIR = "/usr/share/fonts/truetype"


def font(path, size):
    return ImageFont.truetype(os.path.join(FONT_DIR, path), size)


F_DISPLAY = font("liberation/LiberationSerif-Bold.ttf", 104)
F_DISPLAY_L = font("liberation/LiberationSerif-Regular.ttf", 96)
F_HERO = font("liberation/LiberationSerif-Bold.ttf", 150)
F_NAME = font("liberation/LiberationSerif-Regular.ttf", 66)
F_SERIF_I = font("liberation/LiberationSerif-Italic.ttf", 50)
F_LABEL = font("dejavu/DejaVuSans.ttf", 30)
F_LABEL_B = font("dejavu/DejaVuSans-Bold.ttf", 30)
F_CAP = font("dejavu/DejaVuSans.ttf", 34)
F_TINY = font("dejavu/DejaVuSans.ttf", 26)
F_MONO = font("dejavu/DejaVuSansMono-Bold.ttf", 40)
F_MONO_S = font("dejavu/DejaVuSansMono.ttf", 34)
F_MARK = font("dejavu/DejaVuSans.ttf", 24)

# ---- Voiceover script -------------------------------------------------------
SCENES = [
    dict(key="open",
         vo="London. A city of a thousand celebrations. And the champagne "
            "that marks them."),
    dict(key="sameday",
         vo="Order today, and we deliver the same day. Chilled, and at "
            "their door within thirty to forty five minutes."),
    dict(key="across",
         vo="From Mayfair to Canary Wharf. Every postcode, at any hour, "
            "around the clock."),
    dict(key="ukwide",
         vo="And far beyond the capital: next day delivery, right across "
            "the United Kingdom."),
    dict(key="presented",
         vo="Each bottle arrives as a gift should. In a gift box, with a "
            "note written in your words."),
    dict(key="names",
         vo="Moet and Chandon. Veuve Clicquot. Dom Perignon. Bollinger. "
            "Krug. Armand de Brignac."),
    dict(key="cta",
         vo="Drinks House two four seven. London's champagne, delivered. "
            "Open twenty four hours, every day. Please drink responsibly."),
]

VO_LEAD = 0.5
VO_TAIL = 0.9
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


# ---- Gold foil --------------------------------------------------------------
# A metallic ramp: deep shadow, warm body, a bright specular band, and back.
FOIL_POS = np.array([0.00, 0.16, 0.33, 0.46, 0.60, 0.78, 1.00])
FOIL_COL = np.array([
    (118, 82, 26), (186, 146, 66), (252, 240, 200), (222, 182, 96),
    (146, 104, 36), (238, 210, 146), (160, 118, 44),
], dtype=np.float32)


def foil_column(h, shift=0.0):
    t = (np.linspace(0.0, 1.0, max(1, h)) + shift) % 1.0
    out = np.empty((max(1, h), 3), dtype=np.float32)
    for c in range(3):
        out[:, c] = np.interp(t, FOIL_POS, FOIL_COL[:, c])
    return out


def foil_tile(w, h, shift=0.0):
    col = foil_column(h, shift)
    return Image.fromarray(
        np.repeat(col[:, None, :], max(1, w), axis=1).astype(np.uint8), "RGB")


def paste_foil(img, mask, xy, alpha=1.0, shift=0.0):
    """Fill `mask` with the metallic ramp and composite it onto `img`."""
    if alpha <= 0.004:
        return
    w, h = mask.size
    if w <= 0 or h <= 0:
        return
    m = mask if alpha >= 0.999 else mask.point(lambda v: int(v * alpha))
    img.paste(foil_tile(w, h, shift), (int(xy[0]), int(xy[1])), m)


_measure = ImageDraw.Draw(Image.new("L", (4, 4)))


@lru_cache(maxsize=512)
def text_mask(text, fnt_key, sp=0):
    """Tight alpha mask for a string (optionally letterspaced)."""
    fnt = FONTS[fnt_key]
    if sp:
        widths = [_measure.textlength(c, font=fnt) for c in text]
        total = int(sum(widths) + sp * (len(text) - 1)) + 8
        l, t, r, b = _measure.textbbox((0, 0), text, font=fnt)
        mask = Image.new("L", (total, int(b - t) + 8), 0)
        md = ImageDraw.Draw(mask)
        x = 4.0
        for c, cw in zip(text, widths):
            md.text((x, 4 - t), c, font=fnt, fill=255)
            x += cw + sp
        return mask
    l, t, r, b = _measure.textbbox((0, 0), text, font=fnt)
    if r - l <= 0 or b - t <= 0:
        return Image.new("L", (1, 1), 0)
    mask = Image.new("L", (int(r - l) + 6, int(b - t) + 6), 0)
    ImageDraw.Draw(mask).text((3 - l, 3 - t), text, font=fnt, fill=255)
    return mask


def foil_ctext(img, y, text, fnt_key, alpha, sp=0, shift=0.0, dy=0, glow=True):
    m = text_mask(text, fnt_key, sp)
    x = (W - m.size[0]) // 2
    if glow and alpha > 0.15:
        halo = m.filter(ImageFilter.GaussianBlur(9)).point(
            lambda v: int(v * 0.42 * alpha))
        img.paste(Image.new("RGB", m.size, GOLD), (x, int(y + dy)), halo)
    paste_foil(img, m, (x, y + dy), alpha, shift)


def glow_dot(img, x, y, r, alpha, color=(255, 224, 160)):
    """Soft bloom pasted onto the RGB base.

    ImageDraw *replaces* pixels rather than blending them, so stacked
    semi-transparent ellipses punch holes in whatever is beneath. Pasting a
    blurred mask composites properly instead.
    """
    if alpha <= 0.02 or r < 1:
        return
    size = max(6, int(r * 6))
    m = Image.new("L", (size, size), 0)
    c = size / 2
    ImageDraw.Draw(m).ellipse([c - r, c - r, c + r, c + r], fill=255)
    m = m.filter(ImageFilter.GaussianBlur(r * 0.85))
    m = m.point(lambda v: int(v * alpha * 0.9))
    img.paste(Image.new("RGB", (size, size), color),
              (int(x - c), int(y - c)), m)


def ctext(d, y, text, fnt, color, alpha, dy=0):
    if alpha <= 0.004:
        return
    tw = d.textlength(text, font=fnt)
    d.text(((W - tw) / 2, y + dy), text, font=fnt,
           fill=(*color, int(255 * alpha)))


def ls_ctext(d, y, text, fnt, color, alpha, sp=10, dy=0):
    if alpha <= 0.004:
        return
    widths = [d.textlength(c, font=fnt) for c in text]
    x = (W - (sum(widths) + sp * (len(text) - 1))) / 2
    col = (*color, int(255 * alpha))
    for c, cw in zip(text, widths):
        d.text((x, y + dy), c, font=fnt, fill=col)
        x += cw + sp


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
    p = ease_out(seg(lt, VO_LEAD, VO_LEAD + 0.5))
    lines = wrap(d, sc["vo"], F_CAP, 840)
    y = 1660 - (len(lines) - 1) * 22
    for ln in lines:
        ctext(d, y, ln, F_CAP, MUTED, alpha * p * 0.9)
        y += 46


# ---- Sky, frame, atmosphere -------------------------------------------------
def make_sky():
    ys = np.linspace(0, 1, H, dtype=np.float32)[:, None]
    top = np.array(SKY_TOP, np.float32)
    mid = np.array(SKY_MID, np.float32)
    low = np.array(SKY_LOW, np.float32)
    a = np.clip(ys / 0.55, 0, 1)
    b = np.clip((ys - 0.55) / 0.45, 0, 1)
    col = top * (1 - a) + mid * a
    col = col * (1 - b) + low * b
    img = np.repeat(col[:, None, :], W, axis=1)
    # warm horizon bloom behind the skyline
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    r = np.sqrt(((xx - W / 2) / 640.0) ** 2 + ((yy - 1180) / 300.0) ** 2)
    bloom = np.exp(-r * r) * 58.0
    img += bloom[:, :, None] * np.array([1.0, 0.74, 0.36], np.float32)
    # vignette
    rv = np.sqrt(((xx - W / 2) / (W * 0.78)) ** 2 +
                 ((yy - H / 2) / (H * 0.78)) ** 2)
    img *= np.clip(1.12 - 0.5 * rv ** 2, 0, 1)[:, :, None]
    return np.clip(img, 0, 255).astype(np.uint8)


SKY = make_sky()


def light_shafts(d, t, alpha):
    """Slow diagonal shafts from the upper left."""
    for k in range(3):
        ph = (t * 0.06 + k * 0.33) % 1.0
        x = -300 + ph * (W + 700)
        a = int(16 * alpha * math.sin(math.pi * ph))
        if a <= 1:
            continue
        d.polygon([(x, 0), (x + 150, 0), (x + 480, H), (x + 300, H)],
                  fill=(255, 226, 170, a))


def sparkles(d, t, alpha, n=26):
    for k in range(n):
        px = (math.sin(k * 12.9898) * 43758.5453) % 1.0
        py = (math.sin(k * 78.233) * 12345.678) % 1.0
        ph = ((t * 0.42 + (math.sin(k * 3.1) * 999.0) % 1.0) % 1.0)
        tw = math.sin(math.pi * ph)
        a = int(210 * alpha * tw * tw)
        if a <= 2:
            continue
        x = 60 + px * (W - 120)
        y = 200 + py * 900
        r = 2 + 5 * tw
        d.line([(x - r * 2.6, y), (x + r * 2.6, y)],
               fill=(*GOLD_LIGHT, a), width=2)
        d.line([(x, y - r * 2.6), (x, y + r * 2.6)],
               fill=(*GOLD_LIGHT, a), width=2)
        d.ellipse([x - r * 0.5, y - r * 0.5, x + r * 0.5, y + r * 0.5],
                  fill=(*GOLD_LIGHT, a))


def bubbles(d, t, alpha):
    for k in range(16):
        px = (math.sin(k * 21.13) * 33333.3) % 1.0
        speed = 60 + 120 * ((math.sin(k * 51.7) * 777.7) % 1.0)
        r = 3 + 7 * ((math.sin(k * 9.41) * 4242.0) % 1.0)
        phase = (math.sin(k * 5.3) * 1234.5) % 1.0
        x = int(px * W + 22 * math.sin(t * 0.7 + k))
        y = H - int(((t * speed + phase * H * 2) % (H + 200)) - 100)
        a = int(46 * alpha)
        d.ellipse([x - r, y - r, x + r, y + r], outline=(*GOLD, a), width=2)


def ornate_frame(d, alpha):
    """Double gold rule with corner filigree."""
    a = int(150 * alpha)
    if a <= 2:
        return
    m1, m2 = 54, 70
    d.rectangle([m1, m1, W - m1, H - m1], outline=(*GOLD_DEEP, a), width=3)
    d.rectangle([m2, m2, W - m2, H - m2],
                outline=(*GOLD, int(a * 0.62)), width=1)
    for sx, sy in ((1, 1), (-1, 1), (1, -1), (-1, -1)):
        cx = m1 if sx > 0 else W - m1
        cy = m1 if sy > 0 else H - m1
        for i, ln in enumerate((66, 44, 24)):
            off = 16 + i * 13
            d.line([(cx + sx * off, cy + sy * 8),
                    (cx + sx * off, cy + sy * (8 + ln))],
                   fill=(*GOLD, int(a * (0.85 - i * 0.2))), width=2)
            d.line([(cx + sx * 8, cy + sy * off),
                    (cx + sx * (8 + ln), cy + sy * off)],
                   fill=(*GOLD, int(a * (0.85 - i * 0.2))), width=2)
        d.ellipse([cx + sx * 12 - 5, cy + sy * 12 - 5,
                   cx + sx * 12 + 5, cy + sy * 12 + 5], fill=(*GOLD, a))


def rule_with_diamond(d, y, half, alpha):
    if alpha <= 0.004 or half < 6:
        return
    a = int(220 * alpha)
    d.line([(W / 2 - half, y), (W / 2 - 18, y)], fill=(*GOLD, a), width=2)
    d.line([(W / 2 + 18, y), (W / 2 + half, y)], fill=(*GOLD, a), width=2)
    d.polygon([(W / 2, y - 9), (W / 2 + 10, y), (W / 2, y + 9),
               (W / 2 - 10, y)], fill=(*GOLD, a))


# ---- London monuments (silhouette masks, filled with foil) ------------------
def _shard(md, cx, base, s):
    apex = base - 470 * s
    md.polygon([(cx - 62 * s, base), (cx + 62 * s, base),
                (cx + 16 * s, apex + 40 * s), (cx + 6 * s, apex),
                (cx - 4 * s, apex + 26 * s), (cx - 14 * s, apex + 6 * s),
                (cx - 22 * s, apex + 44 * s)], fill=255)


def _gherkin(md, cx, base, s):
    h = 300 * s
    pts = []
    for i in range(25):
        f = i / 24
        y = base - h * f
        wdt = 44 * s * math.sin(math.pi * (0.12 + 0.86 * f)) ** 0.65
        pts.append((cx - wdt, y))
    for i in range(24, -1, -1):
        f = i / 24
        y = base - h * f
        wdt = 44 * s * math.sin(math.pi * (0.12 + 0.86 * f)) ** 0.65
        pts.append((cx + wdt, y))
    md.polygon(pts, fill=255)
    md.ellipse([cx - 7 * s, base - h - 12 * s, cx + 7 * s, base - h + 4 * s],
               fill=255)


def _st_pauls(md, cx, base, s):
    md.rectangle([cx - 96 * s, base - 96 * s, cx + 96 * s, base], fill=255)
    for sx in (-1, 1):
        md.rectangle([cx + sx * 78 * s - 17 * s, base - 176 * s,
                      cx + sx * 78 * s + 17 * s, base - 80 * s], fill=255)
        md.polygon([(cx + sx * 78 * s - 17 * s, base - 176 * s),
                    (cx + sx * 78 * s + 17 * s, base - 176 * s),
                    (cx + sx * 78 * s, base - 208 * s)], fill=255)
    md.rectangle([cx - 46 * s, base - 200 * s, cx + 46 * s, base - 90 * s],
                 fill=255)
    md.pieslice([cx - 58 * s, base - 306 * s, cx + 58 * s, base - 190 * s],
                180, 360, fill=255)
    md.rectangle([cx - 13 * s, base - 336 * s, cx + 13 * s, base - 286 * s],
                 fill=255)
    md.ellipse([cx - 9 * s, base - 352 * s, cx + 9 * s, base - 334 * s],
               fill=255)
    md.line([(cx, base - 380 * s), (cx, base - 344 * s)],
            fill=255, width=max(2, int(5 * s)))
    md.line([(cx - 12 * s, base - 366 * s), (cx + 12 * s, base - 366 * s)],
            fill=255, width=max(2, int(5 * s)))


def _eye(md, cx, base, s):
    r = 132 * s
    cy = base - r - 34 * s
    md.ellipse([cx - r, cy - r, cx + r, cy + r], outline=255,
               width=max(3, int(7 * s)))
    for k in range(16):
        ang = k * math.pi / 8
        md.line([(cx, cy), (cx + r * math.cos(ang), cy + r * math.sin(ang))],
                fill=255, width=max(1, int(2.4 * s)))
        md.ellipse([cx + r * math.cos(ang) - 7 * s,
                    cy + r * math.sin(ang) - 7 * s,
                    cx + r * math.cos(ang) + 7 * s,
                    cy + r * math.sin(ang) + 7 * s], fill=255)
    md.ellipse([cx - 13 * s, cy - 13 * s, cx + 13 * s, cy + 13 * s], fill=255)
    for sx in (-1, 1):
        md.line([(cx, cy), (cx + sx * 54 * s, base)], fill=255,
                width=max(3, int(8 * s)))


def _elizabeth_tower(md, cx, base, s):
    """Elizabeth Tower (Big Ben). Returns the clock centre and radius."""
    # plinth
    md.rectangle([cx - 60 * s, base - 26 * s, cx + 60 * s, base], fill=255)
    # shaft, tapering slightly
    md.polygon([(cx - 46 * s, base - 20 * s), (cx + 46 * s, base - 20 * s),
                (cx + 40 * s, base - 322 * s), (cx - 40 * s, base - 322 * s)],
               fill=255)
    # clock stage — widest part of the tower
    md.rectangle([cx - 54 * s, base - 412 * s, cx + 54 * s, base - 316 * s],
                 fill=255)
    md.rectangle([cx - 59 * s, base - 424 * s, cx + 59 * s, base - 404 * s],
                 fill=255)
    # belfry
    md.rectangle([cx - 46 * s, base - 466 * s, cx + 46 * s, base - 420 * s],
                 fill=255)
    for k in range(3):
        x = cx - 30 * s + k * 30 * s
        md.line([(x, base - 462 * s), (x, base - 428 * s)], fill=0,
                width=max(1, int(7 * s)))
    md.rectangle([cx - 50 * s, base - 476 * s, cx + 50 * s, base - 462 * s],
                 fill=255)
    # spire + finial
    md.polygon([(cx - 44 * s, base - 476 * s), (cx + 44 * s, base - 476 * s),
                (cx, base - 588 * s)], fill=255)
    md.ellipse([cx - 8 * s, base - 606 * s, cx + 8 * s, base - 586 * s],
               fill=255)
    return (cx, base - 364 * s, 36 * s)


def _tower_bridge(md, cx, base, s):
    span = 150 * s
    for sx in (-1, 1):
        tx = cx + sx * span
        md.rectangle([tx - 30 * s, base - 210 * s, tx + 30 * s, base],
                     fill=255)
        md.polygon([(tx - 34 * s, base - 210 * s),
                    (tx + 34 * s, base - 210 * s),
                    (tx, base - 286 * s)], fill=255)
        md.rectangle([tx - 5 * s, base - 306 * s, tx + 5 * s, base - 280 * s],
                     fill=255)
    md.rectangle([cx - span - 8 * s, base - 190 * s,
                  cx + span + 8 * s, base - 162 * s], fill=255)
    md.rectangle([cx - span - 96 * s, base - 44 * s,
                  cx + span + 96 * s, base - 26 * s], fill=255)
    for sx in (-1, 1):
        for k in range(9):
            f = k / 8
            x = cx + sx * (span + 8 * s + f * 88 * s)
            y = base - 44 * s - 74 * s * math.sin(math.pi * (1 - f) * 0.5)
            md.line([(x, y), (x, base - 44 * s)], fill=255,
                    width=max(1, int(2.2 * s)))
        md.line([(cx + sx * (span + 8 * s), base - 118 * s),
                 (cx + sx * (span + 96 * s), base - 44 * s)],
                fill=255, width=max(2, int(4 * s)))


@lru_cache(maxsize=8)
def skyline_mask(s10):
    """The full skyline band as one mask (s10 = scale × 10, for caching)."""
    s = s10 / 10.0
    bw, bh = int(W * s), int(560 * s)
    mask = Image.new("L", (bw, bh), 0)
    md = ImageDraw.Draw(mask)
    base = bh - int(24 * s)
    # laid out left-to-right with a little natural overlap, all within frame
    _shard(md, int(120 * s), base, s * 0.80)
    _gherkin(md, int(248 * s), base, s * 0.85)
    _st_pauls(md, int(420 * s), base, s * 0.72)
    _eye(md, int(612 * s), base, s * 0.62)
    _elizabeth_tower(md, int(790 * s), base, s * 0.64)
    _tower_bridge(md, int(880 * s), base, s * 0.52)
    return mask


@lru_cache(maxsize=8)
def big_ben_mask(s10):
    s = s10 / 10.0
    w, h = int(320 * s), int(640 * s)
    mask = Image.new("L", (w, h), 0)
    md = ImageDraw.Draw(mask)
    feat = _elizabeth_tower(md, w // 2, h - int(20 * s), s)
    return mask, feat


def draw_skyline(img, d, y_base, alpha, reveal=1.0, s=1.0):
    """Foil-filled skyline with a soft glow beneath it."""
    if alpha <= 0.01:
        return
    mask = skyline_mask(int(s * 10))
    mw, mh = mask.size
    x0 = (W - mw) // 2
    y0 = int(y_base - mh)
    if reveal < 1.0:
        cut = int(mw * clamp01(reveal))
        if cut <= 0:
            return
        mask = mask.crop((0, 0, cut, mh))
    halo = mask.filter(ImageFilter.GaussianBlur(16)).point(
        lambda v: int(v * 0.5 * alpha))
    img.paste(Image.new("RGB", mask.size, (188, 132, 54)), (x0, y0), halo)
    paste_foil(img, mask, (x0, y0), alpha, shift=0.12)


def clock_face(d, cx, cy, r, alpha, p):
    """The illuminated dial: warm glass, gold ring, sweeping hands."""
    a = int(255 * alpha)
    if a <= 2:
        return
    d.ellipse([cx - r, cy - r, cx + r, cy + r],
              fill=(255, 236, 196, int(a * 0.94)))
    d.ellipse([cx - r, cy - r, cx + r, cy + r],
              outline=(*GOLD_DEEP, a), width=max(2, int(r * 0.13)))
    for k in range(12):
        ang = k * math.pi / 6
        d.line([(cx + r * 0.82 * math.sin(ang), cy - r * 0.82 * math.cos(ang)),
                (cx + r * 0.64 * math.sin(ang), cy - r * 0.64 * math.cos(ang))],
               fill=(90, 62, 22, a), width=max(1, int(r * 0.07)))
    ang = math.radians(-90 + 360 * ease_in_out(p))
    d.line([(cx, cy), (cx + r * 0.72 * math.cos(ang),
                       cy + r * 0.72 * math.sin(ang))],
           fill=(48, 34, 14, a), width=max(2, int(r * 0.09)))
    d.line([(cx, cy), (cx, cy - r * 0.46)], fill=(48, 34, 14, a),
           width=max(2, int(r * 0.11)))
    d.ellipse([cx - r * 0.09, cy - r * 0.09, cx + r * 0.09, cy + r * 0.09],
              fill=(48, 34, 14, a))


def draw_big_ben(img, d, cx, y_base, alpha, s, clock_p):
    if alpha <= 0.01:
        return
    mask, feat = big_ben_mask(int(s * 10))
    mw, mh = mask.size
    x0, y0 = int(cx - mw / 2), int(y_base - mh)
    halo = mask.filter(ImageFilter.GaussianBlur(20)).point(
        lambda v: int(v * 0.55 * alpha))
    img.paste(Image.new("RGB", mask.size, (196, 138, 58)), (x0, y0), halo)
    paste_foil(img, mask, (x0, y0), alpha, shift=0.08)
    fx, fy, fr = feat
    glow_dot(img, x0 + fx, y0 + fy, fr * 1.7, alpha * 0.85, (255, 214, 140))
    clock_face(d, x0 + fx, y0 + fy, fr, alpha, clock_p)


# ---- Great Britain (real coastline, baked) ----------------------------------
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
_gxs = [p[0] for p in GB]
_gys = [p[1] for p in GB]
GB_BOX = (min(_gxs), min(_gys), max(_gxs), max(_gys))
UK_CITIES = [
    ("EDINBURGH", (0.2620, 0.2160)),
    ("MANCHESTER", (0.2470, 0.5760)),
    ("BIRMINGHAM", (0.3120, 0.6820)),
    ("CARDIFF", (0.2180, 0.7900)),
    ("BRISTOL", (0.2780, 0.7830)),
]


def gb_project(cx, cy, size):
    x0, y0, x1, y1 = GB_BOX
    k = size / (y1 - y0)
    ox = cx - (x0 + x1) / 2 * k
    oy = cy - (y0 + y1) / 2 * k
    return lambda x, y: (ox + x * k, oy + y * k)


def draw_uk(img, d, cx, cy, size, alpha, p, spread, t):
    if alpha <= 0.01:
        return
    proj = gb_project(cx, cy, size)
    pts = [proj(x, y) for x, y in GB]
    # foil-filled landmass
    xs = [q[0] for q in pts]
    ys = [q[1] for q in pts]
    bx0, by0 = int(min(xs)) - 4, int(min(ys)) - 4
    bw, bh = int(max(xs) - min(xs)) + 8, int(max(ys) - min(ys)) + 8
    if p > 0.98 and bw > 0 and bh > 0:
        m = Image.new("L", (bw, bh), 0)
        ImageDraw.Draw(m).polygon([(q[0] - bx0, q[1] - by0) for q in pts],
                                  fill=88)
        paste_foil(img, m, (bx0, by0), alpha, shift=0.3)
    segs = len(pts) - 1
    drawn = p * segs
    for i in range(segs):
        if drawn <= i:
            break
        f = clamp01(drawn - i)
        x0, y0 = pts[i]
        x1, y1 = pts[i + 1]
        d.line([(x0, y0), (x0 + (x1 - x0) * f, y0 + (y1 - y0) * f)],
               fill=(*GOLD, int(235 * alpha)), width=3)
    if p < 0.94:
        return
    lx, ly = proj(*LONDON)
    for k, (name, pos) in enumerate(UK_CITIES):
        pk = clamp01(spread * len(UK_CITIES) - k)
        if pk <= 0:
            continue
        tx, ty = proj(*pos)
        mx = (lx + tx) / 2 + (ly - ty) * 0.22
        my = (ly + ty) / 2 + (tx - lx) * 0.22
        prev = None
        for j in range(19):
            u = (j / 18) * pk
            bx = (1 - u) ** 2 * lx + 2 * (1 - u) * u * mx + u * u * tx
            by = (1 - u) ** 2 * ly + 2 * (1 - u) * u * my + u * u * ty
            if prev:
                d.line([prev, (bx, by)],
                       fill=(*GOLD_LIGHT, int(150 * alpha)), width=2)
            prev = (bx, by)
        if pk > 0.97:
            d.ellipse([tx - 5, ty - 5, tx + 5, ty + 5],
                      fill=(*GOLD_LIGHT, int(240 * alpha)))
    pulse = (t * 0.8) % 1.0
    glow_dot(img, lx, ly, 16, alpha, (255, 220, 150))
    d.ellipse([lx - 8, ly - 8, lx + 8, ly + 8],
              fill=(*GOLD_LIGHT, int(255 * alpha)))
    rr = 14 + 34 * pulse
    d.ellipse([lx - rr, ly - rr, lx + rr, ly + rr],
              outline=(*GOLD_LIGHT, int(200 * alpha * (1 - pulse))), width=2)


# ---- Gift still life --------------------------------------------------------
GIFT_W, GIFT_H = 840, 600
BOTTLE_X, GIFT_BOX_X, CARD_X = 150, 430, 712
GIFT_BASE, CARD_Y = 556, 452
WINE = (122, 26, 42)
WINE_HI = (168, 44, 62)


def _bottle(md, cx, base, s):
    """Classic champagne silhouette: body, sloped shoulder, neck, capsule."""
    bw, nw = 54 * s, 19 * s
    body_top, neck_top = base - 236 * s, base - 404 * s
    left, right = [], []
    for i in range(13):
        f = i / 12
        y = body_top - (body_top - neck_top) * f
        wdt = bw + (nw - bw) * (f ** 0.62)
        left.append((cx - wdt, y))
        right.append((cx + wdt, y))
    pts = [(cx - bw, base), *left, (cx - nw, base - 430 * s),
           (cx + nw, base - 430 * s), *reversed(right), (cx + bw, base)]
    md.polygon(pts, fill=255)
    # capsule over the cork
    md.rectangle([cx - 24 * s, base - 452 * s, cx + 24 * s, base - 422 * s],
                 fill=255)


def _giftbox(md, cx, base, s):
    md.rectangle([cx - 148 * s, base - 196 * s, cx + 148 * s, base], fill=255)
    md.rectangle([cx - 168 * s, base - 250 * s, cx + 168 * s, base - 192 * s],
                 fill=255)


@lru_cache(maxsize=4)
def gift_mask(s10):
    s = s10 / 10.0
    m = Image.new("L", (int(GIFT_W * s), int(GIFT_H * s)), 0)
    md = ImageDraw.Draw(m)
    _bottle(md, BOTTLE_X * s, GIFT_BASE * s, s)
    _giftbox(md, GIFT_BOX_X * s, GIFT_BASE * s, s)
    md.rectangle([(CARD_X - 104) * s, (CARD_Y - 80) * s,
                  (CARD_X + 104) * s, (CARD_Y + 80) * s], fill=255)
    return m


def draw_gift(img, d, cx, cy, alpha, p, s=1.0):
    if alpha <= 0.01:
        return
    m = gift_mask(int(s * 10))
    mw, mh = m.size
    x0, y0 = int(cx - mw / 2), int(cy - mh / 2)
    halo = m.filter(ImageFilter.GaussianBlur(18)).point(
        lambda v: int(v * 0.38 * alpha))
    img.paste(Image.new("RGB", m.size, (176, 124, 50)), (x0, y0), halo)
    paste_foil(img, m, (x0, y0), alpha, shift=0.2)

    a = int(255 * alpha)
    bx, base = x0 + BOTTLE_X * s, y0 + GIFT_BASE * s
    gx = x0 + GIFT_BOX_X * s
    nx, ny = x0 + CARD_X * s, y0 + CARD_Y * s

    # bottle: dark label band, so the silhouette reads as a bottle
    d.rectangle([bx - 46 * s, base - 190 * s, bx + 46 * s, base - 70 * s],
                fill=(26, 20, 26, a))
    d.rectangle([bx - 46 * s, base - 190 * s, bx + 46 * s, base - 70 * s],
                outline=(*GOLD, a), width=max(2, int(3 * s)))
    d.line([(bx - 24 * s, base - 452 * s), (bx - 24 * s, base - 422 * s)],
           fill=(*GOLD_DEEP, a), width=max(2, int(3 * s)))
    d.line([(bx - 24 * s, base - 424 * s), (bx + 24 * s, base - 424 * s)],
           fill=(*GOLD_DEEP, a), width=max(2, int(3 * s)))

    # box: lid shadow line separates lid from body
    d.line([(gx - 148 * s, base - 194 * s), (gx + 148 * s, base - 194 * s)],
           fill=(92, 62, 24, a), width=max(2, int(4 * s)))

    # ribbon down the box, then the bow
    rp = ease_out(seg(p, 0.0, 0.5))
    if rp > 0:
        d.rectangle([gx - 15 * s, base - 250 * s,
                     gx + 15 * s, base - 250 * s + 250 * s * rp],
                    fill=(*WINE, a))
    if p > 0.45:
        bp = ease_out(seg(p, 0.45, 0.95))
        ly, lw, lh = base - 272 * s, 62 * s * bp, 34 * s * bp
        for sgn in (-1, 1):
            d.polygon([(gx, ly), (gx + sgn * lw, ly - lh),
                       (gx + sgn * lw * 0.92, ly + lh * 0.72)],
                      fill=(*WINE_HI, a))
            d.polygon([(gx, ly), (gx + sgn * lw * 0.52, ly + lh * 1.5),
                       (gx + sgn * lw * 0.86, ly + lh * 1.35)],
                      fill=(*WINE, a))
        d.ellipse([gx - 13 * s, ly - 13 * s, gx + 13 * s, ly + 13 * s],
                  fill=(*GOLD_LIGHT, a))

    # note card: dark inset, then handwriting that writes itself
    d.rectangle([nx - 88 * s, ny - 64 * s, nx + 88 * s, ny + 64 * s],
                fill=(24, 19, 24, a))
    for i, frac in enumerate((0.86, 0.62, 0.34)):
        rp = ease_out(seg(p, 0.3 + i * 0.2, 0.75 + i * 0.2))
        if rp <= 0:
            continue
        yy = ny - 34 * s + i * 34 * s
        d.line([(nx - 64 * s, yy), (nx - 64 * s + 128 * s * frac * rp, yy)],
               fill=(*GOLD, a), width=max(2, int(3 * s)))


# ---- Frame ------------------------------------------------------------------
def scene_alpha(t, sc, fade=0.55):
    s0, s1 = sc["start"], sc["start"] + sc["len"]
    if t < s0 or t >= s1:
        return 0.0, 0.0
    a_in = ease_out(seg(t, s0, s0 + fade))
    a_out = 1.0 - ease_in_out(seg(t, s1 - fade, s1))
    return a_in * a_out, t - s0


def render_frame(i, total):
    t = i / FPS
    base = Image.fromarray(SKY.copy())
    ov = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(ov)
    cx = W // 2

    light_shafts(d, t, 1.0)
    sparkles(d, t, 0.85)
    bubbles(d, t, 1.0)

    for sc in SCENES:
        a, lt = scene_alpha(t, sc)
        if a <= 0:
            continue
        key = sc["key"]
        ornate_frame(d, a)

        if key == "open":
            drift = 14 * math.sin(lt * 0.4)
            draw_skyline(base, d, 1290 + drift,
                         a * ease_out(seg(lt, 0.0, 1.6)),
                         reveal=ease_in_out(seg(lt, 0.1, 2.0)), s=1.0)
            ls_ctext(d, 210, "LONDON", F_LABEL, MUTED, a * 0.9, sp=16)
            p1 = ease_out(seg(lt, 1.0, 2.0))
            if p1 > 0:
                foil_ctext(base, 380, "THE GIFT", "display", a * p1,
                           dy=int(24 * (1 - p1)))
                foil_ctext(base, 500, "OF CHAMPAGNE", "display", a * p1,
                           dy=int(24 * (1 - p1)))
            rule_with_diamond(d, 660, int(220 * ease_in_out(
                seg(lt, 1.8, 2.6))), a)
            p2 = ease_out(seg(lt, 2.2, 3.0))
            ctext(d, 700, "delivered across the capital", F_SERIF_I,
                  MUTED, a * p2)

        elif key == "sameday":
            draw_big_ben(base, d, cx, 1250, a * ease_out(seg(lt, 0.0, 1.2)),
                         1.0, seg(lt, 0.4, 2.8))
            ls_ctext(d, 210, "SAME DAY  ·  LONDON", F_LABEL, GOLD, a, sp=13)
            p1 = ease_out(seg(lt, 1.2, 2.0))
            if p1 > 0:
                foil_ctext(base, 1330, "30–45", "hero", a * p1,
                           dy=int(20 * (1 - p1)))
            p2 = ease_out(seg(lt, 1.6, 2.4))
            ls_ctext(d, 1500, "MINUTES", F_LABEL_B, CREAM, a * p2, sp=17)
            rule_with_diamond(d, 1570, int(200 * ease_in_out(
                seg(lt, 2.0, 2.8))), a)

        elif key == "across":
            draw_skyline(base, d, 1180, a * ease_out(seg(lt, 0.0, 1.0)),
                         s=1.0)
            ls_ctext(d, 210, "EVERY POSTCODE", F_LABEL, GOLD, a, sp=14)
            # a delivery arc travelling across the skyline
            ap = ease_in_out(seg(lt, 0.7, 2.6))
            ax, ay, bx2, by2 = 190, 900, 900, 860
            mx, my = (ax + bx2) / 2, 560
            prev = None
            for j in range(29):
                u = (j / 28) * ap
                px = (1 - u) ** 2 * ax + 2 * (1 - u) * u * mx + u * u * bx2
                py = (1 - u) ** 2 * ay + 2 * (1 - u) * u * my + u * u * by2
                if prev:
                    d.line([prev, (px, py)],
                           fill=(*GOLD_LIGHT, int(190 * a)), width=3)
                prev = (px, py)
            if prev and ap > 0.02:
                glow_dot(base, prev[0], prev[1], 18, a)
                d.ellipse([prev[0] - 7, prev[1] - 7, prev[0] + 7, prev[1] + 7],
                          fill=(*GOLD_LIGHT, int(255 * a)))
            p1 = ease_out(seg(lt, 1.4, 2.2))
            if p1 > 0:
                foil_ctext(base, 1270, "MAYFAIR", "name", a * p1)
            p2 = ease_out(seg(lt, 1.7, 2.5))
            ctext(d, 1362, "to", F_SERIF_I, MUTED, a * p2)
            p3 = ease_out(seg(lt, 2.0, 2.8))
            if p3 > 0:
                foil_ctext(base, 1424, "CANARY WHARF", "name", a * p3)
            p4 = ease_out(seg(lt, 2.4, 3.2))
            ls_ctext(d, 1545, "AROUND THE CLOCK", F_LABEL, MUTED, a * p4,
                     sp=12)

        elif key == "ukwide":
            ls_ctext(d, 210, "UK-WIDE  ·  NEXT DAY", F_LABEL, GOLD, a, sp=13)
            draw_uk(base, d, cx, 760, 660, a, seg(lt, 0.1, 1.9),
                    seg(lt, 1.9, 3.2), lt)
            p1 = ease_out(seg(lt, 2.1, 2.9))
            if p1 > 0:
                foil_ctext(base, 1240, "ANYWHERE", "display_l", a * p1,
                           dy=int(18 * (1 - p1)))
                foil_ctext(base, 1355, "IN BRITAIN", "display_l", a * p1,
                           dy=int(18 * (1 - p1)))
            rule_with_diamond(d, 1500, int(200 * ease_in_out(
                seg(lt, 2.7, 3.4))), a)
            p2 = ease_out(seg(lt, 2.9, 3.6))
            ctext(d, 1540, "by tomorrow", F_SERIF_I, MUTED, a * p2)

        elif key == "presented":
            ls_ctext(d, 210, "PRESENTED, NOT POSTED", F_LABEL, GOLD, a, sp=11)
            draw_gift(base, d, cx, 740, a * ease_out(seg(lt, 0.0, 1.0)),
                      seg(lt, 0.5, 2.6), s=1.0)
            items = ["Gift boxes & gift sets",
                     "A note in your words",
                     "Chilled, wrapped, delivered"]
            y = 1180
            for k, it in enumerate(items):
                pk = ease_out(seg(lt, 1.3 + k * 0.36, 2.0 + k * 0.36))
                if pk <= 0:
                    continue
                ctext(d, y, it, F_NAME, CREAM, a * pk, dy=int(14 * (1 - pk)))
                y += 118

        elif key == "names":
            ls_ctext(d, 210, "THE HOUSES", F_LABEL, GOLD, a, sp=15)
            rule_with_diamond(d, 300, int(180 * ease_in_out(
                seg(lt, 0.1, 0.9))), a)
            names = ["Moët & Chandon", "Veuve Clicquot", "Dom Pérignon",
                     "Bollinger", "Krug", "Armand de Brignac"]
            y = 430
            for k, nm in enumerate(names):
                pk = ease_out(seg(lt, 0.5 + k * 0.3, 1.2 + k * 0.3))
                if pk > 0:
                    foil_ctext(base, y, nm, "name", a * pk,
                               dy=int(12 * (1 - pk)), shift=k * 0.07)
                y += 104
            rule_with_diamond(d, y + 20, int(180 * ease_in_out(
                seg(lt, 2.6, 3.3))), a)
            draw_skyline(base, d, 1520, a * 0.55 * ease_out(
                seg(lt, 0.4, 1.6)), s=0.7)

        elif key == "cta":
            draw_skyline(base, d, 1560, a * 0.62 * ease_out(
                seg(lt, 0.0, 1.2)), s=0.8)
            p1 = ease_out(seg(lt, 0.2, 1.0))
            if p1 > 0:
                foil_ctext(base, 420, "DRINKS HOUSE", "display", a * p1,
                           dy=int(20 * (1 - p1)))
                foil_ctext(base, 545, "247", "hero", a * p1,
                           dy=int(20 * (1 - p1)))
            rule_with_diamond(d, 760, int(230 * ease_in_out(
                seg(lt, 0.9, 1.6))), a)
            p2 = ease_out(seg(lt, 1.1, 1.8))
            ctext(d, 800, "London's champagne, delivered.", F_SERIF_I,
                  CREAM, a * p2)
            p3 = ease_out(seg(lt, 1.4, 2.1))
            ctext(d, 910, "drinkshouse247.co.uk", F_MONO, CREAM, a * p3)
            ctext(d, 985, "+44 20 3488 3266", F_MONO_S, GOLD, a * p3)
            p4 = ease_out(seg(lt, 1.8, 2.5))
            ls_ctext(d, 1080, "SAME DAY LONDON  ·  NEXT DAY UK", F_LABEL,
                     GOLD, a * p4, sp=8)
            ls_ctext(d, 1150, "OPEN 24/7", F_LABEL_B, CREAM, a * p4, sp=13)

        if key != "cta":
            caption(d, lt, sc, a)
        ctext(d, H - 108, "18+ · Please drink responsibly", F_TINY, MUTED,
              a * 0.65)

    out = Image.alpha_composite(base.convert("RGBA"), ov)

    total_s = total / FPS
    fade = ease_out(seg(t, 0.0, 0.7)) * (
        1.0 - ease_in_out(seg(t, total_s - 0.8, total_s)))
    if fade < 1.0:
        black = Image.new("RGBA", (W, H), (0, 0, 0, int(255 * (1 - fade))))
        out = Image.alpha_composite(out, black)

    return np.asarray(out.convert("RGB"))


FONTS = {
    "display": F_DISPLAY,
    "display_l": F_DISPLAY_L,
    "hero": F_HERO,
    "name": F_NAME,
    "label": F_LABEL,
}


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
        if i % 60 == 0:
            print(f"  frame {i}/{total}")
    proc.stdin.close()
    rc = proc.wait()
    if rc != 0:
        raise SystemExit(f"ffmpeg failed with code {rc}")
    print("Done:", OUT)


if __name__ == "__main__":
    main()
