# Configuration: where projects live, which Python runs the engine ----------------------

#' DirectoR home folder
#'
#' Projects are stored in `<home>/projects`. Set with `options(director.home = ...)`,
#' the `DIRECTOR_HOME` environment variable, or `run_app(home = ...)`.
#' @return A path.
#' @export
director_home <- function() {
  h <- getOption("director.home") %||% Sys.getenv("DIRECTOR_HOME", "")
  if (!nzchar(h)) h <- tools::R_user_dir("DirectoR", "data")
  dir.create(file.path(h, "projects"), showWarnings = FALSE, recursive = TRUE)
  normalizePath(h, mustWork = FALSE)
}

#' Folder of the bundled Python engine
#' @return A path.
#' @export
director_engine <- function() {
  p <- system.file("engine", package = "DirectoR")
  if (!nzchar(p)) p <- file.path(getwd(), "inst", "engine")
  normalizePath(p, mustWork = FALSE)
}

#' Python interpreter used by the engine
#'
#' Uses, in order: `options(director.python)`, the `DIRECTOR_PYTHON` environment variable, the Python
#' chosen in the app's Engine check (saved in `<home>/director.json`), then the first Python found that
#' can import the engine's packages. Besides `PATH`, the usual install locations are searched
#' (Homebrew, python.org, pyenv, conda/miniforge, reticulate), because R started from RStudio or
#' R.app on macOS gets a minimal `PATH` that doesn't include them.
#' @param refresh Search again instead of using the cached result.
#' @return A path (empty string when none is found).
#' @export
director_python <- function(refresh = FALSE) {
  p <- getOption("director.python") %||% Sys.getenv("DIRECTOR_PYTHON", "")
  if (nzchar(p)) return(path.expand(p))
  saved <- dr_settings()$python %||% ""
  if (nzchar(saved) && file.exists(saved)) return(saved)
  if (!refresh && !is.null(.dr_state$python)) return(.dr_state$python)
  cands <- dr_python_candidates()
  best <- ""
  for (c in cands) if (isTRUE(dr_python_probe(c)$ok)) { best <- c; break }
  if (!nzchar(best) && length(cands)) best <- cands[[1]]
  .dr_state$python <- best
  best
}

.dr_state <- new.env(parent = emptyenv())

# every python3 we can find, in a sensible order (no duplicates)
dr_python_candidates <- function() {
  home <- path.expand("~")
  win <- .Platform$OS.type == "windows"
  exe <- if (win) "python.exe" else "python3"
  onpath <- unname(c(Sys.which("python3"), Sys.which("python")))
  globs <- if (win) c(file.path(Sys.getenv("LOCALAPPDATA"), "Programs", "Python", "Python3*", "python.exe"),
                       file.path(home, c("miniconda3", "anaconda3", "miniforge3"), "python.exe"))
           else c("/opt/homebrew/bin/python3", "/opt/homebrew/bin/python3.1[0-9]", "/usr/local/bin/python3", "/usr/local/bin/python3.1[0-9]",
                  "/Library/Frameworks/Python.framework/Versions/Current/bin/python3", "/Library/Frameworks/Python.framework/Versions/3.*/bin/python3",
                  file.path(home, ".pyenv", "shims", "python3"),
                  file.path(Sys.getenv("CONDA_PREFIX"), "bin", "python3"),
                  file.path(home, c("miniforge3", "mambaforge", "miniconda3", "anaconda3", "opt/anaconda3", "opt/miniconda3"), "bin", "python3"),
                  file.path(c("/opt/anaconda3", "/opt/miniconda3", "/opt/homebrew/Caskroom/miniforge/base"), "bin", "python3"),
                  file.path(home, ".virtualenvs", "*", "bin", "python3"),
                  file.path(home, "Library", "r-miniconda", "bin", "python3"), file.path(home, ".local", "share", "r-miniconda", "bin", "python3"),
                  file.path(home, ".local", "bin", "python3"), "/usr/bin/python3")
  found <- c(onpath, Sys.glob(globs))
  found <- found[nzchar(found) & file.exists(found)]
  # compare literal paths: a virtualenv's python is a symlink to its base interpreter but has its own packages
  found <- path.expand(found)
  unique(found)
}

