# Story page: template, storyboard editor, live preview ------------------------------------

SCENE_TYPES <- list(
  hook = list(label = "Hook", icon = "zap", color = "#ec4899"), title = list(label = "Title", icon = "sparkles", color = "#a855f7"),
  shot = list(label = "Shot", icon = "shots", color = "#6366f1"), features = list(label = "Features", icon = "grid", color = "#10b981"),
  montage = list(label = "Montage", icon = "film", color = "#f59e0b"), grid = list(label = "Wall", icon = "layers", color = "#06b6d4"),
  stat = list(label = "Stat", icon = "hash", color = "#f97316"), quote = list(label = "Quote", icon = "quote", color = "#d946ef"),
  end = list(label = "End card", icon = "flag", color = "#8b5cf6"))
TRANSITIONS <- c("auto", "cut", "fade", "blur", "zoom", "slide", "push", "whip", "rise", "flash", "wipe", "iris", "flip")
LAYOUTS <- c(window = "Window", tilt = "Tilt in", float = "Float 3-D", full = "Full bleed", split = "Split + text", phone = "Phone")
CAMERAS <- c(auto = "Smart zoom", follow = "Follow cursor", push = "Slow push", pan = "Steady", static = "Locked")
ANIMS <- c(rise = "Rise", slam = "Slam", pop = "Pop", blur = "Blur in", drop = "Drop", type = "Type")
ICONS_FEAT <- c("chart", "bolt", "lock", "users", "globe", "layers", "check", "clock", "search", "code", "download", "sparkles", "map", "table", "target", "sliders")

# one plain (non-Shiny) form control; director.js reports edits as input$story_edit
ed_input <- function(f, value, placeholder = NULL, cls = "", type = "text") {
  tags$input(class = paste("form-control ed", cls), type = type, `data-f` = f, value = value %||% "", placeholder = placeholder, spellcheck = "true")
}
ed_area <- function(f, value, placeholder = NULL, cls = "") tags$textarea(class = paste("form-control ed", cls), `data-f` = f, placeholder = placeholder, rows = 2, value %||% "")
ed_select <- function(f, choices, selected, title = NULL) {
  if (is.null(names(choices))) names(choices) <- choices
  tags$select(class = "form-select ed", `data-f` = f, title = title,
              lapply(seq_along(choices), function(i) tags$option(value = choices[[i]], selected = if (identical(as.character(choices[[i]]), as.character(selected %||% ""))) NA else NULL, names(choices)[i])))
}

