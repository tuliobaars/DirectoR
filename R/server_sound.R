# Sound page: voice-over and music ---------------------------------------------------------

PROVIDERS <- list(
  auto = list(label = "Auto", sub = "Best available"), human = list(label = "Your voice", sub = "Record or upload each line"),
  say = list(label = "macOS voices", sub = "Premium voices sound great"), edge = list(label = "Edge neural", sub = "Free, online"),
  openai = list(label = "OpenAI", sub = "Expressive, API key"), elevenlabs = list(label = "ElevenLabs", sub = "Studio quality, API key"),
  piper = list(label = "Piper", sub = "Neural, offline"), pico = list(label = "Pico", sub = "Offline, synthetic"), espeak = list(label = "eSpeak", sub = "Offline, robotic"))
MOODS <- list(
  auto = list(label = "Auto", sub = "Fits the template", c = c("#6366f1", "#ec4899")), keys = list(label = "Keys", sub = "Felt piano, soft pulse", c = c("#60a5fa", "#a78bfa")),
  pulse = list(label = "Pulse", sub = "Electronic, four-on-the-floor", c = c("#f472b6", "#8b5cf6")), bright = list(label = "Bright", sub = "Pop: stabs, claps, bells", c = c("#fbbf24", "#f472b6")),
  drive = list(label = "Drive", sub = "Synthwave arps, saw bass", c = c("#22d3ee", "#a855f7")), ambient = list(label = "Ambient", sub = "Airy pads, no drums", c = c("#93c5fd", "#c4b5fd")),
  lofi = list(label = "Lo-fi", sub = "Dusty chords, vinyl", c = c("#fdba74", "#a3a3a3")), cinematic = list(label = "Cinematic", sub = "Drones, toms, big hits", c = c("#f87171", "#6366f1")),
  custom = list(label = "Your track", sub = "Upload a licensed file", c = c("#34d399", "#60a5fa")), none = list(label = "No music", sub = "Voice and sound design", c = c("#52525b", "#3f3f46")))
KEY_ENV <- c(openai = "OPENAI_API_KEY", elevenlabs = "ELEVENLABS_API_KEY")

eq_vis <- function(c1, c2, n = 14, seed = 1, mood = NULL) {
  set.seed(seed)
  HTML(paste0("<div class='eq' style='position:absolute;inset:0;display:flex;align-items:center;justify-content:center;gap:3px;background:radial-gradient(circle at 30% 30%,", c1, "33,transparent 60%),#0d0d14'>",
              paste0(sprintf("<i style='width:3px;border-radius:2px;height:%d%%;background:linear-gradient(%s,%s);animation:eq %.2fs ease-in-out %.2fs infinite'></i>",
                             sample(20:85, n, TRUE), c1, c2, stats::runif(n, .7, 1.4), stats::runif(n, 0, .6)), collapse = ""),
              if (!is.null(mood) && !mood %in% c("auto", "none")) sprintf("<span class='pv' data-preview='%s' title='Listen'><svg viewBox='0 0 24 24'><path class='pl' d='M8 5.5v13l11-6.5z'/><path class='st' d='M7 7h10v10H7z'/></svg></span>", mood) else "",
              "</div>"))
}

SFX_PREVIEWS <- c(click = "Click", whoosh = "Whoosh", hit = "Hit", riser = "Riser", tick = "Tick")

