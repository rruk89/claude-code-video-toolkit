#!/usr/bin/env python3
"""
"5 Drinks Facts That Sound Fake (But Aren't)" — vertical short for
Drinks House 247.

Pure-Python renderer: PIL draws each frame, frames are piped to a bundled
ffmpeg (via imageio-ffmpeg) and encoded to H.264 MP4.

    pip install imageio-ffmpeg numpy pillow
    python render.py

Output: output/alcohol-facts-short.mp4  (1080x1920, 30fps, ~31.5s)
"""

import math
import os
import subprocess

import imageio_ffmpeg
import numpy as np
from PIL import Image, ImageDraw, ImageFont

# ---- Config -----------------------------------------------------------------
W, H = 1080, 1920
FPS = 30
DURATION = 31.5
TOTAL = int(FPS * DURATION)
OUT = os.path.join(os.path.dirname(__file__), "output",
                   "alcohol-facts-short.mp4")

BG_TOP = (10, 9, 14)
BG_BOTTOM = (30, 20, 22)
GOLD = (212, 175, 85)
CHAMPAGNE = (245, 222, 150)
INK = (246, 243, 236)
MUTED = (172, 163, 150)
AMBER = (198, 122, 46)
WINE = (128, 32, 56)
WOOD = (74, 48, 32)
TOAST_C = (214, 164, 96)
CRUST = (150, 100, 52)

FONT_DIR = "/usr/share/fonts/truetype"


def font(path, size):
    return ImageFont.truetype(os.path.join(FONT_DIR, path), size)


F_HUGE = font("dejavu/DejaVuSans-Bold.ttf", 190)
F_BIG = font("dejavu/DejaVuSans-Bold.ttf", 128)
F_TITLE = font("dejavu/DejaVuSans-Bold.ttf", 104)
F_H2 = font("dejavu/DejaVuSans-Bold.ttf", 76)
F_FACT = font("dejavu/DejaVuSans.ttf", 54)
F_SMALL = font("dejavu/DejaVuSans.ttf", 38)
F_H2S = font("dejavu/DejaVuSans-Bold.ttf", 62)
F_MONO = font("dejavu/DejaVuSansMono-Bold.ttf", 58)
F_MONO_S = font("dejavu/DejaVuSansMono.ttf", 42)


# ---- Easing -----------------------------------------------------------------
def ease_out(t):
    return 1 - (1 - t) ** 3


def ease_in(t):
    return t * t


def ease_in_out(t):
    return 3 * t * t - 2 * t * t * t


def clamp01(x):
    return max(0.0, min(1.0, x))


def seg(t, start, end):
    if end <= start:
        return 1.0 if t >= end else 0.0
    return clamp01((t - start) / (end - start))


def scene(t, s0, s1, fade=0.4):
    if t < s0 or t >= s1:
        return 0.0, 0.0
    a_in = ease_out(seg(t, s0, s0 + fade))
    a_out = 1.0 - ease_in_out(seg(t, s1 - fade, s1))
    return a_in * a_out, t - s0


# ---- Background -------------------------------------------------------------
def make_gradient():
    top = np.array(BG_TOP, dtype=np.float32)
    bot = np.array(BG_BOTTOM, dtype=np.float32)
    ramp = np.linspace(0, 1, H, dtype=np.float32)[:, None]
    grad = (top[None, :] * (1 - ramp) + bot[None, :] * ramp)
    return np.repeat(grad[:, None, :], W, axis=1).astype(np.uint8)


BG = make_gradient()


def draw_bubbles(d, t, alpha_scale=1.0):
    for k in range(26):
        px = (math.sin(k * 12.9898) * 43758.5453) % 1.0
        speed = 90 + 160 * ((math.sin(k * 78.233) * 12345.678) % 1.0)
        r = 3 + 9 * ((math.sin(k * 39.425) * 9876.543) % 1.0)
        phase = ((math.sin(k * 3.7) * 1234.56) % 1.0)
        x = int(px * W + 26 * math.sin(t * 0.8 + k))
        y = H - int(((t * speed + phase * H * 2) % (H + 200)) - 100)
        a = int(46 * alpha_scale * (0.4 + 0.6 * ((k * 7) % 5) / 4))
        if a <= 0:
            continue
        d.ellipse([x - r, y - r, x + r, y + r],
                  outline=(*CHAMPAGNE, a), width=2)


