"""DirectoR engine command line.

    python -m director doctor [--json]
    python -m director <step> --project DIR [options]

Steps (each writes status.json while it runs and appends to log.txt):
  scout      fetch the source, detect and launch the app, explore it in a browser
  plan       write the storyboard (scenes, voice-over script, shot recipes)   --template T --no-llm
  voice      synthesize the voice-over                                        --line SCENE (one-line preview)
  capture    record the shots                                                 --shots id,id
  timeline   resolve the storyboard into timeline.json (+ stage pages)        --preview
  music      compose the score + sound design, and mix with the voice-over
  render     render the film and mux the deliverables                          --quality draft|final
  stills     render a few frames                                               --times 1,2.5 --out DIR
  auto       all of the above, in order                                        --quality --from STEP --template T
"""
import argparse, json, os, sys, time, traceback

from .util import Project, Job, DirectorError, read_json, write_json


def _captured(P):
    sb = P.get("storyboard") or {}
    from .timeline import shot_info
    return all(shot_info(P, s["id"], s) for s in sb.get("shots") or [])


def set_min_lengths(P):
    """every shot must be long enough for the scenes that use it"""
    from .timeline import durations
    sb = P.get("storyboard"); clips = (read_json(P.p("vo", "clips.json"), {}) or {}).get("clips") or {}
    need = {}
    for s, d, _ in durations(P, sb, {k: v["dur"] for k, v in clips.items()}):
        if s.get("shot"): need[s["shot"]] = max(need.get(s["shot"], 0), (d + 1.2) * 1000)
        for x in s.get("shots") or []: need[x] = max(need.get(x, 0), 2500)
    for sh in sb["shots"]:
        sh["min_ms"] = int(need.get(sh["id"], 3000))
    P.put("storyboard", sb)


def step_scout(P, job, a, keep_server=False):
    from . import source, scout
    with job.phase("reading the source", 0.0, 0.2):
        facts = source.ingest(P, job)
    kind = facts.get("source_kind")
    if kind == "media":
        return {"kind": "media"}
    with job.phase("launching the app", 0.2, 0.35):
        srv = source.AppServer(P, job, facts)
        url = srv.__enter__()
    ok = False
    try:
        with job.phase("exploring the app", 0.35, 1.0):
            res = scout.scout(P, job, url)
        ok = True
    finally:
        if keep_server and ok and kind != "url": P.shared_server = srv      # autopilot records with the same app
        else: srv.stop()
    # what we'd use when the user leaves the brand fields empty (shown as placeholders in the app)
    from .plan import brand
    B = brand(P, facts, res)
    facts = P.get("facts") or {}
    facts["brand_auto"] = {"name": B["name"], "tagline": B["tagline"], "description": B["description"][:400], "url": B["url"], "cta": B["cta"],
                           "colors": (res.get("colors") or {}).get("palette") or [], "logo": res.get("logo_file") or ""}
    P.put("facts", facts)
    c = P.cfg
    if c.get("name") in (None, "", "Untitled film", "New film") or c.get("name_auto"):
        c["name"] = B["name"]; c["name_auto"] = True; P.save_cfg(c)
    return {"views": len(res["views"]), "framework": res.get("framework"), "name": B["name"]}


def step_plan(P, job, a):
    from .plan import plan
    sb = plan(P, job, template=a.template, use_llm=not a.no_llm)
    # a fresh plan invalidates the voice-over; footage is kept when recipes are unchanged
    return {"scenes": len(sb["scenes"]), "shots": len(sb["shots"])}


def step_voice(P, job, a):
    from .voice import voice
    return voice(P, job, line=a.line)


def step_capture(P, job, a):
    from .capture import capture
    from .timeline import shot_info
    set_min_lengths(P)
    only = [x for x in (a.shots or "").split(",") if x] or None
    if only is None and getattr(a, "missing_only", False):
        sb = P.get("storyboard")
        only = [s["id"] for s in sb["shots"] if not shot_info(P, s["id"], s)]
        if not only:
            job.msg("All shots are already recorded."); return {"recorded": [], "failed": [], "kept": len(sb["shots"])}
    return capture(P, job, only)


