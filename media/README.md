# DirectoR: promo video

| File | What |
|---|---|
| `DirectoR_teaser_30s.mp4` | 30 s teaser: fast cuts on a 120 BPM grid, kinetic type, music and UI clicks. No voice. |
| `DirectoR_teaser_30s_poster.png` | Poster frame (the end card). |

Format: 1920 × 1080, 60 fps, H.264 (High, yuv420p), AAC 48 kHz stereo at 256 kb/s, `+faststart`. Loudness
(measured with ffmpeg `ebur128`): −14.0 LUFS integrated, true peak −1.9 dBTP (targets −14 LUFS and ≤ −1 dBTP,
as for QuantSkill's teaser).

## How it was made

With **QuantSkill's video utility** (`QuantSkill/dev/video`), imported read-only and unchanged:

| Step | From QuantSkill/dev/video | DirectoR-specific (`taiga-design-system/tools/video/directoR/`) |
|---|---|---|
| Footage | `recorder.py`: deterministic 60 fps capture (virtual clock, frame-stepped CSS animations, seeded randomness, a drawn cursor that drives the real mouse) | `shots.py`: what to film in the DirectoR studio |
| Edit | `stage/stage.js`, `stage/stage.css`: the motion-graphics engine | `stage/teaser.js`: the timeline, cut to the form of the teaser score |
| Render | `render.py`: stage → frames → H.264, three parallel chunks | – |
| Music | `music.py` `teaser()`: original score synthesised with numpy (no samples or loops); UI clicks placed from the footage's click markers | – |
| Mux | `ff.py` (encoder); targets of `make.py`'s `mux_teaser()` (−14 LUFS, −1 dBTP, LRA 9, AAC 256k) | `make_promo.py`: `mux_teaser()` hard-codes QuantSkill's file names. This mux measures first (two-pass `loudnorm`), then limits with headroom for AAC overshoot |

Rebuild: `python3 taiga-design-system/tools/video/directoR/make_promo.py` (add `--reshoot` to record the
footage again). Intermediate files go to `$QS_VIDEO_BUILD` (default `/tmp/drvideo`), separate from
QuantSkill's own build folder.

## What's in it

"Your app deserves a launch film." (DirectoR's own headline) → pasting `~/code/quantskill` and
**Create film** → the autopilot overlay → what the scout saw → the storyboard with the live preview
playing → recorded footage (hover to play) → picking a music mood → "Under 60 seconds." → format and
look → rendering, with the job dock → "Shiny · Streamlit · Quarto · Any website." → end card.

## Things to know before publishing

- **The studio footage comes from a test bench, not a running R session.** No R runtime was available
  where this was made. The studio page is DirectoR's real UI (`app_ui()` and every `renderUI` output
  from its own R code, run in webR; `director.css`, `director.js`), and its state changes go through
  `director.js`'s own message handlers. See `taiga-design-system/tools/bench/README.md`.
- **The films inside it are real DirectoR output.** The QuantSkill and Lumen study-story projects were
  made by DirectoR's engine (`python -m director scout / plan / capture / timeline / render`): scout
  screenshots, the storyboard and script (written by DirectoR's built-in copywriter from the README),
  the recorded footage, the live preview and the draft render on the Export page.
- **Progress messages are simulated.** The autopilot overlay and the render dock are driven by `dr-job`
  messages written for the video, with texts of the kind the engine reports. The timings shown
  (for example "~1m 54s left") are illustrative.
- **The music is original** (synthesised by QuantSkill's `music.py`), so there is nothing to license.
- The font on the title cards is Inter (SIL Open Font License), as in QuantSkill's films.

This folder is not yet in `.Rbuildignore`. Add `^media$` (and `^docs$`) there before `R CMD build`, so the
video does not end up in the package tarball.
