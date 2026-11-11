# Entry points ------------------------------------------------------------------------------

dr_register_assets <- function(home = director_home()) {
  www <- system.file("app", "www", package = "DirectoR")
  if (!nzchar(www)) www <- file.path(getwd(), "inst", "app", "www")
  shiny::addResourcePath("dr-www", www)
  # Inter (SIL OFL) ships base64-encoded with the engine; decode it once for the UI
  fdir <- file.path(tempdir(), "dr-font")
  if (!file.exists(file.path(fdir, "inter.woff2"))) {
    dir.create(fdir, showWarnings = FALSE)
    b64 <- file.path(director_engine(), "stage", "inter.woff2.b64")
    if (file.exists(b64)) writeBin(jsonlite::base64_dec(paste(readLines(b64, warn = FALSE), collapse = "")), file.path(fdir, "inter.woff2"))
  }
  shiny::addResourcePath("dr-font", fdir)
  shiny::addResourcePath("drp", dr_projects_dir(home))
  cache <- file.path(home, "cache", "demos"); dir.create(cache, recursive = TRUE, showWarnings = FALSE)
  shiny::addResourcePath("dr-cache", cache)
  invisible(TRUE)
}

#' The DirectoR Shiny app object
#'
#' Use in an `app.R` for deployment: `DirectoR::director_app()`.
#' @param home Folder where projects are stored (see [director_home()]).
#' @param python Python interpreter for the engine (see [director_python()]).
#' @param ... Passed to [shiny::shinyApp()].
#' @return A `shiny.appobj`.
#' @export
director_app <- function(home = director_home(), python = director_python(), ...) {
  options(director.home = home, director.python = python)
  # repositories, screen recordings and music files are big; Shiny's default upload limit is 5 MB
  if (is.null(getOption("shiny.maxRequestSize")) || getOption("shiny.maxRequestSize") < 4 * 1024^3) options(shiny.maxRequestSize = 4 * 1024^3)
  home <- director_home()
  dr_register_assets(home)
  roots <- dr_media_roots(home)
  # one request handler: the studio at "/", media with byte ranges under /drm/ (see media.R), 404 otherwise
  router <- function(req) {
    path <- req$PATH_INFO %||% "/"
    if (startsWith(path, "/drm/")) return(tryCatch(dr_serve_media(req, roots), error = function(e) shiny::httpResponse(500L, "text/plain", conditionMessage(e))))
    if (path %in% c("/", "", "/index.html")) return(app_ui(req))
    NULL
  }
  shiny::shinyApp(ui = router, server = app_server(home), uiPattern = ".*", ...)
}

#' Run DirectoR
#'
#' Opens the studio: paste a link to a website, a Shiny app or a Git repository
#' (or drop a zip) and DirectoR directs a launch or teaser film for it.
#' @inheritParams director_app
#' @param port,launch.browser,host Passed to [shiny::runApp()].
#' @return Called for its side effect.
#' @examples
#' \dontrun{
#' DirectoR::run_app()
#' }
#' @export
run_app <- function(home = director_home(), python = director_python(), port = getOption("shiny.port"), launch.browser = interactive(), host = "127.0.0.1") {
  app <- director_app(home = home, python = python)
  shiny::runApp(app, port = port, launch.browser = launch.browser, host = host)
}