def step_timeline(P, job, a):
    from .timeline import build
    from .render import prepare
    if not P.get("storyboard"): return {"skipped": "no storyboard"}
    tl = build(P, job, preview=a.preview)
    prepare(P)
    return {"duration": tl["duration"], "scenes": len(tl["scenes"])}


def step_music(P, job, a):
    from .timeline import build
    from .music import music
    from .render import prepare
    build(P, job)
    r = music(P, job)
    prepare(P)
    return r


def step_render(P, job, a):
    from .timeline import build
    from .render import render, prepare
    from .music import mix
    from .mux import mux
    if getattr(a, "aspect", None):
        P.override = {"format": {"aspect": a.aspect}}
        try:
            return _render(P, job, a, build, render, mix, mux)
        finally:
            P.override = {}
            build(P, job); prepare(P)
    return _render(P, job, a, build, render, mix, mux)


def _render(P, job, a, build, render, mix, mux):
    with job.phase("timeline", 0.0, 0.02):
        build(P, job)
        if not os.path.exists(P.p("audio", "music.wav")):
            from .music import music
            music(P, job)
        else:
            mix(P, job)
    with job.phase("rendering", 0.02, 0.9):
        video = render(P, job, quality=a.quality)
    with job.phase("finishing", 0.9, 1.0):
        return mux(P, job, video, quality=a.quality)


def step_stills(P, job, a):
    from .render import stills
    from .timeline import build
    build(P, job)
    times = [float(x) for x in (a.times or "0").split(",") if x]
    paths, errs = stills(P, times, a.out or P.p("render", "stills"), scale=a.scale)
    return {"stills": paths, "errors": errs[:5]}


def step_auto(P, job, a):
    """everything, in order. The app is launched once and shared by the scout and the capture.
    Non-essential steps degrade instead of failing the film: no voice -> music-only film; no music ->
    sound design only; a shot that can't be recorded -> its screenshot is used."""
    from .source import AppServer
    order = ["scout", "plan", "voice", "capture", "music", "render"]
    start = order.index(a.start) if a.start in order else 0
    if start == 0 and a.skip_scout and P.get("scout"): start = 1
    span = {"scout": (0, .12), "plan": (.12, .15), "voice": (.15, .22), "capture": (.22, .55), "music": (.55, .6), "render": (.6, 1.0)}
    res, skipped = {}, []
    server = None
    try:
        for st in order[start:]:
            lo, hi = span[st]
            with job.phase(st, lo, hi):
                if st == "voice" and not (P.get("storyboard") or {}).get("vo", True):
                    continue
                if st == "capture":
                    a.missing_only = True
                    from .timeline import shot_info
                    sb = P.get("storyboard") or {}
                    todo = [s for s in sb.get("shots") or [] if not s.get("media") and not shot_info(P, s["id"], s)]
                    if todo and server is None and (P.cfg["source"].get("kind") not in ("url", "media")):
                        server = AppServer(P, job); server.__enter__(); P.shared_server = server
                try:
                    if st == "scout":
                        res[st] = step_scout(P, job, a, keep_server=True)
                        server = getattr(P, "shared_server", None) or None
                    else:
                        res[st] = STEPS[st](P, job, a)
                except DirectorError as e:
                    if st == "capture":
                        job.warn("No footage could be recorded (%s); the film uses the screenshots from the scout." % str(e).splitlines()[0]); skipped.append(st)
                    elif st in ("voice", "music"):
                        job.warn("%s failed, continuing without it: %s" % ("The voice-over" if st == "voice" else "The music", str(e).splitlines()[0]))
                        skipped.append(st)
                        if st == "voice":
                            write_json(P.p("vo", "clips.json"), {"voice": "none", "clips": {}})
                        else:
                            _silent_music(P)
                    else:
                        raise
    finally:
        srv = getattr(P, "shared_server", None)
        if srv is not None:
            P.shared_server = None; srv.stop()
    out = res.get("render") or {}
    if skipped and isinstance(out, dict): out["skipped"] = skipped
    return out


