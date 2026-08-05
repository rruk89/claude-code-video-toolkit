# Drinks House 247 — Informational Reel

A vertical 9:16 short (1080×1920, 30fps, ~21s) for
[Drinks House 247](https://drinkshouse247.co.uk) — 24/7 premium alcohol
delivery in London. Built with the same dependency-light pipeline as the
[intro-video example](../intro-video/): Pillow draws every frame, a bundled
FFmpeg (`imageio-ffmpeg`) encodes to H.264.

Five scenes over a dark-and-gold luxe look with rising champagne bubbles:

1. **Brand intro** — flute icon, "Drinks House 247", tagline
2. **Speed** — animated clock, 30–45 min same-day delivery across London
3. **Range** — 1500+ premium drinks: champagne, wine, spirits, beer
4. **Service** — open 24/7, no minimum order, gift wrapping, UK-wide next-day
5. **CTA** — drinkshouse247.co.uk · +44 20 3488 3266 · 18+ drink responsibly

## Run

```bash
pip install imageio-ffmpeg numpy pillow
python render.py
```

Output: `output/drinks-house-247-reel.mp4`

## Customize

Constants at the top of `render.py` control resolution, fps, duration, and
palette. Scene copy and timings live in `render_frame()` — each scene is a
`scene(t, start, end)` block.
