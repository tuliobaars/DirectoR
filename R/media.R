# Media route with HTTP Range support -------------------------------------------------------
# Safari only plays audio/video from servers that answer byte-range requests (206 Partial Content).
# Shiny's static file server doesn't, so media (previews, voice lines, mixes, films) are served here:
#   drm/p/<project>/<file>   project files
#   drm/c/<file>             generated previews (cache)
#   drm/w/<file>             files shipped with the app (www)

.dr_mime <- c(mp3 = "audio/mpeg", wav = "audio/wav", m4a = "audio/mp4", aac = "audio/aac", ogg = "audio/ogg", webm = "video/webm", opus = "audio/ogg",
              flac = "audio/flac", aiff = "audio/aiff", mp4 = "video/mp4", mov = "video/quicktime", srt = "text/plain; charset=utf-8",
              txt = "text/plain; charset=utf-8", jpg = "image/jpeg", jpeg = "image/jpeg", png = "image/png", json = "application/json")

dr_media_roots <- function(home) {
  www <- system.file("app", "www", package = "DirectoR")
  if (!nzchar(www)) www <- file.path(getwd(), "inst", "app", "www")
  list(p = dr_projects_dir(home), c = file.path(home, "cache", "demos"), w = www)
}

#' Serve one media request (internal)
#' @param req A Rook request.
#' @param roots Named list of folders.
#' @return A `shiny::httpResponse`, or `NULL` when the path is not a media path.
#' @keywords internal
dr_serve_media <- function(req, roots) {
  path <- req$PATH_INFO %||% ""
  m <- regmatches(path, regexec("^/drm/([pcw])/(.+)$", path))[[1]]
  if (length(m) != 3) return(NULL)
  root <- roots[[m[2]]]
  rel <- utils::URLdecode(m[3])
  if (grepl("(^|/)\\.\\.(/|$)", rel) || grepl("^/", rel)) return(shiny::httpResponse(403L, "text/plain", "forbidden"))
  f <- file.path(root, rel)
  rootn <- normalizePath(root, mustWork = FALSE); fn <- normalizePath(f, mustWork = FALSE)
  if (!file.exists(fn) || dir.exists(fn) || !startsWith(fn, rootn)) return(shiny::httpResponse(404L, "text/plain", "not found"))
  size <- file.size(fn)
  ct <- .dr_mime[[tolower(tools::file_ext(fn))]] %||% "application/octet-stream"
  head_only <- identical(toupper(req$REQUEST_METHOD %||% "GET"), "HEAD")
  hdr <- list(`Accept-Ranges` = "bytes", `Cache-Control` = "no-cache")
  read <- function(a, n) { if (head_only || n <= 0) return(raw(0)); con <- file(fn, "rb"); on.exit(close(con)); if (a > 0) seek(con, a); readBin(con, "raw", n) }
  rng <- req$HTTP_RANGE %||% ""
  r <- regmatches(rng, regexec("^bytes=(\\d*)-(\\d*)$", trimws(rng)))[[1]]
  if (length(r) == 3 && size > 0) {
    if (nzchar(r[2])) {
      a <- as.numeric(r[2])
      b <- if (nzchar(r[3])) min(as.numeric(r[3]), size - 1) else min(size - 1, a + 8 * 1024^2 - 1)   # open-ended: 8 MB at a time
    } else {                                                     # "bytes=-N": the last N bytes
      n <- as.numeric(r[3]); a <- max(0, size - n); b <- size - 1
    }
    if (is.na(a) || a >= size || b < a) {
      return(shiny::httpResponse(416L, ct, raw(0), headers = c(hdr, list(`Content-Range` = sprintf("bytes */%.0f", size)))))
    }
    return(shiny::httpResponse(206L, ct, read(a, b - a + 1),
                               headers = c(hdr, list(`Content-Range` = sprintf("bytes %.0f-%.0f/%.0f", a, b, size)))))
  }
  shiny::httpResponse(200L, ct, read(0, size), headers = hdr)
}

dr_media_url <- function(kind, rel, v = NULL) {
  paste0("drm/", kind, "/", paste(vapply(strsplit(rel, "/", fixed = TRUE)[[1]], utils::URLencode, "", reserved = TRUE), collapse = "/"),
         if (!is.null(v)) paste0("?v=", v) else "")
}
