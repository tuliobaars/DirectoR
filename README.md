# DirectoR

**Launch and teaser films for apps and websites.** You paste a link to a website, a Shiny app or a
Git repository, or drop a zip of the source. DirectoR then launches the app and explores it like a
curious user. It writes a storyboard and a voice-over script, records real interactions as perfectly
smooth 60 fps footage, composes original music, and cuts a film under 60 seconds with kinetic
typography, camera moves and transitions.

The project grew out of the promo pipeline in QuantSkill's `dev/video` folder. That pipeline was
hand-scripted for one app. DirectoR makes it generic and data-driven, and wraps it in a Shiny studio.

```r
# install.packages(c("shiny", "bslib", "jsonlite", "processx"))
# then install DirectoR from this folder: R CMD INSTALL DirectoR   (or devtools::install("DirectoR"))
DirectoR::run_app()
```

To try it right away, there is a small example dashboard in `inst/examples/orbit`. Paste the
folder's path into the Library page, or run the app and paste its URL:

```r
shiny::runApp(system.file("examples/orbit", package = "DirectoR"), port = 3838)   # then paste http://127.0.0.1:3838
```

## One-time setup of the film engine

The engine is Python (bundled in `inst/engine`). It drives Chromium through Playwright, and it uses ffmpeg.

```sh
brew install ffmpeg                      # macOS  (Ubuntu: sudo apt install ffmpeg)
python3 -m pip install -r "$(Rscript -e 'cat(system.file("engine/requirements.txt", package = "DirectoR"))')"
python3 -m playwright install chromium
```

In the app, click the terminal icon at the bottom left to check the engine. It shows the versions,
every Python it found (and whether each one has the packages), and the command that fixes anything
missing. From R: `DirectoR::director_doctor()`.

**Which Python?** R started from RStudio or R.app on macOS doesn't see your shell's `PATH`, so a
plain `python3` there is usually Xcode's `/usr/bin/python3`, without your packages. DirectoR therefore
searches the usual places: Homebrew, python.org, pyenv, conda/miniforge and reticulate. It uses the
first Python that can import the engine's packages. Pick another one in the Engine check (the choice is
remembered), set `DIRECTOR_PYTHON`, or call `run_app(python = "/path/to/python3")`. Homebrew's
`/opt/homebrew/bin` and `/usr/local/bin` are added to the engine's `PATH`, so ffmpeg and git are found too.

**Updating:** replace the whole DirectoR folder (delete the old one first, so that no stale engine files
remain), then reinstall it. The Engine check shows "DirectoR x.y.z · engine x.y.z"; the two must match.

Optional voices:

| Voice | Setup | Notes |
|---|---|---|
| macOS voices | built in | Download a Premium or Enhanced voice: System Settings › Accessibility › Spoken Content › Manage Voices. |
| Edge neural | `pip install edge-tts` | Free neural voices. Needs internet. |
| OpenAI | API key in the app (kept for the session only) | `gpt-4o-mini-tts`, follows the tone you pick. |
| ElevenLabs | API key in the app | Studio quality. |
| Piper | `pip install piper-tts` | Offline neural. The voice model downloads on first use. |
| Pico / eSpeak | `pip install ttspico` / `apt install espeak-ng` | Offline. Synthetic sound; fine for drafts. |
| Your voice | nothing | Record each line in the browser, or upload files. The cut follows your timing. |

In **Auto** mode, DirectoR picks the best voice that works on your machine. If a voice fails (for
example, no internet for Edge), it falls back to the next one.

## The studio

| Page | What you do there |
|---|---|
| **Library** | Paste a link or drop a zip. Pick a format and, if you like, *Direct it for me* (full autopilot). All your films are listed with posters. |
| **Source** | Choose the source type (website, Git repo, zip, folder, or screenshots and recordings) and launch options (command, start page, browser size, dark scheme, fps, sharpness). Shows what the scout found: app type, missing R packages (one-click install), screens, colours. Brand fields start empty, which means "use what was detected". |
| **Story** | Five templates: Launch film, Teaser, Feature tour, Social vertical, Calm demo. Tone, audience and an optional AI copywriter (OpenAI, Anthropic, or a local Ollama/LM Studio server). Every scene is editable: on-screen text, voice-over line, minimum duration, transition, and for footage the shot, layout and camera. You can reorder, duplicate, skip and add scenes (hook, title, shot, features, montage, 3-D wall, stat, quote, end card). The live preview plays the film in real time, with music and voice, and no rendering. |
| **Shots** | The recorded footage; hover a card to play it. Each shot is a recipe of actions: click, hover, type, choose an option, drag a slider, scroll, wait for the app, press a key. Targets come from the scout's element lists, or you click on the screenshot. If you change a recipe, the shot is marked for re-recording. |
| **Sound** | Voice provider, voice, speed, pronunciations, and a preview of each line. Music has 7 moods (Keys, Pulse, Bright, Drive, Ambient, Lo-fi, Cinematic): selecting a mood plays a preview, or use its play badge. "Preview with these settings" composes a preview with your harmony, variation and transpose. Set tempo, level and ducking, or upload your own track. Sound design (UI clicks, whooshes, hits, risers) has its own previews and can be switched off. |
| **Look** | Format (16:9, 9:16, 1:1, 4:5); theme (light, dark, brand gradient); background (aurora, mesh, grid, spotlight, solid); typeface; browser window chrome (macOS, minimal, glass, none); corner radius; film grain; transitions (12 kinds, or auto per cut); captions (clean or bold word-by-word); cursor style. |
| **Export** | Draft (half size, 30 fps, fast) or Final (1080p60). Optional vertical and square versions in the same run. Gives you the MP4, a captioned MP4, SRT, poster and script. |

