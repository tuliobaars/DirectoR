"""Render the stage (timeline.json) to video frames with Chromium, in parallel chunks.

The stage page is a pure function of time: for every output frame we call
Stage.render(t), wait for images and fonts, and screenshot it. Frames are piped
into ffmpeg. Quality presets:
  draft   half resolution, 30 fps, fast encode (for checking the cut)
  final   full resolution, 60 fps (or project fps), high quality
"""
import base64, json, os, shutil, subprocess, time
from concurrent.futures import ProcessPoolExecutor

from . import ff as FF
from .fonts import inter_woff2
from .util import STAGE_SRC, DirectorError, read_json, write_json

QUALITY = {"draft": {"scale": 0.5, "fps": 30, "crf": 24, "preset": "veryfast", "jpeg": 82},
           "final": {"scale": 1.0, "fps": None, "crf": 17, "preset": "medium", "jpeg": 94}}

PAGE = """<!doctype html><html><head><meta charset="utf-8"><link rel="stylesheet" href="stage/stage.css?v={v}">
<style>html,body{{width:{W}px;height:{H}px}}</style></head>
<body><div id="stage"></div>
<script src="stage/timeline.js?v={v}"></script><script src="stage/stage.js?v={v}"></script><script src="stage/film.js?v={v}"></script>{extra}
<script>
window.READY = false;
(document.fonts && document.fonts.load ? Promise.all([document.fonts.load("700 100px Inter"), document.fonts.load("500 40px Inter"), document.fonts.load("800 100px Inter")]) : Promise.resolve())
  .catch(function () {{}}).then(function () {{ var q = location.search.match(/[?&]scale=([\d.]+)/); Stage.init(window.TL, {{ preview: {preview}, scale: q ? parseFloat(q[1]) : 1 }}); window.READY = true; {after} }});
</script></body></html>"""


def prepare(P, preview=False):
    """copy the stage into the project and write stage.html / preview.html + stage/timeline.js"""
    sd = P.d("stage")
    for f in ("stage.css", "stage.js", "film.js", "preview.js", "preview.css"):
        src = os.path.join(STAGE_SRC, f)
        if os.path.exists(src): _atomic_copy(src, os.path.join(sd, f))
    font = inter_woff2()
    if font and not os.path.exists(os.path.join(sd, "inter.woff2")):
        open(os.path.join(sd, "inter.woff2"), "wb").write(font)
    tl = P.get("timeline")
    if not tl: raise DirectorError("Build the timeline first.")
    cursors = {}
    for sc in tl["scenes"]:
        infos = [sc.get("info")] + [it.get("info") for it in sc.get("items") or []]
        shots = [sc.get("shot")] + [it.get("shot") for it in sc.get("items") or []]
        for sid, info in zip(shots, infos):
            if sid and info and info.get("cursor") and sid not in cursors:
                cursors[sid] = read_json(P.p(info["cursor"]), [])
    audio = ""
    if os.path.exists(P.p("audio", "mix.wav")):
        # served by the app's media route (byte ranges: Safari needs them); relative to <app>/drp/<project>/preview.html
        import urllib.parse
        audio = "../../drm/p/%s/audio/mix.wav?v=%d" % (urllib.parse.quote(os.path.basename(P.root)), int(os.path.getmtime(P.p("audio", "mix.wav"))))
    v = str(int(time.time()))
    _atomic_write(os.path.join(sd, "timeline.js"), "window.TL = %s;\nwindow.CURSORS = %s;\nwindow.AUDIO = %s;\n" % (json.dumps(tl), json.dumps(cursors, separators=(",", ":")), json.dumps(audio)))
    W, H = tl["W"], tl["H"]
    _atomic_write(P.p("stage.html"), PAGE.format(v=v, W=W, H=H, extra="", preview="false", after=""))
    _atomic_write(P.p("preview.html"), PAGE.format(v=v, W=W, H=H, preview="true", extra='<script src="stage/preview.js?v=%s"></script>' % v,
                                                   after="window.Player && Player.start();").replace(
        "<style>html,body{width:%dpx;height:%dpx}</style>" % (W, H), "<link rel='stylesheet' href='stage/preview.css?v=%s'>" % v))
    return P.p("stage.html")


