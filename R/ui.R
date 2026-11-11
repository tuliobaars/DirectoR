# The studio UI ---------------------------------------------------------------------------

TEMPLATES <- list(
  list(value = "launch", label = "Launch film", sub = "Voice-over story: hook, product, features, end card. 40\u201360 s."),
  list(value = "teaser", label = "Teaser", sub = "Music only, cut on the beat, kinetic type. 15\u201330 s."),
  list(value = "tour", label = "Feature tour", sub = "Numbered walkthrough of the main screens, with voice-over."),
  list(value = "social", label = "Social vertical", sub = "9:16 for Reels, Shorts, TikTok. Bold captions, fast."),
  list(value = "demo", label = "Calm demo", sub = "Quiet and product-first. For docs and READMEs.")
)

NAV <- list(
  list(id = "lib", label = "Library", icon = "library"),
  list(id = "source", label = "Source", icon = "source"),
  list(id = "story", label = "Story", icon = "story"),
  list(id = "shots", label = "Shots", icon = "shots"),
  list(id = "sound", label = "Sound", icon = "sound"),
  list(id = "look", label = "Look", icon = "look"),
  list(id = "export", label = "Export", icon = "export")
)

#' The DirectoR UI
#' @param request Shiny request.
#' @return A Shiny UI.
#' @export
app_ui <- function(request = NULL) {
  theme <- bslib::bs_theme(version = 5, bg = "#07070a", fg = "#f4f4f6", primary = "#a855f7", base_font = "Inter", "enable-shadows" = FALSE)
  bslib::page(
    theme = theme, title = "DirectoR",
    tags$head(
      tags$meta(name = "viewport", content = "width=device-width, initial-scale=1"),
      tags$meta(name = "color-scheme", content = "dark"),
      tags$link(rel = "icon", href = "data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'><defs><linearGradient id='g' x1='0' y1='0' x2='1' y2='1'><stop offset='0' stop-color='%236366f1'/><stop offset='.5' stop-color='%23a855f7'/><stop offset='1' stop-color='%23ec4899'/></linearGradient></defs><rect width='32' height='32' rx='9' fill='url(%23g)'/><path d='m13 11 9 5-9 5z' fill='white'/></svg>"),
      tags$link(rel = "stylesheet", href = "dr-www/director.css"),
      tags$script(src = "dr-www/director.js")
    ),
    tags$script(HTML("document.body.classList.add('dr','noproj');")),
    div(class = "dr-shell",
        div(class = "dr-rail",
            div(class = "dr-logo", title = "DirectoR", onclick = "Shiny.setInputValue('nav', 'lib', {priority:'event'})", dr_icon("logo", 24)),
            lapply(NAV, function(n) tags$button(class = paste("dr-nav", if (n$id == "lib") "active"), id = paste0("nav_", n$id), `data-nav` = n$id,
                                                dr_icon(n$icon, 20), tags$span(n$label), tags$i(class = "dot"))),
            div(class = "spacer"),
            div(class = "engine", id = "engine_btn", `data-act` = "engine", title = "Engine check", dr_icon("terminal", 19))),
        div(class = "dr-main",
            div(class = "dr-top",
                div(class = "crumb", htmltools::span(class = "lib", onclick = "Shiny.setInputValue('nav','lib',{priority:'event'})", "Library"), dr_icon("chevron", 14, "dim"),
                    tags$input(id = "proj_name", class = "title-in", type = "text", value = "", placeholder = "Untitled film", spellcheck = "false")),
                shiny::uiOutput("top_chips", inline = TRUE),
                div(class = "grow"),
                dr_btn("top_preview", "Preview", "play", "ghost sm"),
                dr_btn("top_auto", "Direct it", "sparkles", "sm", title = "Autopilot: scout, write, record, score and cut the whole film"),
                dr_btn("top_render", "Render", "export", "primary sm")),
            div(class = "dr-page",
                shiny::tabsetPanel(id = "pages", type = "hidden", selected = "lib",
                  shiny::tabPanelBody("lib", page_library()),
                  shiny::tabPanelBody("source", page_source()),
                  shiny::tabPanelBody("story", page_story()),
                  shiny::tabPanelBody("shots", page_shots()),
                  shiny::tabPanelBody("sound", page_sound()),
                  shiny::tabPanelBody("look", page_look()),
                  shiny::tabPanelBody("export", page_export()))))),
    # job dock, toasts, autopilot overlay (driven by director.js)
    div(id = "dr-dock",
        div(class = "jt", div(class = "ring", style = "--p:0", tags$i("0%")),
            div(class = "grow", div(class = "nm", "Working"), div(class = "msg", "\u2026")),
            dr_btn(NULL, NULL, "terminal", "ghost xs icon", onclick = "DR.toggleLog()", title = "Log"),
            dr_btn(NULL, NULL, "x", "ghost xs icon", onclick = "DR.dockClose()", title = "Hide")),
        div(class = "bar", tags$i(style = "width:0%")),
        div(class = "foot", htmltools::span(class = "eta", ""), div(class = "grow"),
            dr_btn("job_cancel", "Cancel", NULL, "xs danger")),
        tags$pre(class = "log")),
    div(id = "dr-toasts"),
    div(id = "dr-auto",
        div(class = "box",
            div(class = "clap", dr_icon("logo", 30)),
            tags$h3("Directing your film"),
            div(class = "muted msg", "Getting ready\u2026"),
            div(class = "phases", lapply(c(scout = "Scout", plan = "Script", voice = "Voice", capture = "Record", music = "Score", render = "Cut"), function(x) x) |>
                  (\(ph) mapply(function(k, v) htmltools::span(class = "ph", `data-ph` = k, v), names(ph), ph, SIMPLIFY = FALSE))()),
            div(class = "big", tags$i(style = "width:0%")),
            div(class = "hrow", style = "justify-content:center;margin-top:14px",
                htmltools::span(class = "dim eta", ""),
                dr_btn(NULL, "Keep working", NULL, "ghost sm", onclick = "DR.autoHide()"),
                dr_btn("auto_cancel", "Cancel", NULL, "sm danger"))))
  )
}

