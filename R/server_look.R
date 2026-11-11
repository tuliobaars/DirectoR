# Look and Export pages ----------------------------------------------------------------------

srv_look <- function(input, output, session, rv, ctx) {
  for (k in c("theme", "background", "font", "window", "transition", "captions", "cursor")) local({
    key <- k
    dr_on(input[[paste0("look_", key)]], { if (!is.null(rv$dir)) ctx$set(c("look", key), input[[paste0("look_", key)]], rebuild = key != "cursor") }, ignoreInit = TRUE)
  })
  dr_on(input$look_aspect, { if (!is.null(rv$dir)) ctx$set(c("format", "aspect"), input$look_aspect, rebuild = TRUE) }, ignoreInit = TRUE)
  dr_on(input$look_radius, { if (!is.null(rv$dir)) ctx$set(c("look", "radius"), input$look_radius, rebuild = TRUE) }, ignoreInit = TRUE)
  dr_on(input$look_grain, { if (!is.null(rv$dir)) ctx$set(c("look", "grain"), isTRUE(input$look_grain), rebuild = TRUE) }, ignoreInit = TRUE)
  output$look_player <- shiny::renderUI({
    rv$player_key
    htmltools::tagList(shiny::isolate(player_ui(rv, ctx)),
                       dr_note(icon = "info", "Cursor style applies to footage recorded after the change. Captions show in the preview with the CC button (or press C)."))
  })
}

