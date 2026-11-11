"""Ingest a source (live URL, git repository, zip, local folder or media files),
detect what kind of app it is, learn facts about it, and launch it locally.

Supported app kinds (first match wins, shallowest folder first):
  shiny-r      app.R, or ui.R + server.R (also inside an R package / golem / rhino project)
  golem        R package with R/run_app.R and no app.R          -> pkgload::load_all(); run_app()
  rpkg-app     R package with inst/<dir>/app.R                   -> pkgload::load_all(); runApp(inst/<dir>)
  shiny-py     app.py importing shiny                            -> python -m shiny run
  streamlit    *.py importing streamlit                          -> streamlit run
  gradio       *.py importing gradio                             -> python file.py (GRADIO_SERVER_PORT)
  quarto       _quarto.yml (needs quarto)                        -> quarto preview
  node         package.json with a dev/start script              -> npm run dev|start (PORT)
  static       index.html (root, docs/, dist/, build/, public/, _site/, site/) or a lone *.html
A custom launch command (project.json app.command, with {port}) overrides detection.
"""
import glob, json, os, re, shutil, signal, socket, subprocess, sys, time, urllib.request, zipfile

from .util import DirectorError, read_json, tail, which, PY

SKIP_DIRS = {".git", "node_modules", "renv", "packrat", "__MACOSX", ".Rproj.user", "__pycache__", ".venv", "venv", "env",
             ".quarto", "revdep", ".github", ".idea", ".vscode", "tests", "test", "man", "vignettes", "data-raw"}
GIT_HOSTS = ("github.com", "gitlab.com", "bitbucket.org", "codeberg.org", "git.sr.ht")


# ------------------------------------------------------------------ classify a pasted link
def classify(value):
    """what a pasted string most likely is: url | git | dir | zip"""
    v = (value or "").strip()
    if not v: return "none"
    if os.path.isdir(os.path.expanduser(v)):
        d = os.path.expanduser(v)
        return "git" if os.path.exists(os.path.join(d, "HEAD")) and os.path.isdir(os.path.join(d, "objects")) else "dir"   # a bare repository
    if v.lower().endswith(".zip") and os.path.exists(os.path.expanduser(v)): return "zip"
    if v.endswith(".git") or v.startswith("git@"): return "git"
    m = re.match(r"^https?://([^/]+)/([^/]+)/([^/#?]+)", v)
    if m and any(m.group(1).endswith(h) for h in GIT_HOSTS):
        return "git"
    if re.match(r"^(https?://|localhost|127\.0\.0\.1)", v) or re.match(r"^[\w.-]+\.[a-z]{2,}(/|$)", v): return "url"
    return "url"


def normalise_url(v):
    v = v.strip()
    if not re.match(r"^https?://", v): v = ("http://" if re.match(r"^(localhost|127\.)", v) else "https://") + v
    return v


def parse_git(url):
    """-> (clone_url, branch or None, subdir or '')"""
    u = url.strip()
    m = re.match(r"^(https?://[^/]+/[^/]+/[^/#?]+?)(?:\.git)?/(?:-/)?(?:tree|blob)/([^/]+)/?(.*)$", u)
    if m:
        return m.group(1) + ".git", m.group(2), m.group(3).strip("/")
    m = re.match(r"^(https?://[^/]+/[^/]+/[^/#?]+?)(?:\.git)?/?$", u)
    if m: return m.group(1) + ".git", None, ""
    return u, None, ""


