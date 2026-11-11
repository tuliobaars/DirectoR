# Server: state, navigation, jobs, library -------------------------------------------------

#' The DirectoR server
#' @param home DirectoR home folder.
#' @return A Shiny server function.
#' @export
app_server <- function(home = director_home()) {
  function(input, output, session) {
    rv <- shiny::reactiveValues(dir = NULL, cfg = NULL, facts = NULL, scout = NULL, sb = NULL, tl = NULL, clips = NULL, man = NULL,
                                page = "lib", tl_v = 0, lib_v = 0, sb_v = 0, shots_v = 0, lines_v = 0, doctor = NULL, secrets = list(),
                                log_open = FALSE, queue = list(), last_t = 0, player_key = "")
    mem <- new.env(parent = emptyenv())      # non-reactive bookkeeping
    mem$last <- list(); mem$quick <- list(); mem$tl_req <- NULL; mem$after <- list()

    # ------------------------------------------------------------------ context helpers
    ctx <- new.env(parent = emptyenv())
    ctx$home <- home
    ctx$toast <- function(title, text = NULL, type = "info", life = NULL) session$sendCustomMessage("dr-toast", list(title = title, text = text, type = type, life = life))
    ctx$url <- function(rel, v = NULL) {
      if (is.null(rv$dir)) return("")
      paste0("drp/", basename(rv$dir), "/", rel, if (!is.null(v)) paste0("?v=", v) else "")
    }
    ctx$media <- function(rel, v = NULL) {           # audio/video: served with byte ranges (Safari needs them)
      if (is.null(rv$dir)) return("")
      dr_media_url("p", paste0(basename(rv$dir), "/", rel), v)
    }
    ctx$reload <- function(what = c("cfg", "facts", "scout", "sb", "tl", "clips", "man")) {
      d <- shiny::isolate(rv$dir); if (is.null(d)) return()
      if ("cfg" %in% what) rv$cfg <- dr_cfg(d)
      if ("facts" %in% what) rv$facts <- dr_doc(d, "facts")
      if ("scout" %in% what) rv$scout <- dr_doc(d, "scout")
      if ("sb" %in% what) { rv$sb <- dr_doc(d, "storyboard"); rv$sb_v <- shiny::isolate(rv$sb_v) + 1; rv$shots_v <- shiny::isolate(rv$shots_v) + 1 }
      if ("tl" %in% what) rv$tl <- dr_doc(d, "timeline")
      if ("clips" %in% what) { rv$clips <- dr_read_json(file.path(d, "vo", "clips.json")); rv$lines_v <- shiny::isolate(rv$lines_v) + 1 }
      if ("man" %in% what) rv$man <- dr_read_json(file.path(d, "out", "manifest.json"))
    }
    # set one setting (path like c("look","theme")); returns TRUE when it changed
    ctx$set <- function(path, value, rebuild = FALSE) {
      d <- shiny::isolate(rv$dir); if (is.null(d)) return(FALSE)
      cfg <- dr_cfg(d)
      old <- dr_get(cfg, path)
      if (identical(old, value) || (is.numeric(old) && is.numeric(value) && length(old) == 1 && length(value) == 1 && isTRUE(all.equal(old, value)))) return(FALSE)
      cfg <- dr_set(cfg, path, value)
      dr_save_cfg(d, cfg); rv$cfg <- cfg
      if (rebuild) ctx$rebuild()
      TRUE
    }
    ctx$env <- function() {
      s <- shiny::isolate(rv$secrets)
      unlist(s[nzchar(unlist(s))])
    }
    ctx$start <- function(step, args = character(), after = NULL, quiet_ok = FALSE) {
      d <- shiny::isolate(rv$dir)
      if (is.null(d)) { ctx$toast("Open a film first", type = "warn"); return(FALSE) }
      if (dr_job_running(d)) { ctx$toast("Busy", "Wait for the current job to finish (or cancel it).", "warn"); return(FALSE) }
      ok <- tryCatch({ dr_job_start(d, step, args, env = ctx$env()); TRUE }, error = function(e) { ctx$toast("Could not start", conditionMessage(e), "bad"); FALSE })
      if (ok) { mem$after[[step]] <- after; mem$last <- list(state = "running", job = step) }
      ok
    }
    # debounced timeline rebuild (runs beside long jobs, in the quiet slot)
    ctx$rebuild <- function() { d <- shiny::isolate(rv$dir); if (!is.null(d) && file.exists(file.path(d, "storyboard.json"))) mem$tl_req <- Sys.time() }
    ctx$go <- function(page) {
      if (!identical(page, "lib") && is.null(shiny::isolate(rv$dir))) { ctx$toast("Create or open a film first", type = "warn"); page <- "lib" }
      rv$page <- page
      shiny::updateTabsetPanel(session, "pages", selected = page)
      ctx$nav_state()
    }
    ctx$nav_state <- function() {
      d <- shiny::isolate(rv$dir)
      done <- character()
      if (!is.null(d)) {
        if (file.exists(file.path(d, "scout.json")) || identical(dr_get(shiny::isolate(rv$cfg), c("source", "kind")), "media")) done <- c(done, "source")
        if (file.exists(file.path(d, "storyboard.json"))) done <- c(done, "story")
        sb <- shiny::isolate(rv$sb)
        st <- shiny::isolate(rv$tl)$shot_status
        if (length(sb$shots) && all(vapply(sb$shots, function(s) identical(st[[s$id]], "ok") || (is.null(st) && file.exists(file.path(d, "shots", s$id, "meta.json"))), logical(1)))) done <- c(done, "shots")
        if (file.exists(file.path(d, "audio", "mix.wav"))) done <- c(done, "sound")
        if (file.exists(file.path(d, "timeline.json"))) done <- c(done, "look")
        if (length(shiny::isolate(rv$man)$renders)) done <- c(done, "export")
      }
      session$sendCustomMessage("dr-nav", list(page = shiny::isolate(rv$page), done = as.list(done), locked = is.null(d)))
    }
    ctx$load <- function(dir, page = "story") {
      ctx$loading_until <- Sys.time() + 2.5      # inputs echo the loaded settings back; don't treat that as edits
      rv$dir <- normalizePath(dir)
      try({ st <- dr_read_json(file.path(ctx$home, "director.json"), list()); st$last_film <- rv$dir; dr_write_json(st, file.path(ctx$home, "director.json")) }, silent = TRUE)
      ctx$reload()
      rv$tl_v <- as.numeric(Sys.time())
      mem$last <- dr_job_status(dir)
      apply_inputs(session, rv, ctx)
      ctx$rebuild()                       # refresh the stage files (they may come from an older engine version)
      page <- if (!is.null(page)) page else "story"
      ctx$go(page)
    }

    # ------------------------------------------------------------------ doctor (background)
    start_doctor <- function() {
      py <- director_python()
      mem$doc_py <- py
      mem$doc_proc <- if (nzchar(py)) tryCatch(processx::process$new(py, c("-m", "director", "doctor", "--json"), wd = director_engine(), env = dr_engine_env(python = py),
                                                                     stdout = "|", stderr = "|"), error = function(e) NULL) else NULL
    }
    start_doctor()
    ctx$recheck <- function() {
      for (k in ls(.dr_state)) if (startsWith(k, "probe:")) rm(list = k, envir = .dr_state)
      .dr_state$python <- NULL
      rv$doctor <- NULL; start_doctor()
    }
    dr_obs({
      if (!is.null(rv$doctor)) return()
      p <- mem$doc_proc
      if (is.null(p)) { rv$doctor <- director_doctor(); return() }
      if (p$is_alive()) { shiny::invalidateLater(500); return() }
      out <- tryCatch(jsonlite::fromJSON(p$read_all_output(), simplifyVector = FALSE), error = function(e) NULL)
      if (!is.null(out)) out$python <- mem$doc_py
      rv$doctor <- out %||% director_doctor(mem$doc_py)
      if (!is.null(out$engine_version) && !identical(out$engine_version, as.character(utils::packageVersion("DirectoR"))))
        ctx$toast("Engine files are from another version", sprintf("DirectoR %s is using engine %s from %s. Reinstall DirectoR so both match.", utils::packageVersion("DirectoR"), out$engine_version, out$engine_path), "warn", 15000)
      if (!isTRUE(rv$doctor$ok)) ctx$toast("The engine needs attention", "Click the terminal icon (bottom left) to see what's missing.", "warn", 8000)
    })
    ctx$doctor <- function() show_doctor(rv, ctx)

    # ------------------------------------------------------------------ navigation
    dr_on(input$nav, {
      if (identical(input$nav, "lib")) try({ st <- dr_read_json(file.path(home, "director.json"), list()); st$last_film <- NULL; dr_write_json(st, file.path(home, "director.json")) }, silent = TRUE)
      ctx$go(input$nav)
    })

    # ------------------------------------------------------------------ job polling
    dr_obs({
      shiny::invalidateLater(550)
      d <- rv$dir
      if (is.null(d)) return()
      st <- dr_job_status(d)
      if (identical(st$state, "unknown")) return()
      prev <- mem$last
      changed <- !identical(st[c("state", "progress", "message", "phase")], prev[c("state", "progress", "message", "phase")])
      if (changed || identical(st$state, "running")) session$sendCustomMessage("dr-job", st)
      mem$last <- st                      # before job_finished(): it may start the next job
      if (identical(prev$state, "running") && !identical(st$state, "running")) shiny::isolate(job_finished(st, rv, ctx, mem, session))
      if (isTRUE(shiny::isolate(rv$log_open))) session$sendCustomMessage("dr-log", list(text = dr_tail(file.path(d, "log.txt"), 60)))
      if (!is.null(ctx$install_proc)) shiny::isolate(install_check(rv, ctx))
      # quiet slot (timeline rebuilds, line previews)
      q <- dr_job_status(d, quiet = TRUE)
      if (identical(q$state, "unknown")) q <- mem$quick
      if (identical(mem$quick$state, "running") && !identical(q$state, "running")) shiny::isolate(quick_finished(q, rv, ctx, mem))
      mem$quick <- q
      # debounced rebuild request
      if (!is.null(mem$tl_req) && difftime(Sys.time(), mem$tl_req, units = "secs") > 0.5 && !identical(q$state, "running")) {
        mem$tl_req <- NULL
        tryCatch({ dr_job_start(d, "timeline", quiet = TRUE); mem$quick <- list(state = "running", job = "timeline") }, error = function(e) NULL)
      }
    })
    dr_on(input$want_log, {
      rv$log_open <- isTRUE(input$want_log > 0)
      if (rv$log_open && !is.null(rv$dir)) session$sendCustomMessage("dr-log", list(text = dr_tail(file.path(rv$dir, "log.txt"), 60)))
    })
    cancel <- function() { if (!is.null(rv$dir) && dr_job_cancel(rv$dir)) ctx$toast("Cancelled", type = "warn"); rv$queue <- list() }
    dr_on(input$job_cancel, cancel())
    dr_on(input$auto_cancel, cancel())

    # ------------------------------------------------------------------ top bar
    dr_on(input$proj_name, {
      nm <- trimws(input$proj_name %||% "")
      if (!is.null(rv$dir) && nzchar(nm) && !identical(nm, rv$cfg$name)) { ctx$set("name", nm); ctx$set("name_auto", FALSE); rv$lib_v <- rv$lib_v + 1 }
    }, ignoreInit = TRUE)
    output$top_chips <- shiny::renderUI({
      if (is.null(rv$dir)) return(NULL)
      tl <- rv$tl; cfg <- rv$cfg
      htmltools::tagList(
        dr_chip(tools::toTitleCase(dr_get(cfg, c("film", "template"), "launch")), "accent", "film"),
        dr_chip(dr_get(cfg, c("format", "aspect"), "16:9"), "", "monitor"),
        if (!is.null(tl$duration)) dr_chip(sprintf("%.1fs", tl$duration), if (tl$duration > 60) "warn" else "", "clock"))
    })
    dr_on(input$top_preview, {
      if (is.null(rv$dir)) return(ctx$toast("Open a film first", type = "warn"))
      ctx$go("story"); session$sendCustomMessage("dr-player", list(type = "dr:play"))
    })
    dr_on(input$top_auto, autopilot(rv, ctx, input))
    dr_on(input$top_render, { if (!is.null(rv$dir)) { ctx$go("export"); start_render(rv, ctx, input) } })

    # ------------------------------------------------------------------ library
    srv_library(input, output, session, rv, ctx)
    srv_source(input, output, session, rv, ctx)
    srv_story(input, output, session, rv, ctx)
    srv_shots(input, output, session, rv, ctx)
    srv_sound(input, output, session, rv, ctx)
    srv_look(input, output, session, rv, ctx)
    srv_export(input, output, session, rv, ctx)
    dr_on(input$ui_act, dispatch_act(input$ui_act, rv, ctx, session, input), ignoreInit = TRUE)
    # the preview iframe is only re-created when the film, its format, or the existence of a preview changes
    dr_obs({
      rv$tl_v
      k <- paste(rv$dir, rv$tl$W, rv$tl$H, !is.null(rv$dir) && file.exists(file.path(rv$dir, "preview.html")))
      if (!identical(k, shiny::isolate(rv$player_key))) rv$player_key <- k
    })

    # a reload (or a dropped connection) brings you back to the film you were working on
    session$onFlushed(function() {
      last <- dr_read_json(file.path(home, "director.json"), list())$last_film %||% ""
      if (nzchar(last) && file.exists(file.path(last, "project.json")) && is.null(shiny::isolate(rv$dir))) {
        shiny::isolate(tryCatch(ctx$load(last, page = if (file.exists(file.path(last, "storyboard.json"))) "story" else "source"),
                                error = function(e) dr_report_error(e, session, "reopening the last film")))
      }
    }, once = TRUE)
    session$onSessionEnded(function() { p <- mem$doc_proc; if (!is.null(p) && p$is_alive()) p$kill() })
  }
}

