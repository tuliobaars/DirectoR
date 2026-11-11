test_that("merge, set and get work on nested lists", {
  a <- list(x = 1, look = list(theme = "auto", radius = 22))
  b <- list(look = list(theme = "dark"), new = "y")
  m <- DirectoR:::dr_merge(a, b)
  expect_equal(m$look$theme, "dark"); expect_equal(m$look$radius, 22); expect_equal(m$new, "y")
  s <- DirectoR:::dr_set(a, c("look", "font"), "Serif")
  expect_equal(DirectoR:::dr_get(s, c("look", "font")), "Serif")
  expect_null(DirectoR:::dr_get(s, c("nope", "deeper")))
  expect_equal(DirectoR:::`%||%`("", "b"), "b"); expect_equal(DirectoR:::`%||%`(NULL, 2), 2); expect_equal(DirectoR:::`%||%`("a", "b"), "a")
})

test_that("JSON round-trips keep lists as lists", {
  p <- tempfile(fileext = ".json")
  x <- list(scenes = list(list(id = "s1", shots = list("shot1")), list(id = "s2", shots = list())), colors = list("#fff"))
  DirectoR:::dr_write_json(x, p)
  y <- DirectoR:::dr_read_json(p)
  expect_equal(y$scenes[[1]]$shots[[1]], "shot1")
  expect_length(y$scenes[[2]]$shots, 0)
  expect_equal(jsonlite::fromJSON(p)$colors, "#fff")
  expect_true(grepl('"colors": \\[', paste(readLines(p), collapse = "")))
})

test_that("slugs and markup", {
  expect_equal(DirectoR:::dr_slug("Orbit: Revenue, in orbit!"), "orbit-revenue-in-orbit")
  expect_equal(DirectoR:::dr_slug(""), "film")
  expect_match(DirectoR:::dr_markup("Skills, *measured.*"), "<span class='grad'>measured.</span>", fixed = TRUE)
  expect_match(DirectoR:::dr_markup("a <b> _quiet_"), "&lt;b&gt;", fixed = TRUE)
})
