# Mascot design brief

The channel has one recurring character — a signature, not a story engine.
It bounces into frame at the start of every video, pops up briefly between
scenes to react to what's happening, and bounces out at the end. The theme
content (colors, counting, animals, bedtime, ...) is always the star; the
mascot is the brand.

The actual design lives in `config/config.yaml` under `mascot:` — this file
explains the reasoning behind it, so future edits stay consistent.

## Why the design is this simple

- **AI generation consistency.** Text-to-video models are weak at holding a
  character's exact look consistent across independently-generated clips.
  A single flat color, no clothing, no props, and a big simple silhouette
  gives the model the least it could get wrong, and keeps every generated
  clip recognizably "the same character."
- **It's pre-rendered once, not per video.** `scripts/generate_mascot_assets.py`
  renders `bounce_in`, `reaction`, and `bounce_out` a single time into
  `assets/mascot/*.mp4`; every video composites those same clips in via
  ffmpeg instead of asking the model to redraw the character fresh each
  time. This is also why consistency matters so much here — get the design
  right once, and it's right in every video from then on, automatically.
- **Sticker/merch potential.** A bold, flat-color, simple silhouette is
  exactly what reproduces well small (stickers, favicons, thumbnail badges).
  Detailed shading, fine linework, or busy color would get muddy at sticker
  size and is also harder for the model to hold consistent.

## If the channel takes off and you want real merch

The AI-generated video frames are good enough to prove the design works
and to see if an audience responds to the character — but they're not good
source art for print. Compression artifacts, slightly-off proportions
between frames, and non-vector output all show up badly at sticker/poster
size. Once you've validated the design (and the name — "Puff" is a
placeholder), the practical path is:

1. Pick your favorite generated frame(s) as a reference.
2. Get a human illustrator (or redraw it yourself) to produce a clean
   vector version — same silhouette, same colors, same personality — for
   actual print production.
3. Keep the AI-generated clips for the channel; use the vector version for
   merch, thumbnails, and any print/product use.

## Regenerating after a design change

Edit `mascot.visual_description` (and the per-clip `prompt_suffix`s if
needed) in `config/config.yaml`, then re-run:

```bash
python scripts/generate_mascot_assets.py
```

This overwrites `assets/mascot/bounce_in.mp4`, `reaction.mp4`, and
`bounce_out.mp4`. Existing videos already in the review queue or approved
folder are unaffected — only videos generated *after* the regeneration will
use the new look.
