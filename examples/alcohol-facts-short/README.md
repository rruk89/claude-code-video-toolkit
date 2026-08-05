# 5 Drinks Facts That Sound Fake (But Aren't)

A vertical 9:16 infotainment short (1080×1920, 30fps, ~31.5s) for
[Drinks House 247](https://drinkshouse247.co.uk). Same dependency-light
pipeline as the other examples: Pillow draws every frame, a bundled FFmpeg
(`imageio-ffmpeg`) encodes H.264.

Hook + five animated fact cards + branded CTA, dark-and-gold look with
rising champagne bubbles throughout:

1. **~49 million bubbles** in a bottle of champagne — flute + ticking counter
2. **Whisky = "water of life"** — tumbler, *uisge beatha* morphing to English
3. **The angels' share** — barrel losing ~2%/year as golden mist
4. **Toasting comes from real toast** — spiced bread drops into a wine glass
5. **A cork flies up to 40 km/h** — cork streaking across, speedometer gauge

Outro: Drinks House 247 card — drinkshouse247.co.uk · +44 20 3488 3266 ·
Open 24/7 · 18+ drink responsibly.

## Run

```bash
pip install imageio-ffmpeg numpy pillow
python render.py
```

Output: `output/alcohol-facts-short.mp4`

## Customize

Scene boundaries are the `S_*` tuples near `render_frame()`; copy and
per-element timings live inside each scene block. Palette and fonts are
constants at the top.