# ------------------------------------------------------------------ fetch
def fetch(P, job):
    """copy/clone/extract the source into src/. Returns the source root folder."""
    cfg = P.cfg; src = cfg["source"]; kind = src.get("kind") or classify(src.get("value"))
    value = (src.get("value") or "").strip()
    dest = P.p("src")
    if kind in ("url", "media", "none"):
        return None
    if os.path.isdir(dest): shutil.rmtree(dest, ignore_errors=True)
    os.makedirs(dest, exist_ok=True)
    if kind == "git":
        if not which("git"): raise DirectorError("git is not installed, so the repository can't be cloned. Install git, or download the repository as a zip and upload it.")
        url, branch, sub = parse_git(value)
        job.msg("Cloning %s%s…" % (url, " (" + branch + ")" if branch else ""))
        cmd = ["git", "clone", "--depth", "1"] + (["--branch", branch] if branch else []) + [url, os.path.join(dest, "repo")]
        r = subprocess.run(cmd, capture_output=True, text=True, env=dict(os.environ, GIT_TERMINAL_PROMPT="0"))
        if r.returncode != 0:
            raise DirectorError("git clone failed: %s" % (r.stderr.strip().splitlines() or ["unknown error"])[-1])
        root = os.path.join(dest, "repo", sub) if sub else os.path.join(dest, "repo")
        if not os.path.isdir(root): raise DirectorError("folder '%s' not found in the repository" % sub)
        return root
    if kind == "zip":
        path = os.path.expanduser(value)
        if not os.path.exists(path): raise DirectorError("zip file not found: %s" % path)
        job.msg("Extracting %s…" % os.path.basename(path))
        with zipfile.ZipFile(path) as z:
            for m in z.infolist():
                n = m.filename
                if n.startswith("__MACOSX/") or "/__MACOSX/" in n or os.path.basename(n) == ".DS_Store": continue
                if os.path.isabs(n) or ".." in n.split("/"): continue            # zip-slip guard
                z.extract(m, os.path.join(dest, "repo"))
        root = os.path.join(dest, "repo")
        kids = [k for k in os.listdir(root) if not k.startswith(".")]
        while len(kids) == 1 and os.path.isdir(os.path.join(root, kids[0])):    # a single top-level folder
            root = os.path.join(root, kids[0]); kids = [k for k in os.listdir(root) if not k.startswith(".")]
        return root
    if kind == "dir":
        path = os.path.abspath(os.path.expanduser(value))
        if not os.path.isdir(path): raise DirectorError("folder not found: %s" % path)
        job.msg("Copying %s…" % path)
        shutil.copytree(path, os.path.join(dest, "repo"), symlinks=True, ignore=copy_ignore)
        return os.path.join(dest, "repo")
    raise DirectorError("unknown source kind: %s" % kind)


def copy_ignore(d, names):
    """skip bulky, machine-specific folders; keep renv/packrat metadata (activate.R, settings) but not their libraries"""
    base = os.path.basename(d)
    skip = {n for n in names if n in (".git", "node_modules", "__pycache__", ".Rproj.user", ".venv", "venv") or n.endswith(".mp4")}
    if base in ("renv", "packrat"): skip |= {n for n in names if n in ("library", "staging", "sandbox", "lib", "local", "python")}
    return skip


# ------------------------------------------------------------------ R start-up (.Rprofile / renv)
def uses_renv(d):
    return os.path.exists(os.path.join(d, "renv.lock")) or "renv/activate.R" in _read(os.path.join(d, ".Rprofile"), 5000)


def r_profile_env(P):
    """An empty user profile: R then skips the project's .Rprofile (renv/packrat activation) and ~/.Rprofile,
    and the app runs on the packages installed on this machine (the missing-package check covers them)."""
    prof = P.p("empty.Rprofile")
    if not os.path.exists(prof): open(prof, "w").write("# DirectoR: the project's .Rprofile is skipped (set App > renv to 'restore' to use it)\n")
    return {"R_PROFILE_USER": prof}


RENV_RESTORE = ("if (!requireNamespace('renv', quietly = TRUE)) install.packages('renv', repos = 'https://cloud.r-project.org'); "
                "renv::restore(prompt = FALSE)")


# ------------------------------------------------------------------ detect
def _read(p, n=200000):
    try:
        with open(p, encoding="utf-8", errors="replace") as f: return f.read(n)
    except OSError: return ""


def _walk(root, max_depth=4):
    root = os.path.abspath(root)
    for d, dirs, files in os.walk(root):
        depth = d[len(root):].count(os.sep)
        dirs[:] = sorted(x for x in dirs if x not in SKIP_DIRS and not x.startswith("."))
        if depth >= max_depth: dirs[:] = []
        yield d, depth, files


