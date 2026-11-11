"""The director: turn what we know about an app into a storyboard.

storyboard.json = {
  template, brand: {name, tagline, description, url, cta},
  scenes: [ {id, type, dur, vo, transition, ...type fields} ],
  shots:  [ {id, label, view, reach: {url, tab}, actions: [...], focus: [x, y, w, h] (0..1), thumb} ]
}

Scene types (rendered by stage/film.js):
  hook      big kinetic statement          text ('*x*' gradient, '_x_' muted, '~x~' warm, '|' new line), anim
  title     logo + name + tagline reveal   title, tagline
  shot      app footage                    shot, layout (window|full|tilt|float|split|phone), camera (auto|push|pan|follow|static), headline, caption, step
  features  3–4 tiles with icons           headline, items [{title, text, icon}]
  montage   quick cuts of several shots    shots [...], caption
  grid      3-D wall of screens            headline, shots [...]
  stat      big counting number            value, label
  quote     testimonial                    text, author
  end       end card                       title, tagline, cta, note
Every scene may carry `vo` (one voice-over line) and `transition` (into this scene).
"""
import copy, json, os, re

from .util import DirectorError

TEMPLATES = {
    "launch": {"label": "Launch film", "vo": True, "duration": 50, "theme": "light", "mood": "keys", "aspect": "16:9",
               "blurb": "Story-driven film with voice-over: the hook, the product, 3–4 features, the end card."},
    "teaser": {"label": "Teaser", "vo": False, "duration": 24, "theme": "dark", "mood": "pulse", "aspect": "16:9",
               "blurb": "Music-only, beat-cut, kinetic type. Built to make people curious."},
    "tour": {"label": "Feature tour", "vo": True, "duration": 40, "theme": "light", "mood": "bright", "aspect": "16:9",
             "blurb": "Numbered walkthrough of the app's main screens, with voice-over."},
    "social": {"label": "Social vertical", "vo": True, "duration": 22, "theme": "dark", "mood": "drive", "aspect": "9:16",
               "blurb": "9:16 for Reels, Shorts and TikTok: bold captions, fast cuts, big type."},
    "demo": {"label": "Calm demo", "vo": True, "duration": 35, "theme": "light", "mood": "ambient", "aspect": "16:9",
             "blurb": "Quiet, product-first: screens in windows with captions. Good for docs and READMEs."},
}

STOP = set("a an the of and or for to in on with by is are be as at from that this it its your you our we their into".split())


# ------------------------------------------------------------------ copy helpers
def clean(s):
    s = re.sub(r"\([^)]*\)", "", s or "")            # asides
    s = re.sub(r"\s+", " ", s).strip()
    return s.replace(" ,", ",").replace(" .", ".")


def sentences(s):
    return [x.strip() for x in re.split(r"(?<=[.!?])\s+(?=[A-Z0-9\"“])", clean(s)) if x.strip()]


def words(s): return re.findall(r"\S+", s or "")


def trim_words(s, n, ellipsis=False):
    w = words(s)
    if len(w) <= n: return s.strip()
    cut = " ".join(w[:n]).rstrip(",;:—-")
    return cut + ("…" if ellipsis else "")


def vo_line(text, max_words=24):
    """a speakable sentence from a feature text"""
    ss = sentences(text)
    if not ss: return ""
    out = ss[0]
    if len(words(out)) < 9 and len(ss) > 1:
        nxt = ss[1]
        if len(words(out)) + len(words(nxt)) > max_words:
            acc = ""
            for p in re.split(r",\s+|;\s+|\s+—\s+|:\s+", nxt):
                if len(words(out + " " + acc + " " + p)) > max_words: break
                acc = (acc + ", " + p) if acc else p
            nxt = acc.rstrip(",;:") + "." if acc else ""
        if nxt: out = out.rstrip() + " " + nxt
    if len(words(out)) > max_words:
        parts = re.split(r",\s+|;\s+|\s+—\s+|:\s+", out)
        acc = ""
        for p in parts:
            if len(words(acc + " " + p)) > max_words: break
            acc = (acc + ", " + p) if acc else p
        out = acc or trim_words(out, max_words)
    out = out.strip().rstrip(",;:")
    if not out.endswith((".", "!", "?")): out += "."
    return out[0].upper() + out[1:]


