# DirectoR 0.1.3

* Fixed a crash on launch in RStudio: `Error in as.character(funBody[[idx]][[1]]): cannot coerce type 'closure'`.
  RStudio's Shiny debugging hook reads the code of every observer, and the error guard added in 0.1.2 put a
  function object inside that code. The guard now contains only plain code. A test now walks every observer's
  code the same way RStudio does.

# DirectoR 0.1.2: speed and resilience

* Slow apps: no fixed start-up deadline. DirectoR waits while the app is busy (CPU or log activity) and only
  gives up after 5–10 minutes without any sign of life, with live progress ("Starting the app… 45s · Loading…").
  It also follows the address an app prints ("Listening on …") when the app picks its own port.
* Slow pages: the browser waits for the page, not for every resource. Third-party files (fonts, CDNs) get 8 s,
  trackers and chat widgets are blocked, navigation is retried, and Shiny counts as ready once it is connected and idle.
* Autopilot launches the app once and reuses it for scouting and recording. It keeps going when the voice,
  the music, a shot or the captions fail, and reports what was skipped.
* Shots and render chunks run as supervised processes: a stuck browser is killed after a few minutes without
  progress, and the work is retried once. Apps are never left running after the engine stops.
* Sound previews now work in Safari. Media is served with HTTP byte ranges, previews start directly from your
  click, and there is a WAV fallback for browsers that can't play MP3. Films in Export seek properly.
* An error in the app shows a message instead of disconnecting the session. Files are written atomically,
  the live preview retries if a reload fails, and reloading the page reopens your film.
* Autopilot from the Library defaults to a Draft (minutes); render the Final from Export. Render uses more workers
  on machines with more cores.

# DirectoR 0.1.1

* R apps that use renv (or packrat) no longer fail with "cannot open file 'renv/activate.R'": the project's
  `.Rprofile` is skipped and the app runs on your installed packages. Source › Advanced › *R projects with
  renv* can restore the lockfile instead. Folder copies keep renv's metadata.
* Python discovery: DirectoR finds a Python that has the engine's packages, even when R runs from
  RStudio/R.app with a minimal PATH (Homebrew, python.org, pyenv, conda, reticulate). You can choose and
  remember one in the Engine check, which also shows versions and the real error.
* The engine gets Homebrew's folders on its PATH (ffmpeg, git, node).
* Music previews: selecting a mood plays it; play badges; "Preview with these settings"; sound-effect
  previews. Bundled previews play instantly.
* Music synthesis is about 5x faster (wavetable oscillators).
* "Install from CRAN" reports when it's done, then scouts again.

# DirectoR 0.1.0

* First release: a Shiny studio that directs launch and teaser films (< 60 s) for web apps, Shiny apps
  and websites, from a link, a Git repository, a zip or a folder (or screenshots and recordings).
* Engine (`inst/engine`): scout, plan (5 templates), voice-over (8 providers, auto fallback), deterministic
  60 fps capture with smart zoom on clicks, original music (7 moods) and sound design, stage renderer with
  12 transitions and 4 formats (16:9, 9:16, 1:1, 4:5), captions, posters.
* Built on the QuantSkill promo tooling (dev/video).