def detect(root):
    """-> dict(kind, appdir, cwd, command(list with {port}), path, label, notes)"""
    if not root: return None
    cands = []
    has_desc = os.path.exists(os.path.join(root, "DESCRIPTION"))
    for d, depth, files in _walk(root):
        fs = set(files); rel = os.path.relpath(d, root)
        lower = {f.lower(): f for f in files}
        if "app.R" in fs or "app.r" in lower or ("server.R" in fs and ("ui.R" in fs or os.path.isdir(os.path.join(d, "www")))) or ("server.R" in fs and "ui.R" in fs):
            app_r = _read(os.path.join(d, lower.get("app.r", "app.R")))
            pri = depth * 10 + (0 if "shiny" in app_r or "rhino" in app_r or "Shiny" in app_r or not app_r else 3)
            cands.append((pri, {"kind": "shiny-r", "appdir": d, "label": "Shiny app (R)" + ("" if rel == "." else " in " + rel)}))
        if "app.py" in fs:
            t = _read(os.path.join(d, "app.py"))
            if re.search(r"^\s*(from shiny|import shiny)", t, re.M):
                cands.append((depth * 10 + 1, {"kind": "shiny-py", "appdir": d, "file": "app.py", "label": "Shiny for Python app"}))
        for f in files:
            if f.endswith(".py"):
                t = _read(os.path.join(d, f), 20000)
                if re.search(r"^\s*import streamlit|^\s*from streamlit", t, re.M):
                    cands.append((depth * 10 + 2 + (0 if f in ("app.py", "streamlit_app.py", "main.py", "Home.py") else 1), {"kind": "streamlit", "appdir": d, "file": f, "label": "Streamlit app"}))
                elif re.search(r"^\s*import gradio|^\s*from gradio", t, re.M):
                    cands.append((depth * 10 + 3, {"kind": "gradio", "appdir": d, "file": f, "label": "Gradio app"}))
        if "_quarto.yml" in fs and which("quarto"):
            cands.append((depth * 10 + 5, {"kind": "quarto", "appdir": d, "label": "Quarto project"}))
        if "package.json" in fs:
            pj = read_json(os.path.join(d, "package.json"), {}) or {}
            sc = pj.get("scripts") or {}
            if "dev" in sc or "start" in sc:
                cands.append((depth * 10 + 6, {"kind": "node", "appdir": d, "script": "dev" if "dev" in sc else "start", "label": "Node web app (npm run %s)" % ("dev" if "dev" in sc else "start")}))
        if "index.html" in fs:
            cands.append((depth * 10 + (4 if os.path.basename(d) in ("docs", "dist", "build", "public", "_site", "site", "www", "html") else 7),
                          {"kind": "static", "appdir": d, "file": "index.html", "label": "Static website" + ("" if rel == "." else " (" + rel + ")")}))
    if has_desc and not any(c[1]["kind"] == "shiny-r" and os.path.abspath(c[1]["appdir"]) == os.path.abspath(root) for c in cands):
        desc = _read(os.path.join(root, "DESCRIPTION"))
        if os.path.exists(os.path.join(root, "R", "run_app.R")) or "golem" in desc:
            cands.append((0, {"kind": "golem", "appdir": root, "label": "Shiny app in an R package (golem-style run_app())"}))
        else:
            for sub in glob.glob(os.path.join(root, "inst", "*", "app.R")) + glob.glob(os.path.join(root, "inst", "*", "server.R")):
                cands.append((1, {"kind": "rpkg-app", "appdir": os.path.dirname(sub), "pkgroot": root, "label": "Shiny app in an R package (inst/%s)" % os.path.basename(os.path.dirname(sub))}))
                break
    if not cands:
        htmls = [h for h in glob.glob(os.path.join(root, "**", "*.html"), recursive=True) if "__MACOSX" not in h and "node_modules" not in h]
        if htmls:
            h = max(htmls, key=lambda p: os.path.getsize(p))
            cands.append((50, {"kind": "static", "appdir": os.path.dirname(h), "file": os.path.basename(h), "label": "Standalone HTML page (%s)" % os.path.relpath(h, root)}))
    if not cands: return None
    cands.sort(key=lambda c: c[0])
    info = dict(cands[0][1]); info["root"] = root
    info["alternatives"] = [c[1]["label"] for c in cands[1:6]]
    return info