# what to do when a job ends --------------------------------------------------------------------

job_finished <- function(st, rv, ctx, mem, session) {
  job <- st$job %||% ""
  if (identical(st$state, "error")) {
    if (!isTRUE(st$cancelled)) ctx$toast(sprintf("%s failed", tools::toTitleCase(job)), st$error %||% st$message, "bad", 12000)
    ctx$reload(); rv$lib_v <- rv$lib_v + 1; rv$queue <- list()
    return(ctx$nav_state())
  }
  w <- unlist(st$warnings)
  ctx$reload()
  if (job == "scout") {
    n <- length(rv$scout$views)
    app <- rv$facts$app$label %||% ""
    ctx$toast("Scouted", if (n) sprintf("%s%d screen%s found. Writing the storyboard\u2026", if (nzchar(app)) paste0(app, " \u00b7 ") else "", n, if (n == 1) "" else "s") else "Writing the storyboard\u2026", "good")
    apply_inputs(session, rv, ctx, brand_only = TRUE)
    session$sendInputMessage("proj_name", list(value = rv$cfg$name %||% ""))
    if (is.null(rv$sb) || isTRUE(mem$after$scout$plan)) ctx$start("plan", after = list(go = "story"))
  } else if (job == "plan") {
    ctx$toast("Storyboard ready", sprintf("%d scenes, %d shots. Record the shots to see real footage.", length(rv$sb$scenes), length(rv$sb$shots)), "good")
    ctx$rebuild()
    if (!is.null(mem$after$plan$go)) ctx$go(mem$after$plan$go)
  } else if (job == "voice") {
    cl <- rv$clips
    ctx$toast("Voice-over ready", if (!is.null(cl$total)) sprintf("%s \u00b7 the film runs %.1fs", cl$voice, cl$total) else cl$voice, "good")
    ctx$rebuild()
  } else if (job == "capture") {
    ctx$toast("Footage recorded", sprintf("%d shot%s.", length(st$result$recorded), if (length(st$result$recorded) == 1) "" else "s"), "good")
    rv$shots_v <- rv$shots_v + 1; ctx$rebuild()
  } else if (job == "music") {
    ctx$toast("Score mixed", "Press play in the preview to hear it.", "good"); rv$tl_v <- as.numeric(Sys.time())
  } else if (job == "render") {
    ctx$toast("Film rendered", st$result$name %||% "", "good", 6000)
    rv$lib_v <- rv$lib_v + 1
    if (length(rv$queue)) {
      nx <- rv$queue[[1]]; rv$queue <- rv$queue[-1]
      ctx$start("render", nx)
    } else ctx$go("export")
  } else if (job == "auto") {
    ctx$toast("Your film is ready", st$result$name %||% "", "good", 8000)
    rv$lib_v <- rv$lib_v + 1; rv$tl_v <- as.numeric(Sys.time())
    ctx$go("export")
  }
  if (length(w) && job != "auto") ctx$toast("Heads-up", paste(utils::tail(w, 3), collapse = "\n"), "warn", 9000)
  ctx$nav_state()
}