def emphasise(text, n=2, mark="*"):
    """put the last n meaningful words in gradient emphasis"""
    text = text.strip().rstrip(".")
    w = text.split(" ")
    if len(w) <= 1: return "%s%s.%s" % (mark, text, mark)
    k = min(n, len(w) - 1)
    while k < len(w) - 1 and w[-k].lower() in STOP: k += 1
    return "%s %s%s.%s" % (" ".join(w[:-k]), mark, " ".join(w[-k:]), mark)


def headline_from(feature, max_words=6):
    if feature.get("title"):
        t = feature["title"].strip().rstrip(".")
        sub = first_clause(feature.get("text", ""), 5)
        if sub and re.match(r"^(before|after|when|if|each|with|for|in|on|at|by|to|from|as|so|and|but|or|then|once|while|every|all|it|this|that|these|those|you|we|they|there)\b", sub, re.I): sub = ""
        if sub and len(words(sub)) >= 2 and len(words(t)) <= 3: return "*%s.* _%s_" % (t, sub.rstrip(".") + ".")
        return "*%s.*" % t if len(words(t)) <= 3 else emphasise(trim_words(t, max_words))
    c = first_clause(feature.get("text", ""), max_words)
    return emphasise(c) if c else ""


def first_clause(text, max_words):
    s = sentences(text)
    if not s: return ""
    c = re.split(r",\s+|;\s+|\s+—\s+|:\s+|\s+\(", s[0])[0].strip().rstrip(".")
    if len(words(c)) > max_words: return ""
    return c


def title_case_name(s):
    return s if any(ch.isupper() for ch in s) else s[:1].upper() + s[1:]


# ------------------------------------------------------------------ brand
def brand(P, facts, scout):
    cfg = P.cfg; b = dict(cfg.get("brand") or {})
    facts = facts or {}; scout = scout or {}
    rd = facts.get("readme") or {}; dd = facts.get("description") or {}; pj = facts.get("package_json") or {}
    meta = scout.get("meta") or {}
    titles = [scout.get("title") or "", meta.get("ogTitle") or "", rd.get("title") or ""]
    navwords = {t.lower() for v in scout.get("views") or [] for t in (v.get("tabs") or []) + [v.get("label") or ""]}
    generic = {"home", "overview", "dashboard", "welcome", "index", "main", "app", "start", "homepage", "landing", "untitled"}
    name, tag = "", ""
    for t in titles:
        parts = [p.strip() for p in re.split(r"\s+[·|—–-]\s+|:\s+|\s+\|\s+", t) if p.strip()]
        if parts and len(words(parts[0])) <= 3:
            name = name or parts[0]
            if len(parts) > 1 and not tag and 1 <= len(words(parts[1])) <= 8:
                cand = parts[1].strip().rstrip(".")
                if cand.lower() not in generic and cand.lower() not in navwords: tag = cand[:1].upper() + cand[1:]
        if name and tag: break
    name = name or meta.get("ogSite") or scout.get("brandText") or dd.get("package") or pj.get("name") or ""
    if not name and cfg.get("name") not in (None, "", "Untitled film", "New film"): name = cfg["name"]
    if not name and facts.get("root"): name = os.path.basename(facts["root"].rstrip("/"))
    if not name and scout.get("url"):
        import urllib.parse
        name = urllib.parse.urlparse(scout["url"]).hostname or "Your app"
        name = re.sub(r"^www\.|\.(com|io|app|org|net|dev|ai|co)$", "", name)
    name = title_case_name(name.strip() or "Your app")
    desc = meta.get("description") or meta.get("ogDescription") or dd.get("description") or pj.get("description") or (facts.get("pyproject") or {}).get("description") or rd.get("paragraph") or ""
    if not tag:
        cand = dd.get("title") or (sentences(meta.get("description") or "")[:1] or [""])[0]
        if cand and len(words(cand)) <= 8: tag = cand
        elif rd.get("summary") and len(words(rd["summary"])) <= 9: tag = rd["summary"]
        else: tag = trim_words(cand or rd.get("summary") or "", 7)
    feats = list(rd.get("features") or [])
    if len(feats) < 3 and dd.get("description"):
        for s in sentences(dd["description"])[1:]:
            feats.append({"title": "", "text": s})
    url = b.get("url") or dd.get("url") or pj.get("homepage") or (facts.get("url") if facts.get("source_kind") == "url" else "") or ""
    if re.search(r"^https?://(localhost|127\.|0\.0\.0\.0|\[::1\]|192\.168\.|10\.)", url or ""): url = ""     # never advertise a local address
    if not url and facts.get("source_kind") == "git" and re.match(r"^https?://", facts.get("source", "")): url = re.sub(r"\.git$", "", facts.get("source", ""))
    cta = b.get("cta") or ""
    if not cta:
        if url: cta = re.sub(r"^https?://(www\.)?", "", url).rstrip("/")
        elif dd.get("package"): cta = "%s::run_app()" % dd["package"]
    return {"name": b.get("name") or name, "tagline": b.get("tagline") or tag.rstrip(".") + ("." if tag and not tag.endswith(("!", "?")) else ""),
            "description": b.get("description") or desc, "summary": rd.get("summary") or (sentences(desc)[:1] or [""])[0],
            "features": feats, "url": url, "cta": cta}