def launch_command(info, rscript="Rscript"):
    """-> (argv with {port}, cwd, env, url path)"""
    k = info["kind"]; d = info["appdir"]; env = {}
    rs = lambda code: [rscript, "-e", code]
    if k == "shiny-r":
        code = "options(shiny.port={port}, shiny.host='127.0.0.1', shiny.launch.browser=FALSE); shiny::runApp('.', port={port}, launch.browser=FALSE)"
        return rs(code), d, env, "/"
    if k == "golem":
        code = ("options(shiny.port={port}, shiny.host='127.0.0.1', shiny.launch.browser=FALSE); "
                "pkgload::load_all('.', export_all=FALSE, helpers=FALSE, quiet=TRUE); "
                "app <- run_app(); if (inherits(app, 'shiny.appobj')) shiny::runApp(app, port={port}, launch.browser=FALSE)")
        return rs(code), d, env, "/"
    if k == "rpkg-app":
        code = ("options(shiny.port={port}, shiny.launch.browser=FALSE); pkgload::load_all('%s', quiet=TRUE); "
                "shiny::runApp('%s', port={port}, launch.browser=FALSE)") % (info["pkgroot"].replace("\\", "/"), d.replace("\\", "/"))
        return rs(code), d, env, "/"
    if k == "shiny-py":
        return [PY, "-m", "shiny", "run", "--host", "127.0.0.1", "--port", "{port}", info.get("file", "app.py")], d, env, "/"
    if k == "streamlit":
        return [PY, "-m", "streamlit", "run", info["file"], "--server.port", "{port}", "--server.headless", "true",
                "--server.address", "127.0.0.1", "--browser.gatherUsageStats", "false"], d, env, "/"
    if k == "gradio":
        env["GRADIO_SERVER_PORT"] = "{port}"; env["GRADIO_SERVER_NAME"] = "127.0.0.1"
        return [PY, info["file"]], d, env, "/"
    if k == "quarto":
        return ["quarto", "preview", "--port", "{port}", "--no-browse", "--no-watch-inputs"], d, env, "/"
    if k == "node":
        env["PORT"] = "{port}"; env["BROWSER"] = "none"
        return ["npm", "run", info.get("script", "dev"), "--", "--port", "{port}"], d, env, "/"
    if k == "static":
        return [PY, "-m", "http.server", "{port}", "--bind", "127.0.0.1"], d, env, "/" + info.get("file", "index.html").replace("index.html", "")
    raise DirectorError("don't know how to launch a %s" % k)


# ------------------------------------------------------------------ R package requirements
R_BASE = {"base", "stats", "utils", "methods", "graphics", "grDevices", "tools", "datasets", "grid", "parallel", "splines", "tcltk", "compiler", "stats4"}


def r_requirements(root, appdir=None):
    """packages the app needs: DESCRIPTION Imports/Depends for a package, else library()/pkg:: calls in the app folder"""
    pk = set()
    desc = _read(os.path.join(root, "DESCRIPTION"))
    scan_dirs = []
    if desc:
        for field in ("Imports", "Depends"):
            m = re.search(r"^%s:\s*(.*?)(?=^\S|\Z)" % field, desc, re.M | re.S)
            if m:
                for x in m.group(1).split(","):
                    name = re.sub(r"\(.*?\)", "", x).strip()
                    if name and name != "R": pk.add(name)
        scan_dirs = [appdir or root]                      # app.R / ui.R / server.R only
        depth = 0
    else:
        scan_dirs = [appdir or root]; depth = 2
    for base in scan_dirs:
        for d, dep, files in _walk(base, depth):
            for f in files:
                if f.endswith((".R", ".r")) and (depth or f in ("app.R", "ui.R", "server.R", "global.R")):
                    t = _read(os.path.join(d, f), 100000)
                    t = "\n".join(l for l in t.splitlines() if not l.lstrip().startswith("#"))
                    pk.update(re.findall(r"(?:library|require|requireNamespace)\(\s*['\"]?([A-Za-z][A-Za-z0-9.]+)", t))
                    pk.update(re.findall(r"\b([A-Za-z][A-Za-z0-9.]{1,30})::", t))
    own = re.search(r"^Package:\s*(\S+)", desc, re.M)
    if own: pk.discard(own.group(1))
    return sorted(p for p in pk if p not in R_BASE and not p.startswith("."))


def r_missing(pkgs, rscript="Rscript"):
    if not pkgs or not which(rscript): return []
    code = "x <- c(%s); cat(x[!vapply(x, requireNamespace, logical(1), quietly=TRUE)], sep='\\n')" % ",".join("'%s'" % p for p in pkgs)
    try:
        r = subprocess.run([rscript, "-e", code], capture_output=True, text=True, timeout=120)
        return [x for x in r.stdout.split() if x]
    except Exception:  # noqa: BLE001
        return []


# ------------------------------------------------------------------ facts
def _first_sentence(t):
    t = re.sub(r"\s+", " ", t).strip()
    m = re.match(r"(.{20,220}?[.!?])(\s|$)", t)
    return (m.group(1) if m else t[:200]).strip()


def _clean_md(t):
    t = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", t)
    t = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", t)
    t = re.sub(r"<[^>]+>", "", t)
    t = re.sub(r"[`*_]{1,3}", "", t)
    return t.strip()


