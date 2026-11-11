# Source page + pushing a project's settings into the inputs -------------------------------

# set every input from the project (called when a project is opened)
apply_inputs <- function(session, rv, ctx, brand_only = FALSE) {
  cfg <- shiny::isolate(rv$cfg); facts <- shiny::isolate(rv$facts)
  auto <- facts$brand_auto %||% list()
  b <- cfg$brand %||% list()
  up <- function(id, value, placeholder = NULL) shiny::updateTextInput(session, id, value = value %||% "", placeholder = placeholder)
  up("brand_name", b$name, auto$name %||% "Name")
  up("brand_tagline", b$tagline, auto$tagline %||% "Tagline")
  shiny::updateTextAreaInput(session, "brand_description", value = b$description %||% "", placeholder = substr(auto$description %||% "", 1, 160))
  up("brand_url", b$url, auto$url %||% "https://")
  up("brand_cta", b$cta, auto$cta %||% "yourapp.com")
  cols <- unlist(b$colors %||% list())
  if (!length(cols)) cols <- unlist(auto$colors %||% list())
  cols <- c(cols, "#6366f1", "#a855f7", "#ec4899")[1:3]
  if (length(unlist(b$colors)) < 3 && length(cols)) cols <- dr_complete_palette(cols)
  for (i in 1:3) session$sendInputMessage(paste0("brand_c", i), list(value = cols[i]))
  if (brand_only) return(invisible())
  session$sendCustomMessage("dr-set", list(id = "proj_name", value = cfg$name %||% ""))
  session$sendInputMessage("proj_name", list(value = cfg$name %||% ""))
  session$sendInputMessage("src_kind", list(value = cfg$source$kind %||% "url"))
  up("app_command", cfg$app$command); up("app_path", cfg$app$path %||% "/"); up("app_wait", as.character(max(300, as.numeric(cfg$app$wait %||% 600))))
  shiny::updateSelectInput(session, "app_renv", selected = cfg$app$renv %||% "ignore")
  sel <- function(id, v) shiny::updateSelectInput(session, id, selected = as.character(v))
  sel("cap_viewport", cfg$capture$viewport %||% "desktop"); sel("cap_scheme", cfg$capture$scheme %||% "light")
  sel("cap_lite", tolower(as.character(cfg$capture$lite %||% "auto"))); sel("cap_fps", cfg$capture$fps %||% 60)
  sel("cap_dpr", cfg$capture$dpr %||% "auto"); sel("cap_workers", cfg$capture$workers %||% 3)
  up("cap_hide", cfg$capture$hide)
  env <- cfg$app$env %||% list()
  shiny::updateTextAreaInput(session, "app_env", value = if (length(env)) paste0(names(env), "=", unlist(env), collapse = "\n") else "")
  session$sendInputMessage("cap_cookies", list(value = isTRUE(cfg$capture$dismiss_cookies %||% TRUE)))
  # story
  session$sendInputMessage("story_template", list(value = cfg$film$template %||% "launch"))
  sel("film_tone", cfg$film$tone %||% "confident"); up("film_audience", cfg$film$audience)
  sel("llm_provider", if (identical(cfg$llm$provider, "openai") && nzchar(cfg$llm$base_url %||% "")) "local" else cfg$llm$provider %||% "none")
  # sound
  session$sendInputMessage("voice_enabled", list(value = isTRUE(cfg$voice$enabled %||% TRUE)))
  shiny::updateSliderInput(session, "voice_rate", value = as.numeric(cfg$voice$rate %||% 1))
  shiny::updateTextAreaInput(session, "voice_lexicon", value = cfg$voice$lexicon %||% "")
  sel("music_key", cfg$music$key %||% "auto")
  shiny::updateNumericInput(session, "music_bpm", value = as.numeric(cfg$music$bpm %||% 0))
  shiny::updateNumericInput(session, "music_seed", value = as.numeric(cfg$music$seed %||% 7))
  shiny::updateSliderInput(session, "music_volume", value = as.numeric(cfg$music$volume %||% 0))
  shiny::updateSliderInput(session, "music_duck", value = as.numeric(cfg$music$duck %||% 10))
  shiny::updateSliderInput(session, "music_transpose", value = as.numeric(cfg$music$transpose %||% 0))
  session$sendInputMessage("music_sfx", list(value = isTRUE(cfg$music$sfx %||% TRUE)))
  # look
  session$sendInputMessage("look_aspect", list(value = cfg$format$aspect %||% "16:9"))
  for (k in c("theme", "background", "font", "window", "transition", "captions", "cursor")) session$sendInputMessage(paste0("look_", k), list(value = cfg$look[[k]] %||% ""))
  shiny::updateSliderInput(session, "look_radius", value = as.numeric(cfg$look$radius %||% 22))
  session$sendInputMessage("look_grain", list(value = isTRUE(cfg$look$grain %||% TRUE)))
  invisible()
}