def draw_glow(d, cx, cy, radius, alpha):
    for k in range(6, 0, -1):
        r = radius * k / 6
        a = int(alpha * (k / 6) * 0.5)
        d.ellipse([cx - r, cy - r, cx + r, cy + r],
                  fill=(GOLD[0], GOLD[1], GOLD[2], a))


def ctext(d, y, text, fnt, color, alpha, dy=0):
    tw = d.textlength(text, font=fnt)
    d.text(((W - tw) / 2, y + dy), text, font=fnt,
           fill=(*color, int(255 * alpha)))


def gold_rule(d, y, half, alpha):
    d.line([(W / 2 - half, y), (W / 2 + half, y)],
           fill=(*GOLD, int(255 * alpha)), width=4)


def badge(d, num, alpha):
    """Big gold scene number at the top."""
    p = ease_out(alpha)
    ctext(d, 210, num, F_BIG, GOLD, alpha, dy=int(24 * (1 - p)))
    gold_rule(d, 400, int(120 * alpha), alpha * 0.8)


def sparkle(d, x, y, r, color, alpha):
    a = int(255 * alpha)
    d.line([(x - r, y), (x + r, y)], fill=(*color, a), width=3)
    d.line([(x, y - r), (x, y + r)], fill=(*color, a), width=3)


# ---- Scene visuals ----------------------------------------------------------
def draw_flute(d, cx, top, height, alpha, fill_level=0.65):
    a = int(255 * alpha)
    bowl_h = int(height * 0.55)
    bw_top, bw_bot = int(height * 0.155), int(height * 0.10)
    fill_top = top + int(bowl_h * (1 - fill_level * 0.9))

    def bw_at(y):
        return bw_top + (bw_bot - bw_top) * (y - top) / bowl_h

    d.polygon([
        (cx - int(bw_at(fill_top)) + 6, fill_top),
        (cx + int(bw_at(fill_top)) - 6, fill_top),
        (cx + bw_bot - 5, top + bowl_h - 4),
        (cx - bw_bot + 5, top + bowl_h - 4),
    ], fill=(CHAMPAGNE[0], CHAMPAGNE[1], CHAMPAGNE[2], int(90 * alpha)))
    d.polygon([
        (cx - bw_top, top),
        (cx + bw_top, top),
        (cx + bw_bot, top + bowl_h),
        (cx - bw_bot, top + bowl_h),
    ], outline=(*GOLD, a), width=5)
    stem_y = top + bowl_h
    base_y = top + height
    d.line([(cx, stem_y), (cx, base_y - 10)], fill=(*GOLD, a), width=5)
    d.line([(cx - int(bw_top * 0.65), base_y),
            (cx + int(bw_top * 0.65), base_y)], fill=(*GOLD, a), width=6)


def draw_tumbler(d, cx, top, alpha, t):
    """Whisky tumbler with amber fill."""
    a = int(255 * alpha)
    w, h = 300, 240
    x0, y0 = cx - w // 2, top
    x1, y1 = cx + w // 2, top + h
    # amber whisky
    d.rounded_rectangle([x0 + 10, y0 + h * 0.45, x1 - 10, y1 - 10],
                        radius=18,
                        fill=(AMBER[0], AMBER[1], AMBER[2],
                              int(150 * alpha)))
    # gentle liquid shimmer line
    sy = y0 + h * 0.45 + 4 * math.sin(t * 2.0)
    d.line([(x0 + 16, sy), (x1 - 16, sy)],
           fill=(*CHAMPAGNE, int(120 * alpha)), width=3)
    # glass outline
    d.rounded_rectangle([x0, y0, x1, y1], radius=22,
                        outline=(*GOLD, a), width=5)
    # ice cube
    d.rounded_rectangle([cx - 40, y0 + h * 0.5, cx + 30, y0 + h * 0.5 + 62],
                        radius=10, outline=(*INK, int(150 * alpha)), width=4)


