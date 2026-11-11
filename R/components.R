# UI components -----------------------------------------------------------------------------
# `tags` comes from htmltools; small builders keep the page code readable.

tags <- htmltools::tags
div <- htmltools::div
HTML <- htmltools::HTML

dr_card <- function(title = NULL, ..., icon = NULL, actions = NULL, class = NULL, id = NULL, body_class = NULL) {
  div(class = paste("card", class), id = id,
      if (!is.null(title)) div(class = "hd", if (!is.null(icon)) div(class = "ico", dr_icon(icon, 16)), tags$h3(title), div(class = "grow"), actions),
      div(class = paste("bd", body_class), ...))
}

dr_field <- function(label, input, help = NULL, class = NULL) {
  div(class = paste("fld", class), if (!is.null(label)) tags$label(label), input, if (!is.null(help)) div(class = "help", help))
}

dr_btn <- function(id = NULL, label = NULL, icon = NULL, class = "", onclick = NULL, title = NULL, disabled = FALSE, ...) {
  cls <- paste("dr-btn", class, if (!is.null(id)) "action-button")
  tags$button(id = id, type = "button", class = cls, onclick = onclick, title = title, disabled = if (disabled) NA else NULL,
              if (!is.null(icon)) dr_icon(icon, if (grepl("\\b(sm|xs)\\b", class)) 15 else 17), if (!is.null(label)) tags$span(label), ...)
}

#' Choice cards / segmented control (a custom Shiny input)
#' @param id Input id.
#' @param choices A list of lists with `value`, `label` and optionally `sub`, `icon`, `vis` (HTML), `disabled`.
#' @param selected Selected value.
#' @param style `"cards"` or `"seg"`.
#' @param min Minimum card width (CSS).
#' @keywords internal
dr_choices <- function(id, choices, selected = NULL, style = "cards", min = "150px", class = NULL) {
  items <- lapply(choices, function(ch) {
    act <- identical(as.character(ch$value), as.character(selected))
    tags$button(type = "button", class = paste(if (act) "active", ch$class), `data-value` = ch$value, title = ch$title, disabled = if (isTRUE(ch$disabled)) NA else NULL,
                if (style == "cards" && !is.null(ch$vis)) div(class = "vis", ch$vis),
                if (style == "seg" && !is.null(ch$icon)) dr_icon(ch$icon, 15),
                if (style == "cards") div(class = "hrow nowrap", style = "gap:8px", if (!is.null(ch$icon)) dr_icon(ch$icon, 16), div(class = "t", ch$label)) else ch$label,
                if (style == "cards" && !is.null(ch$sub)) div(class = "s", ch$sub))
  })
  div(id = id, class = paste("dr-choices", style, class), `data-value` = selected %||% "", style = if (style == "cards") sprintf("--min:%s", min), items)
}

dr_color <- function(id, value = "#6366f1") {
  tags$input(id = id, type = "color", class = "dr-color", value = value %||% "#6366f1")
}

dr_switch <- function(id, label, value = FALSE) {
  div(class = "form-check form-switch",
      tags$input(id = id, class = "form-check-input dr-switch", type = "checkbox", role = "switch", checked = if (isTRUE(value)) NA else NULL),
      tags$label(class = "form-check-label", `for` = id, label))
}

dr_select <- function(id, label, choices, selected = NULL, help = NULL) {
  dr_field(label, shiny::selectInput(id, NULL, choices, selected = selected, selectize = FALSE), help)
}

dr_text <- function(id, label, value = "", placeholder = NULL, help = NULL) {
  dr_field(label, shiny::textInput(id, NULL, value, placeholder = placeholder), help)
}

dr_chip <- function(text, class = "", icon = NULL) htmltools::span(class = paste("chip", class), if (!is.null(icon)) dr_icon(icon, 13), text)

dr_empty <- function(icon, title, text = NULL, ...) {
  div(class = "empty", div(class = "ico", dr_icon(icon, 22)), tags$b(title), if (!is.null(text)) div(class = "muted", style = "max-width:460px", text), ...)
}

dr_note <- function(..., class = "", icon = "info") div(class = paste("note", class), dr_icon(icon, 17), div(...))

# tiny visuals for choice cards ---------------------------------------------------------------

vis_template <- function(kind) {
  win <- function(l, t, w, h) sprintf("<div class='win' style='left:%s%%;top:%s%%;width:%s%%;height:%s%%'></div>", l, t, w, h)
  bar <- function(l, t, w) sprintf("<div class='bar' style='left:%s%%;top:%s%%;width:%s%%'></div>", l, t, w)
  HTML(switch(kind,
    launch = paste0(bar(30, 14, 40), win(22, 30, 56, 58)),
    teaser = paste0("<div style='position:absolute;inset:0;display:grid;place-items:center;font:800 22px Inter;letter-spacing:-.04em;color:#fff'>BOOM.</div>"),
    tour = paste0("<div style='position:absolute;left:12%;top:14%;width:14px;height:14px;border-radius:50%;background:linear-gradient(135deg,#6366f1,#a855f7)'></div>", bar(26, 17, 34), win(12, 38, 76, 52)),
    social = paste0(win(36, 8, 28, 84)),
    demo = paste0(win(14, 16, 72, 68)),
    ""))
}
