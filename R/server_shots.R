# Shots page: footage cards, recipe editor -------------------------------------------------

VERBS <- c(wait = "Wait", drift = "Idle cursor", show = "Show cursor", hide = "Hide cursor", move = "Move to", hover = "Hover", click = "Click",
           type = "Type", select = "Choose option", slide = "Drag slider", scroll = "Scroll", key = "Press key", settle = "Wait for app", goto = "Go to page")

act_label <- function(a) {
  tgt <- a$target %||% list()
  what <- tgt$text %||% (if (!is.null(tgt$fx)) sprintf("point %.0f%%, %.0f%%", tgt$fx * 100, tgt$fy * 100)) %||% tgt$css %||% ""
  if (nchar(what) > 28) what <- paste0(substr(what, 1, 26), "\u2026")
  switch(a$do %||% "",
    wait = sprintf("wait %.1fs", (a$ms %||% 600) / 1000), drift = sprintf("idle %.1fs", (a$ms %||% 1200) / 1000), show = "cursor in", hide = "cursor out",
    settle = "wait for app", move = paste("move \u2192", what), hover = paste("hover", what), click = paste("click", what),
    type = sprintf("type \u201c%s\u201d", a$text %||% ""), select = sprintf("choose %s in %s", a$option %||% 2, what), slide = sprintf("slide %s to %.0f%%", what, 100 * (a$to %||% .7)),
    scroll = sprintf("scroll %s", if (is.numeric(a$to)) paste0(round(a$to), "px") else a$to %||% "down"), key = paste("key", a$key %||% "Enter"),
    goto = paste("go to", a$url %||% "/"), a$do %||% "?")
}

# a representative frame: just after the screen opened, else 40% in (even: proxies keep every 2nd frame)
shot_still_frame <- function(dir, id, meta) {
  mk <- dr_read_json(file.path(dir, "shots", id, "markers.json"), list())
  n <- as.integer(meta$frames %||% 0); fps <- as.numeric(meta$fps %||% 60)
  i <- if (!is.null(mk$click_nav)) as.integer(mk$click_nav + 1.0 * fps) else as.integer(n * 0.4)
  i <- max(0L, min(n - 1L, i)); i - i %% 2L
}

shot_card <- function(sh, dir, url, sb, status = NULL) {
  meta <- dr_read_json(file.path(dir, "shots", sh$id, "meta.json"))
  stale <- !is.null(meta) && identical(status, "stale")
  rec <- !is.null(meta) && !stale
  proxy <- file.path("shots", sh$id, "proxy")
  has_proxy <- dir.exists(file.path(dir, proxy))
  still <- if (rec && has_proxy) file.path(proxy, sprintf("f%05d.jpg", shot_still_frame(dir, sh$id, meta))) else if (rec && isTRUE(meta$still)) file.path("shots", sh$id, "still.jpg") else sh$thumb %||% ""
  used <- sum(vapply(sb$scenes, function(s) identical(s$shot, sh$id) || sh$id %in% unlist(s$shots), logical(1)))
  v <- if (rec) as.integer(file.mtime(file.path(dir, "shots", sh$id, "meta.json"))) else 0
  div(class = "shot",
      div(class = "flip", `data-dir` = if (rec && has_proxy) paste0(url(proxy), "/") else NULL, `data-n` = meta$frames %||% 0,
          if (nzchar(still)) tags$img(src = paste0(url(still), "?v=", v), loading = "lazy"),
          div(class = "fbadge", if (rec) dr_chip(if (isTRUE(meta$still)) "Still" else sprintf("%.1fs \u00b7 %d fps", (meta$frames %||% 0) / (meta$fps %||% 60), meta$fps %||% 60), "good", "check")
                                else if (stale) dr_chip("Recipe changed: re-record", "warn", "refresh") else dr_chip("Not recorded", "warn", "clock")),
          if (rec && has_proxy) div(class = "hint", "hover to play")),
      div(class = "sb",
          div(class = "nm", sh$label %||% sh$id, htmltools::span(class = "dim", style = "font-weight:500;font-size:12px", sh$id),
              div(style = "flex:1"), if (used) dr_chip(sprintf("in %d scene%s", used, if (used == 1) "" else "s")) else dr_chip("unused", "warn")),
          if (is.null(sh$media)) div(class = "acts-list", lapply(sh$actions %||% list(), function(a) htmltools::span(class = paste0("act k-", a$do), act_label(a))))
          else div(class = "dim", style = "font-size:12.5px", dr_icon("image", 13), " ", basename(sh$media)),
          div(class = "hrow",
              tags$button(class = "dr-btn xs", `data-act` = "shot_rec", `data-id` = sh$id, dr_icon("refresh", 13), if (rec) "Re-record" else "Record"),
              if (is.null(sh$media)) tags$button(class = "dr-btn xs", `data-act` = "shot_edit", `data-id` = sh$id, dr_icon("sliders", 13), "Edit"),
              div(style = "flex:1"),
              tags$button(class = "dr-btn ghost xs icon danger", `data-act` = "shot_del", `data-id` = sh$id, `data-confirm` = "Delete this shot?", title = "Delete", dr_icon("trash", 13)))))
}