# ------------------------------------------------------------------ views & shots
def rank_views(scout):
    vs = list((scout or {}).get("views") or [])
    def score(v):
        s = 10 if v["kind"] == "home" else 0
        s += min(6, len(v.get("outputs") or [])) * 2 + min(4, len(v.get("inputs") or []))
        if re.search(r"about|help|faq|settings|login|sign|contact|privacy|terms|legal|imprint|blog|docs?$|source", v.get("label", ""), re.I): s -= 12
        return s
    return sorted(vs, key=score, reverse=True)


DANGER = re.compile(r"delete|remove|logout|log out|sign out|reset|clear|close|cancel|dismiss|download|export|buy|pay|checkout|subscribe|sign up|register|login|log in|×", re.I)
ACTION_OK = re.compile(r"run|update|go\b|apply|start|generate|simulate|refresh|calculate|submit|search|compute|plot|show|draw|predict|analy|fit|explore|try|play|next|continue|begin|add|create|new", re.I)


def norm_box(b, vw, vh):
    if not b: return None
    x, y, w, h = b
    if y > vh * 0.95: return None                      # below the fold
    return [round(max(0, x / vw), 4), round(max(0, y / vh), 4), round(min(1, w / vw), 4), round(min(1, h / vh), 4)]


SAMPLE_TEXT = [(r"e-?mail", "alex@example.com"), (r"\bname\b|candidate|person|user", "Alex Morgan"), (r"team|group|org|company", "Data Science"),
               (r"city|location|place|address", "Lisbon"), (r"search|filter|find|query|look", "growth"), (r"title|subject|topic", "Quarterly review"),
               (r"url|link|website", "example.com"), (r"number|amount|count|age|year", "42")]


def sample_text(i):
    lab = " ".join([i.get("label") or "", i.get("placeholder") or ""]).lower()
    for rx, txt in SAMPLE_TEXT:
        if re.search(rx, lab): return txt
    return None


