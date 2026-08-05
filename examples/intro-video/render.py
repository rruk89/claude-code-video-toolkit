#!/usr/bin/env python3
"""
Render a short branded intro video for the Claude Code Video Toolkit.

Pure-Python renderer: PIL draws each frame, frames are piped to a bundled
ffmpeg (via imageio-ffmpeg) and encoded to H.264 MP4. No system ffmpeg,
Node, or GPU required.

    pip install imageio-ffmpeg numpy pillow
    python render.py

Output: output/toolkit-intro.mp4  (1920x1080, 30fps, ~10s)
"""

import math
import os
import subprocess

import imageio_ffmpeg
import numpy as np
from PIL import Image, ImageDraw, ImageFont

# ---- Config -----------------------------------------------------------------
W, H = 1920, 1080
FPS = 30
DURATION = 10.0
TOTAL = int(FPS * DURATION)
OUT = os.path.join(os.path.dirname(__file__), "output", "toolkit-intro.mp4")

# Anthropic-ish warm palette on a deep slate background
BG_TOP = (16, 18, 27)
BG_BOTTOM = (28, 24, 34)
ACCENT = (217, 119, 87)      # warm clay/terracotta
ACCENT_SOFT = (233, 168, 130)
INK = (240, 238, 244)
MUTED = (150, 150, 168)

FONT_DIR = "/usr/share/fonts/truetype"


def font(path, size):
    return ImageFont.truetype(os.path.join(FONT_DIR, path), size)


F_TITLE = font("dejavu/DejaVuSans-Bold.ttf", 96)
F_SUB = font("dejavu/DejaVuSans.ttf", 40)
F_MONO = font("dejavu/DejaVuSansMono-Bold.ttf", 34)
F_TAG = font("dejavu/DejaVuSansMono.ttf", 28)

FEATURES = [
    "Remotion  —  React to MP4",
    "Manim  —  3Blue1Brown-style math",
    "Playwright  —  screen recording",
    "FFmpeg  —  encode & post-process",
]


# ---- Easing -----------------------------------------------------------------
def ease_out(t):
    return 1 - (1 - t) ** 3


def ease_in_out(t):
    return 3 * t * t - 2 * t * t * t


def clamp01(x):
    return max(0.0, min(1.0, x))


def seg(t, start, end):
    """Normalized 0..1 progress of t within [start, end]."""
    if end <= start:
        return 1.0 if t >= end else 0.0
    return clamp01((t - start) / (end - start))


# ---- Static background gradient ---------------------------------------------
def make_gradient():
    top = np.array(BG_TOP, dtype=np.float32)
    bot = np.array(BG_BOTTOM, dtype=np.float32)
    ramp = np.linspace(0, 1, H, dtype=np.float32)[:, None]
    grad = (top[None, :] * (1 - ramp) + bot[None, :] * ramp)
    return np.repeat(grad[:, None, :], W, axis=1).astype(np.uint8)


BG = make_gradient()


def lerp_color(a, b, t):
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


