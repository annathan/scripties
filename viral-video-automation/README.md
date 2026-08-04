# Viral Video Automation

An automated pipeline that scans what's currently performing well in a
chosen kids/cute-content niche on YouTube, generates original AI video
concepts inspired by those patterns, produces the videos, and — after a
mandatory human approval step — publishes them to YouTube.

No stage uploads or publishes anything automatically. Every video sits in a
review queue until you explicitly approve it.

## Why this design

**Not a copy machine.** Stage 1 only extracts pattern-level signals
(topics, title structure, pacing, view velocity) from top-performing
videos — never their scripts, footage, or specific content. Stage 2's
prompts to Claude explicitly require wholly original titles, characters,
and stories inspired by those patterns, not reproductions.

**YouTube monetization risk.** YPP's policies restrict monetizing
"inauthentic," "mass-produced," or "repetitious" content — this has hit
faceless/AI-generated channels since 2023–2024. This pipeline is built to
reduce that risk (original scripts per video, distinct scenes, real
editing/captions/music) but it doesn't eliminate it — a real human should
skim every video before it's approved, and the channel's early output
should aim for variety and polish, not volume.

**Kids content specifically.** `made_for_kids` is set on every upload
(config/config.yaml → `upload.made_for_kids`), which YouTube requires by
law (COPPA) for child-directed content — it auto-disables personalized ads
and comments on the video. Style guardrails in config also force
stylized/cartoon visuals rather than photorealistic depictions of children.

## The mascot

The channel has one recurring character (`config.yaml` → `mascot:`,
placeholder name "Puff") — a signature, not the show. It bounces in as a
bumper at the very start of every video, pops into a corner briefly at each
scene transition to react, and bounces out at the end. Scene content itself
is always theme-driven (colors, counting, animals, ...) and never depends
on the mascot appearing in it.

The mascot's clips are pre-rendered **once** via
`python scripts/generate_mascot_assets.py` into `assets/mascot/`, then
composited into every subsequent video with ffmpeg — this sidesteps
text-to-video models' weak character consistency across independently
generated clips (the single biggest practical obstacle to a recurring
character), and is much cheaper than regenerating it per video. Re-run that
script any time you tweak the design in config.

Design rationale, and — if the channel takes off — how to turn the AI
design into real merch/stickers, is in `assets/mascot/DESIGN_BRIEF.md`.

## Narration (text-to-speech)

Every scene's `narration` line gets voiced (`config.yaml` → `narration:`)
and mixed into that scene's audio — this is what makes captions readable
*and* audible, since text-to-video providers don't generate narration
matched to your script on their own. Narration is **spoken**, not sung —
a concept titled "A Silly Sorry Song" gets a spoken narration reading of
its lines, not an actual song. Real singing would need a different kind
of tool (e.g. Suno/Udio-style music generation) and isn't wired in.

Each line is fitted to its scene's *actual* rendered duration (the same
ffprobe-measured value captions and mascot timing use): trimmed if it
runs long, padded with silence if it runs short. If you see "narration is
longer than its video clip" warnings often, either shorten your narration
style or give scenes more room (`target_duration_seconds` /
`scenes_per_video`). Background music gets ducked
(`music_volume_when_narration`) so it doesn't compete with narration.