# can this python run the engine? -> list(ok, version, missing)
dr_python_probe <- function(py) {
  key <- paste0("probe:", py)
  if (!is.null(.dr_state[[key]])) return(.dr_state[[key]])
  code <- paste("import sys, importlib", "miss = []",
                "for m in ('numpy', 'scipy', 'PIL', 'playwright'):",
                "    try: importlib.import_module(m)",
                "    except Exception: miss.append(m)",
                "print(sys.version.split()[0] + '|' + ','.join(miss))", sep = "\n")
  r <- tryCatch(processx::run(py, c("-c", code), error_on_status = FALSE, timeout = 20), error = function(e) list(status = 1, stdout = "", stderr = conditionMessage(e)))
  out <- strsplit(trimws(r$stdout %||% ""), "|", fixed = TRUE)[[1]]
  res <- if (identical(r$status, 0L) && length(out) >= 1) {
    miss <- if (length(out) > 1 && nzchar(out[2])) strsplit(out[2], ",")[[1]] else character()
    ver_ok <- utils::compareVersion(out[1], "3.9") >= 0
    list(ok = !length(miss) && ver_ok, version = out[1], missing = miss, old = !ver_ok)
  } else list(ok = FALSE, version = "", missing = "python does not run", old = FALSE)
  .dr_state[[key]] <- res
  res
}

# small persistent settings (the chosen python)
dr_settings <- function(home = getOption("director.home") %||% Sys.getenv("DIRECTOR_HOME", "")) {
  if (!nzchar(home)) home <- tools::R_user_dir("DirectoR", "data")
  dr_read_json(file.path(home, "director.json"), list())
}

dr_save_python <- function(py, home = director_home()) {
  s <- dr_read_json(file.path(home, "director.json"), list()); s$python <- py
  dr_write_json(s, file.path(home, "director.json"))
  .dr_state$python <- py
  options(director.python = NULL)
  invisible(py)
}

dr_engine_env <- function(extra = NULL, python = director_python()) {
  env <- c("current", PYTHONPATH = director_engine(), PYTHONUNBUFFERED = "1", PYTHONIOENCODING = "utf-8")
  # R started from a GUI (RStudio, R.app) has a minimal PATH: add the usual tool folders so the engine
  # finds Homebrew's ffmpeg, git, node, quarto... and the python's own folder (pip-installed tools)
  if (.Platform$OS.type != "windows") {
    extra_path <- c(if (nzchar(python)) dirname(python), "/opt/homebrew/bin", "/usr/local/bin", "/opt/local/bin", "/usr/bin", "/bin", "/usr/sbin", "/sbin")
    path <- unique(c(extra_path[dir.exists(extra_path)], strsplit(Sys.getenv("PATH"), ":", fixed = TRUE)[[1]]))
    env <- c(env, PATH = paste(path[nzchar(path)], collapse = ":"))
  }
  rs <- file.path(R.home("bin"), "Rscript")
  if (file.exists(rs) && !nzchar(Sys.getenv("DIRECTOR_RSCRIPT"))) env <- c(env, DIRECTOR_RSCRIPT = rs)
  if (length(extra)) env <- c(env, extra)
  env
}

#' Check the engine's requirements
#'
#' Runs `python -m director doctor` and returns what it found: Python packages,
#' Chromium, ffmpeg (H.264, libass), git, Rscript and the available voices.
#' @param python Python interpreter.
#' @return A list with `ok`, `problems`, `notes`, `voices`, ...
#' @export
director_doctor <- function(python = director_python()) {
  if (!nzchar(python)) {
    return(list(ok = FALSE, problems = list(list(what = "Python 3", fix = "Install Python 3.9+ and set DIRECTOR_PYTHON")), notes = list(), voices = list()))
  }
  res <- tryCatch(
    processx::run(python, c("-m", "director", "doctor", "--json"), wd = director_engine(), env = dr_engine_env(python = python),
                  error_on_status = FALSE, timeout = 90),
    error = function(e) list(status = 1, stdout = "", stderr = conditionMessage(e)))
  out <- tryCatch(jsonlite::fromJSON(res$stdout, simplifyVector = FALSE), error = function(e) NULL)
  if (is.null(out)) {
    err <- trimws(strsplit(res$stderr %||% "", "\n")[[1]]); err <- err[nzchar(err)]
    return(list(ok = FALSE, failed = TRUE, python = python, error = paste(utils::tail(err, 2), collapse = "\n"),
                problems = list(list(what = sprintf("Python packages for the engine in %s", python),
                                     fix = sprintf("%s -m pip install -r \"%s\" && %s -m playwright install chromium", shQuote(python), file.path(director_engine(), "requirements.txt"), shQuote(python)),
                                     detail = paste(utils::tail(err, 2), collapse = "\n"))), notes = list(), voices = list()))
  }
  out$python <- python
  out
}
