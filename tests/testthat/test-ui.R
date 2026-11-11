test_that("the UI renders with every page and the custom controls", {
  html <- as.character(app_ui())
  for (id in c("lib_source", "lib_create", "src_scout", "story_generate", "shots_record", "sound_voice", "sound_music", "export_go", "dr-dock", "dr-auto"))
    expect_match(html, sprintf('id="%s"', id), fixed = TRUE)
  expect_match(html, "dr-choices", fixed = TRUE)
  expect_false(grepl("<c2>|<e2>", html))                         # non-ASCII is escaped properly
  expect_match(html, "\u00b7", fixed = TRUE)
})

test_that("scene cards render for every scene type", {
  sb <- list(vo = TRUE, shots = list(list(id = "shot1", label = "Home", thumb = "scout/home.jpg")),
             scenes = lapply(names(DirectoR:::SCENE_TYPES), function(k) { s <- DirectoR:::new_scene(k, list(shots = list(list(id = "shot1")), brand = list(name = "X"))); s$id <- paste0("s_", k); s }))
  for (i in seq_along(sb$scenes)) {
    h <- as.character(DirectoR:::scene_card(sb$scenes[[i]], i, length(sb$scenes), sb, NULL, tempdir(), identity))
    expect_match(h, sprintf('data-scene="%s"', sb$scenes[[i]]$id), fixed = TRUE)
    expect_match(h, 'data-f="vo"', fixed = TRUE)
  }
})

test_that("edits apply to scenes", {
  sb <- list(shots = list(list(id = "a"), list(id = "b"), list(id = "c")))
  sc <- list(type = "montage", shots = list("a"), dur = 3, items = list(list(title = "x")))
  sc <- DirectoR:::apply_edit(sc, "shots.c", TRUE, sb); expect_equal(unlist(sc$shots), c("a", "c"))
  sc <- DirectoR:::apply_edit(sc, "shots.a", FALSE, sb); expect_equal(unlist(sc$shots), "c")
  sc <- DirectoR:::apply_edit(sc, "dur", "4.5", sb); expect_equal(sc$dur, 4.5)
  sc <- DirectoR:::apply_edit(sc, "items.1.title", "Fast", sb); expect_equal(sc$items[[1]]$title, "Fast")
  sc <- DirectoR:::apply_edit(sc, "step", "", sb); expect_null(sc$step)
})
