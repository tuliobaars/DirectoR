"""Engine tests. Run with pytest, or without it:  python3 tests/engine/test_engine.py

Unit tests need numpy/scipy/pillow only. Tests marked `needs_browser` also need
Playwright's Chromium and ffmpeg (they are skipped when those are missing).
"""
import json, os, shutil, subprocess, sys, tempfile, time, wave

HERE = os.path.dirname(os.path.abspath(__file__))
ENGINE = os.path.abspath(os.path.join(HERE, "..", "..", "inst", "engine"))
sys.path.insert(0, ENGINE)

import numpy as np  # noqa: E402

from director import plan, source, timeline, voice, music, mux  # noqa: E402
from director.util import Project, Job, deep_merge  # noqa: E402


def tmpdir():
    return tempfile.mkdtemp(prefix="drtest-")


def write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    open(path, "w").write(text)


# ------------------------------------------------------------------ copy
def test_vo_line_keeps_title_and_trims():
    v = plan.vo_line("Report. Reality-check radar (self vs measured), levels with 95% ranges, topic breakdown, calibration, focus next, and one PDF with a section per skill category including a full question review.", 22)
    assert v.startswith("Report. Reality-check radar")
    assert len(v.split()) <= 22 and v.endswith(".")


def test_emphasise_and_hook():
    assert plan.emphasise("Revenue, in orbit") == "Revenue, *in orbit.*"
    assert plan.emphasise("Skills measured", 1) == "Skills *measured.*"
    B = {"summary": "Revenue, in orbit. A tiny dashboard.", "tagline": "x", "name": "Orbit"}
    assert plan.hook_line(B) == "Revenue, *in orbit.*"
    long = {"summary": "Self-reported skill levels are generous, so a 4 out of 5 says little.", "tagline": "Skills, measured.", "name": "Q"}
    assert "*" in plan.hook_line(long) and len(plan.hook_line(long).split()) <= 8


def test_headline_from_feature():
    assert plan.headline_from({"title": "Predict", "text": "Before any question, people rate themselves."}) == "*Predict.*"
    assert plan.headline_from({"title": "Explore", "text": "Adaptive questions find your level."}).startswith("*Explore.* _Adaptive questions")


def test_bullets_and_readme_facts():
    d = tmpdir()
    write(os.path.join(d, "README.md"), """# Orbit: revenue, in orbit.

Orbit is a tiny dashboard that shows revenue by region and forecasts the next months.

## Installation
- install it with remotes

## Features
1. **Overview.** Revenue, customers and growth at a glance.
2. **Explore.** Pick a region; the chart follows
   instantly.
- Plain bullet that is long enough to count.

## License
MIT
""")
    f = source.readme_facts(d)
    assert f["title"].startswith("Orbit")
    assert f["features_from"] == "Features"
    assert f["features"][0] == {"title": "Overview", "text": "Revenue, customers and growth at a glance."}
    assert f["features"][1]["text"].endswith("follows instantly.")
    assert "Installation" not in f["headings"]


# ------------------------------------------------------------------ sources
def test_classify_and_parse_git():
    assert source.classify("https://github.com/rstudio/shiny-examples") == "git"
    assert source.classify("https://github.com/a/b/tree/main/sub/dir") == "git"
    assert source.classify("https://myapp.shinyapps.io/demo/") == "url"
    assert source.classify("localhost:3838") == "url"
    assert source.parse_git("https://github.com/a/b/tree/dev/inst/app") == ("https://github.com/a/b.git", "dev", "inst/app")
    assert source.parse_git("https://gitlab.com/a/b.git") == ("https://gitlab.com/a/b.git", None, "")