def draw_barrel(d, cx, top, alpha, t):
    """Whisky barrel with golden mist rising (the angels' share)."""
    a = int(255 * alpha)
    w, h = 300, 320
    x0, y0 = cx - w // 2, top
    x1, y1 = cx + w // 2, top + h
    d.rounded_rectangle([x0, y0, x1, y1], radius=46,
                        fill=(WOOD[0], WOOD[1], WOOD[2], int(220 * alpha)),
                        outline=(*GOLD, a), width=5)
    # hoops
    for fy in (0.18, 0.5, 0.82):
        y = y0 + h * fy
        d.line([(x0 + 8, y), (x1 - 8, y)], fill=(*GOLD, int(a * 0.8)),
               width=6)
    # rising golden mist
    for k in range(9):
        ph = ((t * 0.35 + k * 0.13) % 1.0)
        my = y0 - 30 - ph * 260
        mx = cx - 70 + (k % 3) * 70 + 26 * math.sin(t * 1.4 + k * 2.1)
        mr = 26 + 14 * ph
        ma = int(70 * alpha * (1 - ph))
        d.ellipse([mx - mr, my - mr * 0.6, mx + mr, my + mr * 0.6],
                  fill=(CHAMPAGNE[0], CHAMPAGNE[1], CHAMPAGNE[2], ma))
    # sparkles among the mist
    for k in range(4):
        ph = ((t * 0.5 + k * 0.27) % 1.0)
        sx = cx - 90 + k * 60 + 18 * math.sin(t * 2 + k)
        sy = y0 - 50 - ph * 230
        sparkle(d, sx, sy, 8, GOLD, alpha * (1 - ph))


def draw_wine_glass(d, cx, rim_y, alpha, toast_p, t):
    """Wine glass; a piece of toast drops in as toast_p goes 0->1 (>1 landed)."""
    a = int(255 * alpha)
    bowl_w, bowl_h = 300, 200
    bx0, bx1 = cx - bowl_w // 2, cx + bowl_w // 2
    wine_y = rim_y + int(bowl_h * 0.18)  # flat wine surface
    # wine: bottom half of an ellipse centered on the surface line
    d.pieslice([bx0 + 14, wine_y - int(bowl_h * 0.78),
                bx1 - 14, wine_y + int(bowl_h * 0.78)],
               0, 180, fill=(WINE[0], WINE[1], WINE[2], int(210 * alpha)))
    # bowl: bottom half-ellipse hanging from the rim
    d.arc([bx0, rim_y - bowl_h, bx1, rim_y + bowl_h], 0, 180,
          fill=(*GOLD, a), width=5)
    d.line([(bx0, rim_y), (bx1, rim_y)], fill=(*GOLD, a), width=5)
    # stem + base
    stem_top = rim_y + bowl_h
    d.line([(cx, stem_top), (cx, stem_top + 120)], fill=(*GOLD, a), width=5)
    d.line([(cx - 80, stem_top + 130), (cx + 80, stem_top + 130)],
           fill=(*GOLD, a), width=6)
    # toast
    if toast_p > 0:
        ta = int(255 * alpha)
        tx = cx - 45
        if toast_p < 1.0:
            drop = ease_in(toast_p)
            ty = int(-140 + drop * (wine_y - 60 + 140))
            d.rounded_rectangle([tx, ty, tx + 90, ty + 80], radius=16,
                                fill=(TOAST_C[0], TOAST_C[1], TOAST_C[2], ta),
                                outline=(*CRUST, ta), width=6)
        else:
            # landed: half-sunk at the wine surface
            d.rounded_rectangle([tx, wine_y - 34, tx + 90, wine_y + 14],
                                radius=12,
                                fill=(TOAST_C[0], TOAST_C[1], TOAST_C[2], ta),
                                outline=(*CRUST, ta), width=6)
            sp = clamp01((toast_p - 1.0) * 2.0)
            if sp < 1.0:
                sa = alpha * (1 - sp)
                r = 16 + 40 * sp
                for sx in (cx - 80, cx + 80):
                    d.arc([sx - r, wine_y - 24 - r, sx + r, wine_y - 24 + r],
                          210, 330, fill=(*WINE, int(220 * sa)), width=5)