def _atomic_write(path, text):
    tmp = path + ".tmp%d" % os.getpid()
    with open(tmp, "w", encoding="utf-8") as f: f.write(text)
    os.replace(tmp, path)


def _atomic_copy(src, dst):
    tmp = dst + ".tmp%d" % os.getpid()
    shutil.copyfile(src, tmp); os.replace(tmp, dst)


def _browser(pw, W, H, scale):
    b = pw.chromium.launch(args=["--force-color-profile=srgb", "--font-render-hinting=none", "--hide-scrollbars", "--allow-file-access-from-files",
                                 "--disable-web-security", "--autoplay-policy=no-user-gesture-required"])
    # scale < 1: a smaller viewport and a scaled stage (Chromium ignores device_scale_factor < 1)
    ctx = b.new_context(viewport={"width": int(round(W * min(1, scale))), "height": int(round(H * min(1, scale)))}, device_scale_factor=max(1, scale))
    return b, ctx


def _open(pw, page_path, W, H, scale):
    b, ctx = _browser(pw, W, H, scale)
    pg = ctx.new_page(); errs = []
    pg.on("pageerror", lambda e: errs.append(str(e)[:300]))
    pg.on("console", lambda m: errs.append(m.text[:300]) if m.type == "error" else None)
    pg.goto("file://" + page_path + ("?scale=%s" % scale if scale < 1 else ""))
    pg.wait_for_function("window.READY === true", timeout=60000)
    return b, ctx, pg, errs


def render_range(args):
    root, page, W, H, f0, f1, fps, out, q, prog_file = args
    from playwright.sync_api import sync_playwright
    with sync_playwright() as pw:
        b, ctx, pg, errs = _open(pw, page, W, H, q["scale"])
        cdp = ctx.new_cdp_session(pg)
        vf = ["-vf", "noise=c0s=5:c0f=t+u"] if q.get("grain") else []          # subtle temporal film grain
        ffp = subprocess.Popen([FF.ffmpeg(), "-y", "-loglevel", "error", "-f", "image2pipe", "-framerate", str(fps), "-c:v", "mjpeg", "-i", "-"]
                               + vf + FF.h264(q["crf"], q["preset"]) + ["-r", str(fps), out], stdin=subprocess.PIPE, stderr=subprocess.PIPE)
        for fi in range(f0, f1):
            pg.evaluate("t => Stage.render(t)", fi / fps)
            d = cdp.send("Page.captureScreenshot", {"format": "jpeg", "quality": q["jpeg"], "optimizeForSpeed": True})
            ffp.stdin.write(base64.b64decode(d["data"]))
            if (fi - f0) % 20 == 0:
                write_json(prog_file, {"done": fi - f0, "total": f1 - f0})
        ffp.stdin.close(); ffp.wait()
        write_json(prog_file, {"done": f1 - f0, "total": f1 - f0})
        b.close()
        if ffp.returncode != 0: raise RuntimeError("ffmpeg: " + ffp.stderr.read().decode(errors="replace")[-400:])
        return errs


def render_worker(P, chunk):
    """worker process: render one chunk of frames (called by `python -m director _render`)"""
    jobs = read_json(P.p("render", "_jobs.json"), [])
    j = next(x for x in jobs if x["i"] == chunk)
    errs = render_range((P.root, j["page"], j["W"], j["H"], j["f0"], j["f1"], j["fps"], j["out"], j["q"], j["prog"]))
    pr = read_json(j["prog"], {}) or {}; pr["errors"] = errs[:5]; write_json(j["prog"], pr)