quick_finished <- function(q, rv, ctx, mem) {
  if (identical(q$job, "timeline")) {
    if (identical(q$state, "done")) { ctx$reload(c("tl")); rv$tl_v <- as.numeric(Sys.time()) }
  } else if (identical(q$job, "voice")) {
    if (identical(q$state, "done")) { rv$lines_v <- rv$lines_v + 1; ctx$toast("Line ready", sprintf("%.1fs", q$result$dur %||% 0), "good", 1800) }
    else ctx$toast("Voice preview failed", q$error %||% q$message, "bad")
  }
}

# autopilot: do what's missing, then render
autopilot <- function(rv, ctx, input) {
  d <- rv$dir
  if (is.null(d)) return(ctx$toast("Create a film first", "Paste a link on the Library page.", "warn"))
  from <- if (!file.exists(file.path(d, "scout.json")) && !identical(rv$cfg$source$kind, "media")) "scout"
          else if (!file.exists(file.path(d, "storyboard.json"))) "plan" else "voice"
  q <- input$export_quality %||% "final"
  if (ctx$start("auto", c("--from", from, "--quality", q))) ctx$toast("Autopilot engaged", sprintf("Starting from: %s", from), "info", 3000)
}

# a sibling film in another template, from the same footage
make_sibling <- function(template, rv, ctx, input) {
  if (is.null(rv$dir)) return()
  if (dr_job_running(rv$dir)) return(ctx$toast("Busy", "Wait for the current job to finish.", "warn"))
  d2 <- dr_duplicate_project(rv$dir, ctx$home)
  lab <- Filter(function(t) identical(t$value, template), TEMPLATES)[[1]]$label
  cfg <- dr_cfg(d2)
  cfg$name <- sprintf("%s \u00b7 %s", sub(" copy$", "", cfg$name), lab); cfg$name_auto <- FALSE
  cfg$film$template <- template
  if (identical(template, "social")) cfg$format$aspect <- "9:16" else if (identical(cfg$format$aspect, "9:16")) cfg$format$aspect <- "16:9"
  dr_save_cfg(d2, cfg)
  unlink(file.path(d2, c("storyboard.json", "timeline.json", "vo/clips.json")))
  rv$lib_v <- rv$lib_v + 1
  ctx$load(d2, page = "story")
  ctx$start("auto", c("--from", "plan", "--template", template, "--quality", input$export_quality %||% "final"))
  ctx$toast(sprintf("Directing the %s", tolower(lab)), "Same footage, new cut. It appears in your library.", "info", 5000)
}