def readme_facts(root):
    out = {}
    for name in ("README.md", "README.Rmd", "README.qmd", "readme.md", "README.rst", "README.txt", "README"):
        p = os.path.join(root, name)
        if os.path.exists(p): break
    else:
        return out
    t = _read(p)
    t = re.sub(r"^---\n.*?\n---\n", "", t, flags=re.S)             # yaml header
    t = re.sub(r"```.*?```", "", t, flags=re.S)                      # code blocks
    t = re.sub(r"<!--.*?-->", "", t, flags=re.S)
    m = re.search(r"^#\s+(.+)$", t, re.M)
    if m: out["title"] = _clean_md(m.group(1))
    paras = [_clean_md(x) for x in re.split(r"\n\s*\n", t)]
    paras = [x for x in paras if len(x) > 40 and not x.startswith(("#", "|", "[!", "!", ">", "-", "*")) and "badge" not in x.lower()]
    if paras: out["summary"] = _first_sentence(paras[0]); out["paragraph"] = re.sub(r"\s+", " ", paras[0])[:600]
    # ---- features: bullets from the most "feature-like" section
    secs = re.split(r"^(#{2,4}\s+.+)$", t, flags=re.M)
    sections = [("", secs[0])] + [(_clean_md(secs[i].lstrip("#").strip()), secs[i + 1]) for i in range(1, len(secs) - 1, 2)]
    GOOD = r"feature|highlight|what (it|you|people)|why|experience|overview|key|capabilit|benefit|how it works|included|at a glance|tour"
    BAD = r"limitation|install|licen[cs]e|contribut|caveat|known|issue|troubleshoot|faq|deploy|layout|develop|requirement|changelog|news|citation|acknowledg|archiv|retriev|test|build|config|option|api|reference|support|credit|roadmap|todo"
    best = []
    for head, body in sections:
        items = bullets(body)
        if len(items) < 2: continue
        score = len(items) + (20 if re.search(GOOD, head, re.I) else 0) - (30 if re.search(BAD, head, re.I) else 0)
        best.append((score, head, items))
    best.sort(key=lambda x: -x[0])
    if best and best[0][0] > -5:
        out["features"] = best[0][2][:8]; out["features_from"] = best[0][1]
    heads = [h for h, _ in sections[1:]]
    out["headings"] = [h for h in heads if not re.search(BAD, h, re.I)][:10]
    return out


def bullets(body):
    """markdown list items (-, *, +, 1.) with continuation lines -> [{title, text}]"""
    items, cur = [], None
    for line in body.splitlines():
        m = re.match(r"^\s{0,3}(?:[-*+]|\d{1,2}[.)])\s+(.*)$", line)
        if m:
            if cur: items.append(cur)
            cur = m.group(1).strip()
        elif cur is not None and line.startswith(("  ", "\t")) and line.strip():
            cur += " " + line.strip()
        elif not line.strip() and cur:
            items.append(cur); cur = None
    if cur: items.append(cur)
    out = []
    for raw in items:
        if len(raw) < 8 or re.match(r"^\[?!\[", raw): continue
        m = re.match(r"^\*\*(.+?)\*\*[:.\s—–-]*\s*(.*)$", raw)
        if m:
            title, text = _clean_md(m.group(1)).rstrip(".:"), _clean_md(m.group(2))
        else:
            text = _clean_md(raw); title = ""
        text = re.sub(r"\s+", " ", text).strip()
        if re.match(r"^(install|see |http|note|run |`)", text, re.I): continue
        out.append({"title": title, "text": text})
    return out


def description_facts(root):
    t = _read(os.path.join(root, "DESCRIPTION"))
    if not t: return {}
    get = lambda k: (re.search(r"^%s:\s*(.*?)(?=^\S|\Z)" % k, t, re.M | re.S) or [None, ""])[1]
    out = {"package": get("Package").strip(), "title": re.sub(r"\s+", " ", get("Title")).strip(),
           "description": re.sub(r"\s+", " ", get("Description")).strip(), "version": get("Version").strip()}
    url = get("URL").split(",")[0].strip()
    if url: out["url"] = url
    return {k: v for k, v in out.items() if v}


def logo_candidates(root):
    pats = ["man/figures/logo.png", "man/figures/logo.svg", "logo.png", "logo.svg", "inst/app/www/logo*.png", "inst/app/www/logo*.svg", "www/logo*.png", "www/logo*.svg",
            "public/logo*.png", "public/logo*.svg", "static/logo*", "assets/logo*", "img/logo*", "images/logo*", "inst/app/www/favicon*", "www/favicon*",
            "public/favicon*.png", "public/favicon.svg", "pkgdown/favicon/apple-touch-icon.png", "**/logo.png", "**/logo.svg", "**/*logo*.png", "**/*logo*.svg"]
    seen = []
    for p in pats:
        for f in glob.glob(os.path.join(root, p), recursive=True):
            if "__MACOSX" in f or "node_modules" in f or f in seen: continue
            if os.path.getsize(f) > 2_000_000: continue
            seen.append(f)
    return seen[:6]