Default provider is ElevenLabs, via `TTS_PROVIDER=elevenlabs` +
`ELEVENLABS_API_KEY` — pick an actual voice from
[elevenlabs.io/app/voice-library](https://elevenlabs.io/app/voice-library)
and put its ID in `narration.voice_id` (the shipped default, "George", is
just ElevenLabs' own docs example, not a considered choice for kids'
content). Unlike `pika.py` (built from search-result summaries since
fal.ai was blocked outright), `elevenlabs.py` uses ElevenLabs' official
Python SDK and was confirmed directly against their "Make your first
request" docs example — no unverified guesswork here.

## Running this unattended

The goal is a couple of uploads a week without babysitting a terminal. To
that end:

- **Retries.** Every external call (YouTube API, Claude, the video-gen
  provider, upload chunks) retries with backoff on transient failures.
  Non-transient ones (bad API key, quota exhausted) fail immediately
  instead of wasting minutes retrying something that will never succeed.
- **One bad concept doesn't kill the batch.** `generate` isolates each
  concept — if one fails, it's logged and skipped, and the rest of the run
  continues. Check the end-of-run summary for anything that needs a
  second look.
- **Ideation is validated, not trusted blindly.** The LLM's response is
  parsed and schema-checked (right keys, right scene count); if it comes
  back malformed, it's automatically re-asked (up to 3 attempts) rather
  than writing garbage into the review queue.
- **Duplicate-avoidance.** Recent titles are fed back into the ideation
  prompt (`ideation.avoid_repeating_last_n_titles` in config) so repeated
  runs don't quietly fill the queue with near-identical videos.
- **Spend cap.** `video_generation.max_videos_per_run` hard-limits how many
  videos one `generate` call will produce, independent of how many
  concepts stage 2 came up with — a guardrail against an unexpectedly large
  ideation batch turning into an unexpectedly large bill.
- **Config is validated at load time** — a typo'd config.yaml fails fast
  with a clear message instead of a confusing `KeyError` three stages in.
- **Everything logs to `data/pipeline.log`** (in addition to the console),
  so a scheduled/unattended run leaves a trail you can check after the
  fact instead of needing to watch it happen.
- **`review prune [days]`** deletes the video files (not the metadata) for
  rejected items older than the given cutoff (default 14 days), so an
  unattended cadence doesn't slowly fill the disk with stuff you already
  said no to.

This repo doesn't include the actual cron/scheduler wiring yet (e.g. a
systemd timer, GitHub Actions schedule, or similar) — `python -m
src.pipeline run` is safe to point at whatever scheduler you prefer since
everything above already assumes it's running unattended.

## Pipeline

```
1. scan     YouTube Data API  -> data/trends/*.json
              (find currently-performing videos in the niche, score them)
2. ideate   Claude            -> data/concepts/*.json
              (turn trend patterns into original concepts + scene scripts)
3. generate text-to-video API -> data/review_queue/<slug>/final.mp4
              (render each scene, concatenate, burn captions, mix music)
4. review   you                -> data/approved/<slug>/
              (watch the gallery, approve or reject each video)
5. upload   YouTube Data API  -> data/uploaded/<slug>.json
              (publish an approved video; you control privacy_status)
```

Run stage by stage, or `scan` → `generate` end to end with `run` (which
still stops at the review gate):

```bash
python -m src.pipeline run
python -m src.pipeline review gallery   # open data/review_queue/index.html
python -m src.pipeline review approve <slug>
python -m src.pipeline upload <slug>
python -m src.pipeline review prune     # delete old rejected videos, keep the metadata
```

## Setup