scene_card <- function(sc, i, n, sb, tl, dir, url) {
  ty <- SCENE_TYPES[[sc$type]] %||% SCENE_TYPES$hook
  tsc <- if (!is.null(tl)) Filter(function(x) identical(x$id, sc$id), tl$scenes) else list()
  tsc <- if (length(tsc)) tsc[[1]] else NULL
  shots <- sb$shots %||% list()
  shot_ids <- vapply(shots, function(s) s$id, "")
  shot_lab <- vapply(shots, function(s) s$label %||% s$id, "")
  thumb <- NULL
  if (identical(sc$type, "shot") && !is.null(sc$shot)) {
    sh <- Filter(function(s) identical(s$id, sc$shot), shots)
    if (length(sh)) {
      meta <- dr_read_json(file.path(dir, "shots", sc$shot, "meta.json"))
      p <- if (!is.null(meta)) file.path("shots", sc$shot, "proxy", sprintf("f%05d.jpg", shot_still_frame(dir, sc$shot, meta))) else ""
      thumb <- if (nzchar(p) && file.exists(file.path(dir, p))) p else sh[[1]]$thumb
    }
  } else if (sc$type %in% c("montage", "grid") && length(sc$shots)) {
    s1 <- sc$shots[[1]]; sh <- Filter(function(s) identical(s$id, s1), shots)
    if (length(sh)) thumb <- sh[[1]]$thumb
  }
  dur <- if (!is.null(tsc)) tsc$dur else sc$dur
  vo <- sc$vo %||% ""
  nw <- length(strsplit(trimws(vo), "\\s+")[[1]]); if (!nzchar(trimws(vo))) nw <- 0
  fields <- switch(sc$type,
    hook = htmltools::tagList(ed_input("text", sc$text, "Big statement \u2014 *stars* for the gradient", "big"),
                              ed_input("sub", sc$sub, "Small line under it (optional)")),
    title = htmltools::tagList(ed_input("title", sc$title, "Product name", "big"), ed_input("tagline", sc$tagline, "Tagline")),
    shot = htmltools::tagList(ed_input("headline", sc$headline, "Headline above the footage \u2014 *stars* for the gradient", "big"),
                              ed_input("caption", sc$caption, "Caption pill on the footage (optional)")),
    features = htmltools::tagList(ed_input("headline", sc$headline, "Headline", "big"),
                                  div(class = "items", lapply(seq_along(sc$items %||% list()), function(k) {
                                    it <- sc$items[[k]]
                                    div(class = "it", ed_input(sprintf("items.%d.title", k), it$title, "Title"), ed_input(sprintf("items.%d.text", k), it$text, "Short text"),
                                        ed_select(sprintf("items.%d.icon", k), ICONS_FEAT, it$icon))
                                  }))),
    montage = ed_input("caption", sc$caption, "Caption (optional)"),
    grid = ed_input("headline", sc$headline, "Headline over the wall", "big"),
    stat = htmltools::tagList(ed_input("value", sc$value, "e.g. 3\u00d7, 120k, 98%", "big"), ed_input("label", sc$label, "What the number means")),
    quote = htmltools::tagList(ed_area("text", sc$text, "The quote"), ed_input("author", sc$author, "Who said it")),
    end = htmltools::tagList(ed_input("title", sc$title, "Name", "big"), ed_input("tagline", sc$tagline, "Tagline"),
                             div(class = "grid2", ed_input("cta", sc$cta, "Call to action: url, install command\u2026"), ed_input("note", sc$note, "Small print (optional)"))),
    NULL)
  picks <- if (sc$type %in% c("montage", "grid")) div(class = "opts", htmltools::span(class = "dim", style = "font-size:12px", "Shots:"),
                                                        lapply(seq_along(shot_ids), function(k) tags$label(class = "chip", style = "cursor:pointer",
                                                          tags$input(type = "checkbox", `data-f` = paste0("shots.", shot_ids[k]), checked = if (shot_ids[k] %in% unlist(sc$shots)) NA else NULL, style = "margin-right:4px"), shot_lab[k])))
  opts <- div(class = "opts",
              ed_select("transition", stats::setNames(TRANSITIONS, paste("In:", tools::toTitleCase(TRANSITIONS))), sc$transition %||% "auto", "Transition into this scene"),
              if (sc$type == "shot") ed_select("shot", stats::setNames(shot_ids, paste("Shot:", shot_lab)), sc$shot),
              if (sc$type == "shot") ed_select("layout", stats::setNames(names(LAYOUTS), LAYOUTS), sc$layout %||% "window"),
              if (sc$type == "shot") ed_select("camera", stats::setNames(names(CAMERAS), CAMERAS), sc$camera %||% "auto"),
              if (sc$type == "hook") ed_select("anim", stats::setNames(names(ANIMS), ANIMS), sc$anim %||% "rise"),
              if (sc$type %in% c("hook", "title", "end")) ed_select("bg", c("Background: film" = "", "Dark" = "dark", "Light" = "light", "Brand" = "brand"), sc$bg %||% ""),
              if (sc$type == "shot") tags$input(class = "form-control ed num", type = "number", min = 0, max = 9, step = 1, `data-f` = "step", value = sc$step %||% "", placeholder = "Step", title = "Step number badge (empty = none)"),
              htmltools::span(class = "dim", style = "font-size:12px;margin-left:4px", "min"),
              tags$input(class = "form-control ed num", type = "number", min = 0.5, max = 20, step = 0.1, `data-f` = "dur", value = sc$dur %||% 3, title = "Minimum seconds (the voice-over can make it longer)"),
              htmltools::span(class = "dim", style = "font-size:12px", "s"))
  div(class = paste("scene", if (isFALSE(sc$enabled)) "off"), `data-scene` = sc$id,
      div(class = "idx", div(class = "n", style = sprintf("background:%s", ty$color), i),
          tags$button(class = "dr-btn ghost xs icon", `data-act` = "scene_up", `data-id` = sc$id, disabled = if (i == 1) NA else NULL, title = "Move up", dr_icon("up", 14)),
          tags$button(class = "dr-btn ghost xs icon", `data-act` = "scene_down", `data-id` = sc$id, disabled = if (i == n) NA else NULL, title = "Move down", dr_icon("down", 14))),
      div(class = "thumb", `data-seek` = if (!is.null(tsc)) tsc$t0 else 0, title = "Play from here",
          style = if (!is.null(thumb)) sprintf("background-image:url('%s')", url(thumb)) else sprintf("background:linear-gradient(135deg,%s33,#0d0d12)", ty$color),
          if (is.null(thumb)) div(class = "ty", dr_icon(ty$icon, 26)),
          div(class = "pl", dr_icon("play", 22)),
          if (!is.null(dur)) div(class = "tl", sprintf("%.1fs", as.numeric(dur)))),
      div(class = "body",
          div(class = "top", htmltools::span(class = "ty", style = sprintf("color:%s", ty$color), ty$label),
              if (identical(sc$type, "shot")) htmltools::span(class = "dim", style = "font-size:12px", shot_lab[match(sc$shot, shot_ids)] %||% ""),
              if (!is.null(tsc)) htmltools::span(class = "dim", style = "font-size:12px", sprintf("%.1f\u2013%.1fs", tsc$t0, tsc$t1)),
              div(class = "grow"),
              div(class = "tools",
                  tags$button(class = "dr-btn ghost xs icon", `data-act` = "scene_toggle", `data-id` = sc$id, title = if (isFALSE(sc$enabled)) "Include" else "Skip", dr_icon(if (isFALSE(sc$enabled)) "eye" else "x", 14)),
                  tags$button(class = "dr-btn ghost xs icon", `data-act` = "scene_dup", `data-id` = sc$id, title = "Duplicate", dr_icon("copy", 14)),
                  tags$button(class = "dr-btn ghost xs icon danger", `data-act` = "scene_del", `data-id` = sc$id, title = "Delete", dr_icon("trash", 14)))),
          fields, picks,
          if (isTRUE(sb$vo %||% TRUE)) div(class = "vo-l", dr_icon("mic", 15), ed_area("vo", vo, "Voice-over line (leave empty for music only)", "vo")),
          div(class = "hrow spread", opts, if (isTRUE(sb$vo %||% TRUE)) htmltools::span(class = paste("meter", if (nw > 26) "over"), if (nw) sprintf("%d words \u00b7 ~%.1fs", nw, nw / 2.6) else "no voice-over"))))
}