srv_export <- function(input, output, session, rv, ctx) {
  dr_on(input$export_go, start_render(rv, ctx, input))
  output$export_renders <- shiny::renderUI({
    man <- rv$man
    if (is.null(rv$dir)) return(NULL)
    rs <- rev(man$renders %||% list())
    if (!length(rs)) return(dr_card(NULL, dr_empty("film", "No renders yet", "Render a draft to check the cut, then the final film.")))
    div(class = "renders", lapply(seq_along(rs), function(i) {
      r <- rs[[i]]; f <- r$files
      v <- as.integer(as.POSIXct(gsub("T", " ", r$created %||% ""), tz = "") %||% 0)
      link <- function(key, label, icon) if (!is.null(f[[key]]) && file.exists(file.path(rv$dir, f[[key]])))
        tags$a(class = "dr-btn xs", href = ctx$url(f[[key]]), download = basename(f[[key]]), target = "_blank", dr_icon(icon, 13), label)
      div(class = "render-card",
          tags$video(controls = NA, playsinline = NA, preload = if (i == 1) "metadata" else "none", poster = if (!is.null(f$poster)) ctx$url(f$poster, v), src = ctx$media(f$video, v),
                     style = if (isTRUE(r$size[[2]] > r$size[[1]])) "max-height:70vh;margin:0 auto" else NULL),
          div(class = "rb",
              div(div(class = "nm", r$name), div(class = "dim", style = "font-size:12px", sprintf("%s \u00b7 %.1fs \u00b7 %d\u00d7%d \u00b7 %s \u00b7 %s", tools::toTitleCase(r$quality %||% ""), r$duration %||% 0,
                                                                                            as.integer(r$size[[1]]), as.integer(r$size[[2]]), dr_fmt_bytes(r$bytes), sub("T", " ", r$created %||% "")))),
              div(style = "flex:1"),
              div(class = "dl", link("video", "MP4", "download"), link("captions", "With captions", "type"), link("srt", "SRT", "type"),
                  link("poster", "Poster", "image"), link("script", "Script", "story"))))
    }))
  })
  output$export_checks <- shiny::renderUI({
    rv$tl_v; sb <- rv$sb
    if (is.null(sb)) return(dr_note(class = "warn", icon = "alert", "There is no storyboard yet."))
    st <- rv$tl$shot_status
    miss <- Filter(function(s) if (!is.null(st)) !identical(st[[s$id]], "ok") else !file.exists(file.path(rv$dir, "shots", s$id, "meta.json")), sb$shots)
    notes <- list()
    if (length(miss)) notes <- c(notes, list(dr_note(class = "warn", icon = "shots", sprintf("%d shot%s not recorded: the film will show screenshots there. ", length(miss), if (length(miss) == 1) " is" else "s are"),
                                                      tags$a(href = "#", `data-nav` = "shots", "Record"))))
    vo_lines <- sum(vapply(sb$scenes, function(s) !isFALSE(s$enabled) && nzchar(trimws(s$vo %||% "")), logical(1)))
    if (vo_lines && isTRUE(rv$cfg$voice$enabled %||% TRUE)) {
      if (is.null(rv$clips)) notes <- c(notes, list(dr_note(class = "warn", icon = "mic", "The script has voice-over lines but no voice yet. ", tags$a(href = "#", `data-nav` = "sound", "Generate it"), " or the film will be music-only.")))
      else if (length(rv$tl$vo_stale) || length(rv$tl$vo_missing)) notes <- c(notes, list(dr_note(class = "warn", icon = "mic",
        sprintf("%d voice-over line%s changed since the voice was made; %s silent until you ", length(unique(c(unlist(rv$tl$vo_stale), unlist(rv$tl$vo_missing)))),
                if (length(unique(c(unlist(rv$tl$vo_stale), unlist(rv$tl$vo_missing)))) == 1) "" else "s", "those scenes stay"), tags$a(href = "#", `data-nav` = "sound", "regenerate it"), ".")))
    }
    if (!file.exists(file.path(rv$dir, "audio", "music.wav"))) notes <- c(notes, list(dr_note(icon = "sound", "The score will be composed automatically before rendering.")))
    if (!is.null(rv$tl$duration) && rv$tl$duration > 60) notes <- c(notes, list(dr_note(class = "warn", icon = "clock", sprintf("The cut is %.1fs, over the 60 s target. Shorten lines or skip a scene.", rv$tl$duration))))
    if (!length(notes)) notes <- list(dr_note(class = "good", icon = "check", "Ready to render."))
    div(class = "stack", style = "gap:8px", notes)
  })
  output$export_more <- shiny::renderUI({
    cur <- rv$cfg$film$template %||% "launch"
    others <- Filter(function(t) !identical(t$value, cur), TEMPLATES)
    div(class = "stack", style = "gap:10px",
        div(class = "dim", style = "font-size:12.5px", "A sibling film in another format: it reuses the brand, the voice and every shot that still fits, then writes, scores and cuts on its own."),
        div(class = "hrow", lapply(others, function(t) tags$button(class = "dr-btn sm", `data-act` = "sibling", `data-arg` = t$value, dr_icon("sparkles", 14), t$label))))
  })
  output$export_facts <- shiny::renderUI({
    tl <- rv$tl; cfg <- rv$cfg; cl <- rv$clips
    if (is.null(tl)) return(div(class = "dim", "Build the storyboard to see the facts."))
    mood <- cfg$music$mood %||% "auto"
    div(class = "kv",
        div(class = "k", "Length"), div(sprintf("%.1f s", tl$duration)),
        div(class = "k", "Format"), div(sprintf("%s \u00b7 %d\u00d7%d \u00b7 %d fps", cfg$format$aspect %||% "16:9", tl$W, tl$H, as.integer(tl$fps %||% 60))),
        div(class = "k", "Scenes"), div(length(tl$scenes)),
        div(class = "k", "Voice"), div(cl$voice %||% "none"),
        div(class = "k", "Music"), div(sprintf("%s \u00b7 %d BPM", tools::toTitleCase(mood), as.integer(tl$bpm %||% 0))),
        div(class = "k", "Captions"), div(tools::toTitleCase(cfg$look$captions %||% "clean")),
        div(class = "k", "Loudness"), div(if (length(tl$vo)) "\u221216 LUFS (speech)" else "\u221214 LUFS (music)"),
        div(class = "k", "Folder"), div(class = "mono", style = "word-break:break-all;font-size:11.5px", rv$dir))
  })
}
