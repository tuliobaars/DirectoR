# Projects: one folder per film -----------------------------------------------------------

dr_projects_dir <- function(home = director_home()) file.path(home, "projects")

#' List DirectoR projects
#' @param home DirectoR home folder.
#' @return A data frame (newest first).
#' @export
dr_projects <- function(home = director_home()) {
  dirs <- list.dirs(dr_projects_dir(home), recursive = FALSE, full.names = TRUE)
  dirs <- dirs[file.exists(file.path(dirs, "project.json"))]
  if (!length(dirs)) return(data.frame(dir = character(), name = character(), modified = as.POSIXct(character()), stringsAsFactors = FALSE))
  rows <- lapply(dirs, function(d) {
    cfg <- dr_read_json(file.path(d, "project.json"), list())
    man <- dr_read_json(file.path(d, "out", "manifest.json"), list())
    last <- if (length(man$renders)) man$renders[[length(man$renders)]] else NULL
    mt <- max(file.mtime(c(file.path(d, "project.json"), file.path(d, c("storyboard.json", "timeline.json", "status.json")))), na.rm = TRUE)
    thumb <- if (!is.null(last$files$thumb)) last$files$thumb else if (file.exists(file.path(d, "scout", "home.jpg"))) "scout/home.jpg" else ""
    data.frame(dir = d, slug = basename(d), name = cfg$name %||% basename(d), template = dr_get(cfg, c("film", "template"), "launch"),
               aspect = dr_get(cfg, c("format", "aspect"), "16:9"), source = dr_get(cfg, c("source", "value"), ""),
               kind = dr_get(cfg, c("source", "kind"), ""), thumb = thumb, duration = as.numeric(last$duration %||% NA),
               renders = length(man$renders), modified = mt, stringsAsFactors = FALSE)
  })
  out <- do.call(rbind, rows)
  out[order(out$modified, decreasing = TRUE), , drop = FALSE]
}

#' Create a project
#' @param source A URL, git repository, zip file or folder (or `""` for screenshots).
#' @param name Film name (defaults to one derived from the source).
#' @param kind Source kind: `"auto"`, `"url"`, `"git"`, `"zip"`, `"dir"` or `"media"`.
#' @param template Film template (`launch`, `teaser`, `tour`, `social`, `demo`).
#' @param home DirectoR home folder.
#' @return The project folder.
#' @export
dr_new_project <- function(source = "", name = NULL, kind = "auto", template = "launch", home = director_home()) {
  if (identical(kind, "auto")) kind <- dr_classify(source)
  name_auto <- is.null(name) || !nzchar(name)
  if (name_auto) name <- dr_guess_name(source, kind)
  base <- dr_slug(name); d <- file.path(dr_projects_dir(home), base); i <- 2
  while (dir.exists(d)) { d <- file.path(dr_projects_dir(home), paste0(base, "-", i)); i <- i + 1 }
  dir.create(d, recursive = TRUE)
  cfg <- list(name = name, name_auto = name_auto, created = dr_now(), source = list(kind = kind, value = source),
              film = list(template = template), format = list(aspect = if (identical(template, "social")) "9:16" else "16:9"))
  dr_write_json(cfg, file.path(d, "project.json"))
  normalizePath(d)
}

dr_classify <- function(x) {
  x <- trimws(x %||% "")
  if (!nzchar(x)) return("media")
  if (dir.exists(path.expand(x))) {
    bare <- file.exists(file.path(path.expand(x), "HEAD")) && dir.exists(file.path(path.expand(x), "objects"))
    return(if (bare) "git" else "dir")
  }
  if (grepl("\\.zip$", x, ignore.case = TRUE) && file.exists(path.expand(x))) return("zip")
  if (grepl("\\.git$", x) || grepl("^git@", x)) return("git")
  if (grepl("^https?://(www\\.)?(github\\.com|gitlab\\.com|bitbucket\\.org|codeberg\\.org)/[^/]+/[^/]+", x)) return("git")
  "url"
}

