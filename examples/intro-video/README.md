# Intro Video Example

A self-contained, code-driven video render — no timeline editor, no system
FFmpeg, no Node, no GPU. Pure Python draws each frame with Pillow and pipes
them to a bundled FFmpeg (via `imageio-ffmpeg`) for H.264 encoding.

It produces a ~10-second 1920×1080 / 30fps animated intro card for the toolkit:
animated title, sweeping underline, staggered feature reveal, and a fade
in/out.

## Run

```bash
pip install imageio-ffmpeg numpy pillow
python render.py
```

Output: `output/toolkit-intro.mp4`

## Why this approach

It's the most dependency-light way to generate a real video anywhere Python
runs. `imageio-ffmpeg` ships a static FFmpeg binary, so there's nothing to
install at the system level. For richer motion-graphics work, reach for
Remotion (`npx skills add remotion`) — see the repo [README](../../README.md).

## Customize

Everything is driven by constants at the top of `render.py`:

- `W`, `H`, `FPS`, `DURATION` — resolution and length
- `BG_TOP` / `BG_BOTTOM` / `ACCENT` — palette
- `FEATURES` — the bullet list
- Timings live in each `seg(t, start, end)` call inside `render_frame()`