srv_shots <- function(input, output, session, rv, ctx) {
  output$shots_grid <- shiny::renderUI({
    rv$shots_v; rv$sb_v; rv$tl_v
    sb <- shiny::isolate(rv$sb); st <- shiny::isolate(rv$tl)$shot_status
    if (is.null(rv$dir)) return(NULL)
    if (is.null(sb) || !length(sb$shots)) return(dr_card(NULL, dr_empty("shots", "No shots yet", "Write the storyboard first: it plans which screens to film and what to do on each.")))
    url <- function(p) ctx$url(p)
    div(class = "shots", lapply(sb$shots, function(sh) shot_card(sh, dir = rv$dir, url = url, sb = sb, status = st[[sh$id]])))
  })
  dr_on(input$shots_record, {
    if (is.null(rv$sb)) return(ctx$toast("Write the storyboard first", type = "warn"))
    ctx$start("capture")
  })

  # ---- editor (modal) -------------------------------------------------------------------
  ed <- shiny::reactiveValues(id = NULL, actions = list(), view = NULL, reach = NULL, label = "", v = 0)
  open_editor <- function(sh) {
    ed$id <- sh$id; ed$actions <- sh$actions %||% list(); ed$view <- sh$view; ed$reach <- sh$reach %||% list(url = "/"); ed$label <- sh$label %||% sh$id; ed$v <- ed$v + 1
    views <- rv$scout$views %||% list()
    vch <- stats::setNames(vapply(views, function(v) v$id, ""), vapply(views, function(v) sprintf("%s (%s)", v$label, v$kind), ""))
    shiny::showModal(shiny::modalDialog(
      title = htmltools::tagList(dr_icon("shots", 18), " Shot recipe"), size = "xl", easyClose = FALSE,
      footer = htmltools::tagList(shiny::modalButton("Cancel"), dr_btn("ed_save", "Save", "check", "sm"), dr_btn("ed_save_rec", "Save & record", "shots", "primary sm")),
      div(class = "cols", style = "grid-template-columns: minmax(0,1.25fr) minmax(0,.75fr)",
          div(class = "stack",
              div(class = "grid3", dr_text("ed_label", "Name", ed$label),
                  dr_select("ed_view", "Starts on screen", vch, sh$view),
                  dr_text("ed_url", "\u2026or at this path", ed$reach$url %||% "/")),
              shiny::uiOutput("ed_rows"),
              div(class = "hrow", lapply(c("click", "hover", "type", "select", "slide", "scroll", "wait", "drift", "settle", "key"), function(k)
                tags$button(class = "dr-btn xs", `data-act` = "shot_ed_add", `data-arg` = k, dr_icon("plus", 12), VERBS[[k]])))),
          div(class = "stack",
              dr_note(icon = "cursor", "Click on the screenshot to add a click at that point. Targets found by the scout are in each row's list; text targets (e.g. a tab name) survive layout changes."),
              shiny::uiOutput("ed_picker")))))
  }
  output$ed_picker <- shiny::renderUI({
    ed$v
    v <- Filter(function(x) identical(x$id, input$ed_view %||% ed$view), rv$scout$views %||% list())
    if (!length(v)) return(dr_empty("image", "No screenshot for this screen"))
    div(class = "picker", `data-input` = "ed_pick", tags$img(src = ctx$url(v[[1]]$thumb)))
  })
  enc_t <- function(x) if (is.null(x)) "" else as.character(jsonlite::toJSON(x[order(names(x))], auto_unbox = TRUE))   # canonical key order
  targets_for <- function() {
    v <- Filter(function(x) identical(x$id, input$ed_view %||% ed$view), rv$scout$views %||% list())
    if (!length(v)) return(c("(none)" = ""))
    v <- v[[1]]
    enc <- enc_t
    c(c("(choose a target)" = ""),
      stats::setNames(vapply(v$tabs %||% list(), function(t) enc(list(kind = "tab", text = t)), ""), paste("Tab:", unlist(v$tabs))),
      stats::setNames(vapply(v$buttons %||% list(), function(b) enc(list(kind = "button", text = b$text)), ""), paste("Button:", vapply(v$buttons %||% list(), function(b) b$text, ""))),
      stats::setNames(vapply(v$inputs %||% list(), function(i) enc(list(css = i$css, kind = if (i$type == "slider") "slider" else i$type)), ""), vapply(v$inputs %||% list(), function(i) sprintf("%s: %s", tools::toTitleCase(i$type), if (nzchar(i$label %||% "")) i$label else i$css), "")),
      stats::setNames(vapply(v$outputs %||% list(), function(o) enc(list(css = o$css)), ""), vapply(v$outputs %||% list(), function(o) sprintf("Output: %s", o$kind), "")))
  }
  output$ed_rows <- shiny::renderUI({
    ed$v
    acts <- shiny::isolate(ed$actions)
    tg <- targets_for()
    div(class = "act-rows", lapply(seq_along(acts), function(i) {
      a <- acts[[i]]; te <- enc_t(a$target)
      tch <- if (nzchar(te) && !te %in% tg) c(tg, stats::setNames(te, paste("Custom:", act_label(a)))) else tg
      needs_t <- a$do %in% c("move", "hover", "click", "type", "select", "slide")
      val <- switch(a$do, type = a$text, select = a$option, slide = a$to, scroll = a$to, key = a$key, goto = a$url, "")
      div(class = "act-row",
          div(class = "n", i),
          shiny::selectInput(paste0("ed_do_", i), NULL, stats::setNames(names(VERBS), VERBS), a$do, selectize = FALSE),
          if (needs_t) shiny::selectInput(paste0("ed_t_", i), NULL, tch, te, selectize = FALSE) else div(class = "dim", style = "font-size:12px", "\u2014"),
          shiny::textInput(paste0("ed_val_", i), NULL, as.character(val %||% ""), placeholder = switch(a$do, type = "text to type", select = "option # or text", slide = "0\u20131", scroll = "px / bottom / next", key = "Enter", goto = "/path", "")),
          shiny::numericInput(paste0("ed_ms_", i), NULL, a$ms %||% switch(a$do, wait = 600, drift = 1200, scroll = 2500, 650), min = 0, step = 50),
          div(class = "hrow nowrap", style = "gap:2px",
              tags$button(class = "dr-btn ghost xs icon", `data-act` = "shot_ed_up", `data-arg` = i, dr_icon("up", 13)),
              tags$button(class = "dr-btn ghost xs icon", `data-act` = "shot_ed_down", `data-arg` = i, dr_icon("down", 13)),
              tags$button(class = "dr-btn ghost xs icon danger", `data-act` = "shot_ed_del", `data-arg` = i, dr_icon("trash", 13))))
    }))
  })
  collect <- function() {
    acts <- ed$actions
    for (i in seq_along(acts)) {
      a <- acts[[i]]
      d <- input[[paste0("ed_do_", i)]] %||% a$do
      a$do <- d
      t <- input[[paste0("ed_t_", i)]]
      if (!is.null(t)) a$target <- if (nzchar(t)) jsonlite::fromJSON(t, simplifyVector = FALSE) else NULL
      val <- input[[paste0("ed_val_", i)]]
      if (!is.null(val)) {
        if (d == "type") a$text <- val
        if (d == "select") { n <- suppressWarnings(as.integer(val)); a$option <- if (is.na(n)) val else n }
        if (d == "slide") a$to <- suppressWarnings(as.numeric(val)) %||% .7
        if (d == "scroll") { n <- suppressWarnings(as.numeric(val)); a$to <- if (is.na(n)) (if (nzchar(val)) val else "next") else n }
        if (d == "key") a$key <- if (nzchar(val)) val else "Enter"
        if (d == "goto") a$url <- val
      }
      ms <- input[[paste0("ed_ms_", i)]]; if (!is.null(ms) && !is.na(ms)) a$ms <- ms
      if (d %in% c("click", "select", "type", "slide") && is.null(a$mark)) a$mark <- paste0("click_", i)
      acts[[i]] <- a
    }
    acts
  }
  dr_on(input$ed_pick, {
    p <- input$ed_pick; ed$actions <- collect()
    ed$actions[[length(ed$actions) + 1]] <- list(do = "click", target = list(fx = p$fx, fy = p$fy), ms = 650, mark = paste0("click_p", length(ed$actions) + 1))
    ed$actions[[length(ed$actions) + 1]] <- list(do = "settle", ms = 1200)
    ed$v <- ed$v + 1
  })
  dr_on(input$ed_view, { ed$v <- ed$v + 1 }, ignoreInit = TRUE)
  ed_act <- function(a) {
    acts <- collect(); i <- as.integer(a$arg)
    if (a$act == "shot_ed_add") {
      k <- a$arg; n <- list(do = k)
      if (k == "type") n$text <- "Hello"
      if (k == "select") n$option <- 1
      if (k == "slide") n$to <- .7
      if (k == "scroll") n$to <- "next"
      if (k == "key") n$key <- "Enter"
      acts[[length(acts) + 1]] <- n
    } else if (a$act == "shot_ed_del") acts[[i]] <- NULL
    else if (a$act == "shot_ed_up" && i > 1) acts[c(i - 1, i)] <- acts[c(i, i - 1)]
    else if (a$act == "shot_ed_down" && i < length(acts)) acts[c(i, i + 1)] <- acts[c(i + 1, i)]
    ed$actions <- acts; ed$v <- ed$v + 1
  }
  save_shot <- function(record = FALSE) {
    sb <- rv$sb; acts <- collect()
    ids <- vapply(sb$shots, function(s) s$id, ""); i <- match(ed$id, ids)
    v <- Filter(function(x) identical(x$id, input$ed_view), rv$scout$views %||% list())
    sh <- if (is.na(i)) list(id = ed$id) else sb$shots[[i]]
    sh$label <- input$ed_label %||% sh$label; sh$actions <- acts
    if (length(v)) { sh$view <- v[[1]]$id; sh$thumb <- v[[1]]$thumb; sh$reach <- list(url = input$ed_url %||% v[[1]]$reach$url %||% "/"); if (!is.null(v[[1]]$reach$tab) && !any(vapply(acts, function(a) identical(a$target$text, v[[1]]$reach$tab), TRUE))) sh$reach$tab <- v[[1]]$reach$tab }
    else sh$reach <- list(url = input$ed_url %||% "/")
    if (is.na(i)) sb$shots[[length(sb$shots) + 1]] <- sh else sb$shots[[i]] <- sh
    save_sb(rv, ctx, sb, TRUE); shiny::removeModal()
    if (record) ctx$start("capture", c("--shots", sh$id)) else ctx$toast("Shot saved", "Record it to see the new footage.", "good")
  }
  dr_on(input$ed_save, save_shot(FALSE))
  dr_on(input$ed_save_rec, save_shot(TRUE))
  dr_on(input$shots_add, {
    sb <- rv$sb
    if (is.null(sb)) return(ctx$toast("Write the storyboard first", type = "warn"))
    if (is.null(rv$scout)) return(ctx$toast("Scout the app first", "New shots start on a screen the scout found.", "warn"))
    ids <- vapply(sb$shots, function(s) s$id, ""); n <- length(ids) + 1; while (paste0("shot", n) %in% ids) n <- n + 1
    v <- rv$scout$views[[1]]
    open_editor(list(id = paste0("shot", n), label = "New shot", view = v$id, reach = list(url = v$reach$url %||% "/"),
                     actions = list(list(do = "wait", ms = 400), list(do = "show", ms = 250), list(do = "drift", ms = 2500))))
  })
  ctx$shot_editor <- function(id) {
    sh <- Filter(function(s) identical(s$id, id), rv$sb$shots)
    if (length(sh)) open_editor(sh[[1]])
  }
  ctx$shot_ed_act <- ed_act
}