def interaction(view, shiny, vw, vh, global_buttons=frozenset(), home=False):
    """the most telling thing to do on a screen -> list of actions"""
    ins = [i for i in (view.get("inputs") or []) if i.get("box") and i["box"][1] < vh * 0.92]
    run = [b for b in (view.get("buttons") or []) if b.get("box") and b["box"][1] < vh * 0.92 and ACTION_OK.search(b["text"]) and not DANGER.search(b["text"]) and b["text"] not in global_buttons]
    then_run = ([{"do": "click", "target": {"text": run[0]["text"], "kind": "button"}, "ms": 700, "mark": "click_run"}, {"do": "settle", "ms": 1800}] if shiny and run else [])
    for i in ins:
        if i["type"] == "slider":
            return [{"do": "slide", "target": {"css": i["css"], "kind": "slider"}, "to": 0.72, "ms": 1300, "mark": "click_slide"},
                    {"do": "settle", "ms": 1400 if then_run else 1600}] + then_run
    for i in ins:
        if i["type"] in ("selectize", "select") and len(i.get("options") or []) > 1:
            return [{"do": "select", "target": {"css": i["css"], "kind": i["type"]}, "option": 1, "ms": 700, "mark": "click_select"},
                    {"do": "settle", "ms": 1400 if then_run else 1600}] + then_run
    for i in ins:
        if i["type"] == "text" and sample_text(i):
            return [{"do": "type", "target": {"css": i["css"]}, "text": sample_text(i), "ms": 650, "cps": 13, "mark": "click_type"}, {"do": "settle", "ms": 900}]
    for i in ins:
        if i["type"] in ("checkbox", "radio"):
            return [{"do": "click", "target": {"css": i["css"]}, "ms": 650, "mark": "click_toggle"}, {"do": "settle", "ms": 1400}]
    btns = [b for b in (view.get("buttons") or []) if b.get("box") and b["box"][1] < vh * 0.92 and not DANGER.search(b["text"]) and b["text"] not in global_buttons]
    if home and btns:
        b = sorted(btns, key=lambda b: (not b.get("primary"), b["box"][1]))[0]
        return [{"do": "hover", "target": {"text": b["text"], "kind": "button"}, "ms": 900, "hold": 900}]
    if shiny:
        for b in btns:
            if ACTION_OK.search(b["text"]):
                return [{"do": "click", "target": {"text": b["text"], "kind": "button"}, "ms": 700, "mark": "click_btn"}, {"do": "settle", "ms": 2000}]
    if btns:
        b = sorted(btns, key=lambda b: (not b.get("primary"), b["box"][1]))[0]
        return [{"do": "hover", "target": {"text": b["text"], "kind": "button"}, "ms": 800}]
    return []


def global_buttons(scout):
    vs = (scout or {}).get("views") or []
    if len(vs) < 2: return frozenset()
    sets = [set(b["text"] for b in v.get("buttons") or []) for v in vs]
    return frozenset(set.intersection(*sets))


def shot_for(view, home, scout, vw, vh, idx, long_scroll=True):
    shiny = (scout or {}).get("framework") in ("shiny", "streamlit", "gradio")
    acts = [{"do": "wait", "ms": 400}, {"do": "show", "ms": 250}]
    reach = {"url": view["reach"].get("url") or "/"}
    if view["kind"] == "tab":
        acts += [{"do": "click", "target": {"kind": "tab", "text": view["reach"]["tab"]}, "ms": 750, "mark": "click_nav"},
                 {"do": "settle", "ms": 1400}]
    inter = interaction(view, shiny, vw, vh, global_buttons(scout), home=view["kind"] == "home")
    acts += inter
    tall = (view.get("height") or vh) > vh * 1.6
    if tall and long_scroll and (view["kind"] == "home" or not inter):
        acts += [{"do": "scroll", "to": min((view.get("height") or vh) - vh, vh * 2.2), "ms": 3200}, {"do": "drift", "ms": 600}]
    if not inter and not tall:
        outs = view.get("outputs") or []
        if outs:
            acts += [{"do": "move", "target": {"css": outs[0]["css"]}, "ms": 900}, {"do": "drift", "ms": 1200}]
        else:
            acts += [{"do": "drift", "ms": 1800}]
    acts += [{"do": "drift", "ms": 1200}]
    outs = view.get("outputs") or []
    focus = norm_box(outs[0]["box"], vw, vh) if outs else None
    label = view["label"]
    if view["kind"] == "home": label = re.split(r"\s+[·|—–-]\s+", label)[0] or "Home"
    return {"id": "shot%d" % (idx + 1), "label": label, "view": view["id"], "reach": reach, "actions": acts,
            "focus": focus, "thumb": view.get("thumb"), "copy": view_copy(view)}