# ------------------------------------------------------------------------------------------ pages

page_library <- function() {
  div(class = "pg",
      div(class = "hero",
          div(class = "eyebrow", tags$b("NEW"), "Launch & teaser films for apps and websites"),
          tags$h1(HTML("Your app deserves<br>a <span class='grad'>launch film</span>.")),
          tags$p(class = "sublead", "Paste a link to a website, a Shiny app or a Git repository, or drop a zip. DirectoR scouts the app, writes the script, records real footage and cuts a film with voice-over, music and transitions. Under 60 seconds."),
          div(class = "omni",
              div(class = "lead-ic", dr_icon("link", 22)),
              tags$input(id = "lib_source", type = "text", class = "form-control", placeholder = "https://your.app  \u00b7  github.com/you/shiny-app  \u00b7  ~/code/my-dashboard", autocomplete = "off", spellcheck = "false"),
              htmltools::span(id = "lib_detect", class = "detect"),
              dr_btn("lib_create", "Create film", "sparkles", "primary lg")),
          div(class = "dropzone", id = "lib_drop",
              dr_icon("zip", 20), htmltools::span(HTML("or <b>drop a .zip</b> of the repository here")),
              htmltools::span(class = "dim", "\u00b7"), htmltools::span("screenshots and screen recordings work too"),
              shiny::fileInput("lib_zip", NULL, multiple = TRUE, accept = c(".zip", "image/*", "video/*"))),
          div(class = "hero-opts",
              dr_choices("lib_template", lapply(TEMPLATES, function(t) list(value = t$value, label = t$label)), "launch", style = "seg"),
              dr_switch("lib_autopilot", "Direct it for me (full autopilot)", TRUE),
              dr_choices("lib_quality", list(list(value = "draft", label = "Draft (fast)"), list(value = "final", label = "Final 1080p60")), "draft", style = "seg")),
          div(class = "how",
              lapply(list(c("1", "Scout", "source", "Launches the app, explores tabs, inputs and pages, learns the brand."),
                          c("2", "Script", "story", "Writes a storyboard and a voice-over from the README and the screens."),
                          c("3", "Record", "shots", "Films real interactions at a smooth 60 fps, with cursor and clicks."),
                          c("4", "Score", "sound", "Voice-over, original music and sound design, mixed and ducked."),
                          c("5", "Cut", "export", "Kinetic type, camera moves and transitions. MP4, captions, poster.")),
                     function(s) div(class = "st", div(class = "n", paste("Step", s[1])), div(class = "t", dr_icon(s[3], 16), s[2]), div(class = "s", s[4]))))),
      div(class = "lib-head", tags$h3("Your films"), shiny::uiOutput("lib_count", inline = TRUE), div(class = "grow")),
      shiny::uiOutput("lib_grid"))
}

