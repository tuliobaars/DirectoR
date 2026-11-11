"""Record the shots of a storyboard (deterministic 60 fps frames), in parallel browsers.

Action vocabulary (shot.actions):
  wait ms | drift ms | show | hide | settle ms (until the app is idle)
  move target | hover target | click target | type target text | key key
  select target option (index or text) | slide target to (0..1 of the track)
  scroll to (px | "bottom" | "next" | target) ms | goto url | js code
Any action can carry "rec": false (done off camera) and "mark": "name" (a named frame).
Targets: {"css": ..., "text": ..., "kind": tab|button|link|slider|select|selectize, "nth": 0} or {"x": px, "y": px}
or {"fx": 0..1, "fy": 0..1} (fraction of the viewport).
"""
import glob, json, os, shutil, subprocess, sys, time, traceback, urllib.parse
from concurrent.futures import ProcessPoolExecutor, as_completed

from . import ff as FF
from .util import Project, DirectorError, read_json, write_json


def recipe_hash(shot):
    """what makes footage stale: where it starts and what it does (not its name)"""
    import hashlib
    key = {"reach": shot.get("reach"), "actions": shot.get("actions"), "media": shot.get("media")}
    return hashlib.sha1(json.dumps(key, sort_keys=True).encode()).hexdigest()[:12]


def est_ms(shot):
    t = 600
    for a in shot.get("actions") or []:
        if a.get("rec") is False: continue
        d = a.get("do")
        t += a.get("ms") or {"click": 700, "move": 600, "hover": 1200, "select": 1500, "slide": 1600, "type": 1200, "show": 250, "hide": 250, "settle": 900, "scroll": 2500}.get(d, 500)
        if d == "click": t += 350
    return t


# ------------------------------------------------------------------ one shot (runs in a worker process)
def _find(r, target, ensure=True, cur=None):
    from .scout import FIND_JS
    if target is None: return None
    if "x" in target and "y" in target: return {"x": float(target["x"]), "y": float(target["y"])}
    if "fx" in target: return {"x": float(target["fx"]) * r.vw, "y": float(target["fy"]) * r.vh}
    bb = r.js(FIND_JS, target)
    if not bb and target.get("kind") == "tab" and cur is not None:
        # narrow layout: the tab is behind a menu button; open it on camera, then look again
        from .scout import OPEN_MENU_JS
        mb = r.js(OPEN_MENU_JS)
        if mb:
            cur.move((mb["x"], mb["y"]), 550); cur.click(mark="click_menu"); r.settle(max_ms=2500, min_ms=450)
            bb = r.js(FIND_JS, target)
    if not bb: return None
    if ensure and (bb["y"] < 70 or bb["y"] > r.vh - 60):
        y = r.scroll_y() + bb["y"] - r.vh * 0.5
        r.scroll_rec(max(0, y), 700)
        bb = r.js(FIND_JS, target)
    return bb