def learn(root, info):
    """facts about the project, from README / DESCRIPTION / package.json / pyproject"""
    if not root: return {}
    f = {"readme": readme_facts(root), "description": description_facts(root)}
    pj = read_json(os.path.join(root, "package.json"), None)
    if isinstance(pj, dict): f["package_json"] = {k: pj.get(k) for k in ("name", "description", "homepage", "version") if pj.get(k)}
    pp = _read(os.path.join(root, "pyproject.toml"))
    if pp:
        m = re.search(r'^description\s*=\s*"(.*?)"', pp, re.M); n = re.search(r'^name\s*=\s*"(.*?)"', pp, re.M)
        f["pyproject"] = {"description": m.group(1) if m else "", "name": n.group(1) if n else ""}
    f["logos"] = logo_candidates(root)
    if info and info.get("kind") in ("shiny-r", "golem", "rpkg-app"):
        f["r_packages"] = r_requirements(root, info.get("appdir"))
    return f


# ------------------------------------------------------------------ launch
def free_port():
    s = socket.socket(); s.bind(("127.0.0.1", 0)); p = s.getsockname()[1]; s.close(); return p


def listening_url(log):
    """the address printed by Shiny / Streamlit / uvicorn / http.server / vite once it is listening"""
    try:
        with open(log, encoding="utf-8", errors="replace") as f: t = f.read()[-20000:]
    except OSError:
        return None
    m = re.findall(r"(?:Listening on|Local URL:|Uvicorn running on|Running on|Serving HTTP on \S+ port)\s*(https?://[\w.\-\[\]:]+)", t)
    if not m: return None
    u = m[-1].replace("0.0.0.0", "127.0.0.1").replace("[::]", "127.0.0.1").replace("localhost", "127.0.0.1")
    return u


def _group_cpu(pgid):
    """total CPU seconds of a process group (the app and its children); -1 if unknown"""
    try:
        out = subprocess.run(["ps", "-A", "-o", "pgid=,time="], capture_output=True, text=True, timeout=5).stdout
    except Exception:  # noqa: BLE001
        return -1.0
    tot = 0.0
    for line in out.splitlines():
        parts = line.split()
        if len(parts) != 2 or parts[0] != str(pgid): continue
        t = parts[1]; days = 0
        if "-" in t: d, t = t.split("-", 1); days = int(d)
        secs = 0.0
        for x in t.split(":"): secs = secs * 60 + float(x)
        tot += secs + days * 86400
    return tot


def _http_ok(url, timeout=2.0):
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "DirectoR"}), timeout=timeout) as r:
            return r.status < 500
    except urllib.error.HTTPError as e:
        return e.code < 500
    except Exception:  # noqa: BLE001
        return False


_LIVE = []


def _register_cleanup(srv):
    import atexit
    _LIVE.append(srv)
    if len(_LIVE) == 1:
        atexit.register(lambda: [x.stop() for x in list(_LIVE)])
        def on_term(signum, frame):
            for x in list(_LIVE): x.stop()
            raise SystemExit(128 + signum)
        for sg in (signal.SIGTERM, signal.SIGHUP) if os.name != "nt" else (signal.SIGTERM,):
            try: signal.signal(sg, on_term)
            except Exception: pass  # noqa: BLE001  (not in the main thread)


def _kill_stale(P):
    """an app left running by an engine that was killed: stop it before starting a new one"""
    f = P.p("app.pid")
    try: pid = int(open(f).read().strip())
    except (OSError, ValueError): return
    try:
        if os.name != "nt": os.killpg(pid, signal.SIGTERM)
        else: os.kill(pid, signal.SIGTERM)
    except Exception: pass  # noqa: BLE001
    try: os.remove(f)
    except OSError: pass