page_source <- function() {
  div(class = "pg",
      div(class = "pg-head", div(tags$h2("Source"), tags$p("What should the film be about? DirectoR launches it, explores it like a curious user, and learns its name, voice and colours.")),
          div(class = "grow"), dr_btn("src_scout", "Scout the app", "eye", "primary")),
      div(class = "cols wide-left",
          div(class = "stack",
              dr_card("The app", icon = "source",
                      div(class = "stack",
                          dr_choices("src_kind", list(list(value = "url", label = "Website / live app", icon = "globe"), list(value = "git", label = "Git repository", icon = "git"),
                                                      list(value = "zip", label = "Zip", icon = "zip"), list(value = "dir", label = "Local folder", icon = "folder"),
                                                      list(value = "media", label = "Screenshots & recordings", icon = "image")), "url", style = "seg"),
                          shiny::uiOutput("src_value_ui"),
                          shiny::uiOutput("src_detect_ui"),
                          tags$details(class = "adv",
                                       tags$summary(dr_icon("sliders", 15), "Advanced: launch & capture", dr_icon("chevron", 14)),
                                       div(class = "in",
                                           div(class = "grid2",
                                               dr_text("app_command", "Launch command (optional)", placeholder = "Rscript -e \"shiny::runApp(port={port})\"", help = "Overrides detection. {port} is replaced by a free port."),
                                               dr_text("app_path", "Start page", "/", help = "Path to open, e.g. /dashboard or /#/home")),
                                           div(class = "grid3",
                                               dr_select("cap_viewport", "Browser size", c("Desktop 1440x810" = "desktop", "Laptop 1280x800" = "laptop", "Wide 1600x900" = "wide", "Tablet 1024x768" = "tablet", "Mobile 390x844" = "mobile")),
                                               dr_select("cap_scheme", "Colour scheme", c("Light" = "light", "Dark" = "dark")),
                                               dr_select("cap_lite", "Heavy effects", c("Auto" = "auto", "Keep (slower)" = "false", "Lighten (faster)" = "true"))),
                                           div(class = "grid3",
                                               dr_select("cap_fps", "Footage fps", c("60 (silky)" = "60", "30 (faster)" = "30")),
                                               dr_select("cap_dpr", "Sharpness", c("Auto (by page weight)" = "auto", "2x (crisp zooms, slower)" = "2", "1.5x" = "1.5", "1x (fastest)" = "1"), "auto"),
                                               dr_select("cap_workers", "Parallel browsers", c("1", "2", "3", "4"), "3")),
                                           div(class = "grid3",
                                               dr_text("cap_hide", "Hide elements (CSS selector)", placeholder = ".cookie-banner, #chat-widget"),
                                               dr_text("app_wait", "Start-up patience (s)", "600", help = "Give up after this long without any sign of activity (min. 300). A busy app gets longer."),
                                               dr_select("app_renv", "R projects with renv", c("Use my installed packages" = "ignore", "Restore the lockfile first" = "restore"), "ignore",
                                                         help = "The project's .Rprofile is skipped unless you restore.")),
                                           dr_field("Environment variables for the app", shiny::textAreaInput("app_env", NULL, "", rows = 2, placeholder = "API_TOKEN=\u2026\nDATA_DIR=/path/to/data"), help = "One per line, KEY=value. Passed to the app when DirectoR launches it."),
                                           dr_switch("cap_cookies", "Dismiss cookie banners automatically", TRUE))))),
              shiny::uiOutput("src_seen_ui")),
          div(class = "stack",
              dr_card("Brand", icon = "sparkles", actions = htmltools::span(class = "dim", style = "font-size:12px", "Leave empty to use what the scout found"),
                      div(class = "stack",
                          div(class = "grid2", dr_text("brand_name", "Name"), dr_text("brand_tagline", "Tagline")),
                          dr_field("One-line description", shiny::textAreaInput("brand_description", NULL, "", rows = 2)),
                          div(class = "grid2", dr_text("brand_url", "Website", placeholder = "https://"), dr_text("brand_cta", "End-card call to action", placeholder = "yourapp.com \u00b7 pkg::run_app()")),
                          dr_field("Brand colours", div(class = "hrow", div(class = "swatches", dr_color("brand_c1"), dr_color("brand_c2"), dr_color("brand_c3")),
                                                        dr_btn("brand_colors_reset", "Use detected", "refresh", "ghost xs"),
                                                        htmltools::span(class = "dim", style = "font-size:12px", "The gradient runs 1 \u2192 2 \u2192 3"))),
                          dr_field("Logo", div(class = "hrow nowrap", shiny::uiOutput("brand_logo_prev"),
                                               div(style = "flex:1", shiny::fileInput("brand_logo", NULL, accept = c("image/png", "image/svg+xml", "image/jpeg", "image/webp"), buttonLabel = "Upload", placeholder = "PNG or SVG, square"))),
                                   help = "Defaults to the favicon, the logo in the page header, or a monogram."))),
              shiny::uiOutput("src_media_ui"))))
}