def run_actions(r, cur, actions, log):
    for a in actions:
        d = a.get("do"); rec = a.get("rec", True); ms = a.get("ms")
        try:
            if d == "wait": (r.rec if rec else r.idle)(ms or 600)
            elif d == "drift": cur.drift(ms or 1200, record=rec)
            elif d == "show": cur.show(ms or 250, record=rec)
            elif d == "hide": cur.hide(ms or 250, record=rec)
            elif d == "settle": r.settle(max_ms=max(ms or 1500, 1500) * 3, min_ms=ms or 900, record=rec)
            elif d == "goto":
                u = urllib.parse.urljoin(r.page.url, a.get("url") or "/"); r.goto(u, settle_ms=600); cur.install()
            elif d == "js": r.js(a.get("code") or "0")
            elif d == "key":
                r.page.keyboard.press(a.get("key") or "Enter"); (r.rec if rec else r.idle)(ms or 300)
            elif d == "scroll":
                to = a.get("to", "next")
                if to == "bottom": y = r.max_scroll()
                elif to == "top": y = 0
                elif to == "next": y = r.scroll_y() + r.vh * 0.8
                elif isinstance(to, dict):
                    bb = _find(r, to, ensure=False); y = r.scroll_y() + (bb["y"] - r.vh * 0.35 if bb else r.vh * 0.8)
                else: y = float(to)
                r.scroll_rec(y, ms or 2500, record=rec)
            elif d in ("move", "hover", "click", "type", "select"):
                bb = _find(r, a.get("target"), cur=cur if rec else None)
                if not bb:
                    log("  target not found: %s" % json.dumps(a.get("target"))[:120]); continue
                cur.move((bb["x"], bb["y"]), ms or 650, record=rec)
                if d == "hover": cur.drift(a.get("hold") or 700, record=rec)
                if d in ("click", "type", "select"):
                    cur.click(record=rec, mark=a.get("mark"))
                if d == "type":
                    for ch in a.get("text") or "":
                        r.page.keyboard.type(ch); (r.rec if rec else r.idle)(1000 / max(4, a.get("cps") or 14))
                    if a.get("enter"): r.page.keyboard.press("Enter")
                if d == "select":
                    (r.rec if rec else r.idle)(350)
                    opt = a.get("option", 1)
                    if bb.get("tag") == "select" and not r.js("(t) => { const e = document.querySelector(t); return !!(e && e.nextElementSibling && e.nextElementSibling.classList.contains('selectize-control')); }", a["target"].get("css") or "x"):
                        sel = r.page.locator(a["target"]["css"]).first
                        if isinstance(opt, int): sel.select_option(index=opt)
                        else: sel.select_option(label=str(opt))
                        (r.rec if rec else r.idle)(300)
                    else:
                        # selectize / custom dropdown: click the option in the open menu
                        o = r.js("""(opt) => { const items = [...document.querySelectorAll('.selectize-dropdown-content .option, .selectize-dropdown .option, [role="option"], .dropdown-item')].filter(e => e.getBoundingClientRect().height > 0);
                                    if (!items.length) return null; let e = typeof opt === 'number' ? items[Math.min(opt, items.length - 1)] : items.find(x => x.innerText.trim() === opt) || items[1] || items[0];
                                    const r = e.getBoundingClientRect(); return {x: r.left + Math.min(r.width / 2, 90), y: r.top + r.height / 2}; }""", opt)
                        if o:
                            cur.move((o["x"], o["y"]), 550, record=rec); cur.click(record=rec, mark=(a.get("mark") or "click") + "_opt")
                        else:
                            r.page.keyboard.press("Escape")
            elif d == "slide":
                bb = _find(r, a.get("target"))
                if not bb: log("  slider not found"); continue
                if bb.get("slider") and bb.get("line"):
                    lx, ly, lw = bb["line"]; x1 = lx + lw * float(a.get("to", 0.7))
                else:
                    x1 = bb["x"] + (bb.get("w") or 200) * 0.3
                cur.drag((bb["x"], bb["y"]), (x1, bb["y"]), ms or 1200, record=rec, mark=a.get("mark"))
            else:
                log("  unknown action %s" % d)
        except Exception as e:  # noqa: BLE001
            log("  action %s failed: %s" % (d, str(e).splitlines()[0][:160]))
            cur.install()


def record_shot(args):
    root, shot, url, opts = args
    P = Project(root)
    out = P.p("shots", shot["id"])
    logf = open(P.p("shots", "_log_%s.txt" % shot["id"]), "w", buffering=1)
    log = lambda m: logf.write(m + "\n")
    prog = P.p("shots", "_prog_%s.json" % shot["id"])
    t0 = time.time()
    from .recorder import Recorder, Cursor
    r = None
    try:
        r = Recorder(None, width=opts["vw"], height=opts["vh"], scale=opts["dpr"], scheme=opts["scheme"], fps=opts["fps"],
                     cursor_style=opts["cursor"], ring=opts["ring"], hide_css=opts["hide_css"], log=log, lite=opts.get("lite", False))
        reach = shot.get("reach") or {}
        target = urllib.parse.urljoin(url, reach.get("url") or "/") if reach.get("url") not in (None, "", "/") else url
        r.goto(target, settle_ms=900, dismiss=opts["dismiss"])
        if reach.get("tab"):
            from .scout import FIND_JS
            bb = r.js(FIND_JS, {"kind": "tab", "text": reach["tab"]})
            if bb: r.page.mouse.click(bb["x"], bb["y"]); r.settle(max_ms=8000, min_ms=900, record=False)
        if reach.get("scroll"): r.js("(y) => window.scrollTo(0, y)", reach["scroll"]); r.idle(300)
        r.set_out(out)
        cur = Cursor(r, hidden=opts["cursor"] == "none")
        expected = max(1, int(est_ms(shot) / r.dt))
        orig = r.rec_frame
        def counted():
            orig()
            if r.n % 15 == 0: write_json(prog, {"n": r.n, "expected": expected})
        r.rec_frame = counted
        run_actions(r, cur, shot.get("actions") or [], log)
        min_ms = float(shot.get("min_ms") or 0)
        if r.n * r.dt < min_ms: cur.drift(min_ms - r.n * r.dt)
        r.finish({"shot": shot["id"], "label": shot.get("label"), "url": r.page.url, "recipe": recipe_hash(shot), "viewport_name": opts.get("viewport_name")})
        write_json(prog, {"n": r.n, "expected": r.n, "done": True})
        errs = r.errors[:5]
        return shot["id"], r.n, round(time.time() - t0, 1), errs, None
    except Exception as e:  # noqa: BLE001
        log(traceback.format_exc())
        return shot["id"], (r.n if r else 0), round(time.time() - t0, 1), [], str(e).splitlines()[0][:300] if str(e) else e.__class__.__name__
    finally:
        if r: r.close()
        logf.close()