new_scene <- function(type, sb) {
  shots <- vapply(sb$shots %||% list(), function(s) s$id, "")
  b <- sb$brand %||% list()
  switch(type,
    hook = list(type = "hook", text = "Say it *boldly.*", anim = "rise", dur = 2.6),
    title = list(type = "title", title = b$name %||% "", tagline = b$tagline %||% "", dur = 3),
    shot = list(type = "shot", shot = if (length(shots)) shots[1] else NULL, layout = "window", camera = "auto", headline = "A *new* scene.", dur = 4),
    features = list(type = "features", headline = "Everything you *need.*", dur = 4.5, items = list(list(title = "Fast", text = "Answers in a blink.", icon = "bolt"),
                                                                                                    list(title = "Secure", text = "Your data stays yours.", icon = "lock"), list(title = "Shared", text = "Built for teams.", icon = "users"))),
    montage = list(type = "montage", shots = as.list(shots[seq_len(min(4, length(shots)))]), dur = 2.8),
    grid = list(type = "grid", headline = "All in *one place.*", shots = as.list(shots[seq_len(min(6, length(shots)))]), dur = 2.6),
    stat = list(type = "stat", value = "10\u00d7", label = "faster than before", dur = 2.6),
    quote = list(type = "quote", text = "It changed how our team works.", author = "A happy user", dur = 3.5),
    end = list(type = "end", title = b$name %||% "", tagline = b$tagline %||% "", cta = b$cta %||% "", dur = 4))
}

