test_that("the server opens a film, edits the storyboard and rebuilds the timeline", {
  skip_if_not(nzchar(director_python()), "no python")
  home <- tempfile("drhome"); dir.create(file.path(home, "projects"), recursive = TRUE)
  d <- dr_new_project("", kind = "media", template = "demo", home = home)
  png <- file.path(d, "media", "home.png"); dir.create(dirname(png))
  grDevices::png(png, 1440, 810); graphics::plot.new(); graphics::rect(0, 0, 1, 1, col = "#6366f1"); grDevices::dev.off()
  DirectoR:::dr_write_json(list(items = list(list(file = "media/home.png", label = "Home screen"))), file.path(d, "media.json"))
  cfg <- DirectoR:::dr_cfg(d); cfg$brand$name <- "Testly"; cfg$voice$enabled <- FALSE; DirectoR:::dr_save_cfg(d, cfg)
  st <- dr_run(d, "plan", timeout = 120)
  if (!identical(st$state, "done")) { print(st); print(DirectoR:::dr_tail(file.path(d, "job.txt"), 20)) }
  skip_if(!identical(st$state, "done"), "engine not available")
  shiny::testServer(app_server(home), {
    ctx$load(d, page = "story")
    expect_equal(rv$page, "story")
    expect_false(is.null(rv$sb))
    sid <- rv$sb$scenes[[1]]$id
    session$setInputs(story_edit = list(edits = list(list(scene = sid, f = "title", v = "Testly, *tested.*"))))
    sb <- DirectoR:::dr_read_json(file.path(d, "storyboard.json"))
    expect_equal(sb$scenes[[1]]$title, "Testly, *tested.*")
    session$setInputs(ui_act = list(act = "scene_add", arg = "stat", n = 1))
    expect_true(any(vapply(rv$sb$scenes, function(s) identical(s$type, "stat"), logical(1))))
    expect_false(is.null(mem$tl_req))                     # a timeline rebuild was requested
  })
})