def view_copy(view):
    """what the screen itself says: its main heading and lead paragraph"""
    heads = [s_["text"] for s_ in view.get("sections") or [] if s_.get("tag") in ("h1", "h2")]
    return {"heading": heads[0] if heads else "", "lead": view.get("lead") or ""}


def tokens(s):
    return {w for w in re.findall(r"[a-z][a-z-]{3,}", (s or "").lower()) if w not in STOP and w not in ("with", "your", "that", "this", "from", "they", "their", "what", "each", "into")}


def match_features(features, shots, scout):
    """pair README features with the screens they describe (keyword overlap); -> {shot id: feature}, leftovers"""
    views = {v["id"]: v for v in (scout or {}).get("views") or []}
    def vtext(sh):
        v = views.get(sh.get("view")) or {}
        return " ".join([sh.get("label", ""), " ".join(s_["text"] for s_ in v.get("sections") or []), v.get("lead", ""),
                         " ".join(b["text"] for b in v.get("buttons") or []), " ".join((i.get("label") or "") for i in v.get("inputs") or [])])
    pairs = []
    for i, f in enumerate(features):
        ft = tokens(f.get("title", "") + " " + f.get("text", ""))
        for sh in shots:
            if (views.get(sh.get("view")) or {}).get("kind") == "home" and len(shots) > 1: continue   # the establishing shot speaks for itself
            ov = ft & tokens(vtext(sh))
            if len(ov) >= 2 or (f.get("title") and f["title"].lower() in sh.get("label", "").lower()):
                pairs.append((len(ov) / (len(ft) ** 0.5 + 1), i, sh["id"]))
    pairs.sort(reverse=True)
    used_f, used_s, out = set(), set(), {}
    for sc, i, sid in pairs:
        if i in used_f or sid in used_s: continue
        out[sid] = features[i]; used_f.add(i); used_s.add(sid)
    return out, [f for i, f in enumerate(features) if i not in used_f]


# ------------------------------------------------------------------ icon picker for feature tiles
ICON_WORDS = [("chart", r"chart|plot|graph|visual|dashboard|trend|metric|analytic|insight|report|radar"), ("bolt", r"fast|speed|instant|quick|real.?time|adaptive"),
              ("lock", r"secure|privacy|safe|auth|encrypt|integrity|key"), ("users", r"team|people|collab|share|user|group|interview"),
              ("globe", r"web|deploy|online|cloud|host|browser|html|world"), ("layers", r"layer|stack|mode|format|quarto|multiple|ways"),
              ("check", r"check|valid|test|accura|correct|verif|reality"), ("clock", r"time|history|session|schedule|resume|progress|async"),
              ("search", r"search|find|explore|discover|filter|query"), ("code", r"code|api|r\b|package|git|program|script|engineer"),
              ("download", r"download|export|pdf|file|save|archive"), ("sparkles", r"ai|smart|magic|auto|gamif|fun|badge|confetti"),
              ("map", r"map|geo|location|spatial"), ("table", r"table|data|row|column|spreadsheet|excel|bank"),
              ("target", r"goal|target|predict|estimate|measure|score|level|stake"), ("sliders", r"setting|control|tune|input|slider|config|custom")]


def icon_for(text):
    for name, rx in ICON_WORDS:
        if re.search(rx, text or "", re.I): return name
    return "sparkles"