page_story <- function() {
  div(class = "pg",
      div(class = "pg-head", div(tags$h2("Story"), tags$p("Pick a format, then shape every scene. Edits play instantly in the preview. *Stars* highlight words with the brand gradient, _underscores_ mute them, | breaks a line.")),
          div(class = "grow"),
          dr_btn("story_generate", "Write storyboard", "wand", "primary")),
      dr_choices("story_template", lapply(TEMPLATES, function(t) list(value = t$value, label = t$label, sub = t$sub, vis = vis_template(t$value), class = "tpl")), "launch", min = "190px"),
      div(class = "hrow", style = "margin:16px 0 22px; gap:16px",
          div(style = "width:200px", dr_select("film_tone", "Tone", c("Confident" = "confident", "Calm" = "calm", "Energetic" = "energetic", "Playful" = "playful"))),
          div(style = "width:240px", dr_text("film_audience", "Audience (optional)", placeholder = "data teams, analysts\u2026")),
          div(style = "width:200px", dr_select("llm_provider", "Copywriter", c("Built-in (offline)" = "none", "OpenAI" = "openai", "Anthropic" = "anthropic", "Local (Ollama / LM Studio)" = "local"))),
          shiny::uiOutput("llm_opts", inline = TRUE)),
      div(class = "cols with-player",
          div(class = "stack",
              shiny::uiOutput("story_scenes"),
              shiny::uiOutput("story_add")),
          div(class = "sticky player-wrap",
              shiny::uiOutput("story_player"),
              shiny::uiOutput("story_stats"))))
}

page_shots <- function() {
  div(class = "pg",
      div(class = "pg-head", div(tags$h2("Shots"), tags$p("The footage: real interactions with your app, recorded frame by frame so cursor moves, scrolling and animations are perfectly smooth.")),
          div(class = "grow"), dr_btn("shots_add", "Add shot", "plus", ""), dr_btn("shots_record", "Record all", "shots", "primary")),
      shiny::uiOutput("shots_grid"))
}