# ---- Frame ------------------------------------------------------------------
def render_frame(i):
    t = i / FPS
    img = Image.fromarray(BG.copy())
    d = ImageDraw.Draw(img, "RGBA")

    cx = W // 2

    # Drifting accent glow behind the title
    glow_p = ease_in_out(seg(t, 0.0, 2.0))
    gy = int(H * 0.34)
    gr = int(260 + 40 * math.sin(t * 0.9))
    ga = int(70 * glow_p)
    for k in range(6, 0, -1):
        r = gr * k / 6
        a = int(ga * (k / 6) * 0.5)
        d.ellipse([cx - r, gy - r, cx + r, gy + r],
                  fill=(ACCENT[0], ACCENT[1], ACCENT[2], a))

    # Title: rises up + fades in
    p_title = ease_out(seg(t, 0.3, 1.4))
    ty = int(H * 0.30 - 40 * (1 - p_title))
    title = "Claude Code"
    tw = d.textlength(title, font=F_TITLE)
    d.text((cx - tw / 2, ty), title, font=F_TITLE,
           fill=(*INK, int(255 * p_title)))

    title2 = "Video Toolkit"
    p_title2 = ease_out(seg(t, 0.55, 1.65))
    ty2 = ty + 104
    tw2 = d.textlength(title2, font=F_TITLE)
    col2 = lerp_color(INK, ACCENT_SOFT, 1.0)
    d.text((cx - tw2 / 2, ty2 - 40 * (1 - p_title2)), title2,
           font=F_TITLE, fill=(*col2, int(255 * p_title2)))

    # Animated underline sweep
    p_line = ease_in_out(seg(t, 1.3, 2.2))
    ly = ty2 + 130
    half = int(260 * p_line)
    d.line([(cx - half, ly), (cx + half, ly)], fill=(*ACCENT, 255), width=4)

    # Subtitle
    p_sub = ease_out(seg(t, 1.6, 2.4))
    sub = "Produce video with Claude Code"
    sw = d.textlength(sub, font=F_SUB)
    d.text((cx - sw / 2, ly + 26), sub, font=F_SUB,
           fill=(*MUTED, int(255 * p_sub)))

    # Feature list — staggered typewriter-ish reveal
    list_top = int(H * 0.63)
    row_h = 66
    for idx, feat in enumerate(FEATURES):
        start = 2.7 + idx * 0.45
        p = ease_out(seg(t, start, start + 0.6))
        if p <= 0:
            continue
        ry = list_top + idx * row_h
        alpha = int(255 * p)
        dx = int(-30 * (1 - p))
        # bullet dot
        dot_x = cx - 340 + dx
        d.ellipse([dot_x, ry + 16, dot_x + 14, ry + 30],
                  fill=(*ACCENT, alpha))
        # reveal characters progressively
        chars = max(0, int(len(feat) * ease_out(seg(t, start, start + 0.9))))
        d.text((dot_x + 34, ry), feat[:chars], font=F_MONO,
               fill=(*INK, alpha))

    # Bottom tag line, gentle pulse near the end
    p_tag = ease_out(seg(t, 5.4, 6.2))
    if p_tag > 0:
        pulse = 0.5 + 0.5 * math.sin((t - 5.4) * 2.2)
        tag = "npx skills add remotion"
        gw = d.textlength(tag, font=F_TAG)
        pad = 26
        bx0, by0 = cx - gw / 2 - pad, int(H * 0.90) - 12
        bx1, by1 = cx + gw / 2 + pad, int(H * 0.90) + 46
        d.rounded_rectangle([bx0, by0, bx1, by1], radius=12,
                            outline=(*ACCENT, int(220 * p_tag)), width=2,
                            fill=(ACCENT[0], ACCENT[1], ACCENT[2],
                                  int(28 * p_tag * (0.6 + 0.4 * pulse))))
        d.text((cx - gw / 2, int(H * 0.90)), tag, font=F_TAG,
               fill=(*ACCENT_SOFT, int(255 * p_tag)))

    # Cinematic fade in/out
    fade = 1.0
    fade *= ease_out(seg(t, 0.0, 0.5))
    fade *= 1.0 - ease_in_out(seg(t, DURATION - 0.6, DURATION))
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
        "-c:v", "libx264", "-preset", "medium", "-crf", "18",
        "-pix_fmt", "yuv420p", "-movflags", "+faststart",
        OUT,
    ]
    print(f"Rendering {TOTAL} frames -> {OUT}")
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for i in range(TOTAL):
        proc.stdin.write(render_frame(i).tobytes())
        if i % 30 == 0:
            print(f"  frame {i}/{TOTAL}")
    proc.stdin.close()
    rc = proc.wait()
    if rc != 0:
        raise SystemExit(f"ffmpeg failed with code {rc}")
    print("Done:", OUT)


if __name__ == "__main__":
    main()