# ------------------------------------------------------------------ templates
class Copy:
    """hands out copy for each screen without repeating itself"""

    def __init__(self, B, shots, scout):
        self.B = B; self.used = []
        self.matched, self.left = match_features(B["features"], shots, scout)

    def dup(self, line):
        t = tokens(line)
        return any(len(t & u) >= max(2, 0.6 * min(len(t), len(u))) for u in self.used if u)

    def use(self, line):
        if line: self.used.append(tokens(line))
        return line

    def for_shot(self, sh, max_words=24):
        """-> (headline, vo, title)"""
        f = self.matched.get(sh["id"])
        cp = sh.get("copy") or {}
        cands = []
        if f:
            vo = vo_line(("%s. %s" % (f["title"], f["text"])) if f.get("title") and f.get("text") else f.get("text") or "", max_words)
            cands.append((headline_from(f), vo, f.get("title") or sh["label"]))
        if cp.get("heading"):
            h = cp["heading"].strip().rstrip(".")
            hl = ("*%s.*" % h) if len(words(h)) <= 3 else emphasise(trim_words(h, 7))
            for src in sentences(cp.get("lead") or "") + [h + "."]:
                vo = vo_line(src, max_words)
                if vo and not self.dup(vo): cands.append((hl, vo, sh["label"])); break
        while self.left and not f:
            g = self.left.pop(0)
            vo = vo_line(("%s. %s" % (g["title"], g["text"])) if g.get("title") and g.get("text") else g.get("text") or "", max_words)
            if vo and not self.dup(vo): cands.append((headline_from(g), vo, g.get("title") or sh["label"])); break
        for hl, vo, title in cands:
            if vo and not self.dup(vo):
                return hl or emphasise(sh["label"], 1), self.use(vo), title
        # nothing to say that isn't filler: a headline, and let the music carry the scene
        return (cands[0][0] if cands else emphasise(sh["label"], 1)), "", (cands[0][2] if cands else sh["label"])


def hook_line(B, max_words=8):
    """a short, punchy statement for the opening: the summary if it is short, else its first clause, else the tagline"""
    summ = (sentences(B.get("summary") or "")[:1] or [""])[0].strip()
    if summ and len(words(summ)) <= max_words: return emphasise(summ, 2)
    c = first_clause(summ, 7)
    if c and len(words(c)) >= 3: return emphasise(c, 2)
    if B.get("tagline"): return emphasise(B["tagline"], 2)
    return "*%s.*" % B["name"]


def T_launch(B, shots, K):
    sc = []
    sc.append({"type": "hook", "text": hook_line(B), "anim": "rise", "vo": K.use(vo_line(B["summary"], 22)) if B["summary"] else "", "dur": 3.6})
    desc = vo_line(B["description"], 14) if B["description"] else ""
    title_vo = ("Meet %s. %s" % (B["name"], desc)).strip() if desc and not K.dup(desc) else "Meet %s." % B["name"]
    sc.append({"type": "title", "title": B["name"], "tagline": B["tagline"], "vo": K.use(title_vo), "dur": 3.4})
    layouts = ["window", "tilt", "float", "window", "split"]
    n = len(shots[:4])
    for i, s in enumerate(shots[:4]):
        hl, vo, title = K.for_shot(s)
        sc.append({"type": "shot", "shot": s["id"], "layout": layouts[i % len(layouts)], "camera": "auto", "headline": hl, "vo": vo, "dur": 4.6})
    rest = K.left
    if len(rest) >= 3:
        items = [{"title": (x.get("title") or first_clause(x["text"], 4) or trim_words(x["text"], 4)).rstrip("."), "text": trim_words(first_clause(x["text"], 12) or x["text"], 12),
                  "icon": icon_for(x.get("title", "") + " " + x["text"])} for x in rest[:4]]
        sc.append({"type": "features", "headline": "And *so much more.*", "items": items[:3 if len(items) < 4 else 4],
                   "vo": "Plus %s." % join_and([i["title"].lower() for i in items[:3] if i["title"]]), "dur": 4.5})
    if len(shots) >= 3:
        sc.append({"type": "montage", "shots": [s["id"] for s in shots[:5]], "caption": "", "vo": "", "dur": 2.8})
    sc.append({"type": "end", "title": B["name"], "tagline": B["tagline"], "cta": B["cta"], "note": "", "vo": "%s. %s" % (B["name"], B["tagline"]), "dur": 4.6})
    return sc


