#!/usr/bin/env python3
"""
"Skip the Lime" — informative tequila short with voiceover, for
Drinks House 247.

Pipeline (all local, no cloud):
  1. Piper TTS synthesizes one WAV per scene from the VO script.
  2. Scene durations auto-fit each voiceover line.
  3. PIL draws every frame; frames + master audio go to a bundled FFmpeg.

    pip install imageio-ffmpeg numpy pillow piper-tts
    # voice model (~100 MB), e.g. from the rhasspy/piper v0.0.2 release:
    #   voice-en-us-ryan-high.tar.gz  ->  en-us-ryan-high.onnx(.json)
    PIPER_MODEL=/path/to/en-us-ryan-high.onnx python render.py

Output: output/tequila-truth-short.mp4  (1080x1920, 30fps, VO-timed ~45s)
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
OUT = os.path.join(HERE, "output", "tequila-truth-short.mp4")
VO_DIR = os.path.join(HERE, "output", "vo")
MODEL = os.environ.get("PIPER_MODEL", os.path.join(HERE, "en-us-ryan-high.onnx"))
SR = 22050

BG_TOP = (10, 9, 14)
BG_BOTTOM = (30, 20, 22)
GOLD = (212, 175, 85)
CHAMPAGNE = (245, 222, 150)
INK = (246, 243, 236)
MUTED = (172, 163, 150)
RED = (205, 70, 60)
LIME_RIND = (110, 160, 60)
LIME_FLESH = (208, 226, 130)
LIME_SEG = (240, 250, 205)
AGAVE_G = (118, 168, 82)
AGAVE_D = (78, 122, 56)
AMBER = (198, 122, 46)
GLASS_GRAY = (200, 200, 210)

FONT_DIR = "/usr/share/fonts/truetype"


def font(path, size):
    return ImageFont.truetype(os.path.join(FONT_DIR, path), size)


F_HUGE = font("dejavu/DejaVuSans-Bold.ttf", 170)
F_TITLE = font("dejavu/DejaVuSans-Bold.ttf", 96)
F_H2 = font("dejavu/DejaVuSans-Bold.ttf", 72)
F_FACT = font("dejavu/DejaVuSans.ttf", 52)
F_SMALL = font("dejavu/DejaVuSans.ttf", 40)
F_CAP = font("dejavu/DejaVuSans.ttf", 40)
F_MONO = font("dejavu/DejaVuSansMono-Bold.ttf", 52)
F_MONO_S = font("dejavu/DejaVuSansMono.ttf", 36)
F_LABEL = font("dejavu/DejaVuSans-Bold.ttf", 34)
F_H2S = font("dejavu/DejaVuSans-Bold.ttf", 58)

# ---- Voiceover script -------------------------------------------------------
SCENES = [
    dict(key="hook",
         vo="Stop taking a lime with every shot of tequila. Here's why."),
    dict(key="mask",
         vo="The salt and lime ritual exists for one reason: to mask the "
            "burn of harsh, cheap tequila."),
    dict(key="mixto",
         vo="That cheap stuff is called mixto. Legally it only needs fifty "
            "one percent agave. The rest is other sugars."),
    dict(key="agave",
         vo="One hundred percent agave tequila is a different drink "
            "entirely. Smooth and complex, with notes of cooked agave, "
            "citrus, and black pepper."),
    dict(key="sip",
         vo="In Mexico, good tequila isn't slammed. It's sipped slowly, "
            "like a fine whisky."),
    dict(key="label",
         vo="So check the label. If it says one hundred percent de agave, "
            "skip the lime, and actually taste it."),
    dict(key="cta",
         vo="Premium tequila, delivered across London in thirty to forty "
            "five minutes. Drinks House two four seven, open twenty four "
            "seven. Please drink responsibly."),
]

VO_LEAD = 0.4    # silence before VO starts in each scene
VO_TAIL = 0.7    # padding after VO ends
MIN_SCENE = 3.2


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
    return t + 0.4  # closing fade tail


def build_master_audio(total):
    n = int(total * SR)
    master = np.zeros(n, dtype=np.float32)
    for sc in SCENES:
        with wave.open(sc["vo_path"], "rb") as w:
            assert w.getframerate() == SR and w.getnchannels() == 1
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


# ---- Background & shared elements -------------------------------------------
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
    """VO line mirrored as a bottom caption (for muted viewing)."""
    p = ease_out(seg(lt, VO_LEAD, VO_LEAD + 0.5))
    lines = wrap(d, sc["vo"], F_CAP, 880)
    y = 1530
    for ln in lines:
        ctext(d, y, ln, F_CAP, MUTED, alpha * p * 0.95)
        y += 56


def kicker(d, alpha):
    ctext(d, 150, "TEQUILA, HONESTLY", F_MONO_S, GOLD, alpha * 0.9)


# ---- Scene-specific visuals -------------------------------------------------
def vis_lime_nosign(d, cx, cy, r, alpha, slash_p):
    a = int(255 * alpha)
    # lime slice
    d.ellipse([cx - r, cy - r, cx + r, cy + r],
              fill=(*LIME_FLESH, a), outline=(*LIME_RIND, a), width=12)
    for k in range(8):
        ang = k * math.pi / 4 + 0.12
        d.line([(cx, cy), (cx + 0.82 * r * math.cos(ang),
                           cy + 0.82 * r * math.sin(ang))],
               fill=(*LIME_SEG, a), width=6)
    d.ellipse([cx - 10, cy - 10, cx + 10, cy + 10], fill=(*LIME_SEG, a))
    # prohibition ring + slash
    rr = int(r * 1.42)
    d.ellipse([cx - rr, cy - rr, cx + rr, cy + rr],
              outline=(*RED, a), width=18)
    if slash_p > 0:
        k = 0.7071
        ax, ay = cx - rr * k, cy - rr * k
        bx, by = cx + rr * k, cy + rr * k
        ex = ax + (bx - ax) * ease_in_out(slash_p)
        ey = ay + (by - ay) * ease_in_out(slash_p)
        d.line([(ax, ay), (ex, ey)], fill=(*RED, a), width=20)


def vis_shot_salt(d, cx, cy, alpha):
    a = int(255 * alpha)
    # shot glass (left)
    gx = cx - 170
    d.polygon([(gx - 80, cy - 90), (gx + 80, cy - 90),
               (gx + 60, cy + 90), (gx - 60, cy + 90)],
              outline=(*GOLD, a), width=5)
    d.polygon([(gx - 68, cy - 40), (gx + 68, cy - 40),
               (gx + 62, cy + 82), (gx - 62, cy + 82)],
              fill=(CHAMPAGNE[0], CHAMPAGNE[1], CHAMPAGNE[2],
                    int(110 * alpha)))
    # salt shaker (right)
    sx = cx + 170
    d.rounded_rectangle([sx - 55, cy - 40, sx + 55, cy + 95], radius=16,
                        outline=(*GLASS_GRAY, a), width=5)
    d.rounded_rectangle([sx - 40, cy - 90, sx + 40, cy - 40], radius=10,
                        outline=(*GOLD, a), width=5)
    for k in range(3):
        d.ellipse([sx - 22 + k * 20, cy - 72, sx - 12 + k * 20, cy - 62],
                  fill=(*GLASS_GRAY, a))
    # plus sign between
    d.line([(cx - 30, cy), (cx + 30, cy)], fill=(*INK, a), width=8)
    d.line([(cx, cy - 30), (cx, cy + 30)], fill=(*INK, a), width=8)


def vis_mixto_bar(d, cx, cy, alpha, p):
    a = int(255 * alpha)
    x0, x1 = 120, W - 120
    bw = x1 - x0
    bh = 120
    gold_w = int(bw * 0.51 * ease_in_out(p))
    d.rounded_rectangle([x0, cy - bh // 2, x1, cy + bh // 2], radius=18,
                        outline=(*GOLD, int(a * 0.6)), width=4)
    if gold_w > 24:
        d.rounded_rectangle([x0 + 6, cy - bh // 2 + 6,
                             x0 + 6 + gold_w, cy + bh // 2 - 6],
                            radius=14, fill=(*GOLD, int(a * 0.9)))
    if p > 0.55:
        pa = a * seg(p, 0.55, 1.0)
        d.text((x0 + 30, cy - 24), "51% AGAVE", font=F_LABEL,
               fill=(BG_TOP[0], BG_TOP[1], BG_TOP[2], int(pa)))
        d.text((x0 + 6 + int(bw * 0.51) + 30, cy - 24), "49% OTHER SUGARS",
               font=F_LABEL, fill=(*MUTED, int(pa)))


def vis_agave(d, cx, base_y, alpha, p):
    a = int(255 * alpha)
    for i, ang in enumerate([-64, -45, -25, 0, 25, 45, 64]):
        ln = (250 if abs(ang) > 40 else 300 + (40 if ang == 0 else 0))
        ln = int(ln * ease_out(seg(p, i * 0.06, 0.6 + i * 0.06)))
        if ln < 8:
            continue
        rad = math.radians(ang)
        tipx = cx + ln * math.sin(rad)
        tipy = base_y - ln * math.cos(rad)
        bx = 20 * math.cos(rad)
        by = 20 * math.sin(rad)
        d.polygon([(cx - bx, base_y - by), (cx + bx, base_y + by),
                   (tipx, tipy)],
                  fill=(AGAVE_G[0], AGAVE_G[1], AGAVE_G[2], int(a * 0.92)),
                  outline=(*AGAVE_D, a))
    d.line([(cx - 150, base_y + 8), (cx + 150, base_y + 8)],
           fill=(*GOLD, int(a * 0.8)), width=5)


def vis_rocks_glass(d, cx, cy, alpha, t):
    a = int(255 * alpha)
    w, h = 280, 220
    x0, y0 = cx - w // 2, cy - h // 2
    x1, y1 = cx + w // 2, cy + h // 2
    d.rounded_rectangle([x0 + 10, y0 + h * 0.42, x1 - 10, y1 - 10],
                        radius=16,
                        fill=(AMBER[0], AMBER[1], AMBER[2], int(150 * alpha)))
    sy = y0 + h * 0.42 + 4 * math.sin(t * 1.8)
    d.line([(x0 + 16, sy), (x1 - 16, sy)],
           fill=(*CHAMPAGNE, int(120 * alpha)), width=3)
    d.rounded_rectangle([x0, y0, x1, y1], radius=20,
                        outline=(*GOLD, a), width=5)
    d.rounded_rectangle([cx - 45, y0 + h * 0.48, cx + 25, y0 + h * 0.48 + 58],
                        radius=10, outline=(*INK, int(140 * alpha)), width=4)
    # rising aroma curls
    for k in range(3):
        ph = ((t * 0.5 + k * 0.33) % 1.0)
        ax = cx - 60 + k * 60 + 14 * math.sin(t * 2 + k * 2)
        ay = y0 - 20 - ph * 110
        aa = int(120 * alpha * (1 - ph))
        d.arc([ax - 16, ay - 16, ax + 16, ay + 16], 20, 200,
              fill=(*CHAMPAGNE, aa), width=4)


def vis_bottle(d, cx, cy, alpha, check_p):
    a = int(255 * alpha)
    bw, bh = 190, 400
    x0, y0 = cx - bw // 2, cy - bh // 2
    x1, y1 = cx + bw // 2, cy + bh // 2
    # neck + cap
    d.rounded_rectangle([cx - 34, y0 - 100, cx + 34, y0 + 20], radius=10,
                        outline=(*GOLD, a), width=5)
    d.rounded_rectangle([cx - 40, y0 - 132, cx + 40, y0 - 100], radius=8,
                        fill=(*GOLD, a))
    # body
    d.rounded_rectangle([x0, y0, x1, y1], radius=28,
                        outline=(*GOLD, a), width=5,
                        fill=(AMBER[0], AMBER[1], AMBER[2], int(60 * alpha)))
    # label band
    ly0, ly1 = cy - 70, cy + 80
    d.rounded_rectangle([x0 + 16, ly0, x1 - 16, ly1], radius=12,
                        fill=(INK[0], INK[1], INK[2], int(235 * alpha)))
    dark = (BG_TOP[0], BG_TOP[1], BG_TOP[2], a)
    for i, txt in enumerate(["100%", "DE AGAVE"]):
        tw = d.textlength(txt, font=F_LABEL)
        d.text((cx - tw / 2, ly0 + 26 + i * 52), txt, font=F_LABEL,
               fill=dark)
    # gold check to the right
    if check_p > 0:
        ca = int(255 * alpha * ease_out(check_p))
        ccx, ccy = x1 + 110, cy
        d.ellipse([ccx - 56, ccy - 56, ccx + 56, ccy + 56],
                  outline=(*GOLD, ca), width=7)
        d.line([(ccx - 24, ccy + 2), (ccx - 4, ccy + 24)],
               fill=(*GOLD, ca), width=9)
        d.line([(ccx - 4, ccy + 24), (ccx + 30, ccy - 20)],
               fill=(*GOLD, ca), width=9)


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
            kicker(d, a)
            vis_lime_nosign(d, cx, 640, 200, a * ease_out(seg(lt, 0.1, 0.7)),
                            seg(lt, 0.6, 1.2))
            p1 = ease_out(seg(lt, 0.8, 1.4))
            ctext(d, 1000, "SKIP THE LIME", F_TITLE, INK, a * p1,
                  dy=int(36 * (1 - p1)))
            p2 = ease_out(seg(lt, 1.2, 1.8))
            ctext(d, 1140, "(with good tequila)", F_FACT, MUTED, a * p2)

        elif key == "mask":
            kicker(d, a)
            draw_glow(d, cx, 620, 300, 45 * a)
            vis_shot_salt(d, cx, 620, a * ease_out(seg(lt, 0.2, 0.9)))
            p1 = ease_out(seg(lt, 0.6, 1.3))
            ctext(d, 980, "SALT + LIME", F_TITLE, GOLD, a * p1)
            p2 = ease_out(seg(lt, 1.0, 1.7))
            ctext(d, 1120, "= a mask for cheap tequila", F_FACT, INK, a * p2)

        elif key == "mixto":
            kicker(d, a)
            p0 = ease_out(seg(lt, 0.2, 0.8))
            ctext(d, 500, "“MIXTO”", F_TITLE, INK, a * p0)
            vis_mixto_bar(d, cx, 760, a, seg(lt, 0.6, 2.0))
            p1 = ease_out(seg(lt, 1.6, 2.3))
            ctext(d, 980, "Only 51% agave required", F_FACT, INK, a * p1)
            p2 = ease_out(seg(lt, 2.0, 2.7))
            ctext(d, 1090, "THE BURN YOU'RE MASKING", F_H2S, GOLD, a * p2)

        elif key == "agave":
            kicker(d, a)
            draw_glow(d, cx, 620, 300, 45 * a)
            vis_agave(d, cx, 780, a, seg(lt, 0.2, 1.6))
            p1 = ease_out(seg(lt, 0.8, 1.5))
            ctext(d, 950, "100% AGAVE", F_TITLE, GOLD, a * p1)
            p2 = ease_out(seg(lt, 1.2, 1.9))
            ctext(d, 1090, "cooked agave · citrus · pepper", F_FACT, INK,
                  a * p2)

        elif key == "sip":
            kicker(d, a)
            draw_glow(d, cx, 620, 300, 45 * a)
            vis_rocks_glass(d, cx, 640, a * ease_out(seg(lt, 0.2, 0.9)), lt)
            p1 = ease_out(seg(lt, 0.6, 1.3))
            ctext(d, 980, "SIP IT", F_TITLE, INK, a * p1)
            p2 = ease_out(seg(lt, 1.0, 1.7))
            ctext(d, 1120, "slowly — like a fine whisky", F_FACT, MUTED,
                  a * p2)

        elif key == "label":
            kicker(d, a)
            draw_glow(d, cx, 640, 320, 45 * a)
            vis_bottle(d, cx - 40, 640, a * ease_out(seg(lt, 0.2, 0.9)),
                       seg(lt, 1.2, 1.8))
            p1 = ease_out(seg(lt, 0.8, 1.5))
            ctext(d, 1010, "READ THE LABEL", F_TITLE, INK, a * p1)
            p2 = ease_out(seg(lt, 1.2, 1.9))
            ctext(d, 1150, "“100% de agave” or nothing", F_FACT,
                  GOLD, a * p2)

        elif key == "cta":
            draw_glow(d, cx, 780, 420, 60 * a)
            p1 = ease_out(seg(lt, 0.2, 0.9))
            ctext(d, 470, "DRINKS HOUSE", F_TITLE, INK, a * p1,
                  dy=int(30 * (1 - p1)))
            ctext(d, 590, "247", F_HUGE, GOLD, a * p1,
                  dy=int(30 * (1 - p1)))
            gold_rule(d, 830, int(220 * ease_in_out(seg(lt, 0.7, 1.3))), a)
            p2 = ease_out(seg(lt, 0.9, 1.6))
            ctext(d, 880, "Premium tequila delivered", F_FACT, INK, a * p2)
            ctext(d, 960, "across London in 30-45 min", F_FACT, INK, a * p2)
            p3 = ease_out(seg(lt, 1.2, 1.9))
            ctext(d, 1100, "drinkshouse247.co.uk", F_MONO, INK, a * p3)
            ctext(d, 1200, "+44 20 3488 3266", F_MONO_S, GOLD, a * p3)
            p4 = ease_out(seg(lt, 1.5, 2.2))
            ctext(d, 1300, "Open 24/7", F_H2, GOLD, a * p4)
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


def main():
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    if not os.path.exists(MODEL):
        raise SystemExit(
            f"Piper model not found: {MODEL}\n"
            "Set PIPER_MODEL to an .onnx voice (see header comment).")
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
