"""Shared helpers: project folders, atomic JSON, job status and logging.

A *project* is a folder (one film) with this layout:

    project.json      settings edited by the Shiny app (source, brand, look, voice, music, format)
    facts.json        what ingest learnt about the app (name, tagline, features, logo, launch command)
    scout.json        what the scout saw in the browser (views, tabs, inputs, outputs, colours)
    storyboard.json   scenes + voice-over lines + shot recipes (the editable plan)
    timeline.json     the storyboard resolved to absolute times (what the stage plays)
    status.json       progress of the running job (polled by the UI)
    log.txt           human-readable log of every job
    src/ scout/ shots/ vo/ audio/ render/ out/ stage/
"""
import datetime, json, os, re, shutil, sys, tempfile, time, traceback

ENGINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STAGE_SRC = os.path.join(ENGINE, "stage")
PY = sys.executable


def now_iso():
    return datetime.datetime.now().isoformat(timespec="seconds")


def read_json(path, default=None):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def write_json(path, data, indent=1):
    """atomic write (the UI may read the file at any moment)"""
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(os.path.abspath(path)), prefix=".tmp-", suffix=".json")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=indent, ensure_ascii=False)
    os.replace(tmp, path)


def slugify(s, maxlen=40):
    s = re.sub(r"[^A-Za-z0-9]+", "-", str(s or "")).strip("-").lower()
    return (s[:maxlen].strip("-") or "film")


def deep_merge(base, over):
    """recursive dict merge (over wins); lists are replaced"""
    out = dict(base or {})
    for k, v in (over or {}).items():
        out[k] = deep_merge(out.get(k), v) if isinstance(v, dict) and isinstance(out.get(k), dict) else v
    return out


DEFAULTS = {
    "name": "Untitled film",
    "source": {"kind": "url", "value": ""},
    "app": {"command": "", "cwd": "", "path": "/", "wait": 600, "env": {}, "renv": "ignore"},
    "brand": {"name": "", "tagline": "", "url": "", "colors": [], "logo": "", "description": ""},
    "film": {"template": "launch", "duration": 45, "tone": "confident", "audience": "", "language": "en"},
    "format": {"aspect": "16:9", "fps": 60, "quality": "final"},
    "look": {"theme": "auto", "transition": "auto", "window": "macos", "font": "Inter", "captions": "clean",
             "cursor": "mac", "background": "aurora", "radius": 22, "grain": True},
    "capture": {"viewport": "desktop", "scheme": "light", "fps": 60, "dpr": "auto", "workers": 3, "hide": "", "dismiss_cookies": True},
    "voice": {"provider": "auto", "voice": "", "rate": 1.0, "enabled": True},
    "music": {"mood": "auto", "bpm": 0, "key": "auto", "file": "", "volume": 0.0, "duck": 12, "sfx": True, "seed": 7},
    "llm": {"provider": "none", "model": "", "base_url": ""},
}

VIEWPORTS = {"desktop": (1440, 810), "laptop": (1280, 800), "wide": (1600, 900), "tablet": (1024, 768), "mobile": (390, 844)}
ASPECTS = {"16:9": (1920, 1080), "9:16": (1080, 1920), "1:1": (1080, 1080), "4:5": (1080, 1350)}


class Project:
    def __init__(self, root):
        self.root = os.path.abspath(root)
        self.override = {}                      # temporary settings (e.g. render another aspect ratio)
        os.makedirs(self.root, exist_ok=True)

    # ---- paths
    def p(self, *parts):
        return os.path.join(self.root, *parts)

    def d(self, *parts):
        path = self.p(*parts); os.makedirs(path, exist_ok=True); return path

    # ---- documents
    @property
    def cfg(self):
        return deep_merge(deep_merge(DEFAULTS, read_json(self.p("project.json"), {})), self.override)

    def save_cfg(self, cfg):
        write_json(self.p("project.json"), cfg)

    def get(self, name, default=None):
        return read_json(self.p(name + ".json"), default)

    def put(self, name, data):
        write_json(self.p(name + ".json"), data)

    @property
    def stage_size(self):
        return ASPECTS.get(self.cfg["format"].get("aspect", "16:9"), ASPECTS["16:9"])

    @property
    def viewport(self):
        c = self.cfg["capture"]
        v = c.get("viewport", "desktop")
        if isinstance(v, (list, tuple)) and len(v) == 2: return int(v[0]), int(v[1])
        if isinstance(v, str) and re.match(r"^\d+x\d+$", v): return tuple(int(x) for x in v.split("x"))
        return VIEWPORTS.get(v, VIEWPORTS["desktop"])