# ------------------------------------------------------------------ proxies (half-size, every 2nd frame) for the live preview
def make_proxy(shot_dir, width=960):
    pdir = os.path.join(shot_dir, "proxy")
    if os.path.isdir(pdir): shutil.rmtree(pdir)
    os.makedirs(pdir)
    frames = sorted(glob.glob(os.path.join(shot_dir, "f*.jpg")))
    if not frames: return 0
    from PIL import Image
    n = 0
    for f in frames[::2]:
        im = Image.open(f); h = int(im.height * width / im.width)
        im.resize((width, h), Image.BILINEAR).save(os.path.join(pdir, os.path.basename(f)), quality=72)
        n += 1
    return n


def _proxy_job(d):
    return d, make_proxy(d)


# ------------------------------------------------------------------ media shots (uploaded images / videos)
def media_shot(P, shot, fps, job):
    src = shot["media"]
    path = src if os.path.isabs(src) else P.p(src)
    out = P.p("shots", shot["id"])
    if os.path.isdir(out): shutil.rmtree(out)
    os.makedirs(out)
    ext = os.path.splitext(path)[1].lower()
    if ext in (".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp"):
        from PIL import Image
        im = Image.open(path).convert("RGB")
        im.save(os.path.join(out, "still.jpg"), quality=92)
        write_json(os.path.join(out, "meta.json"), {"fps": fps, "still": True, "frames": 0, "size": list(im.size), "viewport": list(im.size), "recipe": recipe_hash(shot)})
        return 0
    # video -> frames at fps, max 1920 wide
    FF.run("-i", path, "-vf", "fps=%d,scale='min(2880,iw)':-2" % fps, "-q:v", "3", os.path.join(out, "f%05d.jpg"))
    frames = sorted(glob.glob(os.path.join(out, "f*.jpg")))
    for i, f in enumerate(frames):                 # ffmpeg numbers from 1; we want 0
        os.rename(f, os.path.join(out, "f%05d.jpg" % i))
    from PIL import Image
    w, h = Image.open(os.path.join(out, "f00000.jpg")).size if frames else (1920, 1080)
    write_json(os.path.join(out, "meta.json"), {"fps": fps, "frames": len(frames), "viewport": [w, h], "dpr": 1, "media": True, "recipe": recipe_hash(shot)})
    write_json(os.path.join(out, "markers.json"), {})
    return len(frames)


