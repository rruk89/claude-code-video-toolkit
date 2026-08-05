# Where Did It All Go Wrong? — a George Best story

A voiced vertical short (1080×1920, 30fps, ~41s) for
[Drinks House 247](https://drinkshouse247.co.uk), retelling the most
famous champagne anecdote in football: George Best, a casino win, a date
with the reigning Miss World, a suite full of champagne and cash — and a
room-service waiter who asks, completely seriously,
*"Mr Best… where did it all go wrong?"*

Best told this story himself for decades; it's presented as
"a true story (as George told it)".

Same fully-local pipeline as the tequila short: Piper TTS per scene,
scene lengths auto-fit the narration, Pillow frames + master audio muxed
by a bundled FFmpeg into H.264 + AAC. Captions mirror the narration for
muted viewing; 18+ footer throughout.

## Run

```bash
pip install imageio-ffmpeg numpy pillow piper-tts

curl -LO https://github.com/rhasspy/piper/releases/download/v0.0.2/voice-en-us-ryan-high.tar.gz
tar xzf voice-en-us-ryan-high.tar.gz

PIPER_MODEL=./en-us-ryan-high.onnx python render.py
```

Output: `output/celebrity-story-short.mp4`

## Customize

Edit the `SCENES` list to change the narration — timings adapt
automatically. Scene visuals live in the `vis_*` functions (football,
casino chips, ice bucket, banknotes, crown, room-service cloche).