srv_sound <- function(input, output, session, rv, ctx) {
  output$voice_providers <- shiny::renderUI({
    d <- rv$doctor; v <- d$voices %||% list()
    sel <- rv$cfg$voice$provider %||% "auto"
    ch <- lapply(names(PROVIDERS), function(k) {
      ok <- k %in% c("auto", "human") || isTRUE(v[[k]]$ok) || (k %in% names(KEY_ENV) && nzchar(rv$secrets[[KEY_ENV[[k]]]] %||% ""))
      list(value = k, label = PROVIDERS[[k]]$label, sub = if (ok || is.null(v[[k]]$why)) PROVIDERS[[k]]$sub else v[[k]]$why, class = "prov", disabled = !ok && !(k %in% names(KEY_ENV)),
           vis = HTML(sprintf("<div class='vis' style='height:30px;%s'>%s</div>", if (!ok) "opacity:.35" else "", paste(rep("<i style='height:40%'></i>", 7), collapse = ""))))
    })
    dr_choices("voice_provider", ch, sel, min = "132px", class = "compact")
  })
  dr_on(input$voice_provider, { if (!is.null(rv$dir)) ctx$set(c("voice", "provider"), input$voice_provider) }, ignoreInit = TRUE)
  output$voice_voice_ui <- shiny::renderUI({
    p <- rv$cfg$voice$provider %||% "auto"
    vs <- unlist(rv$doctor$voices[[p]]$voices %||% list())
    cur <- rv$cfg$voice$voice %||% ""
    if (p %in% c("auto", "human")) return(dr_field("Voice", div(class = "dim", style = "padding:9px 0", if (p == "human") "Your recordings" else "Chosen automatically")))
    if (p == "elevenlabs") vs <- stats::setNames(vs, sub(":.*$", "", vs))
    if (!length(vs)) return(dr_text("voice_voice", "Voice", cur))
    ch <- c(vs, if (nzchar(cur) && !cur %in% vs) cur)
    dr_select("voice_voice", "Voice", ch, if (nzchar(cur)) cur else ch[1])
  })
  dr_on(input$voice_voice, { if (!is.null(rv$dir)) ctx$set(c("voice", "voice"), input$voice_voice) }, ignoreInit = TRUE)
  dr_on(input$voice_rate, { if (!is.null(rv$dir)) ctx$set(c("voice", "rate"), input$voice_rate) }, ignoreInit = TRUE)
  dr_on(input$voice_lexicon, { if (!is.null(rv$dir)) ctx$set(c("voice", "lexicon"), input$voice_lexicon) }, ignoreInit = TRUE)
  dr_on(input$voice_enabled, { if (!is.null(rv$dir) && ctx$set(c("voice", "enabled"), isTRUE(input$voice_enabled))) ctx$rebuild() }, ignoreInit = TRUE)
  dr_on(input$voice_key, {
    p <- rv$cfg$voice$provider %||% ""
    env <- KEY_ENV[p]; if (is.na(env)) env <- "OPENAI_API_KEY"
    s <- rv$secrets; s[[env]] <- input$voice_key %||% ""; rv$secrets <- s
  }, ignoreInit = TRUE)
  dr_on(input$sound_voice, {
    if (is.null(rv$sb)) return(ctx$toast("Write the storyboard first", type = "warn"))
    ctx$start("voice")
  })

  output$voice_lines <- shiny::renderUI({
    rv$lines_v; rv$sb_v
    sb <- shiny::isolate(rv$sb); cl <- shiny::isolate(rv$clips)
    if (is.null(sb)) return(dr_empty("type", "No script yet"))
    sc <- Filter(function(s) !isFALSE(s$enabled) && nzchar(trimws(s$vo %||% "")), sb$scenes)
    if (!length(sc)) return(dr_empty("mic", "No voice-over lines", if (isTRUE(sb$vo)) "Add lines in Story." else "This template is music-only. Add lines in Story if you want a voice."))
    human <- identical(rv$cfg$voice$provider, "human")
    div(class = "lines", lapply(sc, function(s) {
      c1 <- cl$clips[[s$id]]
      f <- if (!is.null(c1)) file.path(rv$dir, c1$file) else ""
      prev <- file.path(rv$dir, "vo", paste0("preview_", s$id, ".wav"))
      src <- if (file.exists(prev) && (!nzchar(f) || file.mtime(prev) > file.mtime(f))) prev else f
      hum <- list.files(file.path(rv$dir, "vo", "human"), pattern = paste0("^", s$id, "\\."), full.names = TRUE)
      div(class = "line",
          div(class = "sid", s$id),
          div(class = "tx", s$vo, if (!is.null(c1) && identical(trimws(c1$text %||% ""), trimws(s$vo))) htmltools::span(class = "d", sprintf("%.1fs", c1$dur))
              else if (!is.null(c1)) dr_chip("changed: regenerate", "warn", "refresh"), if (length(hum)) dr_chip("recorded", "good", "mic")),
          div(class = "hrow nowrap",
              if (nzchar(src) && file.exists(src)) tags$audio(controls = NA, preload = "none", src = ctx$media(sub(paste0(normalizePath(rv$dir), "/"), "", normalizePath(src), fixed = TRUE), as.integer(file.mtime(src)))),
              if (human) tags$button(class = "dr-btn xs rec-btn", onclick = sprintf("DR.record(this,'%s')", s$id), dr_icon("mic", 13), if (length(hum)) "Redo" else "Record")
              else tags$button(class = "dr-btn xs", `data-act` = "line_preview", `data-id` = s$id, title = "Synthesize just this line", dr_icon("play", 12), "Try")))
    }))
  })
  dr_on(input$vo_record, {
    r <- input$vo_record; if (is.null(rv$dir) || is.null(r$data)) return()
    dir.create(file.path(rv$dir, "vo", "human"), showWarnings = FALSE, recursive = TRUE)
    ext <- if (grepl("ogg", r$mime)) "ogg" else if (grepl("mp4|aac", r$mime)) "m4a" else "webm"
    for (o in list.files(file.path(rv$dir, "vo", "human"), pattern = paste0("^", r$scene, "\\."), full.names = TRUE)) unlink(o)
    writeBin(jsonlite::base64_dec(r$data), file.path(rv$dir, "vo", "human", paste0(r$scene, ".", ext)))
    rv$lines_v <- rv$lines_v + 1
    ctx$toast("Line recorded", sprintf("Scene %s. Generate the voice-over when every line is recorded.", r$scene), "good")
  })

  # ---- music
  output$music_moods <- shiny::renderUI({
    sel <- rv$cfg$music$mood %||% "auto"
    dr_choices("music_mood", lapply(seq_along(MOODS), function(i) { k <- names(MOODS)[i]; m <- MOODS[[k]]
      list(value = k, label = m$label, sub = m$sub, class = "mood", vis = eq_vis(m$c[1], m$c[2], 14, i, k)) }), sel, min = "118px")
  })
  dr_on(input$music_mood, { if (!is.null(rv$dir)) ctx$set(c("music", "mood"), input$music_mood) }, ignoreInit = TRUE)

  # ---- previews: bundled ones play straight from the browser (director.js); the server composes the rest
  #      (your harmony / variation / transpose, or a WAV for browsers that can't play the bundled MP3s)
  pv <- new.env(parent = emptyenv())
  play <- function(url, key) session$sendCustomMessage("dr-play", list(url = url, key = key))
  dr_on(input$music_preview, {
    r <- input$music_preview; mood <- r$mood %||% (rv$cfg$music$mood %||% "auto")
    if (identical(mood, "auto")) mood <- c(launch = "keys", teaser = "pulse", tour = "bright", social = "drive", demo = "ambient")[[rv$cfg$film$template %||% "launch"]] %||% "keys"
    if (identical(mood, "none")) return()
    if (identical(mood, "custom")) {
      f <- rv$cfg$music$file %||% ""
      if (!nzchar(f) || is.null(rv$dir) || !file.exists(file.path(rv$dir, f))) return(ctx$toast("Upload a track first", type = "info", life = 2500))
      return(play(ctx$media(f), r$key %||% "custom"))
    }
    m <- rv$cfg$music %||% list()
    custom <- isTRUE(r$settings)
    if (!custom && !isTRUE(r$wav)) return(play(dr_media_url("w", sprintf("demos/music_%s.mp3", mood)), r$key %||% mood))
    args <- c("-m", "director", "demo", "--out", file.path(ctx$home, "cache", "demos"), "--mood", mood)
    if (isTRUE(r$wav) && !custom) {                       # same sound as the bundled MP3, as WAV: a quick transcode
      www <- dr_media_roots(ctx$home)$w
      mp3 <- file.path(www, "demos", if (mood %in% names(SFX_PREVIEWS)) sprintf("sfx_%s.mp3", mood) else sprintf("music_%s.mp3", mood))
      if (file.exists(mp3)) args <- c("-m", "director", "demo", "--out", file.path(ctx$home, "cache", "demos"), "--transcode", mp3)
    }
    if (custom) args <- c(args, "--harmony", m$key %||% "auto", "--seed", as.integer(m$seed %||% 7), "--transpose", as.integer(m$transpose %||% 0), "--bpm", as.numeric(m$bpm %||% 0))
    if (!is.null(pv$proc) && pv$proc$is_alive()) try(pv$proc$kill(), silent = TRUE)
    py <- director_python()
    pv$proc <- tryCatch(processx::process$new(py, args, wd = director_engine(), env = dr_engine_env(python = py), stdout = "|", stderr = "|"),
                        error = function(e) { session$sendCustomMessage("dr-play", list(error = conditionMessage(e))); NULL })
    if (is.null(pv$proc)) return()
    pv$key <- r$key %||% mood; pv$t0 <- Sys.time()
    session$sendCustomMessage("dr-play", list(loading = pv$key))
    if (custom) ctx$toast("Composing a preview\u2026", sprintf("%s with your harmony, variation and transpose. A few seconds.", tools::toTitleCase(mood)), "info", 3500)
  })
  dr_obs({
    p <- pv$proc
    if (is.null(p)) { shiny::invalidateLater(1000); return() }
    if (p$is_alive()) {
      if (difftime(Sys.time(), pv$t0, units = "secs") > 90) { try(p$kill(), silent = TRUE) } else { shiny::invalidateLater(300); return() }
    }
    out <- tryCatch(p$read_all_output(), error = function(e) "")
    err <- tryCatch(p$read_all_error(), error = function(e) "")
    pv$proc <- NULL
    lines <- strsplit(trimws(out), "\n")[[1]]
    f <- tryCatch(jsonlite::fromJSON(utils::tail(lines, 1))$file, error = function(e) NULL)
    if (is.null(f)) {
      e <- trimws(strsplit(err, "\n")[[1]]); e <- e[nzchar(e)]
      return(session$sendCustomMessage("dr-play", list(error = paste(utils::tail(e, 2), collapse = " ") %||% "The preview could not be made.")))
    }
    play(dr_media_url("c", f), pv$key)
  })
  output$sfx_chips <- shiny::renderUI({
    div(class = "hrow", style = "gap:6px", htmltools::span(class = "dim", style = "font-size:12px;margin-right:2px", "Listen:"),
        lapply(names(SFX_PREVIEWS), function(k) tags$button(class = "dr-btn xs sfx-pv", `data-sfx` = k, `data-key` = paste0("sfx-", k),
                                                            dr_icon("play", 11), SFX_PREVIEWS[[k]])))
  })
  bindn <- function(id, path, conv = as.numeric) dr_on(input[[id]], { if (!is.null(rv$dir) && !is.null(input[[id]]) && !is.na(input[[id]])) ctx$set(path, conv(input[[id]])) }, ignoreInit = TRUE)
  bindn("music_bpm", c("music", "bpm")); bindn("music_seed", c("music", "seed")); bindn("music_volume", c("music", "volume"))
  bindn("music_duck", c("music", "duck")); bindn("music_transpose", c("music", "transpose")); bindn("music_offset", c("music", "offset"))
  dr_on(input$music_key, { if (!is.null(rv$dir)) ctx$set(c("music", "key"), input$music_key) }, ignoreInit = TRUE)
  dr_on(input$music_sfx, { if (!is.null(rv$dir)) ctx$set(c("music", "sfx"), isTRUE(input$music_sfx)) }, ignoreInit = TRUE)
  dr_on(input$music_shuffle, { s <- sample(1:9999, 1); shiny::updateNumericInput(session, "music_seed", value = s) })
  output$music_custom_ui <- shiny::renderUI({
    if (!identical(rv$cfg$music$mood, "custom")) return(NULL)
    f <- rv$cfg$music$file %||% ""
    div(class = "grid2",
        dr_field("Track", shiny::fileInput("music_file", NULL, accept = c("audio/*", ".mp3", ".wav", ".m4a", ".aac", ".flac", ".ogg"), buttonLabel = "Upload\u2026", placeholder = if (nzchar(f)) basename(f) else "MP3, WAV, M4A\u2026")),
        dr_field("Start at (s)", shiny::numericInput("music_offset", NULL, as.numeric(rv$cfg$music$offset %||% 0), min = 0, step = .5)))
  })
  dr_on(input$music_file, {
    f <- input$music_file; if (is.null(f) || is.null(rv$dir)) return()
    dir.create(file.path(rv$dir, "assets"), showWarnings = FALSE)
    dst <- file.path(rv$dir, "assets", paste0("music.", tolower(tools::file_ext(f$name[1]))))
    file.copy(f$datapath[1], dst, overwrite = TRUE)
    ctx$set(c("music", "file"), file.path("assets", basename(dst))); ctx$toast("Track uploaded", f$name[1], "good")
  })
  dr_on(input$sound_music, {
    if (is.null(rv$sb)) return(ctx$toast("Write the storyboard first", type = "warn"))
    ctx$start("music")
  })
  output$music_mix_ui <- shiny::renderUI({
    rv$tl_v
    if (is.null(rv$dir)) return(NULL)
    mix <- file.path(rv$dir, "audio", "mix.wav")
    if (!file.exists(mix)) return(dr_empty("volume", "Nothing mixed yet", "\u201cCompose & mix\u201d writes the score for the current cut and mixes it with the voice-over and sound design."))
    tl <- rv$tl
    div(class = "stack",
        tags$audio(controls = NA, preload = "none", style = "width:100%", src = ctx$media("audio/mix.wav", as.integer(file.mtime(mix)))),
        div(class = "hrow", dr_chip(sprintf("%.1fs", tl$duration %||% 0), "", "clock"), dr_chip(sprintf("%d BPM", as.integer(tl$bpm %||% 0)), "", "sound"),
            dr_chip(if (length(tl$vo)) sprintf("%d voice lines", length(tl$vo)) else "music only", "", "mic"),
            dr_chip(sprintf("%d sound effects", length(tl$sfx)), "", "zap")),
        dr_note(icon = "info", "The preview player plays this mix in sync with the picture. Re-mix after changing the cut: scene lengths drive the score."))
  })
}

line_act <- function(a, rv, ctx, session) {
  if (a$act == "line_preview") {
    tryCatch({ dr_job_start(rv$dir, "voice", c("--line", a$id), quiet = TRUE, env = ctx$env()); ctx$toast("Synthesizing\u2026", a$id, "info", 1500) },
             error = function(e) ctx$toast("Could not start", conditionMessage(e), "bad"))
  }
}