def stills(P, times, out_dir, scale=0.5, preview=False):
    """a few frames as JPEG (storyboard thumbnails, posters, checks)"""
    page = prepare(P)
    tl = P.get("timeline"); W, H = tl["W"], tl["H"]
    from playwright.sync_api import sync_playwright
    os.makedirs(out_dir, exist_ok=True); paths = []
    with sync_playwright() as pw:
        b, ctx, pg, errs = _open(pw, page, W, H, scale)
        cdp = ctx.new_cdp_session(pg)
        for t in times:
            pg.evaluate("t => Stage.render(t)", t)
            d = cdp.send("Page.captureScreenshot", {"format": "jpeg", "quality": 85})
            p = os.path.join(out_dir, "t%07.3f.jpg" % t); open(p, "wb").write(base64.b64decode(d["data"])); paths.append(p)
        b.close()
    return paths, errs


def render(P, job, quality="final", workers=None):
    q = dict(QUALITY.get(quality, QUALITY["final"]))
    tl = P.get("timeline")
    if not tl: raise DirectorError("Build the timeline first.")
    page = prepare(P)
    W, H = tl["W"], tl["H"]
    q["grain"] = bool((tl.get("theme") or {}).get("grain"))
    fps = q["fps"] or int(tl.get("fps") or 60)
    dur = float(tl["duration"])
    n_frames = int(round(dur * fps))
    workers = workers or int(P.cfg["format"].get("render_workers") or max(2, min(8, (os.cpu_count() or 4) - 1)))
    rd = P.d("render")
    for f in os.listdir(rd):
        if f.startswith("part") or f.startswith("_prog"): os.remove(os.path.join(rd, f))
    step = (n_frames + workers - 1) // workers
    jobs = []
    for i in range(workers):
        s, e = i * step, min(n_frames, (i + 1) * step)
        if s >= e: continue
        jobs.append({"i": i, "page": page, "W": W, "H": H, "f0": s, "f1": e, "fps": fps, "out": os.path.join(rd, "part%02d.mp4" % i), "q": q,
                     "prog": os.path.join(rd, "_prog%02d.json" % i)})
    write_json(os.path.join(rd, "_jobs.json"), jobs)
    job.progress(0.0, "Rendering %d frames (%dx%d, %d fps) in %d workers…" % (n_frames, int(W * q["scale"]), int(H * q["scale"]), fps, len(jobs)))
    t0 = time.time()
    from .util import run_workers, ENGINE, PY
    def tick(running, done):
        d = sum((read_json(j["prog"], {}) or {}).get("done", 0) for j in jobs)
        el = time.time() - t0
        job.progress(d / max(1, n_frames), "Rendering… %d/%d frames (%.1f fps)" % (d, n_frames, d / max(1e-3, el)))
    res = run_workers([j["i"] for j in jobs], len(jobs), lambda i: [PY, "-m", "director", "_render", "--project", P.root, "--chunk", str(i)],
                      lambda i: jobs[[j["i"] for j in jobs].index(i)]["prog"], job=job, stall_s=300, retries=1, on_tick=tick, env={"PYTHONPATH": ENGINE})
    bad = [i for i, (ok, _) in res.items() if not ok]
    if bad:
        raise DirectorError("Rendering failed: %s" % (res[bad[0]][1].strip().splitlines() or ["unknown error"])[-1][:300])
    errs_all = []
    for j in jobs: errs_all += (read_json(j["prog"], {}) or {}).get("errors") or []
    if errs_all: job.warn("stage errors: " + "; ".join(sorted(set(errs_all))[:3]))
    lst = os.path.join(rd, "parts.txt")
    open(lst, "w").write("".join("file '%s'\n" % j["out"] for j in jobs))
    out = os.path.join(rd, "video_%s.mp4" % quality)
    FF.run("-f", "concat", "-safe", "0", "-i", lst, "-c", "copy", out)
    job.log("rendered %s in %.0fs" % (out, time.time() - t0))
    return out
