# The Gift of Champagne — high-end gifting film

A deliberately quiet, minimal gifting film with voiceover (1080×1920,
30fps, ~39s) for [Drinks House 247](https://drinkshouse247.co.uk).

Where the other examples in this repo are dark and bold, this one is the
opposite: warm ivory ground, thin antique-gold hairlines, classical
serif set large with generous negative space, letterspaced small-caps
labels, and slow eased motion. No bubbles, no glows, no filled shapes —
every motif is line art that draws itself.

## Scenes

1. **Open** — a gold ribbon bow ties itself · *"Some gifts are remembered."*
2. **Same day, London** — hairline dial sweeping · **30–45 minutes**, chilled, to their door
3. **UK-wide, next day** — the Great Britain coastline strokes itself in, London pulses · *"Anywhere in Britain, by tomorrow."*
4. **Presented, not posted** — gift box with a ribbon and a note card that writes itself · gift boxes & sets, a note in your words
5. **The houses** — Moët & Chandon · Veuve Clicquot · Dom Pérignon · Bollinger · Krug · Armand de Brignac
6. **Close** — Drinks House 247 · drinkshouse247.co.uk · +44 20 3488 3266 · same day London, next day UK, open 24/7

Every scene mirrors its narration as a caption for muted viewing, with a
persistent 18+ line.

## Pipeline

Fully local, no cloud APIs: Piper TTS synthesizes one WAV per scene,
scene durations auto-fit each narration line, Pillow draws every frame,
and a bundled FFmpeg (`imageio-ffmpeg`) muxes video and audio into
H.264 + AAC.

```bash
pip install imageio-ffmpeg numpy pillow piper-tts

curl -LO https://github.com/rhasspy/piper/releases/download/v0.0.2/voice-en-us-ryan-high.tar.gz
tar xzf voice-en-us-ryan-high.tar.gz

PIPER_MODEL=./en-us-ryan-high.onnx python render.py
```

Output: `output/champagne-gifting-film.mp4`

## Notes

The `GB` coastline is real data, not a sketch: the largest ring of the
United Kingdom feature from Natural Earth's 1:50m admin-0 boundaries,
projected equirectangular with a cos(latitude) correction, simplified
with Douglas–Peucker to 145 points and normalised to unit height. It is
baked into the script so rendering stays offline.

## Customize

Edit the `SCENES` list to change the narration — timings adapt
automatically. The palette is five constants at the top; motifs live in
the `draw_*` functions.