# ------------------------------------------------------------------ job status
class Job:
    """Progress reporter. Writes status.json (atomically) and appends to log.txt.

    Progress is hierarchical: `with job.phase("capture", 0.2, 0.8):` maps the
    phase's own 0..1 progress into the overall 0.2..0.8 range."""

    def __init__(self, project, name, quiet=False):
        self.P = project; self.name = name
        self.status_file = project.p("status_quick.json" if quiet else "status.json")
        self.t0 = time.time(); self.lo, self.hi = 0.0, 1.0
        self.stack = []; self.warnings = []
        self.state = {"job": name, "state": "running", "progress": 0.0, "message": "Starting…", "phase": "",
                      "started": now_iso(), "updated": now_iso(), "pid": os.getpid(), "warnings": []}
        self._last = 0
        self.log("=== %s started (%s)" % (name, now_iso()))
        self._write(force=True)

    def _write(self, force=False):
        t = time.time()
        if not force and t - self._last < 0.25: return
        self._last = t
        self.state["updated"] = now_iso(); self.state["elapsed"] = round(t - self.t0, 1)
        p = self.state["progress"]
        self.state["eta"] = round((t - self.t0) * (1 - p) / p, 0) if p > 0.03 else None
        try: write_json(self.status_file, self.state)
        except Exception as e:  # noqa: BLE001  (reporting must never break the work)
            print("status not written: %s" % e, flush=True)

    def log(self, msg):
        line = "[%s] %s" % (datetime.datetime.now().strftime("%H:%M:%S"), msg)
        print(line, flush=True)
        try:
            with open(self.P.p("log.txt"), "a", encoding="utf-8") as f:
                f.write(line + "\n")
        except OSError: pass

    def progress(self, frac, msg=None, force=False):
        frac = max(0.0, min(1.0, float(frac)))
        self.state["progress"] = round(self.lo + (self.hi - self.lo) * frac, 4)
        if msg:
            # log a message when its wording changes (numbers ignored), or every 15 s: counters don't flood the log
            stem = re.sub(r"[\d.,:]+", "#", msg)
            if stem != getattr(self, "_stem", None) or time.time() - getattr(self, "_logged", 0) > 15:
                self.log(msg); self._stem = stem; self._logged = time.time()
            self.state["message"] = msg
        self._write(force=force or bool(msg))

    def msg(self, msg):
        self.progress((self.state["progress"] - self.lo) / max(1e-9, self.hi - self.lo), msg)

    def warn(self, msg):
        self.log("WARNING: " + msg)
        self.state["warnings"] = (self.state.get("warnings") or [])[-19:] + [msg]
        self._write(force=True)

    class _Phase:
        def __init__(self, job, label, a, b): self.job, self.label, self.a, self.b = job, label, a, b
        def __enter__(self):
            j = self.job; j.stack.append((j.lo, j.hi, j.state.get("phase")))
            span = j.hi - j.lo; j.lo, j.hi = j.lo + span * self.a, j.lo + span * self.b
            j.state["phase"] = self.label; j.progress(0, self.label[:1].upper() + self.label[1:] + "…", force=True)
            return j
        def __exit__(self, *exc):
            j = self.job
            if not exc[0]: j.progress(1.0)
            j.lo, j.hi, ph = j.stack.pop(); j.state["phase"] = ph
            return False

    def phase(self, label, a, b):
        return Job._Phase(self, label, a, b)

    def done(self, msg="Done", result=None):
        self.lo, self.hi = 0.0, 1.0
        self.state.update({"state": "done", "progress": 1.0, "message": msg, "result": result, "finished": now_iso()})
        self.log("=== %s done in %.0fs: %s" % (self.name, time.time() - self.t0, msg))
        self._write(force=True)

    def fail(self, err):
        tb = traceback.format_exc()
        msg = str(err) or err.__class__.__name__
        self.state.update({"state": "error", "message": msg, "error": msg, "finished": now_iso()})
        self.log("ERROR: " + msg)
        if tb and "NoneType: None" not in tb: self.log(tb)
        self._write(force=True)


class DirectorError(Exception):
    """An error with a message meant for the user (shown as-is in the UI)."""


def which(name):
    return shutil.which(name)


def tail(path, n=30):
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            return "".join(f.readlines()[-n:])
    except OSError:
        return ""


# ------------------------------------------------------------------ supervised worker processes
def run_workers(tasks, workers, cmd, prog_file, job=None, stall_s=240, retries=1, on_tick=None, env=None):
    """Run `cmd(task) -> argv` for every task in separate processes, at most `workers` at a time.
    A worker whose progress file (`prog_file(task)`) hasn't changed for `stall_s` seconds is killed.
    Failed or killed tasks are retried `retries` times. Returns {task: (ok, output_tail)}.
    Unlike a process pool, a hung browser can't block the whole job."""
    import subprocess, signal
    queue = [(t, 0) for t in tasks]; running = {}; result = {}
    envx = dict(os.environ); envx.update(env or {})
    def sig(p):
        try:
            mt = os.path.getmtime(prog_file(p)) if os.path.exists(prog_file(p)) else 0
        except OSError: mt = 0
        return mt
    while queue or running:
        while queue and len(running) < max(1, workers):
            t, attempt = queue.pop(0)
            try: os.remove(prog_file(t))
            except OSError: pass
            logf = tempfile.NamedTemporaryFile(prefix="drw-", suffix=".log", delete=False)
            pr = subprocess.Popen(cmd(t), stdout=logf, stderr=subprocess.STDOUT, env=envx, start_new_session=(os.name != "nt"))
            running[t] = {"p": pr, "attempt": attempt, "log": logf.name, "last": time.time(), "sig": 0}
        for t, r in list(running.items()):
            s_ = sig(t)
            if s_ != r["sig"]: r["sig"] = s_; r["last"] = time.time()
            rc = r["p"].poll()
            stalled = rc is None and time.time() - r["last"] > stall_s
            if stalled:
                try:
                    if os.name != "nt": os.killpg(r["p"].pid, signal.SIGKILL)
                    else: r["p"].kill()
                except Exception: pass  # noqa: BLE001
                r["p"].wait(10); rc = -9
                if job: job.warn("a worker made no progress for %ds and was restarted" % stall_s)
            if rc is None: continue
            out = tail(r["log"], 15)
            try: os.remove(r["log"])
            except OSError: pass
            del running[t]
            if rc == 0: result[t] = (True, out)
            elif r["attempt"] < retries:
                if job: job.log("retrying %s (%s)" % (t, (out.strip().splitlines() or ["failed"])[-1][:140]))
                queue.append((t, r["attempt"] + 1))
            else: result[t] = (False, out)
        if on_tick: on_tick(running, result)
        time.sleep(0.4)
    return result
