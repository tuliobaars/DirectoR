# Small helpers ---------------------------------------------------------------------------

`%||%` <- function(a, b) {
  if (is.null(a) || length(a) == 0) return(b)
  if (is.atomic(a) && length(a) == 1 && (is.na(a) || (is.character(a) && !nzchar(a)))) return(b)
  a
}

#' Read a JSON file (lists are kept as lists)
#' @param path File path.
#' @param default Returned when the file is missing or invalid.
#' @return A list (or `default`).
#' @keywords internal
dr_read_json <- function(path, default = NULL) {
  if (!file.exists(path)) return(default)
  tryCatch(jsonlite::read_json(path, simplifyVector = FALSE), error = function(e) default)
}

#' Write a JSON file atomically
#' @param x Object to write.
#' @param path File path.
#' @return `path`, invisibly.
#' @keywords internal
dr_write_json <- function(x, path) {
  dir.create(dirname(path), showWarnings = FALSE, recursive = TRUE)
  tmp <- tempfile(tmpdir = dirname(path), pattern = ".tmp-", fileext = ".json")
  txt <- jsonlite::toJSON(x, auto_unbox = TRUE, pretty = TRUE, null = "null", na = "null", digits = NA)
  writeLines(txt, tmp, useBytes = TRUE)
  if (!file.rename(tmp, path)) { file.copy(tmp, path, overwrite = TRUE); unlink(tmp) }
  invisible(path)
}

# recursive merge of named lists (over wins; unnamed lists are replaced)
dr_merge <- function(base, over) {
  if (!is.list(base) || !is.list(over) || is.null(names(over))) return(over)
  for (k in names(over)) {
    if (is.list(over[[k]]) && !is.null(names(over[[k]])) && is.list(base[[k]]) && !is.null(names(base[[k]]))) {
      base[[k]] <- dr_merge(base[[k]], over[[k]])
    } else {
      base[k] <- list(over[[k]])
    }
  }
  base
}

# set a value deep inside a nested list: dr_set(cfg, c("look", "theme"), "dark")
dr_set <- function(x, path, value) {
  if (length(path) == 1) { x[path] <- list(value); return(x) }
  sub <- x[[path[1]]]
  if (!is.list(sub)) sub <- list()
  x[[path[1]]] <- dr_set(sub, path[-1], value)
  x
}

dr_get <- function(x, path, default = NULL) {
  for (p in path) {
    if (!is.list(x) || is.null(x[[p]])) return(default)
    x <- x[[p]]
  }
  x
}

dr_slug <- function(x) {
  x <- tolower(gsub("[^A-Za-z0-9]+", "-", x %||% "film"))
  x <- gsub("^-+|-+$", "", x)
  if (!nzchar(x)) x <- "film"
  substr(x, 1, 40)
}

dr_now <- function() format(Sys.time(), "%Y-%m-%dT%H:%M:%S")

dr_fmt_secs <- function(s) {
  if (is.null(s) || is.na(s)) return("")
  s <- as.numeric(s)
  if (s < 60) return(sprintf("%.0fs", s))
  sprintf("%dm %02ds", as.integer(s %/% 60), as.integer(round(s %% 60)))
}

dr_fmt_bytes <- function(b) {
  if (is.null(b) || is.na(b)) return("")
  b <- as.numeric(b)
  if (b < 1024^2) return(sprintf("%.0f KB", b / 1024))
  sprintf("%.1f MB", b / 1024^2)
}

dr_html_escape <- function(x) htmltools::htmlEscape(x %||% "")

# "*x* _y_" markup -> HTML spans (same markup as the films)
dr_markup <- function(x) {
  x <- dr_html_escape(x)
  x <- gsub("\\*([^*]+)\\*", "<span class='grad'>\\1</span>", x)
  x <- gsub("(^|\\s)_([^_]+)_", "\\1<span class='muted'>\\2</span>", x)
  x <- gsub("~([^~]+)~", "<span class='warm'>\\1</span>", x)
  gsub("\\s*\\|\\s*", "<br>", x)
}

# Error-guarded observers ---------------------------------------------------------------
# An uncaught error in a Shiny observer ends the session ("Disconnected from the server").
# dr_on()/dr_obs() are observeEvent()/observe() that report the error as a toast and keep going.

dr_report_error <- function(e, session = NULL, where = "") {
  msg <- conditionMessage(e)
  message(sprintf("[DirectoR] error in %s: %s", where, msg))
  if (!is.null(session)) try(session$sendCustomMessage("dr-toast", list(type = "bad", title = "Something went wrong",
                                                                          text = paste0(msg, if (nzchar(where)) paste0("\n(", where, ")")), life = 10000)), silent = TRUE)
  invisible(NULL)
}

# the handler wrapped in tryCatch. Only plain code (symbols, calls, constants) may go in here:
# RStudio's Shiny debug hook walks observer code and fails on embedded objects such as functions.
dr_guard_expr <- function(h, where) {
  # the reporter is looked up by name in DirectoR's namespace: works wherever the observer lives
  bquote(tryCatch(.(h), error = function(e) get("dr_report_error", envir = asNamespace("DirectoR"))(e, if (exists("session", inherits = TRUE)) session else NULL, .(as.character(where)))))
}

dr_on <- function(eventExpr, handlerExpr, ..., ignoreInit = FALSE, ignoreNULL = TRUE) {
  ev <- substitute(eventExpr); h <- substitute(handlerExpr); env <- parent.frame()
  where <- paste(deparse(ev, width.cutoff = 60L)[1], collapse = "")
  shiny::observeEvent(ev, dr_guard_expr(h, where), event.quoted = TRUE, handler.quoted = TRUE, event.env = env, handler.env = env,
                      ignoreInit = ignoreInit, ignoreNULL = ignoreNULL, ...)
}

dr_obs <- function(x, ...) {
  h <- substitute(x); env <- parent.frame()
  shiny::observe(dr_guard_expr(h, "background task"), quoted = TRUE, env = env, ...)
}
