test_that("an error in an observer is reported and the session survives", {
  msgs <- list()
  srv <- function(input, output, session) {
    n <- shiny::reactiveVal(0)
    DirectoR:::dr_on(input$boom, stop("kaboom"))
    DirectoR:::dr_on(input$ok, n(n() + 1))
    output$n <- shiny::renderText(n())
  }
  shiny::testServer(srv, {
    session$setInputs(boom = 1)                # would end a normal Shiny session
    session$setInputs(ok = 1); session$setInputs(ok = 2)
    expect_equal(output$n, "2")
  })
})

test_that("media are served with byte ranges, and paths can't escape", {
  root <- tempfile("media"); dir.create(file.path(root, "a"), recursive = TRUE)
  f <- file.path(root, "a", "x.wav"); writeBin(as.raw(0:255), f)
  roots <- list(p = root, c = root, w = root)
  r <- DirectoR:::dr_serve_media(list(PATH_INFO = "/drm/p/a/x.wav", HTTP_RANGE = "bytes=10-19"), roots)
  expect_equal(r$status, 206L); expect_equal(r$content, as.raw(10:19))
  expect_equal(r$headers$`Content-Range`, "bytes 10-19/256")
  expect_equal(DirectoR:::dr_serve_media(list(PATH_INFO = "/drm/p/a/x.wav"), roots)$status, 200L)
  expect_equal(DirectoR:::dr_serve_media(list(PATH_INFO = "/drm/p/a/x.wav", HTTP_RANGE = "bytes=-6"), roots)$content, as.raw(250:255))
  expect_equal(DirectoR:::dr_serve_media(list(PATH_INFO = "/drm/p/a/x.wav", HTTP_RANGE = "bytes=999-"), roots)$status, 416L)
  expect_equal(DirectoR:::dr_serve_media(list(PATH_INFO = "/drm/p/../secret"), roots)$status, 403L)
  expect_equal(DirectoR:::dr_serve_media(list(PATH_INFO = "/drm/p/%2e%2e/secret"), roots)$status, 403L)
  expect_equal(DirectoR:::dr_serve_media(list(PATH_INFO = "/drm/p/a/nope.wav"), roots)$status, 404L)
  expect_null(DirectoR:::dr_serve_media(list(PATH_INFO = "/other"), roots))
})

test_that("an unreadable status file is 'unknown', never a finished job", {
  d <- tempfile("drproj"); dir.create(d)
  writeLines("{\"job\": \"capture\", \"sta", file.path(d, "status.json"))
  expect_equal(dr_job_status(d)$state, "unknown")
})

test_that("guarded observer code is plain code (RStudio's debug hook walks it)", {
  # mirrors .rs.findBreakpointSteps: every element must be a symbol, a call or a constant, never an object
  walk <- function(x) {
    if (is.function(x) || is.environment(x)) return(FALSE)
    if (is.pairlist(x)) return(all(vapply(as.list(x), function(a) if (identical(a, quote(expr = ))) TRUE else walk(a), logical(1))))
    if (is.list(x)) return(FALSE)
    if (is.call(x)) {
      head <- x[[1]]
      if (!(is.symbol(head) || is.call(head))) return(FALSE)
      ok <- tryCatch({ as.character(head); TRUE }, error = function(e) FALSE)
      return(ok && all(vapply(as.list(x)[-1], function(a) if (missing(a)) TRUE else walk(a), logical(1))))
    }
    TRUE
  }
  expr <- DirectoR:::dr_guard_expr(quote({ x <- input$a; if (is.null(x)) return(); ctx$set(c("look", "theme"), x) }), "input$a")
  expect_true(walk(expr))
  fn <- function() NULL; body(fn) <- expr            # what shiny turns it into
  expect_true(all(vapply(as.list(body(fn)), walk, logical(1))))
})