start_render <- function(rv, ctx, input) {
  q <- input$export_quality %||% "final"
  extra <- list()
  if (isTRUE(input$export_vertical)) extra <- c(extra, list(c("--quality", q, "--aspect", "9:16")))
  if (isTRUE(input$export_square)) extra <- c(extra, list(c("--quality", q, "--aspect", "1:1")))
  if (ctx$start("render", c("--quality", q))) rv$queue <- extra
}

show_doctor <- function(rv, ctx) {
  d <- rv$doctor
  if (is.null(d)) return(ctx$toast("Checking the engine\u2026", "Try again in a few seconds.", type = "info"))
  items <- function(xs, cls) lapply(xs, function(p) dr_note(class = cls, icon = if (cls == "bad") "alert" else "info",
                                                            tags$b(p$what), div(class = "mono", style = "margin-top:6px;user-select:all;word-break:break-all", p$fix),
                                                            if (!is.null(p$detail)) tags$pre(p$detail)))
  v <- d$voices %||% list()
  pkg_v <- as.character(utils::packageVersion("DirectoR"))
  cands <- dr_python_candidates()
  cur <- d$python %||% director_python()
  py_rows <- lapply(cands, function(py) {
    pr <- dr_python_probe(py)
    status <- if (isTRUE(pr$ok)) dr_chip(paste("ready \u00b7", pr$version), "good", "check")
              else if (isTRUE(pr$old)) dr_chip(paste("too old \u00b7", pr$version), "warn")
              else if (nzchar(pr$version)) dr_chip(paste("missing:", paste(pr$missing, collapse = ", ")), "warn")
              else dr_chip("does not run", "bad")
    div(class = "hrow", style = "padding:8px 10px;border:1px solid var(--line);border-radius:10px;background:var(--panel)",
        htmltools::span(class = "mono", style = "flex:1;word-break:break-all", py), status,
        if (identical(path.expand(py), path.expand(cur))) dr_chip("in use", "accent")
        else tags$button(class = "dr-btn xs", `data-act` = "use_python", `data-id` = py, "Use"))
  })
  shiny::showModal(shiny::modalDialog(
    title = htmltools::tagList(dr_icon("terminal", 18), " Engine check"), size = "l", easyClose = TRUE,
    footer = htmltools::tagList(tags$button(class = "dr-btn sm", `data-act` = "recheck", dr_icon("refresh", 14), "Re-check"), shiny::modalButton("Close")),
    div(class = "stack",
        if (isTRUE(d$failed)) dr_note(class = "bad", icon = "alert", tags$b(sprintf("The engine could not run with %s", cur)), tags$pre(d$error %||% ""),
                                      div("Choose the Python where you installed the requirements below, or install them into this one."))
        else if (!is.null(d$engine_version) && !identical(d$engine_version, pkg_v))
          dr_note(class = "warn", icon = "alert", tags$b("Version mismatch"), div(sprintf("DirectoR %s is running engine files %s from %s. Reinstall DirectoR (or update that folder) so they match.", pkg_v, d$engine_version, d$engine_path))),
        div(class = "kv",
            div(class = "k", "DirectoR"), div(pkg_v, htmltools::span(class = "dim", sprintf("  engine %s", d$engine_version %||% "?"))),
            div(class = "k", "Engine folder"), div(class = "mono", style = "word-break:break-all", d$engine_path %||% director_engine()),
            if (!isTRUE(d$failed)) htmltools::tagList(
              div(class = "k", "Chromium"), div(d$chromium %||% htmltools::span(class = "bad", "missing")),
              div(class = "k", "ffmpeg"), div(class = "mono", d$ffmpeg %||% "missing", if (isTRUE(d$libx264)) dr_chip("x264", "good"), if (isTRUE(d$libass)) dr_chip("libass", "good")),
              div(class = "k", "git / Rscript"), div(if (isTRUE(d$git)) dr_chip("git", "good") else dr_chip("no git", "warn"), if (isTRUE(d$rscript)) dr_chip("Rscript", "good") else dr_chip("no Rscript", "warn")),
              div(class = "k", "Voices"), div(class = "hrow", lapply(names(v), function(k) dr_chip(k, if (isTRUE(v[[k]]$ok)) "good" else ""))))),
        tags$h4(style = "margin:8px 0 0;font-size:14px", "Python"),
        div(class = "dim", style = "font-size:12.5px", "DirectoR uses the first Python that has the engine's packages. RStudio and R.app don't see your shell's PATH, so Homebrew, python.org, pyenv and conda installs are searched too."),
        div(class = "stack", style = "gap:6px", py_rows),
        div(class = "hrow nowrap", tags$input(id = "py_custom", type = "text", class = "form-control", placeholder = "/path/to/python3", style = "flex:1"),
            tags$button(class = "dr-btn sm", onclick = "Shiny.setInputValue('ui_act', {act: 'use_python', id: document.getElementById('py_custom').value, n: Math.random()}, {priority: 'event'})", "Use this path")),
        if (length(d$problems)) items(d$problems, "bad") else if (!isTRUE(d$failed)) dr_note(class = "good", icon = "check", "Everything the engine needs is installed."),
        if (length(d$notes)) items(d$notes, "warn"))))
}