dr_guess_name <- function(source, kind) {
  s <- trimws(source %||% "")
  if (!nzchar(s)) return("New film")
  if (kind %in% c("git")) {
    m <- regmatches(s, regexec("^https?://[^/]+/[^/]+/([^/#?]+)", s))[[1]]
    if (length(m) > 1) return(sub("\\.git$", "", m[2]))
    return(sub("\\.git$", "", basename(s)))
  }
  if (kind %in% c("zip", "dir")) return(sub("\\.zip$", "", basename(s), ignore.case = TRUE))
  h <- sub("^https?://", "", s); h <- sub("/.*$", "", h); h <- sub("^www\\.", "", h)
  h <- sub(":.*$", "", h)
  if (h %in% c("localhost", "127.0.0.1")) return("My app")
  parts <- strsplit(h, ".", fixed = TRUE)[[1]]
  if (length(parts) >= 2 && parts[length(parts) - 1] %in% c("shinyapps", "github", "netlify", "vercel", "posit", "rstudio")) {
    m <- regmatches(s, regexec("^https?://[^/]+/([^/#?]+)", s))[[1]]
    if (length(m) > 1 && nzchar(m[2])) return(m[2])
    return(parts[1])
  }
  if (length(parts) >= 2) parts[length(parts) - 1] else h
}

dr_delete_project <- function(dir) {
  if (dir.exists(dir) && file.exists(file.path(dir, "project.json"))) unlink(dir, recursive = TRUE, force = TRUE)
}

dr_duplicate_project <- function(dir, home = director_home()) {
  cfg <- dr_read_json(file.path(dir, "project.json"), list())
  nm <- paste(cfg$name %||% basename(dir), "copy")
  d <- file.path(dr_projects_dir(home), dr_slug(nm)); i <- 2
  while (dir.exists(d)) { d <- file.path(dr_projects_dir(home), paste0(dr_slug(nm), "-", i)); i <- i + 1 }
  dir.create(d)
  keep <- c("project.json", "facts.json", "scout.json", "storyboard.json", "scout", "shots", "vo", "assets", "src")
  for (k in keep) {
    p <- file.path(dir, k)
    if (dir.exists(p)) file.copy(p, d, recursive = TRUE) else if (file.exists(p)) file.copy(p, d)
  }
  cfg$name <- nm; cfg$created <- dr_now()
  dr_write_json(cfg, file.path(d, "project.json"))
  normalizePath(d)
}

# project documents ---------------------------------------------------------------------

dr_defaults <- function() {
  list(name = "Untitled film", source = list(kind = "url", value = ""),
       app = list(command = "", cwd = "", path = "/", wait = 600, renv = "ignore"),
       brand = list(name = "", tagline = "", url = "", cta = "", colors = list(), logo = "", description = ""),
       film = list(template = "launch", duration = 45, tone = "confident", audience = "", language = "en"),
       format = list(aspect = "16:9", fps = 60, quality = "final"),
       look = list(theme = "auto", transition = "auto", window = "macos", font = "Inter", captions = "clean", cursor = "mac",
                   background = "aurora", radius = 22, grain = TRUE),
       capture = list(viewport = "desktop", scheme = "light", fps = 60, dpr = "auto", workers = 3, hide = "", dismiss_cookies = TRUE, lite = "auto"),
       voice = list(provider = "auto", voice = "", rate = 1, enabled = TRUE, lexicon = ""),
       music = list(mood = "auto", bpm = 0, key = "auto", file = "", volume = 0, duck = 10, sfx = TRUE, seed = 7, transpose = 0, offset = 0),
       llm = list(provider = "none", model = "", base_url = ""))
}

dr_cfg <- function(dir) dr_merge(dr_defaults(), dr_read_json(file.path(dir, "project.json"), list()))

dr_save_cfg <- function(dir, cfg) {
  cfg$modified <- dr_now()
  dr_write_json(cfg, file.path(dir, "project.json"))
}

dr_doc <- function(dir, name, default = NULL) dr_read_json(file.path(dir, paste0(name, ".json")), default)