def test_detect_app_kinds():
    cases = {
        "shiny-r": {"app.R": "library(shiny)\nshinyApp(ui, server)"},
        "shiny-py": {"app.py": "from shiny import App, ui\n"},
        "streamlit": {"streamlit_app.py": "import streamlit as st\nst.title('x')"},
        "static": {"docs/index.html": "<html><title>x</title></html>"},
        "golem": {"DESCRIPTION": "Package: mypkg\nImports: golem, shiny\n", "R/run_app.R": "run_app <- function() {}"},
    }
    for kind, files in cases.items():
        d = tmpdir()
        for name, body in files.items(): write(os.path.join(d, name), body)
        info = source.detect(d)
        assert info and info["kind"] == kind, (kind, info)


def test_r_requirements_prefers_description():
    d = tmpdir()
    write(os.path.join(d, "DESCRIPTION"), "Package: pk\nImports:\n    shiny (>= 1.7),\n    jsonlite\nSuggests: testthat\n")
    write(os.path.join(d, "app.R"), "pkgload::load_all('.')\n# library(ggplot2)\n")
    write(os.path.join(d, "dev", "x.R"), "library(tidyverse)")
    assert source.r_requirements(d, d) == ["jsonlite", "pkgload", "shiny"]


# ------------------------------------------------------------------ timeline
def test_palette_and_clip_map():
    p = timeline.palette3(["#0071e3"])
    assert len(p) == 3 and all(c.startswith("#") and len(c) == 7 for c in p)
    assert timeline.palette3([]) == timeline.DEFAULT_COLORS
    info = {"frames": 600, "fps": 60, "markers": {"click_nav": 60, "click_slide": 240}}
    frm, speed = timeline.clip_map(info, 4.0)
    assert abs(frm - 1.3) < 1e-6 and 0.85 <= speed <= 1.35


def test_durations_follow_voice_and_beats():
    d = tmpdir(); P = Project(d)
    P.save_cfg({"film": {"template": "teaser"}})
    sb = {"template": "teaser", "vo": False, "scenes": [{"id": "s1", "type": "hook", "dur": 1.9}, {"id": "s2", "type": "end", "dur": 3.1}]}
    rows = timeline.durations(P, sb, {})
    assert [r[1] for r in rows] == [2.0, 3.0]            # 120 BPM: snapped to whole beats
    sb2 = {"template": "launch", "vo": True, "scenes": [{"id": "s1", "type": "hook", "dur": 2.0}]}
    rows = timeline.durations(P, sb2, {"s1": 5.0})
    assert rows[0][1] >= 5.0 + 0.6 + 0.45 - 1e-6


# ------------------------------------------------------------------ voice text
def test_speech_text():
    lex = voice.parse_lexicon("SQL = sequel\n")
    assert voice.speech_text("Meet *QuantSkill*. Ask SQL questions.", lex, "QuantSkill") == "Meet Quant Skill . Ask sequel questions."
    assert voice.speech_text("Export a PDF", {}, "", spell=True) == "Export a P D F"
    assert voice.speech_text("Export a PDF", {}, "", spell=False) == "Export a PDF"


# ------------------------------------------------------------------ music
def test_compose_all_moods_short():
    tl = {"duration": 6.0, "bpm": 0, "scenes": [{"type": "hook", "t0": 0, "t1": 1.5}, {"type": "shot", "t0": 1.5, "t1": 4}, {"type": "end", "t0": 4, "t1": 6}],
          "hits": [{"t": 0.1, "kind": "hit"}], "sfx": [{"t": 1.4, "kind": "whoosh", "dur": .5}, {"t": 2.5, "kind": "click"}]}
    for mood in music.MOODS:
        x = music.compose(dict(tl, bpm=music.MOODS[mood]["bpm"]), mood)
        assert x.shape == (2, int(6.0 * music.SR)), mood
        assert np.isfinite(x).all() and np.abs(x).max() <= 1.0 and np.abs(x).max() > 0.05, mood
    fx = music.sfx(tl)
    assert fx.shape == (2, int(6.0 * music.SR)) and np.abs(fx).max() > 0