page_sound <- function() {
  div(class = "pg",
      div(class = "pg-head", div(tags$h2("Sound"), tags$p("A voice that tells the story and an original score that fits the cut. Music ducks under the voice automatically.")),
          div(class = "grow"), dr_btn("sound_voice", "Generate voice-over", "mic", ""), dr_btn("sound_music", "Compose & mix", "sound", "primary")),
      div(class = "cols",
          div(class = "stack",
              dr_card("Voice-over", icon = "mic", actions = dr_switch("voice_enabled", "On", TRUE),
                      div(class = "stack",
                          shiny::uiOutput("voice_providers"),
                          div(class = "grid3",
                              shiny::uiOutput("voice_voice_ui"),
                              dr_field("Speed", shiny::sliderInput("voice_rate", NULL, min = .8, max = 1.3, value = 1, step = .02, ticks = FALSE)),
                              shiny::conditionalPanel("['openai','elevenlabs'].indexOf(input.voice_provider) >= 0",
                                dr_field("API key (this session only)", tags$input(id = "voice_key", type = "password", class = "form-control dr-secret", placeholder = "sk-\u2026", autocomplete = "off")))),
                          dr_field("Pronunciation", shiny::textAreaInput("voice_lexicon", NULL, "", rows = 2, placeholder = "QuantSkill = Quant Skill\nSQL = sequel"), help = "One per line: word = how to say it. CamelCase product names are split automatically."))),
              dr_card("Lines", icon = "type", shiny::uiOutput("voice_lines"))),
          div(class = "stack",
              dr_card("Music", icon = "sound",
                      div(class = "stack",
                          shiny::uiOutput("music_moods"),
                          div(class = "hrow", style = "gap:8px", tags$button(class = "dr-btn xs", id = "music_preview_btn", onclick = "DR.previewMood(null, true)", dr_icon("play", 11), "Preview with these settings"),
                              htmltools::span(class = "dim", style = "font-size:12px", "Selecting a mood plays it. The score for your film follows its own cut.")),
                          div(class = "grid3",
                              dr_select("music_key", "Harmony", c("Auto" = "auto", "Minor (moody)" = "minor", "Major (bright)" = "major", "Dreamy (maj7)" = "dreamy")),
                              dr_field("Tempo (BPM, 0 = auto)", shiny::numericInput("music_bpm", NULL, 0, min = 0, max = 180, step = 1)),
                              dr_field("Variation", div(class = "hrow nowrap", shiny::numericInput("music_seed", NULL, 7, min = 1, max = 9999, step = 1), dr_btn("music_shuffle", NULL, "refresh", "icon", title = "Another take")))),
                          div(class = "grid3",
                              dr_field("Music level (dB)", shiny::sliderInput("music_volume", NULL, min = -12, max = 6, value = 0, step = 1, ticks = FALSE)),
                              dr_field("Duck under voice (dB)", shiny::sliderInput("music_duck", NULL, min = 0, max = 20, value = 10, step = 1, ticks = FALSE)),
                              dr_field("Transpose", shiny::sliderInput("music_transpose", NULL, min = -6, max = 6, value = 0, step = 1, ticks = FALSE))),
                          div(class = "hrow spread", dr_switch("music_sfx", "Sound design: UI clicks, whooshes on transitions, hits", TRUE), shiny::uiOutput("sfx_chips", inline = TRUE)),
                          shiny::uiOutput("music_custom_ui"))),
              dr_card("Mix", icon = "volume", shiny::uiOutput("music_mix_ui")))))
}