dr_complete_palette <- function(cols) {
  cols <- cols[grepl("^#[0-9a-fA-F]{6}$", cols)]
  if (!length(cols)) return(c("#6366f1", "#a855f7", "#ec4899"))
  while (length(cols) < 3) {
    rgb <- grDevices::col2rgb(cols[length(cols)]) / 255
    hsv <- grDevices::rgb2hsv(rgb[1], rgb[2], rgb[3], maxColorValue = 1)
    cols <- c(cols, grDevices::hsv((hsv[1] + 0.12) %% 1, max(.55, hsv[2]), max(.75, hsv[3])))
  }
  tolower(substr(cols[1:3], 1, 7))
}

srv_source <- function(input, output, session, rv, ctx) {
  # ---- source kind & value
  dr_on(input$src_kind, { if (!is.null(rv$dir)) ctx$set(c("source", "kind"), input$src_kind) }, ignoreInit = TRUE)
  output$src_value_ui <- shiny::renderUI({
    k <- rv$cfg$source$kind %||% "url"; v <- rv$cfg$source$value %||% ""
    switch(k,
      url = dr_text("src_value", "Link", v, placeholder = "https://your.app or http://localhost:3838", help = "Any website or web app: Shiny (shinyapps.io, Posit Connect), Streamlit, dashboards, landing pages."),
      git = dr_text("src_value", "Repository", v, placeholder = "https://github.com/you/app  (\u2026/tree/main/subfolder works too)", help = "Cloned with git, then launched locally: Shiny (R or Python), golem/rhino, Streamlit, Gradio, Quarto, static sites, Node."),
      dir = dr_text("src_value", "Folder on this computer", v, placeholder = "~/code/my-shiny-app", help = "Copied into the project before launching (your folder is never modified)."),
      zip = div(class = "stack", shiny::fileInput("src_zip", "Zip of the repository", accept = ".zip", buttonLabel = "Choose\u2026", placeholder = if (nzchar(v)) basename(v) else "No file"),
                if (nzchar(v)) div(class = "dim", style = "font-size:12px", dr_icon("zip", 13), " ", basename(v))),
      media = dr_note("Upload screenshots (PNG/JPG) and screen recordings (MP4/MOV/WebM) below. Each becomes a shot; stills get camera moves.", icon = "image"))
  })
  dr_on(input$src_value, {
    v <- trimws(input$src_value %||% "")
    if (!is.null(rv$dir) && !identical(v, rv$cfg$source$value %||% "")) ctx$set(c("source", "value"), v)
  }, ignoreInit = TRUE)
  dr_on(input$src_zip, {
    f <- input$src_zip; if (is.null(f) || is.null(rv$dir)) return()
    dst <- file.path(rv$dir, "upload.zip"); file.copy(f$datapath[1], dst, overwrite = TRUE)
    ctx$set(c("source", "value"), dst); ctx$set(c("source", "kind"), "zip")
    ctx$toast("Zip uploaded", f$name[1], "good")
  })
  dr_on(input$src_scout, {
    if (is.null(rv$dir)) return(ctx$toast("Create a film first", type = "warn"))
    if (identical(rv$cfg$source$kind, "media")) return(ctx$start("plan", after = list(go = "story")))
    if (!nzchar(rv$cfg$source$value %||% "")) return(ctx$toast("Add a source first", type = "warn"))
    ctx$start("scout", after = list(plan = is.null(rv$sb)))
  })

  # ---- detection summary
  output$src_detect_ui <- shiny::renderUI({
    f <- rv$facts; st <- rv$cfg
    if (is.null(f)) return(NULL)
    app <- f$app %||% list()
    miss <- unlist(f$r_missing)
    div(class = "stack", style = "gap:10px",
        div(class = "hrow", dr_chip(app$label %||% "Unknown", "accent", switch(app$kind %||% "", url = "globe", media = "image", "zap")),
            if (length(app$alternatives)) htmltools::span(class = "dim", style = "font-size:12px", "also found: ", paste(unlist(app$alternatives)[1:min(3, length(app$alternatives))], collapse = " \u00b7 "))),
        if (length(miss)) dr_note(class = "warn", icon = "alert",
                                  tags$b(sprintf("The app needs %d R package%s that %s not installed: ", length(miss), if (length(miss) == 1) "" else "s", if (length(miss) == 1) "is" else "are")),
                                  htmltools::span(class = "mono", paste(miss, collapse = ", ")),
                                  div(style = "margin-top:8px", tags$button(class = "dr-btn xs", `data-act` = "install_pkgs", dr_icon("download", 13), "Install from CRAN"))))
  })

  # ---- advanced settings
  bind <- function(id, path, conv = identity, rebuild = FALSE) dr_on(input[[id]], { if (!is.null(rv$dir)) ctx$set(path, conv(input[[id]]), rebuild) }, ignoreInit = TRUE)
  bind("app_command", c("app", "command")); bind("app_path", c("app", "path")); bind("app_renv", c("app", "renv"))
  bind("app_wait", c("app", "wait"), function(x) max(300, suppressWarnings(as.numeric(x)) %||% 600))
  bind("cap_viewport", c("capture", "viewport")); bind("cap_scheme", c("capture", "scheme"))
  bind("cap_lite", c("capture", "lite"), function(x) if (x == "auto") "auto" else identical(x, "true"))
  bind("cap_fps", c("capture", "fps"), as.numeric); bind("cap_dpr", c("capture", "dpr"), function(x) if (identical(x, "auto")) "auto" else as.numeric(x)); bind("cap_workers", c("capture", "workers"), as.numeric)
  bind("cap_hide", c("capture", "hide")); bind("cap_cookies", c("capture", "dismiss_cookies"), isTRUE)
  bind("app_env", c("app", "env"), function(x) {
    lines <- strsplit(x %||% "", "\n")[[1]]
    kv <- regmatches(lines, regexec("^\\s*([A-Za-z_][A-Za-z0-9_]*)\\s*=\\s*(.*?)\\s*$", lines))
    kv <- Filter(function(m) length(m) == 3, kv)
    if (!length(kv)) return(stats::setNames(list(), character(0)))
    stats::setNames(lapply(kv, `[[`, 3), vapply(kv, `[[`, "", 2))
  })

  # ---- brand
  bind("brand_name", c("brand", "name"), trimws, TRUE); bind("brand_tagline", c("brand", "tagline"), trimws, TRUE)
  bind("brand_description", c("brand", "description"), trimws); bind("brand_url", c("brand", "url"), trimws, TRUE); bind("brand_cta", c("brand", "cta"), trimws, TRUE)
  # the three pickers update one by one when a film is opened: wait for all three, and ignore the echo of a load
  cols <- shiny::debounce(shiny::reactive(c(input$brand_c1, input$brand_c2, input$brand_c3)), 700)
  dr_on(cols(), {
    if (is.null(rv$dir) || length(cols()) < 3) return()
    if (!is.null(ctx$loading_until) && Sys.time() < ctx$loading_until) return()
    cur <- unlist(rv$cfg$brand$colors %||% list()); auto <- unlist(rv$facts$brand_auto$colors %||% list())
    base <- if (length(cur)) cur else dr_complete_palette(c(auto, "#6366f1", "#a855f7", "#ec4899")[seq_len(max(1, length(auto)))])
    if (identical(tolower(cols()), tolower(base[1:3]))) return()
    ctx$set(c("brand", "colors"), as.list(tolower(cols())), TRUE)
  }, ignoreInit = TRUE)
  dr_on(input$brand_colors_reset, {
    if (is.null(rv$dir)) return()
    ctx$set(c("brand", "colors"), list(), TRUE); apply_inputs(session, rv, ctx, brand_only = TRUE)
  })
  dr_on(input$brand_logo, {
    f <- input$brand_logo; if (is.null(f) || is.null(rv$dir)) return()
    ext <- tolower(tools::file_ext(f$name[1])); dir.create(file.path(rv$dir, "assets"), showWarnings = FALSE)
    dst <- file.path(rv$dir, "assets", paste0("logo_upload.", ext)); file.copy(f$datapath[1], dst, overwrite = TRUE)
    ctx$set(c("brand", "logo"), file.path("assets", basename(dst)), TRUE)
    ctx$toast("Logo updated", type = "good")
  })
  output$brand_logo_prev <- shiny::renderUI({
    cfg <- rv$cfg; f <- rv$facts
    p <- cfg$brand$logo %||% f$brand_auto$logo %||% ""
    if (!nzchar(p) || is.null(rv$dir) || !file.exists(file.path(rv$dir, p))) return(div(class = "logo-prev", dr_icon("image", 20)))
    div(class = "logo-prev", style = sprintf("background-image:url('%s')", ctx$url(p, as.integer(file.mtime(file.path(rv$dir, p))))))
  })

  # ---- what the scout saw
  output$src_seen_ui <- shiny::renderUI({
    sc <- rv$scout
    if (is.null(sc)) {
      if (identical(rv$cfg$source$kind, "media")) return(NULL)
      return(dr_card("What DirectoR saw", icon = "eye", dr_empty("eye", "Not scouted yet", "Scouting launches the app in a browser, explores tabs and pages, and picks up the name, tagline, logo and colours.")))
    }
    pal <- unlist(sc$colors$palette)
    dr_card(sprintf("What DirectoR saw \u00b7 %d screen%s", length(sc$views), if (length(sc$views) == 1) "" else "s"), icon = "eye",
            actions = htmltools::tagList(if (!is.null(sc$framework)) dr_chip(sc$framework, "accent"), lapply(pal, function(c) htmltools::span(style = sprintf("width:18px;height:18px;border-radius:6px;background:%s;display:inline-block;box-shadow:0 0 0 1px rgba(255,255,255,.2)", c)))),
            div(class = "views", lapply(sc$views, function(v) {
              n_in <- length(v$inputs); n_out <- length(v$outputs)
              div(class = "view",
                  div(class = "im", style = sprintf("background-image:url('%s')", ctx$url(v$thumb, as.integer(file.mtime(file.path(rv$dir, v$thumb)))))),
                  div(class = "cap", htmltools::span(class = "nm", v$label), dr_chip(v$kind),
                      if (n_in) htmltools::span(class = "dim", style = "font-size:11.5px", sprintf("%d in", n_in)),
                      if (n_out) htmltools::span(class = "dim", style = "font-size:11.5px", sprintf("%d out", n_out))))
            })))
  })

  # ---- media uploads (screenshots & recordings)
  output$src_media_ui <- shiny::renderUI({
    if (!identical(rv$cfg$source$kind, "media") || is.null(rv$dir)) return(NULL)
    rv$shots_v
    m <- dr_read_json(file.path(rv$dir, "media.json"), list(items = list()))
    dr_card("Screenshots & recordings", icon = "image",
            div(class = "stack",
                shiny::fileInput("src_media", NULL, multiple = TRUE, accept = c("image/*", "video/*"), buttonLabel = "Add files\u2026", placeholder = "PNG, JPG, MP4, MOV, WebM"),
                if (!length(m$items)) dr_empty("image", "No files yet", "Each file becomes a shot. Name them well; the names become captions.")
                else div(class = "views", lapply(seq_along(m$items), function(i) {
                  it <- m$items[[i]]; is_img <- grepl("\\.(png|jpe?g|webp|gif)$", it$file, ignore.case = TRUE)
                  div(class = "view", if (is_img) div(class = "im", style = sprintf("background-image:url('%s')", ctx$url(it$file))) else div(class = "im", style = "display:grid;place-items:center", dr_icon("shots", 28)),
                      div(class = "cap", htmltools::span(class = "nm", it$label),
                          tags$button(class = "dr-btn ghost xs icon", `data-act` = "shot_media_del", `data-id` = i, dr_icon("trash", 13))))
                }))))
  })
  dr_on(input$src_media, {
    f <- input$src_media; if (is.null(f) || is.null(rv$dir)) return()
    m <- dr_read_json(file.path(rv$dir, "media.json"), list(items = list()))
    dir.create(file.path(rv$dir, "media"), showWarnings = FALSE)
    for (i in seq_len(nrow(f))) {
      nm <- gsub("[^A-Za-z0-9._-]+", "_", f$name[i]); file.copy(f$datapath[i], file.path(rv$dir, "media", nm), overwrite = TRUE)
      m$items[[length(m$items) + 1]] <- list(file = file.path("media", nm), label = tools::toTitleCase(gsub("[_-]+", " ", tools::file_path_sans_ext(f$name[i]))))
    }
    dr_write_json(m, file.path(rv$dir, "media.json")); rv$shots_v <- rv$shots_v + 1
    ctx$toast(sprintf("%d file%s added", nrow(f), if (nrow(f) == 1) "" else "s"), "Write the storyboard to use them.", "good")
  })
}