# ------------------------------------------------------------------ captions
def test_captions_srt_and_ass():
    tl = {"W": 1920, "H": 1080, "capstyle": "clean", "theme": {"c3": "#ec4899"},
          "captions": [{"start": 1.0, "end": 3.5, "text": "Meet Orbit, the dashboard that forecasts revenue for every region you care about.",
                        "words": ["Meet", "Orbit"], "wt": [1.0, 1.5]}]}
    srt, ass = mux.captions(tl)
    assert srt.startswith("1\n00:00:00,950 --> 00:00:03,750\nMeet Orbit")
    assert "\\N" in ass and "PlayResX: 1920" in ass
    tl["capstyle"] = "bold"; tl["W"], tl["H"] = 1080, 1920
    srt, ass = mux.captions(tl)
    assert "{\\k" in ass and "MEET" in ass


# ------------------------------------------------------------------ end to end (browser + ffmpeg)
def have_browser():
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p: p.chromium.launch().close()
        return bool(shutil.which("ffmpeg"))
    except Exception:  # noqa: BLE001
        return False


def make_media_project():
    from PIL import Image, ImageDraw
    d = tmpdir(); os.makedirs(os.path.join(d, "media"))
    for i, col in enumerate(["#6366f1", "#ec4899"]):
        im = Image.new("RGB", (1440, 810), "white"); dr = ImageDraw.Draw(im)
        dr.rectangle([100, 100, 1340, 700], fill=col); dr.text((140, 140), "Screen %d" % (i + 1), fill="white")
        im.save(os.path.join(d, "media", "screen_%d.png" % (i + 1)))
    json.dump({"name": "Test", "source": {"kind": "media", "value": ""}, "film": {"template": "teaser"}, "brand": {"name": "Testly", "tagline": "Tests, rendered."},
               "voice": {"enabled": False}}, open(os.path.join(d, "project.json"), "w"))
    json.dump({"items": [{"file": "media/screen_1.png", "label": "First screen"}, {"file": "media/screen_2.png", "label": "Second screen"}]}, open(os.path.join(d, "media.json"), "w"))
    return d


def run_cli(*args):
    r = subprocess.run([sys.executable, "-m", "director"] + list(args), cwd=ENGINE, capture_output=True, text=True, env=dict(os.environ, PYTHONPATH=ENGINE))
    return r.returncode, r.stdout + r.stderr


def test_media_project_end_to_end():
    if not have_browser():
        print("  (skipped: no Chromium/ffmpeg)"); return
    d = make_media_project()
    code, out = run_cli("auto", "-p", d, "--from", "plan", "--quality", "draft")
    assert code == 0, out[-2000:]
    st = json.load(open(os.path.join(d, "status.json")))
    assert st["state"] == "done"
    man = json.load(open(os.path.join(d, "out", "manifest.json")))
    r = man["renders"][-1]
    assert os.path.getsize(os.path.join(d, r["files"]["video"])) > 50_000
    tl = json.load(open(os.path.join(d, "timeline.json")))
    assert tl["duration"] < 60 and tl["shot_status"] == {"shot1": "ok", "shot2": "ok"}
    # a stale recipe is detected
    sb = json.load(open(os.path.join(d, "storyboard.json")))
    sb["shots"][0]["media"] = "media/screen_2.png"; json.dump(sb, open(os.path.join(d, "storyboard.json"), "w"))
    assert run_cli("timeline", "-p", d)[0] == 0
    assert json.load(open(os.path.join(d, "timeline.json")))["shot_status"]["shot1"] == "stale"


def test_copy_keeps_renv_metadata_not_libraries():
    d = tmpdir()
    assert source.copy_ignore(os.path.join(d, "renv"), ["activate.R", "settings.json", "library", "staging"]) == {"library", "staging"}
    assert source.copy_ignore(d, ["renv", "R", ".git", "node_modules"]) == {".git", "node_modules"}