# library --------------------------------------------------------------------------------------

srv_library <- function(input, output, session, rv, ctx) {
  output$lib_count <- shiny::renderUI({ rv$lib_v; n <- nrow(dr_projects(ctx$home)); if (n) dr_chip(n) })
  output$lib_grid <- shiny::renderUI({
    rv$lib_v
    pr <- dr_projects(ctx$home)
    if (!nrow(pr)) return(dr_empty("film", "No films yet", "Paste a link above to direct your first one."))
    div(class = "lib-grid", lapply(seq_len(nrow(pr)), function(i) {
      r <- pr[i, ]
      poster <- if (nzchar(r$thumb)) sprintf("background-image:url('drp/%s/%s?v=%s')", r$slug, r$thumb, as.integer(r$modified)) else ""
      div(class = "film", `data-act` = "open", `data-id` = r$dir,
          div(class = "poster", style = poster,
              if (!nzchar(r$thumb)) div(class = "none", dr_icon("film", 34)),
              div(class = "chips", dr_chip(tools::toTitleCase(r$template), "accent"), dr_chip(r$aspect)),
              if (!is.na(r$duration)) div(class = "dur", sprintf("%.0fs", r$duration))),
          div(class = "meta",
              div(class = "grow", div(class = "nm", r$name), div(class = "sub", if (nzchar(r$source)) r$source else "Screenshots & recordings")),
              div(class = "acts",
                  tags$button(class = "dr-btn ghost xs icon", `data-act` = "dup", `data-id` = r$dir, title = "Duplicate", dr_icon("copy", 14)),
                  tags$button(class = "dr-btn ghost xs icon danger", `data-act` = "del", `data-id` = r$dir, title = "Delete", `data-confirm` = sprintf("Delete \"%s\" and all its footage?", r$name), dr_icon("trash", 14)))))
    }))
  })
  dr_on(input$lib_source, {
    v <- trimws(input$lib_source %||% "")
    html <- if (!nzchar(v)) "" else {
      k <- dr_classify(v)
      lab <- c(url = "Website", git = "Git repo", zip = "Zip", dir = "Folder", media = "")[[k]]
      ic <- c(url = "globe", git = "git", zip = "zip", dir = "folder", media = "image")[[k]]
      as.character(dr_chip(lab, "accent", ic))
    }
    session$sendCustomMessage("dr-detect", list(html = html))
  }, ignoreInit = TRUE)
  create <- function(source, kind = "auto", media = NULL) {
    tpl <- input$lib_template %||% "launch"
    d <- dr_new_project(source, kind = kind, template = tpl, home = ctx$home)
    if (!is.null(media)) {
      dir.create(file.path(d, "media"), showWarnings = FALSE)
      items <- lapply(seq_len(nrow(media)), function(i) {
        nm <- gsub("[^A-Za-z0-9._-]+", "_", media$name[i]); dst <- file.path(d, "media", nm)
        file.copy(media$datapath[i], dst, overwrite = TRUE)
        list(file = file.path("media", nm), label = tools::toTitleCase(gsub("[_-]+", " ", tools::file_path_sans_ext(media$name[i]))))
      })
      dr_write_json(list(items = items), file.path(d, "media.json"))
    }
    shiny::updateTextInput(session, "lib_source", value = "")
    session$sendCustomMessage("dr-set", list(id = "lib_source", value = ""))
    rv$lib_v <- rv$lib_v + 1
    ctx$load(d, page = "source")
    if (isTRUE(input$lib_autopilot)) ctx$start("auto", c("--from", if (identical(kind, "media") || identical(dr_classify(source), "media") && !is.null(media)) "plan" else "scout", "--quality", input$lib_quality %||% "draft"))
    else if (!is.null(media)) ctx$start("plan", after = list(go = "story"))
    else ctx$start("scout", after = list(plan = TRUE))
  }
  dr_on(input$lib_create, {
    v <- trimws(input$lib_source %||% "")
    if (!nzchar(v)) return(ctx$toast("Paste a link first", "A website, a Shiny app URL, a GitHub repository or a local folder. Or drop a zip.", "warn"))
    k <- dr_classify(v)
    if (k == "url" && !grepl("^https?://|^localhost|^127\\.", v) && !grepl("\\.", v)) return(ctx$toast("That doesn't look like a link", v, "warn"))
    create(v, k)
  })
  dr_on(input$lib_zip, {
    f <- input$lib_zip
    if (is.null(f) || !nrow(f)) return()
    zips <- grepl("\\.zip$", f$name, ignore.case = TRUE)
    if (any(zips)) {
      tmp <- file.path(tempdir(), paste0("dr-upload-", as.integer(Sys.time())))
      dir.create(tmp, showWarnings = FALSE)
      dst <- file.path(tmp, f$name[which(zips)[1]]); file.copy(f$datapath[which(zips)[1]], dst)
      d <- dr_new_project(dst, kind = "zip", template = input$lib_template %||% "launch", home = ctx$home)
      keep <- file.path(d, "upload.zip"); file.copy(dst, keep, overwrite = TRUE)
      cfg <- dr_cfg(d); cfg$source$value <- keep; cfg$name <- sub("\\.zip$", "", f$name[which(zips)[1]], ignore.case = TRUE); dr_save_cfg(d, cfg)
      rv$lib_v <- rv$lib_v + 1
      ctx$load(d, page = "source")
      if (isTRUE(input$lib_autopilot)) ctx$start("auto", c("--from", "scout", "--quality", input$lib_quality %||% "draft")) else ctx$start("scout", after = list(plan = TRUE))
    } else {
      create("", "media", media = f)
    }
  })
}

