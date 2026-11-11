test_that("sources are classified and named", {
  expect_equal(DirectoR:::dr_classify("https://github.com/rstudio/shiny-examples"), "git")
  expect_equal(DirectoR:::dr_classify("https://my.shinyapps.io/app/"), "url")
  expect_equal(DirectoR:::dr_classify(tempdir()), "dir")
  expect_equal(DirectoR:::dr_classify(""), "media")
  expect_equal(DirectoR:::dr_guess_name("https://github.com/acme/orbit-dash.git", "git"), "orbit-dash")
  expect_equal(DirectoR:::dr_guess_name("https://acme.shinyapps.io/sales/", "url"), "sales")
  expect_equal(DirectoR:::dr_guess_name("https://www.example.com/x", "url"), "example")
  expect_equal(DirectoR:::dr_guess_name("~/zips/my-app.zip", "zip"), "my-app")
})

test_that("projects are created, listed, duplicated and deleted", {
  home <- tempfile("drhome"); dir.create(home)
  d <- dr_new_project("https://example.com", template = "social", home = home)
  expect_true(file.exists(file.path(d, "project.json")))
  cfg <- DirectoR:::dr_cfg(d)
  expect_equal(cfg$format$aspect, "9:16"); expect_equal(cfg$source$kind, "url"); expect_true(isTRUE(cfg$name_auto))
  expect_equal(cfg$look$theme, "auto")                      # defaults are merged in
  d2 <- dr_new_project("https://example.com", home = home)   # same name -> new folder
  expect_false(identical(d, d2))
  pr <- dr_projects(home)
  expect_equal(nrow(pr), 2)
  d3 <- DirectoR:::dr_duplicate_project(d, home)
  expect_match(DirectoR:::dr_cfg(d3)$name, "copy$")
  DirectoR:::dr_delete_project(d3)
  expect_equal(nrow(dr_projects(home)), 2)
})

test_that("job status detects processes that died without reporting", {
  d <- tempfile("drproj"); dir.create(d)
  DirectoR:::dr_write_json(list(job = "capture", state = "running", pid = 999999), file.path(d, "status.json"))
  st <- dr_job_status(d)
  expect_equal(st$state, "error")
  expect_equal(dr_job_status(tempfile())$state, "idle")
})