def draw_cork_flight(d, alpha, p, t):
    """Cork flying across the frame with a golden trail + speed gauge."""
    if p <= 0:
        return
    fp = clamp01(p)
    x = int(-120 + fp * (W + 240))
    y = int(760 - 150 * math.sin(math.pi * fp))
    # trail
    for k in range(10):
        tp = fp - k * 0.045
        if tp <= 0:
            continue
        txp = int(-120 + tp * (W + 240))
        typ = int(760 - 150 * math.sin(math.pi * tp))
        ta = int(120 * alpha * (1 - k / 10))
        tr = 12 - k
        if tr < 3:
            tr = 3
        d.ellipse([txp - tr, typ - tr, txp + tr, typ + tr],
                  fill=(GOLD[0], GOLD[1], GOLD[2], ta))
    # cork body (tan with gold band)
    a = int(255 * alpha)
    d.rounded_rectangle([x - 38, y - 26, x + 38, y + 26], radius=12,
                        fill=(TOAST_C[0], TOAST_C[1], TOAST_C[2], a),
                        outline=(*CRUST, a), width=4)
    d.line([(x - 10, y - 26), (x - 10, y + 26)], fill=(*GOLD, a), width=6)


def draw_gauge(d, cx, cy, r, progress, alpha):
    """Semicircular speedometer sweeping to `progress` (0..1)."""
    a = int(255 * alpha)
    d.arc([cx - r, cy - r, cx + r, cy + r], 180, 360,
          fill=(*GOLD, int(a * 0.5)), width=8)
    sweep = 180 * ease_in_out(progress)
    if sweep > 2:
        d.arc([cx - r, cy - r, cx + r, cy + r], 180, 180 + sweep,
              fill=(*CHAMPAGNE, a), width=10)
    ang = math.radians(180 + sweep)
    d.line([(cx, cy), (cx + (r - 34) * math.cos(ang),
                       cy + (r - 34) * math.sin(ang))],
           fill=(*INK, a), width=7)
    d.ellipse([cx - 9, cy - 9, cx + 9, cy + 9], fill=(*GOLD, a))


# ---- Frame ------------------------------------------------------------------
S_HOOK = (0.0, 3.2)
S_F1 = (3.2, 8.2)
S_F2 = (8.2, 13.2)
S_F3 = (13.2, 18.2)
S_F4 = (18.2, 23.2)
S_F5 = (23.2, 27.2)
S_OUT = (27.2, 31.5)