class AppServer:
    """Runs the app in its own process group; `with AppServer(P, job) as url:`"""

    def __init__(self, P, job, facts=None):
        self.P, self.job = P, job
        self.facts = facts if facts is not None else (P.get("facts") or {})
        self.proc = None; self.url = None

    def __enter__(self):
        shared = getattr(self.P, "shared_server", None)
        if shared is not None and shared is not self and shared.alive():
            self.borrowed = True; self.url = shared.url
            self.job.log("reusing the app that is already running at %s" % self.url)
            return self.url
        cfg = self.P.cfg; app = cfg.get("app") or {}
        src = cfg["source"]; kind = src.get("kind") or classify(src.get("value"))
        if kind == "url":
            self.url = normalise_url(src.get("value", ""))
            return self.url
        if kind == "media": return None
        custom = (app.get("command") or "").strip()
        info = self.facts.get("app") or {}
        if not custom and not info:
            raise DirectorError("No runnable app was found in the source. Set a launch command in Source › Advanced (use {port}), or upload screenshots instead.")
        port = free_port()
        rscript = os.environ.get("DIRECTOR_RSCRIPT") or "Rscript"
        if custom:
            import shlex
            argv = shlex.split(custom.replace("{port}", str(port)))
            cwd = app.get("cwd") or info.get("appdir") or info.get("root") or self.P.p("src"); env = {}; path = app.get("path") or "/"
        else:
            argv, cwd, env, path = launch_command(info, rscript)
            argv = [a.replace("{port}", str(port)) for a in argv]
            env = {k: v.replace("{port}", str(port)) for k, v in env.items()}
            if app.get("path") and app["path"] != "/": path = app["path"]
        if argv and argv[0] in ("Rscript", rscript) and not which(argv[0]):
            raise DirectorError("Rscript was not found on PATH, so the Shiny app can't be started. Install R, or set DIRECTOR_RSCRIPT.")
        if info.get("kind") == "node" and not custom and not os.path.isdir(os.path.join(cwd, "node_modules")):
            if not which("npm"): raise DirectorError("This is a Node project but npm is not installed.")
            self.job.msg("Installing npm dependencies (first run only)…")
            subprocess.run(["npm", "install", "--no-audit", "--no-fund"], cwd=cwd, capture_output=True, timeout=900)
        envx = dict(os.environ); envx.update({k: str(v) for k, v in (app.get("env") or {}).items()}); envx.update(env)
        is_r = info.get("kind") in ("shiny-r", "golem", "rpkg-app") or (bool(argv) and os.path.basename(argv[0]).lower() in ("rscript", "rscript.exe", "r", "r.exe"))
        renv_mode = (app.get("renv") or "ignore").lower()
        self.renv = is_r and uses_renv(cwd)
        if is_r and renv_mode != "restore":
            envx.update(r_profile_env(self.P))
            if self.renv: self.job.log("renv project: its .Rprofile is skipped and the app uses the packages installed here")
        elif is_r and self.renv:
            self.job.msg("Restoring the renv library (first run can take a while)…")
            r = subprocess.run([rscript, "-e", RENV_RESTORE], cwd=cwd, env=envx, capture_output=True, text=True, timeout=3600)
            rlog = self.P.p("renv_restore.log")
            open(rlog, "w").write((r.stdout or "") + (r.stderr or ""))
            if r.returncode != 0:
                raise DirectorError("renv::restore() failed (see renv_restore.log).\n%s" % tail(rlog, 15))
        envx.setdefault("R_DEFAULT_PACKAGES", "datasets,utils,grDevices,graphics,stats,methods")
        self.log = self.P.p("app.log")
        self.job.msg("Launching %s on port %d…" % (info.get("label") or "app", port))
        self.job.log("$ (cd %s) %s" % (cwd, " ".join(argv)))
        _kill_stale(self.P)
        self.proc = subprocess.Popen(argv, cwd=cwd, env=envx, stdout=open(self.log, "w"), stderr=subprocess.STDOUT,
                                     start_new_session=(os.name != "nt"))
        # never leave an orphan app behind: stop it when the engine exits or is terminated, and remember its pid
        open(self.P.p("app.pid"), "w").write(str(self.proc.pid))
        _register_cleanup(self)
        base = "http://127.0.0.1:%d" % port
        self.url = base + (path if path.startswith("/") else "/" + path)
        # No fixed deadline: heavy apps can take minutes to load packages and data. We wait as long as the app
        # shows signs of life (CPU time or new log output) and give up only when it stalls for `wait` seconds.
        # patience: at least 5 minutes without any activity (apps waiting on a database look idle), 30 minutes overall while busy
        t0 = time.time(); stall = max(float(app.get("wait") or 600), float(os.environ.get("DIRECTOR_MIN_WAIT", 300))); hard = max(stall * 3, 1800.0)
        last_act, last_cpu, last_size, said = time.time(), -1.0, -1, 0.0
        while True:
            el = time.time() - t0
            if self.proc.poll() is not None:
                raise DirectorError("The app stopped while starting (exit code %s).\n%s" % (self.proc.returncode, self.hint(tail(self.log, 25))))
            lst = listening_url(self.log)
            if lst and lst.rstrip("/") != base:                    # the app chose its own port (runApp(port = ...) inside)
                base = lst.rstrip("/"); self.url = base + (path if path.startswith("/") else "/" + path)
            if _http_ok(base + "/", timeout=5.0):
                self.job.msg("App is up at %s (%.0fs)" % (self.url, el))
                return self.url
            cpu = _group_cpu(self.proc.pid)
            size = os.path.getsize(self.log) if os.path.exists(self.log) else 0
            if cpu > last_cpu + 0.05 or size != last_size:
                last_act = time.time(); last_cpu, last_size = max(cpu, last_cpu), size
            if time.time() - said > 2.5:
                said = time.time()
                line = (tail(self.log, 1) or "").strip()[:90]
                self.job.msg("Starting the app… %.0fs%s" % (el, (" · " + line) if line else ""))
            if time.time() - last_act > stall or el > hard:
                self.stop()
                why = "stopped responding for %.0fs" % stall if el <= hard else "did not start within %.0f minutes" % (hard / 60)
                raise DirectorError("The app %s while starting. If it is just slow, raise Source › Advanced › start-up timeout.\n%s" % (why, self.hint(tail(self.log, 25))))
            time.sleep(0.5)

    @staticmethod
    def hint(log):
        if re.search(r"renv/activate\.R|packrat/init\.R|This project is using renv|renv::", log):
            return ("The project is set up with renv/packrat, and its start-up script could not run here. DirectoR normally skips it; "
                    "if you chose Source › Advanced › renv = 'restore', switch back to 'ignore' (uses your installed packages).\n\n%s" % log)
        m = re.findall(r"there is no package called ['‘]([^'’]+)['’]", log)
        if m: return "Missing R package(s): %s. Install them (Source › Install missing packages) and try again.\n\n%s" % (", ".join(sorted(set(m))), log)
        m = re.findall(r"No module named '([^']+)'", log)
        if m: return "Missing Python module(s): %s.\n\n%s" % (", ".join(sorted(set(m))), log)
        return log

    def alive(self):
        return bool(self.url) and (self.proc is None or self.proc.poll() is None)

    def stop(self):
        if getattr(self, "borrowed", False): return
        if self in _LIVE: _LIVE.remove(self)
        if self.proc is not None:
            try: os.remove(self.P.p("app.pid"))
            except OSError: pass
        if self.proc and self.proc.poll() is None:
            try:
                if os.name != "nt": os.killpg(self.proc.pid, signal.SIGTERM)
                else: self.proc.terminate()
                self.proc.wait(8)
            except Exception:  # noqa: BLE001
                try:
                    if os.name != "nt": os.killpg(self.proc.pid, signal.SIGKILL)
                    else: self.proc.kill()
                except Exception:  # noqa: BLE001
                    pass
        self.proc = None

    def __exit__(self, *exc):
        self.stop(); return False