def T_teaser(B, shots, K):
    sc = []
    tag = B["tagline"].rstrip(".") or B["name"]
    ws = words(tag)
    hook = (" ".join(ws[:-1]) + " *" + ws[-1] + ".*") if len(ws) > 1 else "*%s.*" % tag
    sc.append({"type": "hook", "text": hook, "anim": "slam", "dur": 2.0, "bg": "dark"})
    if shots: sc.append({"type": "shot", "shot": shots[0]["id"], "layout": "full", "camera": "auto", "caption": "", "dur": 2.0})
    sc.append({"type": "title", "title": B["name"], "tagline": "", "dur": 2.0})
    if len(shots) > 1:
        sc.append({"type": "montage", "shots": [s["id"] for s in shots[1:5]] or [shots[0]["id"]], "dur": 4.0})
    titles = [x["title"] for x in B["features"] if x.get("title") and len(words(x["title"])) <= 2][:3]
    if len(titles) >= 2:
        sc.append({"type": "hook", "text": " ".join("%s." % t for t in titles[:-1]) + " *%s.*" % titles[-1], "anim": "slam", "dur": 2.0})
    for i, s in enumerate(shots[:3]):
        hl, vo, title = K.for_shot(s, 10)
        sc.append({"type": "shot", "shot": s["id"], "layout": ["tilt", "full", "float"][i % 3], "camera": "auto", "caption": trim_words(title, 5), "dur": 2.0})
    if len(shots) >= 3: sc.append({"type": "grid", "headline": "All in *one place.*", "shots": [s["id"] for s in shots[:6]], "dur": 2.5})
    sc.append({"type": "end", "title": B["name"], "tagline": B["tagline"], "cta": B["cta"], "dur": 4.0})
    return sc


def T_tour(B, shots, K):
    sc = []
    sc.append({"type": "title", "title": B["name"], "tagline": B["tagline"], "vo": K.use("This is %s. %s" % (B["name"], vo_line(B["description"] or B["tagline"], 18))), "dur": 3.6})
    for i, s in enumerate(shots[:5]):
        hl, vo, title = K.for_shot(s, 22)
        t = title.rstrip(".")
        sc.append({"type": "shot", "shot": s["id"], "layout": "window", "camera": "auto", "headline": "*%s.*" % t if len(words(t)) <= 4 else emphasise(t),
                   "step": i + 1, "vo": vo, "dur": 5.0})
    sc.append({"type": "end", "title": B["name"], "tagline": B["tagline"], "cta": B["cta"], "vo": "Try %s today." % B["name"], "dur": 4.2})
    return sc


def T_social(B, shots, K):
    sc = []
    first = (sentences(B["summary"])[:1] or [""])[0] if B["summary"] else ""
    sc.append({"type": "hook", "text": hook_line(B, 6), "anim": "pop", "vo": K.use(vo_line(first, 10)) if first else "", "dur": 2.4})
    sc.append({"type": "title", "title": B["name"], "tagline": B["tagline"], "vo": "Meet %s." % B["name"], "dur": 2.0})
    for i, s in enumerate(shots[:3]):
        hl, vo, title = K.for_shot(s, 12)
        sc.append({"type": "shot", "shot": s["id"], "layout": "phone" if B.get("_mobile") else "window", "camera": "auto", "headline": hl, "vo": vo, "dur": 3.0})
    sc.append({"type": "end", "title": B["name"], "tagline": B["tagline"], "cta": B["cta"], "vo": "Link in bio.", "dur": 3.0})
    return sc


def T_demo(B, shots, K):
    sc = []
    sc.append({"type": "title", "title": B["name"], "tagline": B["tagline"], "vo": K.use(vo_line(B["summary"] or B["description"], 20)), "dur": 3.5})
    for i, s in enumerate(shots[:4]):
        hl, vo, title = K.for_shot(s, 22)
        sc.append({"type": "shot", "shot": s["id"], "layout": "window", "camera": "push", "caption": trim_words(title, 5), "vo": vo, "dur": 5.0})
    sc.append({"type": "end", "title": B["name"], "tagline": B["tagline"], "cta": B["cta"], "vo": "", "dur": 3.5})
    return sc


def join_and(xs):
    xs = [x for x in xs if x]
    return xs[0] if len(xs) == 1 else ", ".join(xs[:-1]) + " and " + xs[-1] if xs else ""


BUILDERS = {"launch": T_launch, "teaser": T_teaser, "tour": T_tour, "social": T_social, "demo": T_demo}


