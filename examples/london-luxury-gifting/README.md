# London's Champagne — luxury gifting film

An opulent, monument-led gifting film with voiceover (1080×1920, 30fps,
~45s) for [Drinks House 247](https://drinkshouse247.co.uk).

Rich rather than restrained — the counterpart to the pared-back
[champagne-gifting-film](../champagne-gifting-film/). Midnight sky with a
warm horizon bloom, **real gold-foil gradients** (every headline and every
piece of artwork is drawn as a mask and filled with a metallic ramp:
shadow → warm body → specular highlight → back), an illustrated London
skyline, ornate corner filigree, drifting light shafts, sparkle and gold
bubbles.

## Monuments

Drawn from scratch as silhouette masks, then foil-filled:

**The Shard · 30 St Mary Axe (the Gherkin) · St Paul's Cathedral ·
the London Eye · Elizabeth Tower (Big Ben) · Tower Bridge**

Elizabeth Tower doubles as the hero of the same-day scene, with an
illuminated dial whose hands sweep a full revolution.

## Scenes

1. **Open** — the skyline strokes in beneath *THE GIFT OF CHAMPAGNE*
2. **Same day · London** — Big Ben, lit clock face · **30–45 MINUTES**
3. **Every postcode** — a delivery arc travels the skyline, *Mayfair to Canary Wharf*, around the clock
4. **UK-wide · next day** — Great Britain in gold, delivery arcs radiating from a pulsing London to Edinburgh, Manchester, Birmingham, Cardiff and Bristol
5. **Presented, not posted** — champagne bottle, gift box with a burgundy ribbon and bow, and a note card that writes itself
6. **The houses** — Moët & Chandon · Veuve Clicquot · Dom Pérignon · Bollinger · Krug · Armand de Brignac
7. **Close** — Drinks House 247 over the skyline · drinkshouse247.co.uk · +44 20 3488 3266 · same day London, next day UK, open 24/7

Every scene mirrors its narration as a caption for muted viewing, with a
persistent 18+ line.

## Run

```bash
pip install imageio-ffmpeg numpy pillow piper-tts

curl -LO https://github.com/rhasspy/piper/releases/download/v0.0.2/voice-en-us-ryan-high.tar.gz
tar xzf voice-en-us-ryan-high.tar.gz

PIPER_MODEL=./en-us-ryan-high.onnx python render.py
```

Output: `output/london-luxury-gifting.mp4`

## Implementation notes

- **Foil.** `paste_foil()` fills any mask with a vertical metallic ramp,
  so headlines and monuments share one light source. `foil_ctext()` adds a
  blurred halo behind the glyphs.
- **Glows.** PIL's `ImageDraw` *replaces* pixels instead of blending, so
  stacked translucent ellipses punch holes in what's beneath them.
  `glow_dot()` pastes a blurred mask onto the RGB base instead — use it
  for any bloom.
- **Coastline.** `GB` is real data: the largest ring of the United Kingdom
  feature from Natural Earth 1:50m, projected equirectangular with a
  cos(latitude) correction, simplified to 145 points and baked in so
  renders stay offline.
- **Caching.** Skyline, Big Ben and gift masks are `lru_cache`d, as are
  text masks, so each is rasterised once rather than per frame.

## Customize

Edit the `SCENES` list to change the narration — timings adapt
automatically. `FOIL_COL` controls the metal (try a cooler ramp for
silver/platinum); monuments live in the `_shard`, `_gherkin`,
`_st_pauls`, `_eye`, `_elizabeth_tower` and `_tower_bridge` functions,
and their layout in `skyline_mask()`.