install_pkgs <- function(rv, ctx) {
  miss <- unlist(rv$facts$r_missing)
  if (!length(miss)) return()
  if (!is.null(ctx$install_proc) && ctx$install_proc$is_alive()) return(ctx$toast("Already installing", type = "info"))
  rs <- file.path(R.home("bin"), "Rscript")
  log <- file.path(rv$dir, "install.log")
  repos <- getOption("repos"); if (is.null(repos) || identical(unname(repos["CRAN"]), "@CRAN@")) repos <- c(CRAN = "https://cloud.r-project.org")
  code <- sprintf("options(repos = c(CRAN = '%s')); install.packages(c(%s)); miss <- c(%s); miss <- miss[!vapply(miss, requireNamespace, TRUE, quietly = TRUE)]; if (length(miss)) { message('STILL MISSING: ', paste(miss, collapse = ', ')); quit(status = 1) }",
                  unname(repos[1]), paste(sprintf("'%s'", miss), collapse = ","), paste(sprintf("'%s'", miss), collapse = ","))
  ctx$install_proc <- processx::process$new(rs, c("-e", code), stdout = log, stderr = "2>&1", cleanup = FALSE)
  ctx$install_dir <- rv$dir
  ctx$toast("Installing R packages", paste(miss, collapse = ", "), "info", 6000)
}

# called by the job poller: report the end of a package installation, then scout again
install_check <- function(rv, ctx) {
  p <- ctx$install_proc
  if (is.null(p) || p$is_alive()) return()
  ctx$install_proc <- NULL
  log <- file.path(ctx$install_dir, "install.log")
  if (identical(p$get_exit_status(), 0L)) {
    ctx$toast("Packages installed", "Scouting the app again\u2026", "good")
    if (identical(rv$dir, ctx$install_dir)) ctx$start("scout", after = list(plan = is.null(rv$sb)))
  } else {
    ctx$toast("Some packages could not be installed", dr_tail(log, 8), "bad", 15000)
  }
}
