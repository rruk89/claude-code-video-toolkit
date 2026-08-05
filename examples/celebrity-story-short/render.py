#!/usr/bin/env python3
"""
"Where Did It All Go Wrong?" — the classic George Best champagne story,
as a voiced vertical short for Drinks House 247.

Same fully-local pipeline as the tequila short: Piper TTS per scene,
scene lengths auto-fit the narration, PIL frames + master audio muxed by
a bundled FFmpeg.

    pip install imageio-ffmpeg numpy pillow piper-tts
    PIPER_MODEL=/path/to/en-us-ryan-high.onnx python render.py

Output: output/celebrity-story-short.mp4  (1080x1920, 30fps, VO-timed)
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
OUT = os.path.join(HERE, "output", "celebrity-story-short.mp4")
VO_DIR = os.path.join(HERE, "output", "vo")
MODEL = os.environ.get("PIPER_MODEL", os.path.join(HERE, "en-us-ryan-high.onnx"))
SR = 22050

BG_TOP = (10, 9, 14)
BG_BOTTOM = (30, 20, 22)
GOLD = (212, 175, 85)
CHAMPAGNE = (245, 222, 150)
INK = (246, 243, 236)
MUTED = (172, 163, 150)
GREEN_FELT = (46, 92, 64)
NOTE_G = (120, 150, 110)
DARK = (16, 14, 20)

FONT_DIR = "/usr/share/fonts/truetype"


def font(path, size):
    return ImageFont.truetype(os.path.join(FONT_DIR, path), size)


F_HUGE = font("dejavu/DejaVuSans-Bold.ttf", 170)
F_TITLE = font("dejavu/DejaVuSans-Bold.ttf", 96)
F_H2 = font("dejavu/DejaVuSans-Bold.ttf", 72)
F_H2S = font("dejavu/DejaVuSans-Bold.ttf", 58)
F_QUOTE = font("dejavu/DejaVuSerif-Bold.ttf", 74)
F_FACT = font("dejavu/DejaVuSans.ttf", 52)
F_SMALL = font("dejavu/DejaVuSans.ttf", 40)
F_CAP = font("dejavu/DejaVuSans.ttf", 40)
F_MONO = font("dejavu/DejaVuSansMono-Bold.ttf", 52)
F_MONO_S = font("dejavu/DejaVuSansMono.ttf", 36)
F_LABEL = font("dejavu/DejaVuSans-Bold.ttf", 34)

# ---- Voiceover script -------------------------------------------------------
SCENES = [
    dict(key="hook",
         vo="Story time. A footballer, Miss World, and a hotel suite full "
            "of champagne."),
    dict(key="best",
         vo="London, the nineteen seventies. George Best, football's first "
            "superstar, has a massive night at the casino."),
    dict(key="suite",
         vo="Back at his hotel, his date is the reigning Miss World. "
            "Champagne on ice. Thousands in cash scattered across the bed."),
    dict(key="waiter",
         vo="Then a waiter arrives with room service. He looks at the "
            "money. He looks at Miss World. And he sighs..."),
    dict(key="quote",
         vo="Mister Best... where did it all go wrong?"),
    dict(key="cta",
         vo="George told that story for the rest of his life. Champagne "
            "for your own story time? Delivered across London in thirty to "
            "forty five minutes. Drinks House two four seven. Please drink "
            "responsibly."),
]

VO_LEAD = 0.4
VO_TAIL = 0.7
MIN_SCENE = 3.2


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
        pad = 0.5 if sc["key"] == "quote" else 0.0  # let the punchline land
        sc["len"] = max(sc["vo_dur"] + VO_LEAD + VO_TAIL + pad, MIN_SCENE)
        sc["start"] = t
        t += sc["len"]
    return t + 0.4


def build_master_audio(total):
    n = int(total * SR)
    master = np.zeros(n, dtype=np.float32)
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


# ---- Background & shared ----------------------------------------------------
def make_gradient():
    top = np.array(BG_TOP, dtype=np.float32)
    bot = np.array(BG_BOTTOM, dtype=np.float32)
    ramp = np.linspace(0, 1, H, dtype=np.float32)[:, None]
    grad = (top[None, :] * (1 - ramp) + bot[None, :] * ramp)
    return np.repeat(grad[:, None, :], W, axis=1).astype(np.uint8)


BG = make_gradient()


def draw_bubbles(d, t):
    for k in range(22):
        px = (math.sin(k * 12.9898) * 43758.5453) % 1.0
        speed = 90 + 160 * ((math.sin(k * 78.233) * 12345.678) % 1.0)
        r = 3 + 9 * ((math.sin(k * 39.425) * 9876.543) % 1.0)
        phase = ((math.sin(k * 3.7) * 1234.56) % 1.0)
        x = int(px * W + 26 * math.sin(t * 0.8 + k))
        y = H - int(((t * speed + phase * H * 2) % (H + 200)) - 100)
        a = int(40 * (0.4 + 0.6 * ((k * 7) % 5) / 4))
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
    lines = wrap(d, sc["vo"], F_CAP, 880)
    y = 1530
    for ln in lines:
        ctext(d, y, ln, F_CAP, MUTED, alpha * p * 0.95)
        y += 56


def kicker(d, alpha, text="A TRUE STORY (AS GEORGE TOLD IT)"):
    ctext(d, 150, text, F_MONO_S, GOLD, alpha * 0.9)


# ---- Icons ------------------------------------------------------------------
def vis_football(d, cx, cy, r, alpha, spin=0.0):
    a = int(255 * alpha)
    d.ellipse([cx - r, cy - r, cx + r, cy + r],
              fill=(INK[0], INK[1], INK[2], int(a * 0.92)),
              outline=(*GOLD, a), width=6)
    pr = r * 0.34
    rot = spin
    pts = [(cx + pr * math.sin(rot + k * 2 * math.pi / 5),
            cy - pr * math.cos(rot + k * 2 * math.pi / 5)) for k in range(5)]
    d.polygon(pts, fill=(*DARK, a))
    for px, py in pts:
        vx, vy = px - cx, py - cy
        n = math.hypot(vx, vy)
        d.line([(px, py), (cx + vx / n * r * 0.94, cy + vy / n * r * 0.94)],
               fill=(*DARK, int(a * 0.8)), width=5)


def vis_chips(d, cx, cy, alpha):
    a = int(255 * alpha)
    stacks = [(cx - 130, 3, GOLD), (cx, 4, (176, 60, 56)), (cx + 130, 2, INK)]
    for sx, n, col in stacks:
        for k in range(n):
            y = cy - k * 26
            d.rounded_rectangle([sx - 62, y - 12, sx + 62, y + 12],
                                radius=12,
                                fill=(col[0], col[1], col[2], int(a * 0.9)),
                                outline=(*DARK, a), width=3)


def vis_bucket(d, cx, cy, alpha, t):
    a = int(255 * alpha)
    # bottle leaning out
    d.rounded_rectangle([cx - 24, cy - 210, cx + 24, cy - 60], radius=14,
                        fill=(GREEN_FELT[0], GREEN_FELT[1], GREEN_FELT[2],
                              int(a * 0.95)), outline=(*GOLD, a), width=4)
    d.rounded_rectangle([cx - 10, cy - 260, cx + 10, cy - 200], radius=6,
                        fill=(GREEN_FELT[0], GREEN_FELT[1], GREEN_FELT[2],
                              int(a * 0.95)), outline=(*GOLD, a), width=3)
    d.rounded_rectangle([cx - 14, cy - 292, cx + 14, cy - 258], radius=6,
                        fill=(*GOLD, a))
    # bucket
    d.polygon([(cx - 130, cy - 70), (cx + 130, cy - 70),
               (cx + 96, cy + 120), (cx - 96, cy + 120)],
              outline=(*GOLD, a), width=6,
              fill=(DARK[0], DARK[1], DARK[2], int(a * 0.7)))
    # ice bumps
    for k, (ix, iy) in enumerate([(-80, -78), (-30, -92), (30, -88),
                                  (80, -76)]):
        d.ellipse([cx + ix - 22, cy + iy - 16, cx + ix + 22, cy + iy + 16],
                  fill=(INK[0], INK[1], INK[2], int(a * 0.85)))
    # sparkle
    ph = (t * 0.8) % 1.0
    sa = alpha * (1 - abs(ph - 0.5) * 2)
    sx, sy = cx + 150, cy - 240
    d.line([(sx - 12, sy), (sx + 12, sy)], fill=(*CHAMPAGNE, int(255 * sa)),
           width=3)
    d.line([(sx, sy - 12), (sx, sy + 12)], fill=(*CHAMPAGNE, int(255 * sa)),
           width=3)


def vis_notes(d, cx, cy, alpha, p):
    """Banknotes scattered across the bed line."""
    a = int(255 * alpha)
    d.line([(cx - 320, cy + 70), (cx + 320, cy + 70)],
           fill=(*GOLD, int(a * 0.7)), width=5)
    spots = [(-240, 18, -8), (-120, -6, 5), (0, 22, -4), (120, -2, 7),
             (240, 14, -6)]
    for i, (dx, dyy, tilt) in enumerate(spots):
        pk = ease_out(seg(p, i * 0.08, 0.5 + i * 0.08))
        if pk <= 0:
            continue
        nx, ny = cx + dx, cy + dyy + int(40 * (1 - pk))
        na = int(a * pk)
        d.rounded_rectangle([nx - 58, ny - 30, nx + 58, ny + 30], radius=8,
                            fill=(NOTE_G[0], NOTE_G[1], NOTE_G[2],
                                  int(na * 0.92)),
                            outline=(*DARK, na), width=3)
        tw = d.textlength("£", font=F_LABEL)
        d.text((nx - tw / 2, ny - 22), "£", font=F_LABEL,
               fill=(*DARK, na))


def vis_crown(d, cx, cy, alpha):
    a = int(255 * alpha)
    d.polygon([(cx - 90, cy + 30), (cx - 90, cy - 20), (cx - 45, cy + 5),
               (cx, cy - 45), (cx + 45, cy + 5), (cx + 90, cy - 20),
               (cx + 90, cy + 30)],
              fill=(*GOLD, int(a * 0.95)), outline=(*CHAMPAGNE, a), width=4)
    d.rounded_rectangle([cx - 95, cy + 30, cx + 95, cy + 58], radius=8,
                        fill=(*GOLD, a))
    for dx in (-60, 0, 60):
        d.ellipse([cx + dx - 8, cy + 36, cx + dx + 8, cy + 52],
                  fill=(*DARK, int(a * 0.8)))


def vis_bell(d, cx, cy, alpha, ring_p):
    a = int(255 * alpha)
    wob = math.sin(ring_p * math.pi * 6) * 8 * (1 - ring_p)
    d.pieslice([cx - 110 + wob, cy - 90, cx + 110 + wob, cy + 130],
               180, 360, fill=(GOLD[0], GOLD[1], GOLD[2], int(a * 0.9)),
               outline=(*CHAMPAGNE, a), width=5)
    d.ellipse([cx - 12 + wob, cy - 108, cx + 12 + wob, cy - 84],
              fill=(*GOLD, a))
    d.line([(cx - 150, cy + 26), (cx + 150, cy + 26)],
           fill=(*CHAMPAGNE, a), width=6)
    if 0 < ring_p < 1:
        ra = int(160 * (1 - ring_p) * alpha)
        rr = 130 + 60 * ring_p
        d.arc([cx - rr, cy - 40 - rr * 0.5, cx + rr, cy - 40 + rr * 0.5],
              200, 340, fill=(*CHAMPAGNE, ra), width=4)


# ---- Frame ------------------------------------------------------------------
def scene_alpha(t, sc, fade=0.4):
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

    draw_bubbles(d, t)

    for sc in SCENES:
        a, lt = scene_alpha(t, sc)
        if a <= 0:
            continue
        key = sc["key"]

        if key == "hook":
            kicker(d, a, "STORYTIME · FOOTBALL EDITION")
            draw_glow(d, cx, 620, 320, 50 * a)
            p0 = ease_out(seg(lt, 0.2, 0.9))
            vis_football(d, cx - 190, 560, 110, a * p0, spin=lt * 0.6)
            vis_crown(d, cx + 190, 540, a * p0)
            vis_bucket(d, cx, 900, a * ease_out(seg(lt, 0.5, 1.2)), lt)
            p1 = ease_out(seg(lt, 0.8, 1.5))
            ctext(d, 1120, "THE CHAMPAGNE STORY", F_H2, GOLD, a * p1)

        elif key == "best":
            kicker(d, a)
            draw_glow(d, cx, 600, 300, 45 * a)
            vis_football(d, cx, 560, 150, a * ease_out(seg(lt, 0.2, 0.9)),
                         spin=lt * 0.5)
            vis_chips(d, cx, 860, a * ease_out(seg(lt, 0.7, 1.4)))
            p1 = ease_out(seg(lt, 0.6, 1.3))
            ctext(d, 990, "GEORGE BEST", F_TITLE, INK, a * p1)
            p2 = ease_out(seg(lt, 1.0, 1.7))
            ctext(d, 1120, "football's first superstar", F_FACT, MUTED,
                  a * p2)

        elif key == "suite":
            kicker(d, a)
            draw_glow(d, cx, 620, 320, 50 * a)
            vis_bucket(d, cx - 200, 700, a * ease_out(seg(lt, 0.2, 0.9)), lt)
            vis_crown(d, cx + 200, 520, a * ease_out(seg(lt, 0.5, 1.2)))
            vis_notes(d, cx + 130, 780, a, seg(lt, 0.8, 2.0))
            p1 = ease_out(seg(lt, 1.0, 1.7))
            ctext(d, 1020, "THE SUITE", F_TITLE, GOLD, a * p1)
            p2 = ease_out(seg(lt, 1.4, 2.1))
            ctext(d, 1150, "champagne · cash · Miss World", F_FACT, INK,
                  a * p2)

        elif key == "waiter":
            kicker(d, a)
            draw_glow(d, cx, 600, 300, 45 * a)
            vis_bell(d, cx, 580, a * ease_out(seg(lt, 0.2, 0.9)),
                     seg(lt, 0.9, 1.9))
            p1 = ease_out(seg(lt, 0.6, 1.3))
            ctext(d, 940, "ROOM SERVICE", F_TITLE, INK, a * p1)
            p2 = ease_out(seg(lt, 1.0, 1.7))
            ctext(d, 1070, "one look... and a sigh", F_FACT, MUTED, a * p2)

        elif key == "quote":
            draw_glow(d, cx, 800, 420, 65 * a)
            p0 = ease_out(seg(lt, 0.1, 0.6))
            ctext(d, 420, "“", font_big_quote(), GOLD, a * p0)
            p1 = ease_out(seg(lt, 0.3, 1.0))
            lines = ["Mr Best...", "where did it", "all go wrong?"]
            y = 640
            for k, ln in enumerate(lines):
                pk = ease_out(seg(lt, 0.3 + k * 0.35, 1.0 + k * 0.35))
                ctext(d, y, ln, F_QUOTE, INK, a * pk,
                      dy=int(30 * (1 - pk)))
                y += 120
            p2 = ease_out(seg(lt, 1.6, 2.3))
            ctext(d, 1100, "— the room-service waiter,", F_FACT, MUTED,
                  a * p2)
            ctext(d, 1170, "completely serious", F_FACT, MUTED, a * p2)

        elif key == "cta":
            draw_glow(d, cx, 760, 420, 60 * a)
            p1 = ease_out(seg(lt, 0.2, 0.9))
            ctext(d, 430, "DRINKS HOUSE", F_TITLE, INK, a * p1,
                  dy=int(30 * (1 - p1)))
            ctext(d, 550, "247", F_HUGE, GOLD, a * p1,
                  dy=int(30 * (1 - p1)))
            gold_rule(d, 790, int(220 * ease_in_out(seg(lt, 0.7, 1.3))), a)
            p2 = ease_out(seg(lt, 0.9, 1.6))
            ctext(d, 840, "Champagne for your own storytime", F_FACT, INK,
                  a * p2)
            ctext(d, 920, "delivered across London in 30-45 min", F_FACT,
                  INK, a * p2)
            p3 = ease_out(seg(lt, 1.2, 1.9))
            ctext(d, 1060, "drinkshouse247.co.uk", F_MONO, INK, a * p3)
            ctext(d, 1160, "+44 20 3488 3266", F_MONO_S, GOLD, a * p3)
            p4 = ease_out(seg(lt, 1.5, 2.2))
            ctext(d, 1260, "Open 24/7", F_H2, GOLD, a * p4)
            p5 = ease_out(seg(lt, 1.8, 2.5))
            ctext(d, 1770, "18+ · Please drink responsibly", F_SMALL, MUTED,
                  a * p5 * 0.9)

        if key != "cta":
            caption(d, lt, sc, a)
            ctext(d, 1820, "18+ · Please drink responsibly", F_SMALL, MUTED,
                  a * 0.55)

    total_s = total / FPS
    fade = ease_out(seg(t, 0.0, 0.35)) * (
        1.0 - ease_in_out(seg(t, total_s - 0.6, total_s)))
    if fade < 1.0:
        ov = Image.new("RGBA", (W, H), (0, 0, 0, int(255 * (1 - fade))))
        img = Image.alpha_composite(img.convert("RGBA"), ov)

    return np.asarray(img.convert("RGB"))


_BIG_QUOTE = None


def font_big_quote():
    global _BIG_QUOTE
    if _BIG_QUOTE is None:
        _BIG_QUOTE = font("dejavu/DejaVuSerif-Bold.ttf", 200)
    return _BIG_QUOTE


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
        "-c:v", "libx264", "-preset", "medium", "-crf", "19",
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
