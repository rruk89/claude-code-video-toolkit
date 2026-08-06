#!/usr/bin/env python3
"""
Drinks House 247 — informational vertical reel (9:16).

Pure-Python renderer: PIL draws each frame, frames are piped to a bundled
ffmpeg (via imageio-ffmpeg) and encoded to H.264 MP4.

    pip install imageio-ffmpeg numpy pillow
    python render.py

Output: output/drinks-house-247-reel.mp4  (1080x1920, 30fps, ~21s)
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
DURATION = 21.0
TOTAL = int(FPS * DURATION)
OUT = os.path.join(os.path.dirname(__file__), "output",
                   "drinks-house-247-reel.mp4")

# Luxe dark + champagne gold palette
BG_TOP = (10, 9, 14)
BG_BOTTOM = (30, 20, 22)
GOLD = (212, 175, 85)
CHAMPAGNE = (245, 222, 150)
INK = (246, 243, 236)
MUTED = (172, 163, 150)

FONT_DIR = "/usr/share/fonts/truetype"


def font(path, size):
    return ImageFont.truetype(os.path.join(FONT_DIR, path), size)


F_HUGE = font("dejavu/DejaVuSans-Bold.ttf", 190)
F_BIG = font("dejavu/DejaVuSans-Bold.ttf", 128)
F_TITLE = font("dejavu/DejaVuSans-Bold.ttf", 104)
F_H2 = font("dejavu/DejaVuSans-Bold.ttf", 76)
F_BODY = font("dejavu/DejaVuSans.ttf", 48)
F_SMALL = font("dejavu/DejaVuSans.ttf", 38)
F_MONO = font("dejavu/DejaVuSansMono-Bold.ttf", 52)
F_MONO_S = font("dejavu/DejaVuSansMono.ttf", 42)


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


def scene(t, s0, s1, fade=0.45):
    """Returns (alpha, local_t) for a scene active on [s0, s1)."""
    if t < s0 or t >= s1:
        return 0.0, 0.0
    a_in = ease_out(seg(t, s0, s0 + fade))
    a_out = 1.0 - ease_in_out(seg(t, s1 - fade, s1))
    return a_in * a_out, t - s0


# ---- Static background gradient ---------------------------------------------
def make_gradient():
    top = np.array(BG_TOP, dtype=np.float32)
    bot = np.array(BG_BOTTOM, dtype=np.float32)
    ramp = np.linspace(0, 1, H, dtype=np.float32)[:, None]
    grad = (top[None, :] * (1 - ramp) + bot[None, :] * ramp)
    return np.repeat(grad[:, None, :], W, axis=1).astype(np.uint8)


BG = make_gradient()


# ---- Decorative elements ----------------------------------------------------
def draw_bubbles(d, t, alpha_scale=1.0):
    """Champagne bubbles rising continuously, deterministic per index."""
    for k in range(26):
        # pseudo-random but deterministic parameters per bubble
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


def draw_flute(d, cx, top, height, alpha):
    """Simple champagne flute, gold outline, partially filled."""
    a = int(255 * alpha)
    bowl_h = int(height * 0.55)
    bw_top, bw_bot = int(height * 0.155), int(height * 0.10)
    # fill (champagne) inside the bowl, lower 2/3
    fill_top = top + int(bowl_h * 0.35)

    def bw_at(y):
        return bw_top + (bw_bot - bw_top) * (y - top) / bowl_h

    d.polygon([
        (cx - int(bw_at(fill_top)) + 6, fill_top),
        (cx + int(bw_at(fill_top)) - 6, fill_top),
        (cx + bw_bot - 5, top + bowl_h - 4),
        (cx - bw_bot + 5, top + bowl_h - 4),
    ], fill=(CHAMPAGNE[0], CHAMPAGNE[1], CHAMPAGNE[2], int(90 * alpha)))
    # bowl outline
    d.polygon([
        (cx - bw_top, top),
        (cx + bw_top, top),
        (cx + bw_bot, top + bowl_h),
        (cx - bw_bot, top + bowl_h),
    ], outline=(*GOLD, a), width=5)
    # stem + base
    stem_y = top + bowl_h
    base_y = top + height
    d.line([(cx, stem_y), (cx, base_y - 10)], fill=(*GOLD, a), width=5)
    d.line([(cx - int(bw_top * 0.65), base_y), (cx + int(bw_top * 0.65), base_y)],
           fill=(*GOLD, a), width=6)
    # tiny bubbles in the glass
    for k in range(5):
        bx = cx - 18 + (k * 9) % 36
        by = fill_top + 14 + ((k * 37) % (bowl_h - int(bowl_h * 0.4)))
        d.ellipse([bx - 3, by - 3, bx + 3, by + 3],
                  outline=(*CHAMPAGNE, int(150 * alpha)), width=1)


def draw_clock(d, cx, cy, r, progress, alpha):
    a = int(255 * alpha)
    d.ellipse([cx - r, cy - r, cx + r, cy + r], outline=(*GOLD, a), width=6)
    # ticks
    for k in range(12):
        ang = k * math.pi / 6
        x1 = cx + (r - 18) * math.sin(ang)
        y1 = cy - (r - 18) * math.cos(ang)
        x2 = cx + (r - 34) * math.sin(ang)
        y2 = cy - (r - 34) * math.cos(ang)
        d.line([(x1, y1), (x2, y2)], fill=(*GOLD, int(a * 0.7)), width=4)
    # sweeping arc
    sweep = 360 * ease_in_out(progress)
    if sweep > 2:
        d.arc([cx - r + 14, cy - r + 14, cx + r - 14, cy + r - 14],
              start=-90, end=-90 + sweep, fill=(*CHAMPAGNE, a), width=10)
    # hands
    ang = math.radians(-90 + sweep)
    d.line([(cx, cy), (cx + (r - 60) * math.cos(ang),
                       cy + (r - 60) * math.sin(ang))],
           fill=(*INK, a), width=7)
    d.line([(cx, cy), (cx, cy - r * 0.42)], fill=(*INK, int(a * 0.8)), width=7)
    d.ellipse([cx - 8, cy - 8, cx + 8, cy + 8], fill=(*GOLD, a))


def ctext(d, y, text, fnt, color, alpha, dy=0):
    tw = d.textlength(text, font=fnt)
    d.text(((W - tw) / 2, y + dy), text, font=fnt,
           fill=(*color, int(255 * alpha)))


def gold_rule(d, y, half, alpha):
    d.line([(W / 2 - half, y), (W / 2 + half, y)],
           fill=(*GOLD, int(255 * alpha)), width=4)


# ---- Frame ------------------------------------------------------------------
def render_frame(i):
    t = i / FPS
    img = Image.fromarray(BG.copy())
    d = ImageDraw.Draw(img, "RGBA")
    cx = W // 2

    draw_bubbles(d, t)

    # ---- Scene 1 (0–4.2s): brand intro
    a, lt = scene(t, 0.0, 4.2)
    if a > 0:
        draw_glow(d, cx, 700, 420, 70 * a)
        p_fl = ease_out(seg(lt, 0.1, 1.0))
        draw_flute(d, cx, 380 - int(30 * (1 - p_fl)), 340, a * p_fl)
        p1 = ease_out(seg(lt, 0.4, 1.3))
        ctext(d, 830, "DRINKS HOUSE", F_TITLE, INK, a * p1,
              dy=int(36 * (1 - p1)))
        p2 = ease_out(seg(lt, 0.7, 1.6))
        ctext(d, 950, "247", F_HUGE, GOLD, a * p2, dy=int(36 * (1 - p2)))
        p3 = ease_in_out(seg(lt, 1.4, 2.2))
        gold_rule(d, 1220, int(240 * p3), a)
        p4 = ease_out(seg(lt, 1.7, 2.5))
        ctext(d, 1260, "Premium Alcohol Delivery", F_BODY, MUTED, a * p4)
        ctext(d, 1330, "London", F_BODY, MUTED, a * p4)

    # ---- Scene 2 (4.2–8.6s): speed
    a, lt = scene(t, 4.2, 8.6)
    if a > 0:
        draw_glow(d, cx, 620, 360, 60 * a)
        draw_clock(d, cx, 560, 190, seg(lt, 0.3, 2.2), a)
        p1 = ease_out(seg(lt, 0.5, 1.3))
        ctext(d, 880, "30–45 MIN", F_BIG, GOLD, a * p1,
              dy=int(40 * (1 - p1)))
        p2 = ease_out(seg(lt, 1.0, 1.8))
        ctext(d, 1110, "Same-day delivery", F_H2, INK, a * p2)
        ctext(d, 1210, "across London", F_H2, INK, a * p2)
        p3 = ease_out(seg(lt, 1.5, 2.3))
        ctext(d, 1360, "Around the clock · Within the M25", F_SMALL,
              MUTED, a * p3)

    # ---- Scene 3 (8.6–13.0s): range
    a, lt = scene(t, 8.6, 13.0)
    if a > 0:
        p1 = ease_out(seg(lt, 0.1, 0.9))
        ctext(d, 380, "1500+", F_HUGE, GOLD, a * p1, dy=int(40 * (1 - p1)))
        ctext(d, 620, "PREMIUM DRINKS", F_H2, INK, a * p1)
        gold_rule(d, 760, int(220 * ease_in_out(seg(lt, 0.6, 1.3))), a)
        items = ["Champagne", "Fine Wine", "Spirits & Whisky",
                 "Beer & Mixers"]
        for k, item in enumerate(items):
            pk = ease_out(seg(lt, 0.9 + k * 0.35, 1.5 + k * 0.35))
            if pk <= 0:
                continue
            y = 850 + k * 130
            dx = int(-40 * (1 - pk))
            bx = cx - 260 + dx
            d.ellipse([bx, y + 22, bx + 16, y + 38],
                      fill=(*GOLD, int(255 * a * pk)))
            d.text((bx + 44, y), item, font=F_H2,
                   fill=(*INK, int(255 * a * pk)))
        p5 = ease_out(seg(lt, 2.6, 3.3))
        ctext(d, 1430, "Moët · Dom Pérignon · Hennessy", F_SMALL,
              MUTED, a * p5)
        ctext(d, 1490, "Veuve Clicquot · Johnnie Walker", F_SMALL,
              MUTED, a * p5)

    # ---- Scene 4 (13.0–17.0s): service
    a, lt = scene(t, 13.0, 17.0)
    if a > 0:
        draw_glow(d, cx, 560, 380, 60 * a)
        p1 = ease_out(seg(lt, 0.1, 0.9))
        ctext(d, 330, "OPEN", F_H2, INK, a * p1)
        ctext(d, 430, "24/7", F_HUGE, GOLD, a * p1, dy=int(40 * (1 - p1)))
        gold_rule(d, 740, int(220 * ease_in_out(seg(lt, 0.6, 1.3))), a)
        items = ["No minimum order", "Gift wrapping available",
                 "Contactless delivery", "UK-wide next-day shipping"]
        for k, item in enumerate(items):
            pk = ease_out(seg(lt, 0.9 + k * 0.35, 1.5 + k * 0.35))
            if pk <= 0:
                continue
            y = 840 + k * 120
            dx = int(-40 * (1 - pk))
            bx = cx - 330 + dx
            # gold check mark
            ca = int(255 * a * pk)
            d.line([(bx, y + 34), (bx + 14, y + 48)], fill=(*GOLD, ca),
                   width=6)
            d.line([(bx + 14, y + 48), (bx + 40, y + 14)], fill=(*GOLD, ca),
                   width=6)
            d.text((bx + 66, y), item, font=F_BODY,
                   fill=(*INK, int(255 * a * pk)))

    # ---- Scene 5 (17.0–21.0s): CTA
    a, lt = scene(t, 17.0, 21.0, fade=0.5)
    if a > 0:
        draw_glow(d, cx, 800, 430, 70 * a)
        p1 = ease_out(seg(lt, 0.1, 0.8))
        pulse = 0.5 + 0.5 * math.sin(lt * 2.6)
        badge = "ORDER NOW"
        bw = d.textlength(badge, font=F_H2)
        pad = 44
        bx0, by0 = cx - bw / 2 - pad, 560
        bx1, by1 = cx + bw / 2 + pad, 700
        d.rounded_rectangle([bx0, by0, bx1, by1], radius=24,
                            outline=(*GOLD, int(255 * a * p1)), width=4,
                            fill=(GOLD[0], GOLD[1], GOLD[2],
                                  int(a * p1 * (36 + 30 * pulse))))
        ctext(d, 590, badge, F_H2, CHAMPAGNE, a * p1)
        p2 = ease_out(seg(lt, 0.5, 1.2))
        ctext(d, 850, "drinkshouse247.co.uk", F_MONO, INK, a * p2)
        p3 = ease_out(seg(lt, 0.8, 1.5))
        ctext(d, 960, "+44 20 3488 3266", F_MONO_S, GOLD, a * p3)
        p4 = ease_out(seg(lt, 1.1, 1.8))
        ctext(d, 1120, "Delivered in 30–45 minutes", F_BODY, INK, a * p4)
        ctext(d, 1190, "London · Same day · Every day", F_SMALL, MUTED,
              a * p4)
        p5 = ease_out(seg(lt, 1.4, 2.1))
        ctext(d, 1770, "18+ · Please drink responsibly", F_SMALL, MUTED,
              a * p5 * 0.9)

    # Cinematic fade in/out
    fade = ease_out(seg(t, 0.0, 0.4)) * (
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
        if i % 60 == 0:
            print(f"  frame {i}/{TOTAL}")
    proc.stdin.close()
    rc = proc.wait()
    if rc != 0:
        raise SystemExit(f"ffmpeg failed with code {rc}")
    print("Done:", OUT)


if __name__ == "__main__":
    main()
