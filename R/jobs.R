# Engine jobs: background processes with a status file ----------------------------------

.dr_jobs <- new.env(parent = emptyenv())

#' Run an engine step in the background
#'
#' Starts `python -m director <step> --project <dir>` with processx. Progress is
#' reported by the engine in `<dir>/status.json` (see [dr_job_status()]).
#' @param dir Project folder.
#' @param step One of `scout`, `plan`, `voice`, `capture`, `timeline`, `music`, `render`, `stills`, `auto`.
#' @param args Extra command-line arguments.
#' @param quiet Report to `status_quick.json` (small jobs that may run beside a long one).
#' @param env Extra environment variables (named character vector), e.g. API keys.
#' @param python Python interpreter.
#' @return The processx process, invisibly.
#' @export
dr_job_start <- function(dir, step, args = character(), quiet = FALSE, env = NULL, python = director_python()) {
  key <- paste0(normalizePath(dir), if (quiet) "#quick" else "")
  old <- .dr_jobs[[key]]
  if (!is.null(old) && old$is_alive()) {
    if (quiet) { try(old$kill_tree(), silent = TRUE) } else stop("Another job is still running for this film.", call. = FALSE)
  }
  if (!nzchar(python)) stop("No Python found. Set DIRECTOR_PYTHON.", call. = FALSE)
  # the initial status is written *before* the engine starts: a fast job may finish (and report) before we get back here
  sf <- file.path(dir, if (quiet) "status_quick.json" else "status.json")
  dr_write_json(list(job = step, state = "running", progress = 0, message = "Starting\u2026", started = dr_now(), updated = dr_now()), sf)
  out <- file.path(dir, if (quiet) "job_quick.txt" else "job.txt")
  env <- env[nzchar(env)]
  p <- tryCatch(processx::process$new(python, c("-u", "-m", "director", step, "--project", normalizePath(dir), args, if (quiet) "--quiet"),
                                      wd = director_engine(), env = dr_engine_env(env, python = python), stdout = out, stderr = "2>&1",
                                      cleanup_tree = TRUE, supervise = TRUE),
                error = function(e) {
                  dr_write_json(list(job = step, state = "error", message = "Could not start the engine", error = conditionMessage(e), started = dr_now()), sf)
                  stop(e)
                })
  .dr_jobs[[key]] <- p
  invisible(p)
}

#' Status of the current (or last) job of a project
#' @param dir Project folder.
#' @param quiet Status of the small side job instead.
#' @return A list: `job`, `state` (`running`, `done`, `error`, `idle`), `progress`, `message`, ...
#' @export
dr_job_status <- function(dir, quiet = FALSE) {
  if (is.null(dir)) return(list(state = "idle"))
  sf <- file.path(dir, if (quiet) "status_quick.json" else "status.json")
  if (!file.exists(sf)) return(list(state = "idle"))
  st <- dr_read_json(sf, NULL)
  if (is.null(st) || is.null(st$state)) return(list(state = "unknown"))     # being rewritten: ask again later
  key <- paste0(normalizePath(dir, mustWork = FALSE), if (quiet) "#quick" else "")
  p <- .dr_jobs[[key]]
  if (identical(st$state, "running")) {
    alive <- if (!is.null(p)) p$is_alive() else dr_pid_alive(st$pid)
    if (!isTRUE(alive)) {
      # the process is gone but never reported: crashed or killed
      tail <- dr_tail(file.path(dir, if (quiet) "job_quick.txt" else "job.txt"), 12)
      st$state <- "error"; st$message <- st$message %||% "The job stopped unexpectedly."
      st$error <- paste0("The engine stopped unexpectedly.\n", tail)
    }
  }
  st
}

dr_job_running <- function(dir) identical(dr_job_status(dir)$state, "running")

#' Cancel the running job of a project
#' @param dir Project folder.
#' @return `TRUE` if a job was cancelled.
#' @export
dr_job_cancel <- function(dir) {
  key <- normalizePath(dir, mustWork = FALSE)
  p <- .dr_jobs[[key]]
  done <- FALSE
  if (!is.null(p) && p$is_alive()) { try(p$kill_tree(), silent = TRUE); done <- TRUE }
  else {
    st <- dr_read_json(file.path(dir, "status.json"), list())
    if (identical(st$state, "running") && dr_pid_alive(st$pid)) { try(tools::pskill(st$pid), silent = TRUE); done <- TRUE }
  }
  st <- dr_read_json(file.path(dir, "status.json"), list())
  if (identical(st$state, "running")) {
    st$state <- "error"; st$message <- "Cancelled"; st$error <- "Cancelled"; st$cancelled <- TRUE
    dr_write_json(st, file.path(dir, "status.json"))
  }
  done
}

dr_pid_alive <- function(pid) {
  if (is.null(pid) || is.na(pid)) return(FALSE)
  if (requireNamespace("ps", quietly = TRUE)) return(isTRUE(tryCatch(as.integer(pid) %in% ps::ps_pids(), error = function(e) FALSE)))
  isTRUE(tryCatch(tools::pskill(as.integer(pid), 0), error = function(e) FALSE))
}

dr_tail <- function(path, n = 30) {
  if (!file.exists(path)) return("")
  x <- tryCatch(readLines(path, warn = FALSE, encoding = "UTF-8"), error = function(e) character())
  paste(utils::tail(x, n), collapse = "\n")
}

#' Run an engine step and wait for it (for scripts and tests)
#' @inheritParams dr_job_start
#' @param timeout Seconds.
#' @return The final status list.
#' @export
dr_run <- function(dir, step, args = character(), env = NULL, python = director_python(), timeout = 3600) {
  p <- dr_job_start(dir, step, args, env = env, python = python)
  p$wait(timeout * 1000)
  if (p$is_alive()) { p$kill_tree(); stop("timeout") }
  dr_job_status(dir)
}