# ------------------------------------------------------------------ media sources (no app: uploaded screenshots / recordings)
def media_shots(P):
    out = []
    for i, m in enumerate((P.get("media") or {}).get("items") or []):
        out.append({"id": "shot%d" % (i + 1), "label": m.get("label") or os.path.splitext(os.path.basename(m["file"]))[0].replace("_", " ").replace("-", " ").title(),
                    "view": None, "media": m["file"], "actions": [], "thumb": m.get("thumb"), "focus": None})
    return out


# ------------------------------------------------------------------ main
def plan(P, job, template=None, use_llm=True):
    cfg = P.cfg
    template = template or cfg["film"].get("template") or "launch"
    if template not in BUILDERS: raise DirectorError("unknown template %s" % template)
    facts = P.get("facts") or {}; scout = P.get("scout") or {}
    B = brand(P, facts, scout)
    vw, vh = P.viewport
    if (facts.get("source_kind") == "media") or (cfg["source"].get("kind") == "media"):
        shots = media_shots(P)
        if not shots: raise DirectorError("Upload at least one screenshot or screen recording first.")
    else:
        if not scout.get("views"): raise DirectorError("Scout the app first (Source › Scout).")
        views = rank_views(scout)
        home = next((v for v in views if v["kind"] == "home"), views[0])
        max_shots = {"launch": 4, "teaser": 5, "tour": 5, "social": 3, "demo": 4}[template]
        chosen = [home] + [v for v in views if v is not home][: max_shots - 1]
        if len(chosen) == 1 and (home.get("height") or vh) > vh * 1.6:
            # single tall page: hero + a scrolling shot
            scroll = dict(home); scroll["id"] = home["id"]; scroll["label"] = "Scroll"
            shots = [shot_for(home, home, scout, vw, vh, 0, long_scroll=False), shot_for(scroll, home, scout, vw, vh, 1, long_scroll=True)]
            shots[1]["actions"] = [{"do": "wait", "ms": 300}, {"do": "scroll", "to": min(home["height"] - vh, vh * 3), "ms": 4200}, {"do": "drift", "ms": 800}]
        else:
            shots = [shot_for(v, home, scout, vw, vh, i) for i, v in enumerate(chosen)]
    B["_mobile"] = vw < 600
    K = Copy(B, shots, scout)
    # story order: the establishing shot, then screens in the README's feature order, then the rest
    fidx = {sid: next((i for i, f in enumerate(B["features"]) if f is feat), 99) for sid, feat in K.matched.items()}
    shots = shots[:1] + sorted(shots[1:], key=lambda sh: (fidx.get(sh["id"], 99), shots.index(sh)))
    scenes = BUILDERS[template](B, shots, K)
    used = set()
    for s in scenes:
        if s.get("shot"): used.add(s["shot"])
        for x in s.get("shots") or []: used.add(x)
    shots = [s for s in shots if s["id"] in used] or shots[:1]
    for i, s in enumerate(scenes):
        s["id"] = "s%d" % (i + 1); s.setdefault("transition", "auto"); s.setdefault("vo", ""); s["enabled"] = True
    tpl = TEMPLATES[template]
    sb = {"version": 1, "template": template, "brand": {k: B[k] for k in ("name", "tagline", "description", "url", "cta")},
          "scenes": scenes, "shots": shots, "vo": tpl["vo"], "copy": "heuristic"}
    if use_llm and (cfg.get("llm") or {}).get("provider", "none") not in ("none", "", None):
        try:
            from . import llm
            job.msg("Writing the script with %s…" % cfg["llm"]["provider"])
            sb = llm.rewrite(P, sb, B, scout, facts, job)
            sb["copy"] = cfg["llm"]["provider"]
        except Exception as e:  # noqa: BLE001
            job.warn("AI copywriter failed (%s); kept the automatic script." % str(e)[:160])
    P.put("storyboard", sb)
    # sync project settings that come with the template (only when still on 'auto')
    c = P.cfg; changed = False
    if c["film"].get("template") != template: c["film"]["template"] = template; changed = True
    if changed: P.save_cfg(c)
    return sb