def _silent_music(P):
    """no score (e.g. the synth failed): keep the sound design and the voice"""
    from .timeline import build
    from .music import sfx, mix
    from . import ff as FF
    import numpy as np
    tl = build(P)
    os.makedirs(P.p("audio"), exist_ok=True)
    FF.write_wav(P.p("audio", "music.wav"), np.zeros((2, int(tl["duration"] * 48000))))
    try: FF.write_wav(P.p("audio", "sfx.wav"), sfx(tl))
    except Exception: pass  # noqa: BLE001
    mix(P)


STEPS = {"scout": step_scout, "plan": step_plan, "voice": step_voice, "capture": step_capture, "timeline": step_timeline,
         "music": step_music, "render": step_render, "stills": step_stills, "auto": step_auto}


def doctor():
    import importlib, shutil, subprocess
    from . import ff as FF
    from .voice import available
    from . import __version__
    out = {"python_version": sys.version.split()[0], "executable": sys.executable, "problems": [], "notes": [],
           "engine_version": __version__, "engine_path": os.path.dirname(os.path.dirname(os.path.abspath(__file__)))}
    if sys.version_info < (3, 9): out["problems"].append({"what": "Python 3.9 or newer (this is %s)" % out["python_version"], "fix": "install a recent Python (brew install python) and choose it in the Engine check"})
    pip = "%s -m pip install" % sys.executable
    for mod, pkg in (("numpy", "numpy"), ("scipy", "scipy"), ("PIL", "pillow"), ("playwright", "playwright")):
        try: importlib.import_module(mod)
        except ImportError: out["problems"].append({"what": "Python package %s" % pkg, "fix": "%s %s" % (pip, pkg)})
    for mod, pkg in (("fontTools", "fonttools"), ("brotli", "brotli")):
        try: importlib.import_module(mod)
        except ImportError: out["notes"].append({"what": "%s (for captions in Inter)" % pkg, "fix": "%s %s" % (pip, pkg)})
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            b = p.chromium.launch(); out["chromium"] = b.version; b.close()
    except Exception as e:  # noqa: BLE001
        out["problems"].append({"what": "Chromium for Playwright", "fix": "%s -m playwright install chromium" % sys.executable, "detail": str(e).splitlines()[0][:160]})
    try:
        out["ffmpeg"] = FF.ffmpeg(); out["libx264"] = FF.has_encoder("libx264"); out["libass"] = FF.has_filter("ass")
        if not (FF.has_encoder("libx264") or FF.has_encoder("h264_videotoolbox") or FF.has_encoder("libopenh264")):
            out["problems"].append({"what": "an H.264 encoder in ffmpeg", "fix": "brew install ffmpeg (macOS) / apt install ffmpeg"})
        if not FF.has_filter("ass"): out["notes"].append({"what": "libass in ffmpeg (burned-in captions)", "fix": "use a full ffmpeg build"})
    except Exception as e:  # noqa: BLE001
        out["problems"].append({"what": "ffmpeg", "fix": "brew install ffmpeg (macOS) / apt install ffmpeg (Linux) / set FFMPEG", "detail": str(e)})
    out["git"] = bool(shutil.which("git")); out["rscript"] = bool(shutil.which(os.environ.get("DIRECTOR_RSCRIPT") or "Rscript"))
    out["voices"] = available()
    out["cpus"] = os.cpu_count()
    out["ok"] = not out["problems"]
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(prog="director", description="DirectoR engine")
    ap.add_argument("step", choices=["doctor", "voices", "demo", "_shot", "_render"] + list(STEPS))
    ap.add_argument("--url"); ap.add_argument("--chunk", type=int, default=0)
    ap.add_argument("--project", "-p")
    ap.add_argument("--template"); ap.add_argument("--no-llm", action="store_true")
    ap.add_argument("--line"); ap.add_argument("--shots"); ap.add_argument("--preview", action="store_true")
    ap.add_argument("--quality", default="final", choices=["draft", "final"])
    ap.add_argument("--times"); ap.add_argument("--out"); ap.add_argument("--scale", type=float, default=0.5)
    ap.add_argument("--from", dest="start", default="scout"); ap.add_argument("--skip-scout", action="store_true")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--missing-only", action="store_true", help="capture: only shots without (up-to-date) footage")
    ap.add_argument("--mood", help="demo: mood(s) or sound effect(s), comma-separated, or 'all'")
    ap.add_argument("--harmony", default="auto"); ap.add_argument("--seed", type=int, default=7); ap.add_argument("--transpose", type=int, default=0)
    ap.add_argument("--bpm", type=float, default=0); ap.add_argument("--no-sfx", action="store_true"); ap.add_argument("--transcode")
    ap.add_argument("--quiet", action="store_true", help="report to status_quick.json (for small jobs that run beside a long one)")
    ap.add_argument("--aspect", help="render another format without changing the project (16:9, 9:16, 1:1, 4:5)")
    a = ap.parse_args(argv)
    if a.step == "doctor":
        d = doctor()
        if a.json: print(json.dumps(d))
        else:
            for p in d["problems"]: print("MISSING:", p["what"], "->", p["fix"])
            for n in d["notes"]: print("note:", n["what"], "->", n["fix"])
            print("voices:", ", ".join(k for k, v in d["voices"].items() if v["ok"]))
            print("doctor:", "all good" if d["ok"] else "%d problem(s)" % len(d["problems"]))
        return 0 if d["ok"] else 1
    if a.step == "demo":
        from .music import demo, MOODS, SFX_DEMOS
        out = a.out or os.path.join(os.path.expanduser("~"), ".cache", "director", "demos")
        if a.transcode:                                  # a WAV copy of a bundled MP3 (browsers that can't play MP3): fast
            from . import ff as FF
            name = os.path.splitext(os.path.basename(a.transcode))[0] + ".wav"; os.makedirs(out, exist_ok=True)
            if not os.path.exists(os.path.join(out, name)): FF.run("-i", a.transcode, "-ac", "2", "-ar", "44100", os.path.join(out, name))
            print(json.dumps({"mood": name, "file": name})); return 0
        which = [x for x in (a.mood or "all").split(",") if x]
        if which == ["all"]: which = list(SFX_DEMOS) + list(MOODS)
        files = {}
        for m in which:
            files[m] = demo(out, m, a.harmony or "auto", a.seed, a.transpose, a.bpm, not a.no_sfx)
            print(json.dumps({"mood": m, "file": files[m]}), flush=True)
        return 0
    if a.step == "_shot":                                # a capture worker (see capture.py)
        from .capture import record_one
        try:
            print(json.dumps(record_one(Project(a.project), a.shots, a.url))); return 0
        except Exception as e:  # noqa: BLE001
            print("ERROR: %s" % (str(e).splitlines()[0] if str(e) else e.__class__.__name__)); return 1
    if a.step == "_render":                              # a render worker (see render.py)
        from .render import render_worker
        try:
            render_worker(Project(a.project), a.chunk); return 0
        except Exception as e:  # noqa: BLE001
            print("ERROR: %s" % (str(e).splitlines()[0] if str(e) else e.__class__.__name__)); return 1
    if a.step == "voices":
        from .voice import available
        print(json.dumps(available())); return 0
    if not a.project: ap.error("--project is required")
    P = Project(a.project)
    job = Job(P, a.step, quiet=a.quiet)
    try:
        res = STEPS[a.step](P, job, a)
        job.done("Done", res)
        return 0
    except DirectorError as e:
        job.fail(e); return 2
    except KeyboardInterrupt:
        job.fail(DirectorError("Cancelled")); return 130
    except Exception as e:  # noqa: BLE001
        job.fail(e); return 1


if __name__ == "__main__":
    sys.exit(main())