save_sb <- function(rv, ctx, sb, structural = FALSE) {
  dr_write_json(sb, file.path(rv$dir, "storyboard.json"))
  rv$sb <- sb
  if (structural) rv$sb_v <- shiny::isolate(rv$sb_v) + 1
  ctx$rebuild()
}

story_act <- function(a, rv, ctx, session) {
  sb <- rv$sb; if (is.null(sb)) return()
  ids <- vapply(sb$scenes, function(s) s$id, "")
  i <- match(a$id, ids)
  act <- a$act
  if (act == "scene_add") {
    sc <- new_scene(a$arg, sb)
    n <- 1; while (paste0("s", n) %in% ids) n <- n + 1
    sc$id <- paste0("s", n); sc$transition <- "auto"; sc$vo <- ""; sc$enabled <- TRUE
    endi <- which(vapply(sb$scenes, function(s) identical(s$type, "end"), logical(1)))
    pos <- if (length(endi) && a$arg != "end") endi[1] - 1 else length(sb$scenes)
    sb$scenes <- append(sb$scenes, list(sc), after = pos)
    save_sb(rv, ctx, sb, TRUE); return(ctx$toast(sprintf("%s scene added", SCENE_TYPES[[a$arg]]$label), type = "good", life = 1600))
  }
  if (is.na(i)) return()
  if (act == "scene_up" && i > 1) sb$scenes[c(i - 1, i)] <- sb$scenes[c(i, i - 1)]
  else if (act == "scene_down" && i < length(sb$scenes)) sb$scenes[c(i, i + 1)] <- sb$scenes[c(i + 1, i)]
  else if (act == "scene_del") sb$scenes[[i]] <- NULL
  else if (act == "scene_dup") { sc <- sb$scenes[[i]]; n <- 1; while (paste0("s", n) %in% ids) n <- n + 1; sc$id <- paste0("s", n); sb$scenes <- append(sb$scenes, list(sc), after = i) }
  else if (act == "scene_toggle") sb$scenes[[i]]$enabled <- isFALSE(sb$scenes[[i]]$enabled)
  save_sb(rv, ctx, sb, TRUE)
}

apply_edit <- function(sc, f, v, sb) {
  parts <- strsplit(f, ".", fixed = TRUE)[[1]]
  if (parts[1] == "items" && length(parts) == 3) {
    k <- as.integer(parts[2]); if (is.null(sc$items) || k > length(sc$items)) return(sc)
    sc$items[[k]][[parts[3]]] <- v; return(sc)
  }
  if (parts[1] == "shots" && length(parts) == 2) {
    cur <- unlist(sc$shots %||% list())
    cur <- if (isTRUE(v)) unique(c(cur, parts[2])) else setdiff(cur, parts[2])
    order <- vapply(sb$shots, function(s) s$id, "")
    sc$shots <- as.list(order[order %in% cur]); return(sc)
  }
  if (f %in% c("dur", "step")) {
    num <- suppressWarnings(as.numeric(v))
    sc[f] <- list(if (is.na(num)) NULL else num)
    if (f == "dur" && !is.na(num)) sc$lock <- FALSE
    return(sc)
  }
  if (f == "bg" && !nzchar(v)) { sc$bg <- NULL; return(sc) }
  sc[[f]] <- v
  sc
}