page_look <- function() {
  aspects <- list(list(value = "16:9", label = "Landscape 16:9", sub = "YouTube, websites, decks", vis = HTML("<i style='width:64px;height:36px'></i>"), class = "aspect"),
                  list(value = "9:16", label = "Vertical 9:16", sub = "Reels, Shorts, TikTok", vis = HTML("<i style='width:30px;height:54px'></i>"), class = "aspect"),
                  list(value = "1:1", label = "Square 1:1", sub = "LinkedIn, X, feeds", vis = HTML("<i style='width:48px;height:48px'></i>"), class = "aspect"),
                  list(value = "4:5", label = "Portrait 4:5", sub = "Instagram feed", vis = HTML("<i style='width:42px;height:52px'></i>"), class = "aspect"))
  bgvis <- function(k) HTML(switch(k,
    aurora = "<div style='position:absolute;inset:0;background:radial-gradient(circle at 20% 30%,rgba(99,102,241,.7),transparent 50%),radial-gradient(circle at 80% 30%,rgba(168,85,247,.6),transparent 50%),radial-gradient(circle at 50% 100%,rgba(236,72,153,.5),transparent 55%)'></div>",
    mesh = "<div style='position:absolute;inset:0;background:radial-gradient(circle at 15% 20%,#6366f1,transparent 45%),radial-gradient(circle at 85% 25%,#a855f7,transparent 45%),radial-gradient(circle at 50% 95%,#ec4899,transparent 50%),radial-gradient(circle at 90% 90%,#6366f1,transparent 40%)'></div>",
    grid = "<div style='position:absolute;inset:0;background-image:radial-gradient(circle at 1px 1px,rgba(255,255,255,.35) 1px,transparent 1.5px);background-size:9px 9px'></div><div style='position:absolute;inset:0;background:radial-gradient(circle at 70% 40%,rgba(168,85,247,.5),transparent 55%)'></div>",
    spotlight = "<div style='position:absolute;inset:0;background:radial-gradient(ellipse 45% 80% at 50% 0%,rgba(168,85,247,.65),transparent 70%)'></div>",
    solid = ""))
  div(class = "pg",
      div(class = "pg-head", div(tags$h2("Look"), tags$p("Format, theme and motion. The brand colours come from your app; everything updates in the preview.")), div(class = "grow")),
      div(class = "cols with-player",
          div(class = "stack",
              dr_card("Format", icon = "monitor", dr_choices("look_aspect", aspects, "16:9", min = "140px")),
              dr_card("Theme", icon = "look",
                      div(class = "stack",
                          dr_choices("look_theme", list(list(value = "auto", label = "Auto"), list(value = "light", label = "Light"), list(value = "dark", label = "Dark"), list(value = "brand", label = "Brand gradient")), "auto", style = "seg"),
                          dr_field("Background", dr_choices("look_background", lapply(c("aurora", "mesh", "grid", "spotlight", "solid"), function(k) list(value = k, label = tools::toTitleCase(k), vis = bgvis(k), class = "bgv")), "aurora", min = "96px")),
                          div(class = "grid2",
                              dr_field("Typeface", dr_choices("look_font", lapply(c("Inter", "System", "Serif", "Rounded", "Mono"), function(k) list(value = k, label = k)), "Inter", style = "seg")),
                              dr_field("Browser window", dr_choices("look_window", list(list(value = "macos", label = "macOS"), list(value = "minimal", label = "Minimal"), list(value = "glass", label = "Glass"), list(value = "none", label = "None")), "macos", style = "seg"))),
                          div(class = "grid2",
                              dr_field("Corner radius", shiny::sliderInput("look_radius", NULL, min = 0, max = 40, value = 22, step = 1, ticks = FALSE)),
                              div(class = "stack", style = "gap:10px;padding-top:22px", dr_switch("look_grain", "Film grain", TRUE))))),
              dr_card("Motion", icon = "zap",
                      div(class = "stack",
                          dr_field("Transitions", dr_choices("look_transition", c(list(list(value = "auto", label = "Auto", sub = "Picked per cut", vis = HTML("<div class='tr-demo'><i></i><div style='position:absolute;inset:0;display:grid;place-items:center;color:#fff;font-weight:700'>\u2726</div></div>"))),
                                                                        lapply(c("cut", "fade", "blur", "zoom", "slide", "push", "whip", "rise", "flash", "wipe", "iris", "flip"), function(k)
                                                                          list(value = k, label = tools::toTitleCase(k), vis = HTML(sprintf("<div class='tr-demo %s'><i></i><b></b></div>", k))))), "auto", min = "96px")),
                          div(class = "grid2",
                              dr_field("Captions", dr_choices("look_captions", list(list(value = "off", label = "Off"), list(value = "clean", label = "Clean"), list(value = "bold", label = "Bold (social)")), "clean", style = "seg")),
                              dr_field("Cursor", dr_choices("look_cursor", list(list(value = "mac", label = "Dark"), list(value = "light", label = "Light"), list(value = "none", label = "Hidden")), "mac", style = "seg")))))),
          div(class = "sticky player-wrap", shiny::uiOutput("look_player"))))
}

page_export <- function() {
  div(class = "pg",
      div(class = "pg-head", div(tags$h2("Export"), tags$p("Render the film. Draft is quick (half size, 30 fps) for checking the cut; Final is 1080p at 60 fps with loudness-normalised audio, captions and a poster.")),
          div(class = "grow")),
      div(class = "cols wide-left",
          div(class = "stack", shiny::uiOutput("export_renders")),
          div(class = "stack",
              dr_card("Render", icon = "film",
                      div(class = "stack",
                          dr_choices("export_quality", list(list(value = "draft", label = "Draft", sub = "960x540 \u00b7 30 fps \u00b7 fast", icon = "zap"),
                                                           list(value = "final", label = "Final", sub = "1080p \u00b7 60 fps \u00b7 master", icon = "film")), "final", min = "150px"),
                          dr_field("Also render", div(class = "stack", style = "gap:8px",
                                                      dr_switch("export_vertical", "Vertical 9:16 version", FALSE), dr_switch("export_square", "Square 1:1 version", FALSE))),
                          dr_btn("export_go", "Render film", "film", "primary lg"),
                          shiny::uiOutput("export_checks"))),
              dr_card("More cuts from the same footage", icon = "layers", shiny::uiOutput("export_more")),
              dr_card("Film facts", icon = "info", shiny::uiOutput("export_facts")))))
}