def test_renv_project_launches_without_its_rprofile():
    """a repo whose .Rprofile sources renv/activate.R, with renv/ not committed (the classic failure)"""
    rs = os.environ.get("DIRECTOR_RSCRIPT") or shutil.which("Rscript")
    if not rs or not have_browser():
        print("  (skipped: no Rscript/Chromium)"); return
    try:
        subprocess.run([rs, "-e", "stopifnot(requireNamespace('shiny'))"], check=True, capture_output=True)
    except Exception:  # noqa: BLE001
        print("  (skipped: no shiny)"); return
    app = tmpdir()
    write(os.path.join(app, ".Rprofile"), 'source("renv/activate.R")\n')
    write(os.path.join(app, "renv.lock"), "{}")
    write(os.path.join(app, "app.R"), "library(shiny)\nshinyApp(fluidPage(titlePanel('Renv test'), h2('Hello')), function(input, output) {})\n")
    d = tmpdir()
    json.dump({"source": {"kind": "dir", "value": app}}, open(os.path.join(d, "project.json"), "w"))
    code, out = run_cli("scout", "-p", d)
    st = json.load(open(os.path.join(d, "status.json")))
    assert code == 0 and st["state"] == "done", (st.get("error") or out)[-800:]
    assert "renv project" in open(os.path.join(d, "log.txt")).read()


def test_sound_previews():
    d = tmpdir()
    assert music.demo(d, "click") == "sfx_click.wav"
    name = music.demo(d, "keys", seed=3)
    x, sr = __import__("director.ff", fromlist=["ff"]).read_wav(os.path.join(d, name))
    assert sr == music.SR and x.shape[1] > 9 * sr and np.isfinite(x).all() and np.abs(x).max() > 0.1
    assert music.demo(d, "keys", seed=3) == name                     # cached


def test_wavetable_saw_matches_additive():
    f, n, ph = 330.0, 12000, 0.7
    t = np.arange(n) / music.SR; k = int(min(60, (music.SR / 2 - 200) / f))
    ref = sum(np.sin(2 * np.pi * h * f * t + ph * h) / h for h in range(1, k + 1)) * (2 / np.pi)
    assert np.max(np.abs(music.saw(f, n, ph) - ref)) < 2e-3


def test_hostile_app_still_scouts():
    """slow start, a third-party script that never answers, and an app that picks its own port"""
    import socket, threading
    rs = os.environ.get("DIRECTOR_RSCRIPT") or shutil.which("Rscript")
    if not rs or not have_browser():
        print("  (skipped: no Rscript/Chromium)"); return
    srv = socket.socket(); srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1); srv.bind(("0.0.0.0", 0)); srv.listen(20)
    hang_port = srv.getsockname()[1]; held = []
    threading.Thread(target=lambda: [held.append(srv.accept()) for _ in range(20)], daemon=True).start()
    own = source.free_port()
    app = tmpdir()
    write(os.path.join(app, "app.R"), """library(shiny)
message("warming up"); Sys.sleep(4)
ui <- fluidPage(tags$head(tags$script(src = "http://127.0.0.2:%d/never.js")), titlePanel("Hostile"),
                tabsetPanel(tabPanel("One", plotOutput("p")), tabPanel("Two", tableOutput("t"))))
server <- function(input, output) { output$p <- renderPlot(plot(1:10)); output$t <- renderTable(head(mtcars)) }
shinyApp(ui, server, options = list(port = %d))
""" % (hang_port, own))
    d = tmpdir()
    json.dump({"source": {"kind": "dir", "value": app}}, open(os.path.join(d, "project.json"), "w"))
    t0 = time.time()
    code, out = run_cli("scout", "-p", d)
    st = json.load(open(os.path.join(d, "status.json")))
    assert code == 0 and st["state"] == "done", (st.get("error") or out)[-800:]
    assert len(json.load(open(os.path.join(d, "scout.json")))["views"]) >= 2
    assert time.time() - t0 < 150, "too slow: %.0fs" % (time.time() - t0)
    assert not os.path.exists(os.path.join(d, "app.pid"))          # the app was stopped


if __name__ == "__main__":
    fails = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn(); print("ok  ", name)
            except Exception as e:  # noqa: BLE001
                fails += 1; print("FAIL", name, "->", repr(e)[:300])
    print("%d failed" % fails)
    sys.exit(1 if fails else 0)