srv_story <- function(input, output, session, rv, ctx) {
  dr_on(input$story_template, {
    if (is.null(rv$dir)) return()
    if (ctx$set(c("film", "template"), input$story_template) && !is.null(rv$sb) && !identical(rv$sb$template, input$story_template)) {
      ctx$toast("Template changed", "Click \u201cWrite storyboard\u201d to rewrite the film in this format.", "info", 4000)
      if (identical(input$story_template, "social") && !identical(rv$cfg$format$aspect, "9:16")) { ctx$set(c("format", "aspect"), "9:16"); session$sendInputMessage("look_aspect", list(value = "9:16")) }
    }
  }, ignoreInit = TRUE)
  bind <- function(id, path) dr_on(input[[id]], { if (!is.null(rv$dir)) ctx$set(path, input[[id]]) }, ignoreInit = TRUE)
  bind("film_tone", c("film", "tone")); bind("film_audience", c("film", "audience"))
  dr_on(input$llm_provider, {
    if (is.null(rv$dir)) return()
    p <- input$llm_provider
    if (p == "local") { ctx$set(c("llm", "provider"), "openai"); if (!nzchar(rv$cfg$llm$base_url %||% "")) ctx$set(c("llm", "base_url"), "http://localhost:11434/v1") }
    else { ctx$set(c("llm", "provider"), p); if (p == "openai") ctx$set(c("llm", "base_url"), "") }
  }, ignoreInit = TRUE)
  output$llm_opts <- shiny::renderUI({
    p <- input$llm_provider %||% "none"
    if (p == "none") return(NULL)
    htmltools::tagList(
      div(style = "width:180px", dr_text("llm_model", "Model", rv$cfg$llm$model %||% "", placeholder = switch(p, openai = "gpt-4.1-mini", anthropic = "claude-sonnet-4-5", local = "llama3.1"))),
      if (p == "local") div(style = "width:250px", dr_text("llm_base", "Server", rv$cfg$llm$base_url %||% "http://localhost:11434/v1")),
      if (p != "local") div(style = "width:220px", dr_field("API key (session only)", tags$input(id = "llm_key", type = "password", class = "form-control dr-secret", placeholder = if (p == "openai") "sk-\u2026" else "sk-ant-\u2026", autocomplete = "off"))))
  })
  dr_on(input$llm_model, { if (!is.null(rv$dir)) ctx$set(c("llm", "model"), input$llm_model) }, ignoreInit = TRUE)
  dr_on(input$llm_base, { if (!is.null(rv$dir)) ctx$set(c("llm", "base_url"), input$llm_base) }, ignoreInit = TRUE)
  dr_on(input$llm_key, {
    k <- input$llm_key %||% ""; p <- input$llm_provider
    s <- rv$secrets
    if (identical(p, "anthropic")) s$ANTHROPIC_API_KEY <- k else s$OPENAI_API_KEY <- k
    rv$secrets <- s
  }, ignoreInit = TRUE)

  dr_on(input$story_generate, {
    if (is.null(rv$dir)) return()
    if (!is.null(rv$sb)) {
      shiny::showModal(shiny::modalDialog(title = "Rewrite the storyboard?", easyClose = TRUE,
        "This replaces the scenes and the script (your edits included). Recorded footage is kept when the shots don't change.",
        footer = htmltools::tagList(shiny::modalButton("Keep mine"), dr_btn("story_generate_ok", "Rewrite", "wand", "primary sm"))))
    } else ctx$start("plan", c("--template", input$story_template %||% "launch"), after = list(go = "story"))
  })
  dr_on(input$story_generate_ok, { shiny::removeModal(); ctx$start("plan", c("--template", input$story_template %||% "launch"), after = list(go = "story")) })

  dr_on(input$story_edit, {
    sb <- rv$sb; if (is.null(sb)) return()
    ids <- vapply(sb$scenes, function(s) s$id, "")
    structural <- FALSE
    for (e in input$story_edit$edits) {
      i <- match(e$scene, ids); if (is.na(i)) next
      sb$scenes[[i]] <- apply_edit(sb$scenes[[i]], e$f, e$v, sb)
      if (e$f %in% c("shot")) structural <- TRUE
    }
    save_sb(rv, ctx, sb, structural)
  })

  output$story_scenes <- shiny::renderUI({
    rv$sb_v
    sb <- shiny::isolate(rv$sb); tl <- shiny::isolate(rv$tl)
    if (is.null(rv$dir)) return(NULL)
    if (is.null(sb)) return(dr_card(NULL, dr_empty("wand", "No storyboard yet", if (is.null(rv$scout) && !identical(rv$cfg$source$kind, "media")) "Scout the app first (Source), or just click \u201cWrite storyboard\u201d." else "Click \u201cWrite storyboard\u201d: DirectoR writes scenes, a voice-over and shot recipes from what it learnt.",
                                                  div(style = "margin-top:10px", dr_btn(NULL, "Write storyboard", "wand", "primary", onclick = "document.getElementById('story_generate').click()")))))
    url <- function(p) ctx$url(p)
    n <- length(sb$scenes)
    div(class = "scenes", lapply(seq_along(sb$scenes), function(i) scene_card(sb$scenes[[i]], i, n, sb, tl, rv$dir, url)))
  })
  # durations / times in the cards follow the timeline without re-rendering the inputs
  dr_on(rv$tl_v, { if (!is.null(rv$dir)) session$sendCustomMessage("dr-player", list(type = "dr:reload")) }, ignoreInit = TRUE)
  output$story_add <- shiny::renderUI({
    if (is.null(rv$sb)) return(NULL)
    div(class = "add-scene", htmltools::span(class = "dim", style = "font-weight:600;font-size:12.5px;margin-right:4px", dr_icon("plus", 14), " Add"),
        lapply(names(SCENE_TYPES), function(k) tags$button(class = "dr-btn xs", `data-act` = "scene_add", `data-arg` = k, dr_icon(SCENE_TYPES[[k]]$icon, 13), SCENE_TYPES[[k]]$label)))
  })
  output$story_player <- shiny::renderUI({ rv$player_key; shiny::isolate(player_ui(rv, ctx)) })
  output$story_stats <- shiny::renderUI({
    tl <- rv$tl; sb <- rv$sb; cl <- rv$clips
    if (is.null(sb)) return(NULL)
    vos <- vapply(sb$scenes, function(s) if (isFALSE(s$enabled)) "" else s$vo %||% "", "")
    words <- sum(vapply(vos, function(v) if (nzchar(trimws(v))) length(strsplit(trimws(v), "\\s+")[[1]]) else 0L, 1L))
    d <- if (!is.null(tl)) tl$duration else NA
    st <- tl$shot_status
    rec <- if (length(sb$shots)) sum(vapply(sb$shots, function(s) if (!is.null(st)) identical(st[[s$id]], "ok") else file.exists(file.path(rv$dir, "shots", s$id, "meta.json")), logical(1))) else 0
    htmltools::tagList(
      div(class = "stats",
          div(class = "stat", div(class = "v", if (is.na(d)) "\u2013" else sprintf("%.1fs", d), style = if (!is.na(d) && d > 60) "color:var(--warn)"), div(class = "l", "Length")),
          div(class = "stat", div(class = "v", sum(!vapply(sb$scenes, function(s) isFALSE(s$enabled), TRUE))), div(class = "l", "Scenes")),
          div(class = "stat", div(class = "v", sprintf("%d/%d", rec, length(sb$shots))), div(class = "l", "Shots recorded")),
          div(class = "stat", div(class = "v", words), div(class = "l", if (!is.null(cl$voice) && !identical(cl$voice, "none")) sprintf("Words \u00b7 %s", cl$voice) else "Voice-over words"))),
      if (rec < length(sb$shots)) dr_note(icon = "shots", "The preview shows screenshots where footage isn't recorded yet. ", tags$a(href = "#", `data-nav` = "shots", "Record the shots"), " for the real thing.")
      else if (is.null(cl) && isTRUE(sb$vo)) dr_note(icon = "mic", "Scene lengths are estimates until the voice-over exists. ", tags$a(href = "#", `data-nav` = "sound", "Generate it"), "."),
      div(class = "kbd-hint", tags$kbd("Space"), " play/pause \u00b7 ", tags$kbd("\u2190"), tags$kbd("\u2192"), " seek \u00b7 ", tags$kbd("C"), " captions \u00b7 click a thumbnail to jump"))
  })
}

player_ui <- function(rv, ctx) {
  if (is.null(rv$dir)) return(NULL)
  ok <- file.exists(file.path(rv$dir, "preview.html"))
  asp <- rv$tl$W %||% 1920; ash <- rv$tl$H %||% 1080
  if (!ok) return(div(class = "player", div(class = "ph", div(dr_icon("play", 30), tags$p(class = "muted", style = "margin-top:8px", "The live preview appears once there is a storyboard.")))))
  h <- if (ash > asp) "min(78vh, 900px)" else sprintf("calc((min(100%%, 1000px)) * %f + 56px)", ash / asp)
  div(class = "player", tags$iframe(class = "dr-player", src = ctx$url("preview.html", shiny::isolate(rv$tl_v)), style = sprintf("height:%s;aspect-ratio:%s", if (ash > asp) "78vh" else "auto", sprintf("%d / %d", asp, ash + round(56 * asp / 900))), allow = "autoplay; fullscreen"))
}