# ------------------------------------------------------------------ the ingest job
def ingest(P, job):
    cfg = P.cfg; src = cfg["source"]
    kind = src.get("kind") or classify(src.get("value"))
    if kind in ("", "auto", None): kind = classify(src.get("value"))
    if kind != cfg["source"].get("kind"):
        c = P.cfg; c["source"]["kind"] = kind; P.save_cfg(c)
    facts = {"source_kind": kind, "source": src.get("value", "")}
    if kind == "url":
        facts["url"] = normalise_url(src.get("value", ""))
        facts["app"] = {"kind": "url", "label": "Live website / app"}
    elif kind == "media":
        facts["app"] = {"kind": "media", "label": "Uploaded screenshots / recordings"}
    else:
        root = fetch(P, job)
        job.progress(0.5, "Detecting the app…")
        info = detect(root)
        facts["root"] = root
        if info:
            facts["app"] = info
            job.msg("Detected: %s" % info["label"])
        else:
            job.warn("No runnable app detected. Use a custom launch command or upload screenshots.")
        facts.update(learn(root, info))
        if facts.get("r_packages"):
            job.progress(0.75, "Checking R packages…")
            miss = r_missing(facts["r_packages"], os.environ.get("DIRECTOR_RSCRIPT") or "Rscript")
            facts["r_missing"] = miss
            if miss: job.warn("R packages needed by the app are not installed: " + ", ".join(miss))
    P.put("facts", facts)
    return facts