dispatch_act <- function(a, rv, ctx, session, input) {
  act <- a$act %||% ""
  if (act == "open") { ctx$load(a$id, page = if (file.exists(file.path(a$id, "storyboard.json"))) "story" else "source"); return() }
  if (act == "del") { dr_delete_project(a$id); if (identical(rv$dir, normalizePath(a$id, mustWork = FALSE))) { rv$dir <- NULL; ctx$go("lib") }; rv$lib_v <- rv$lib_v + 1; return(ctx$toast("Deleted", type = "info")) }
  if (act == "dup") { d <- dr_duplicate_project(a$id, ctx$home); rv$lib_v <- rv$lib_v + 1; return(ctx$toast("Duplicated", basename(d), "good")) }
  if (startsWith(act, "scene_")) return(story_act(a, rv, ctx, session))
  if (startsWith(act, "shot_")) return(shot_act(a, rv, ctx, session, input))
  if (startsWith(act, "line_")) return(line_act(a, rv, ctx, session))
  if (act == "install_pkgs") return(install_pkgs(rv, ctx))
  if (act == "engine") return(ctx$doctor())
  if (act == "recheck") { shiny::removeModal(); ctx$recheck(); return(ctx$toast("Checking the engine\u2026", "Open the Engine check again in a few seconds.", "info", 3000)) }
  if (act == "use_python") {
    py <- path.expand(trimws(a$id %||% ""))
    if (!nzchar(py) || !file.exists(py)) return(ctx$toast("Python not found", py, "bad"))
    pr <- dr_python_probe(py)
    dr_save_python(py, ctx$home); shiny::removeModal(); ctx$recheck()
    return(ctx$toast(sprintf("Using %s", py), if (isTRUE(pr$ok)) "Saved. It has everything the engine needs." else sprintf("Saved, but it is missing: %s", paste(pr$missing, collapse = ", ")), if (isTRUE(pr$ok)) "good" else "warn", 7000))
  }
  if (act == "sibling") return(make_sibling(a$arg, rv, ctx, input))
}