# ------------------------------------------------------------------ the capture job
def capture(P, job, only=None):
    from .source import AppServer
    cfg = P.cfg; sb = P.get("storyboard")
    if not sb: raise DirectorError("Plan the film first (Story).")
    shots = [s for s in sb["shots"] if not only or s["id"] in only]
    if not shots: raise DirectorError("No shots to record.")
    c = cfg["capture"]; vw, vh = P.viewport
    fps = int(c.get("fps") or 60)
    os.makedirs(P.p("shots"), exist_ok=True)
    media = [s for s in shots if s.get("media")]
    live = [s for s in shots if not s.get("media")]
    for i, s in enumerate(media):
        job.progress(i / max(1, len(shots)), "Importing %s…" % s["label"])
        media_shot(P, s, fps, job)
    results = []
    if live:
        look = cfg["look"]
        colors = (P.get("scout") or {}).get("colors", {}).get("palette") or []
        ring = "rgba(0,113,227,.28)"
        if colors:
            h = colors[0].lstrip("#"); ring = "rgba(%d,%d,%d,.30)" % tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))
        hide = c.get("hide") or ""
        hide_css = ("%s{display:none!important}" % hide) if hide.strip() else ""
        opts = {"vw": vw, "vh": vh, "dpr": 1.0, "scheme": c.get("scheme") or "light", "fps": fps,
                "cursor": look.get("cursor") or "mac", "ring": ring, "hide_css": hide_css, "dismiss": bool(c.get("dismiss_cookies", True))}
        with AppServer(P, job) as url:
            lite = c.get("lite", "auto"); dpr = c.get("dpr", "auto")
            if lite == "auto" or dpr in ("auto", None, ""):
                sc = P.get("scout") or {}
                cost = sc.get("frame_cost") if list(sc.get("viewport") or []) == [vw, vh] else None
                if cost is None:
                    job.msg("Measuring how heavy the page is to record…")
                    from .recorder import Recorder
                    pr = None
                    try:
                        pr = Recorder(None, width=vw, height=vh, scale=1, scheme=opts["scheme"], fps=fps, log=job.log)
                        pr.goto(url, settle_ms=600, dismiss=opts["dismiss"]); cost = pr.frame_cost(6)
                    except Exception as e:  # noqa: BLE001
                        job.log("  probe failed (%s); assuming a heavy page" % str(e).splitlines()[0][:100]); cost = 1.0
                    finally:
                        if pr: pr.close()
                heavy = cost > 0.25
                if lite == "auto": lite = heavy
                if dpr in ("auto", None, ""): dpr = 1.0 if heavy else 1.5
                job.log("frame cost %.0f ms -> %s, %.1fx sharpness" % (cost * 1000, "lite effects (heavy blurs replaced by look-alikes)" if lite else "full effects", float(dpr)))
            opts["dpr"] = float(dpr)
            opts["lite"] = bool(lite)
            workers = max(1, min(int(c.get("workers") or 3), len(live), os.cpu_count() or 2))
            job.progress(0.05, "Recording %d shot%s in %d browser%s…" % (len(live), "s" if len(live) > 1 else "", workers, "s" if workers > 1 else ""))
            byid = {s["id"]: s for s in live}
            optf = P.p("shots", "_opts.json"); write_json(optf, opts)
            from .util import run_workers, ENGINE, PY
            def cmd(sid): return [PY, "-m", "director", "_shot", "--project", P.root, "--shots", sid, "--url", url]
            def prog(sid): return P.p("shots", "_prog_%s.json" % sid)
            def tick(running, done):
                tot = exp = 0
                for s in live:
                    pr_ = read_json(prog(s["id"]), {}) or {}
                    e = pr_.get("expected") or est_ms(s) / (1000 / fps); tot += min(pr_.get("n", 0) if s["id"] not in done else e, e); exp += e
                job.progress(0.05 + 0.8 * tot / max(1, exp), "Recording… %d/%d shots done" % (len(done), len(live)))
            out = run_workers(list(byid), workers, cmd, prog, job=job, stall_s=float(c.get("stall") or 240), retries=1, on_tick=tick,
                              env={"PYTHONPATH": ENGINE})
            for sid, (ok_, log_) in out.items():
                meta = read_json(P.p("shots", sid, "meta.json"), None)
                if ok_ and meta:
                    results.append((sid, meta.get("frames", 0), None)); job.log("recorded %s: %d frames" % (sid, meta.get("frames", 0)))
                else:
                    err = (log_.strip().splitlines() or ["unknown error"])[-1][:200]
                    results.append((sid, 0, err)); job.warn("shot %s could not be recorded (%s); its screenshot is used instead" % (sid, err))
    ok = [s for s in live if not any(r[0] == s["id"] and r[2] for r in results)]
    job.progress(0.87, "Building preview proxies…")
    dirs = [P.p("shots", s["id"]) for s in ok + media if glob.glob(P.p("shots", s["id"], "f*.jpg"))]
    if dirs:
        try:
            with ProcessPoolExecutor(max_workers=min(4, len(dirs))) as ex:
                list(ex.map(_proxy_job, dirs))
        except Exception as e:  # noqa: BLE001  (previews then load the full frames; slower but fine)
            job.warn("preview proxies not made: %s" % str(e).splitlines()[0][:120])
    failed = [r[0] for r in results if r[2]]
    if failed and len(failed) == len(live): raise DirectorError("All shots failed to record. See the log.")
    return {"recorded": [s["id"] for s in ok + media], "failed": failed}


def record_one(P, sid, url):
    """worker process: record one shot (called by `python -m director _shot`)"""
    sb = P.get("storyboard"); shot = next((x for x in sb["shots"] if x["id"] == sid), None)
    if not shot: raise DirectorError("no shot %s" % sid)
    opts = read_json(P.p("shots", "_opts.json"), {})
    write_json(P.p("shots", "_prog_%s.json" % sid), {"n": 0, "expected": 1, "stage": "opening"})
    sid_, n, secs, errs, err = record_shot((P.root, shot, url, opts))
    if err: raise DirectorError(err)
    return {"shot": sid, "frames": n, "seconds": secs, "page_errors": errs}