shot_act <- function(a, rv, ctx, session, input) {
  if (a$act %in% c("shot_ed_add", "shot_ed_del", "shot_ed_up", "shot_ed_down")) return(ctx$shot_ed_act(a))
  if (a$act == "shot_rec") return(ctx$start("capture", c("--shots", a$id)))
  if (a$act == "shot_edit") return(ctx$shot_editor(a$id))
  if (a$act == "shot_del") {
    sb <- rv$sb; sb$shots <- Filter(function(s) !identical(s$id, a$id), sb$shots)
    for (i in seq_along(sb$scenes)) {
      if (identical(sb$scenes[[i]]$shot, a$id)) sb$scenes[[i]]$enabled <- FALSE
      if (!is.null(sb$scenes[[i]]$shots)) sb$scenes[[i]]$shots <- as.list(setdiff(unlist(sb$scenes[[i]]$shots), a$id))
    }
    unlink(file.path(rv$dir, "shots", a$id), recursive = TRUE)
    save_sb(rv, ctx, sb, TRUE); return(ctx$toast("Shot deleted", "Scenes that used it were switched off.", "info"))
  }
  if (a$act == "shot_media_del") {
    m <- dr_read_json(file.path(rv$dir, "media.json"), list(items = list()))
    i <- as.integer(a$id); if (i <= length(m$items)) { unlink(file.path(rv$dir, m$items[[i]]$file)); m$items[[i]] <- NULL }
    dr_write_json(m, file.path(rv$dir, "media.json")); rv$shots_v <- rv$shots_v + 1
  }
}