def render_frame(i):
    t = i / FPS
    img = Image.fromarray(BG.copy())
    d = ImageDraw.Draw(img, "RGBA")
    cx = W // 2

    draw_bubbles(d, t)

    # ---- HOOK
    a, lt = scene(t, *S_HOOK, fade=0.3)
    if a > 0:
        p1 = ease_out(seg(lt, 0.05, 0.5))
        ctext(d, 640, "5 DRINKS FACTS", F_TITLE, INK, a * p1,
              dy=int(-50 * (1 - p1)))
        p2 = ease_out(seg(lt, 0.45, 0.95))
        ctext(d, 790, "THAT SOUND FAKE...", F_H2, GOLD, a * p2,
              dy=int(40 * (1 - p2)))
        p3 = ease_out(seg(lt, 1.3, 1.8))
        pulse = 1 + 0.03 * math.sin(lt * 6)
        f_but = font("dejavu/DejaVuSans-Bold.ttf", int(76 * pulse))
        tw = d.textlength("...BUT AREN'T", font=f_but)
        d.text(((W - tw) / 2, 1010), "...BUT AREN'T", font=f_but,
               fill=(*INK, int(255 * a * p3)))
        gold_rule(d, 1180, int(200 * ease_in_out(seg(lt, 1.6, 2.2))), a)

    # ---- FACT 01: 49 million bubbles
    a, lt = scene(t, *S_F1)
    if a > 0:
        badge(d, "01", a)
        draw_glow(d, cx, 660, 330, 55 * a)
        pf = ease_out(seg(lt, 0.2, 1.0))
        draw_flute(d, cx, 480 - int(24 * (1 - pf)), 380, a * pf)
        # extra bubbles streaming inside/above the flute
        for k in range(10):
            ph = ((lt * 0.6 + k * 0.1) % 1.0)
            bx = cx - 30 + (k % 5) * 15 + 8 * math.sin(lt * 3 + k)
            by = 900 - ph * 330
            br = 3 + (k % 3) * 2
            d.ellipse([bx - br, by - br, bx + br, by + br],
                      outline=(*CHAMPAGNE, int(160 * a * (1 - ph))), width=2)
        # ticking counter
        cnt = int(49_000_000 * ease_out(seg(lt, 0.5, 2.6)))
        ctext(d, 980, f"{cnt:,}", F_MONO, GOLD, a * ease_out(seg(lt, 0.4, 1.0)))
        p1 = ease_out(seg(lt, 0.7, 1.4))
        ctext(d, 1180, "A bottle of champagne holds", F_FACT, INK, a * p1)
        p2 = ease_out(seg(lt, 1.0, 1.7))
        ctext(d, 1280, "~49 MILLION BUBBLES", F_H2, GOLD, a * p2)

    # ---- FACT 02: water of life
    a, lt = scene(t, *S_F2)
    if a > 0:
        badge(d, "02", a)
        draw_glow(d, cx, 640, 320, 50 * a)
        pf = ease_out(seg(lt, 0.2, 1.0))
        draw_tumbler(d, cx, 520 - int(24 * (1 - pf)), a * pf, t)
        # gaelic morphing into english above the glass
        p_ga = ease_out(seg(lt, 0.6, 1.3)) * (1 - ease_in_out(seg(lt, 2.0, 2.5)))
        if p_ga > 0.01:
            ctext(d, 870, "uisge beatha", F_FACT, CHAMPAGNE, a * p_ga)
        p_en = ease_out(seg(lt, 2.6, 3.2))
        if p_en > 0.01:
            ctext(d, 870, "water of life", F_FACT, CHAMPAGNE, a * p_en)
        p1 = ease_out(seg(lt, 0.9, 1.6))
        ctext(d, 1180, "Whisky literally means", F_FACT, INK, a * p1)
        p2 = ease_out(seg(lt, 1.2, 1.9))
        ctext(d, 1280, "'WATER OF LIFE'", F_H2, GOLD, a * p2)
        p3 = ease_out(seg(lt, 1.6, 2.3))
        ctext(d, 1420, "from the Gaelic - uisge beatha", F_SMALL, MUTED,
              a * p3)

    # ---- FACT 03: angels' share
    a, lt = scene(t, *S_F3)
    if a > 0:
        badge(d, "03", a)
        draw_glow(d, cx, 680, 320, 50 * a)
        pf = ease_out(seg(lt, 0.2, 1.0))
        draw_barrel(d, cx, 560 - int(24 * (1 - pf)), a * pf, lt)
        p1 = ease_out(seg(lt, 0.8, 1.5))
        ctext(d, 1130, "Distillers lose ~2% of barrel", F_FACT, INK, a * p1)
        ctext(d, 1210, "whisky to evaporation each year", F_FACT, INK,
              a * p1)
        p2 = ease_out(seg(lt, 1.4, 2.1))
        ctext(d, 1340, "THE ANGELS' SHARE", F_H2, GOLD, a * p2)

    # ---- FACT 04: toasting
    a, lt = scene(t, *S_F4)
    if a > 0:
        badge(d, "04", a)
        draw_glow(d, cx, 660, 320, 50 * a)
        pf = ease_out(seg(lt, 0.2, 1.0))
        toast_p = seg(lt, 1.0, 1.7) + clamp01((lt - 1.7) * 2.5) * 0.0
        # toast_p runs 0..1 during the drop; >1 = landed
        tp = seg(lt, 1.0, 1.7)
        if lt >= 1.7:
            tp = 1.0 + (lt - 1.7)
        draw_wine_glass(d, cx, 560 - int(24 * (1 - pf)), a * pf, tp, lt)
        p1 = ease_out(seg(lt, 0.6, 1.3))
        ctext(d, 1130, "'Toasting' comes from real toast:", F_FACT, INK,
              a * p1)
        p2 = ease_out(seg(lt, 1.0, 1.7))
        ctext(d, 1210, "spiced bread dropped into wine", F_FACT, INK,
              a * p2)
        p3 = ease_out(seg(lt, 1.5, 2.2))
        ctext(d, 1350, "TO IMPROVE ITS FLAVOUR", F_H2S, GOLD, a * p3)
        p4 = ease_out(seg(lt, 1.9, 2.6))
        ctext(d, 1470, "1500s England", F_SMALL, MUTED, a * p4)

    # ---- FACT 05: flying cork
    a, lt = scene(t, *S_F5)
    if a > 0:
        badge(d, "05", a)
        cork_p = seg(lt, 0.5, 2.2)
        draw_cork_flight(d, a, cork_p, lt)
        draw_gauge(d, cx, 1020, 150, seg(lt, 0.5, 2.0), a)
        kmh = int(40 * ease_in_out(seg(lt, 0.5, 2.0)))
        ctext(d, 1060, f"{kmh} km/h", F_MONO, GOLD, a * ease_out(seg(lt, 0.4, 1.0)))
        p1 = ease_out(seg(lt, 0.7, 1.4))
        ctext(d, 1250, "A champagne cork can fly at", F_FACT, INK, a * p1)
        p2 = ease_out(seg(lt, 1.0, 1.7))
        ctext(d, 1350, "UP TO 40 KM/H", F_H2, GOLD, a * p2)

    # ---- OUTRO / CTA
    a, lt = scene(t, *S_OUT, fade=0.5)
    if a > 0:
        draw_glow(d, cx, 820, 420, 65 * a)
        p0 = ease_out(seg(lt, 0.1, 0.7))
        ctext(d, 420, "Thirsty for more?", F_H2, CHAMPAGNE, a * p0)
        p1 = ease_out(seg(lt, 0.5, 1.2))
        ctext(d, 640, "DRINKS HOUSE", F_TITLE, INK, a * p1,
              dy=int(30 * (1 - p1)))
        ctext(d, 760, "247", F_BIG, GOLD, a * p1, dy=int(30 * (1 - p1)))
        gold_rule(d, 960, int(220 * ease_in_out(seg(lt, 0.9, 1.5))), a)
        p2 = ease_out(seg(lt, 1.1, 1.8))
        ctext(d, 1010, "Premium drinks delivered across", F_FACT, INK,
              a * p2)
        ctext(d, 1090, "London in 30-45 minutes", F_FACT, INK, a * p2)
        p3 = ease_out(seg(lt, 1.4, 2.1))
        ctext(d, 1230, "drinkshouse247.co.uk", F_MONO, INK, a * p3)
        ctext(d, 1340, "+44 20 3488 3266", F_MONO_S, GOLD, a * p3)
        p4 = ease_out(seg(lt, 1.7, 2.4))
        ctext(d, 1450, "Open 24/7", F_H2, GOLD, a * p4)
        p5 = ease_out(seg(lt, 2.0, 2.7))
        ctext(d, 1770, "18+ · Please drink responsibly", F_SMALL, MUTED,
              a * p5 * 0.9)

    # Fade in/out
    fade = ease_out(seg(t, 0.0, 0.35)) * (
        1.0 - ease_in_out(seg(t, DURATION - 0.6, DURATION)))
    if fade < 1.0:
        ov = Image.new("RGBA", (W, H), (0, 0, 0, int(255 * (1 - fade))))
        img = Image.alpha_composite(img.convert("RGBA"), ov)

    return np.asarray(img.convert("RGB"))


def main():
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    cmd = [
        ffmpeg, "-y",
        "-f", "rawvideo", "-pix_fmt", "rgb24",
        "-s", f"{W}x{H}", "-r", str(FPS),
        "-i", "-",
        "-an",
        "-c:v", "libx264", "-preset", "medium", "-crf", "19",
        "-pix_fmt", "yuv420p", "-movflags", "+faststart",
        OUT,
    ]
    print(f"Rendering {TOTAL} frames -> {OUT}")
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE,
                            stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL)
    for i in range(TOTAL):
        proc.stdin.write(render_frame(i).tobytes())
        if i % 90 == 0:
            print(f"  frame {i}/{TOTAL}")
    proc.stdin.close()
    rc = proc.wait()
    if rc != 0:
        raise SystemExit(f"ffmpeg failed with code {rc}")
    print("Done:", OUT)


if __name__ == "__main__":
    main()