**macOS / Linux:**
```bash
cd viral-video-automation
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

**Windows (cmd.exe):**
```
cd viral-video-automation
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
```

**Windows (PowerShell):** same as above, but `.venv\Scripts\Activate.ps1`
and `Copy-Item .env.example .env`.

Install [ffmpeg](https://ffmpeg.org/) and make sure it's on `PATH` — every
stage-3 provider (including the keyless mock one) shells out to it for
concatenation, captions, and music mixing. On Windows: `winget install
ffmpeg` (or Chocolatey's `choco install ffmpeg`), then open a new terminal
so `PATH` picks it up. Confirm with `ffmpeg -version` on any platform.

### Try it with zero API keys first

`VIDEO_PROVIDER=mock` (the default in `.env.example`) renders placeholder
clips locally via ffmpeg instead of calling a real text-to-video API. You
still need `YOUTUBE_API_KEY` (free, read-only) and `ANTHROPIC_API_KEY` for
stages 1–2, but you can validate the whole scan → ideate → generate →
review flow, including captions, mascot compositing, and music mixing,
before spending anything on real video generation or setting up YouTube
upload OAuth. Run `python scripts/generate_mascot_assets.py` once first
(also works with `VIDEO_PROVIDER=mock`) so stage 3 has bumper/reaction
clips to composite in.

### Credentials, one stage at a time

| Stage | Needs | How to get it |
|---|---|---|
| 1. scan | `YOUTUBE_API_KEY` | Google Cloud Console → enable "YouTube Data API v3" → Credentials → API key. Read-only, no OAuth. |
| 2. ideate | `ANTHROPIC_API_KEY` | [console.anthropic.com](https://console.anthropic.com) |
| 3. generate | `RUNWAY_API_KEY` or `FAL_KEY` | Set `VIDEO_PROVIDER=runway` or `VIDEO_PROVIDER=pika`. Pika's API is served through [fal.ai](https://fal.ai) (a `FAL_KEY`, not a separate Pika key). See `src/video_providers/` to plug in a different vendor (Kling, Luma, Sora, ...) — they all follow roughly the same submit/poll/download shape. |
| 3. narration | `ELEVENLABS_API_KEY` | Set `TTS_PROVIDER=elevenlabs`. [elevenlabs.io](https://elevenlabs.io) — also pick a real voice ID from their voice library for `narration.voice_id` in config. |
| 5. upload | OAuth client + token | Run `python scripts/setup_youtube_oauth.py` once (see that script's docstring for the one-time Cloud Console setup). |

## Configuration

Everything content-shaped lives in `config/config.yaml`: search queries and
scoring thresholds for stage 1, the LLM model and originality/safety
guardrails for stage 2, resolution/duration/scene count for stage 3, and
`privacy_status` / `made_for_kids` for stage 5. Secrets always come from
`.env`, never the yaml.

Start `upload.privacy_status` at `private` (the default) and manually
promote videos to `public` from YouTube Studio until you trust the
pipeline's output — flipping that default to `public` in config is a
one-line change once you're confident.

## Project layout

```
config/config.yaml           all the tunable pipeline settings, incl. mascot design
src/
  trend_scanner.py           stage 1
  ideation.py                stage 2 (incl. JSON/schema validation + duplicate-avoidance)
  video_generator.py         stage 3 (scenes -> concat -> mascot composite -> captions -> narration -> music -> bumpers)
  video_providers/           stage 3 (pluggable text-to-video backends)
    base.py                  the interface
    mock.py                  keyless local placeholder (ffmpeg color+text)
    runway.py                real text-to-video example
    pika.py                  real text-to-video example (via fal.ai)
  tts_providers/             stage 3 (pluggable text-to-speech backends)
    base.py                  the interface
    mock.py                  keyless local placeholder (a tone, not silence)
    elevenlabs.py            real text-to-speech provider
  review.py                  stage 4 (incl. prune for old rejected videos)
  uploader.py                stage 5
  pipeline.py                CLI entrypoint wiring it all together
  retry.py                   shared exponential-backoff helper for external calls
  logging_setup.py           shared console + data/pipeline.log logging config
scripts/
  setup_youtube_oauth.py     one-time OAuth authorization for uploads
  generate_mascot_assets.py  renders the mascot's clip library (run once, or after a redesign)
assets/
  music/                     your own royalty-free/licensed tracks (gitignored)
  mascot/                    generated mascot clips (gitignored) + DESIGN_BRIEF.md
data/                         all generated output (gitignored except folder structure)
```

## Adding a real video-gen provider

Implement `VideoProvider.generate_scene_clip()` in a new file under
`src/video_providers/`, register it in `src/video_providers/__init__.py`'s
`get_provider()`, and point `VIDEO_PROVIDER` at it. `runway.py` and
`pika.py` are working templates for the general "submit prompt → poll job
→ download clip" shape most vendors use.

**A note on `pika.py` specifically:** Pika's official API access goes
through fal.ai (a `FAL_KEY`, not a separate Pika-branded API) — confirmed
against fal's schema for `fal-ai/pika/v2.2/text-to-video`. One constraint
worth knowing: fal's `duration` field is an enum of exactly **5 or 10
seconds**, not a free-form number, so `pika.py` rounds whatever
`scene_duration` the pipeline asks for to the nearest allowed value —
the clip Pika actually renders can therefore be shorter/longer than
requested. `video_generator.py` accounts for this by measuring each
clip's real duration (`ffprobe`) after generation and building captions
and mascot-transition timing from that, rather than trusting the request
— so this is safe to use even if your scene length doesn't land neatly on
5 or 10 seconds, but the video's actual total runtime may end up shorter
or longer than `target_duration_seconds` as a result.
