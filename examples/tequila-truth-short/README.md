# Skip the Lime — Tequila, Honestly

An informative vertical short **with voiceover** (1080×1920, 30fps, ~49s)
for [Drinks House 247](https://drinkshouse247.co.uk): why good tequila
doesn't need the salt-and-lime ritual.

Fully local pipeline — no cloud APIs:

1. **Piper TTS** synthesizes one WAV per scene from the `SCENES` script
2. Scene durations auto-fit each voiceover line (`VO_LEAD`/`VO_TAIL` pads)
3. **Pillow** draws every frame; frames + master audio are muxed by a
   bundled FFmpeg (`imageio-ffmpeg`) into H.264 + AAC

Scenes: no-lime sign hook → salt+lime = a mask → "mixto" 51% agave bar
chart → 100% agave tasting notes → sip it like whisky → read the label →
brand CTA. Each scene mirrors its VO line as a bottom caption for muted
viewing, with an 18+ footer throughout.

## Run

```bash
pip install imageio-ffmpeg numpy pillow piper-tts

# Voice model (~100 MB) — en-us-ryan-high from the rhasspy/piper
# v0.0.2 GitHub release:
curl -LO https://github.com/rhasspy/piper/releases/download/v0.0.2/voice-en-us-ryan-high.tar.gz
tar xzf voice-en-us-ryan-high.tar.gz

PIPER_MODEL=./en-us-ryan-high.onnx python render.py
```

Output: `output/tequila-truth-short.mp4` (per-scene VO WAVs land in
`output/vo/`).

## Customize

- Edit the `SCENES` list to change the script — timings adapt automatically
- Swap `PIPER_MODEL` for any Piper voice (e.g. an en_GB voice for a
  British accent)
- Palette/fonts are constants at the top; per-scene visuals live in the
  `vis_*` functions