## What it can film

DirectoR detects the kind of app, installs nothing on its own, and launches it on a free local port:

* **Shiny (R)**: `app.R`, `ui.R` + `server.R`, golem or rhino projects, and apps inside R packages
  (`inst/<dir>/app.R`). Missing R packages are listed, and you can install them in one click.
* **Shiny for Python**, **Streamlit**, **Gradio**.
* **Quarto** projects (needs `quarto`), **Node** apps (`npm run dev`/`start`), and **static sites**
  (`index.html` in the root, `docs/`, `dist/`, `build/`, `public/`, `_site/`, or a lone HTML file).
* **Anything else**: give a launch command with `{port}` in *Source › Advanced*. Or paste the URL of a
  running app, or upload screenshots and screen recordings.

GitHub, GitLab, Bitbucket and Codeberg links are cloned. `…/tree/<branch>/<subfolder>` links clone
that branch and use that subfolder.

Python apps must have their dependencies installed in the Python that launches them (the engine's
Python, or the one in your launch command). Node apps get `npm install` on first launch. Responsive
layouts are handled: at the Mobile browser size, DirectoR opens hamburger menus to reach collapsed tabs.

## How it works

```
scout     launch the app, explore tabs, pages and links, inputs and outputs; learn the name, tagline, logo and colours
plan      storyboard + voice-over script + shot recipes (README features matched to the screens they describe)
voice     one clip per line, cleaned up, cached; the scenes stretch to fit the voice-over
capture   record each shot with a deterministic clock: perfectly smooth 60 fps, real hover and click states
music     compose a score that follows the cut (drop, break, hits, ending), plus sound design; mix and duck it
render    the stage (HTML/CSS/JS motion graphics) is a pure function of time; Chromium renders it frame by frame
mux       loudness (-14 LUFS music-only, -16 LUFS with speech), captions, poster, script
```

Each step is also a command: `python -m director <step> --project <folder>`, run from `inst/engine`.
The R functions `dr_job_start()`, `dr_job_status()` and `dr_run()` run the steps from R, for scripting.

### Deterministic capture

Headless Chromium can't screen-record smoothly. So, as in QuantSkill's recorder, time is virtual:

* Playwright's clock fakes timers, `requestAnimationFrame` and `Date`.
* Every CSS animation is seeked frame by frame.
* `Math.random` is seeded.
* A drawn cursor drives the real mouse, so hover states are real.

Server-backed apps (Shiny, Streamlit) still answer in real time. The recorder waits for them to be idle,
and records meanwhile. Very heavy pages (large blur filters) are detected, and their blurs are replaced
by look-alike masks so that recording stays fast. Each shot also stores the cursor's path. The camera
uses it to zoom smoothly onto clicks and to follow the pointer, like a screen-recording editor.

### Project folder

Projects live in `tools::R_user_dir("DirectoR", "data")/projects`. Change this with `DIRECTOR_HOME` or
`run_app(home = …)`. Each film is one folder:

```
project.json  storyboard.json  timeline.json  facts.json  scout.json  status.json  log.txt
src/  scout/  shots/<id>/f00000.jpg…  vo/  audio/  stage/  preview.html  out/
```

`storyboard.json` is plain JSON. You can edit it by hand, version it, or generate it.

## Reliability

* **Slow apps** are expected. DirectoR waits while the app is busy and gives up only after it stalls (at least 5
  minutes, see *Source › Advanced › Start-up patience*). Progress shows in the job panel. Autopilot starts the app
  once and reuses it.
* **Slow or broken third-party resources** (fonts, CDNs, analytics) can't block the browser: they get 8 s and are
  then dropped.
* **Failures degrade instead of aborting** in autopilot: no voice gives a music-only film, no music leaves the sound
  design, and a shot that can't be recorded falls back to its screenshot. Stuck browser workers are restarted and
  the work is retried.
* Every engine step writes `log.txt` in the film's folder, and the job panel's terminal icon shows it.

## Safety

DirectoR runs the code you point it at: it launches apps from repositories, zips and folders on your
machine (and may install R packages you approve). Use it on code you trust, as you would when running the
app yourself. API keys typed in the app are kept in memory for the session and never written to disk.

## Limits

* Films are capped at about 60 s. If the script is too long, synthetic voices are sped up a little
  and you get a warning.
* The built-in copywriter only uses what the app and its README say, so no invented claims. It is
  plain. For livelier copy, edit the script or switch on the AI copywriter.
* Pages behind a login need a start page that is already logged in, or a launch command that logs in.
  Otherwise, use screenshots and recordings.
* Recording speed depends on the machine and the page. Most apps record at 5–15 frames per second per
  browser, and a typical film needs 1–3 minutes of capture. A Final render of a 45 s film takes a few
  minutes on a laptop.

## Tests

```sh
python3 tests/engine/test_engine.py            # engine: copy, detection, timeline, music, captions, end-to-end render
Rscript -e 'testthat::test_dir("tests/testthat")'
```

## Credits

Inter typeface by Rasmus Andersson (SIL Open Font License), stored base64-encoded in
`inst/engine/stage/inter.woff2.b64`. The music and sound effects are synthesised from scratch, so
there is nothing to license. The film engine builds on the QuantSkill promo tooling.
