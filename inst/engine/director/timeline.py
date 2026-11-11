"""Resolve storyboard + voice-over + footage into timeline.json (absolute times).

The stage (stage/film.js) is a pure function of this file and of t, so the live
preview in the app and the final render show exactly the same film. Music and
sound design are also placed from it (cuts, clicks, hits, voice-over segments).
"""
import colorsys, glob, json, os, re, shutil

from .util import read_json, write_json

MIN_DUR = {"hook": 2.0, "title": 2.4, "shot": 2.6, "features": 3.4, "montage": 2.0, "grid": 2.4, "stat": 2.4, "quote": 3.0, "end": 3.4}
TR_DUR = {"cut": 0.0, "fade": 0.5, "blur": 0.6, "zoom": 0.55, "slide": 0.6, "whip": 0.36, "rise": 0.55, "flash": 0.3, "wipe": 0.65, "iris": 0.7, "push": 0.6, "flip": 0.7}
TRANSITIONS = list(TR_DUR)
MOOD_BPM = {"pulse": 120, "keys": 96, "ambient": 80, "drive": 128, "lofi": 84, "cinematic": 90, "bright": 112, "none": 100}
TEMPLATE_MOOD = {"launch": "keys", "teaser": "pulse", "tour": "bright", "social": "drive", "demo": "ambient"}
TEMPLATE_THEME = {"launch": "light", "teaser": "dark", "tour": "light", "social": "dark", "demo": "light"}
DEFAULT_COLORS = ["#2563eb", "#7c3aed", "#db2777"]
LEAD, TAIL = 0.3, 0.45


def auto_transition(template, prev, cur, i):
    a, b = prev["type"], cur["type"]
    if template in ("teaser", "social"):
        if b == "end": return "flash"
        if a == "hook" and b == "shot": return "zoom"
        if b == "hook": return "cut"
        if b == "montage" or a == "montage": return "cut"
        return ["whip", "zoom", "cut", "slide"][i % 4]
    if template == "demo":
        return "fade" if b != "end" else "blur"
    if a == "hook" and b == "title": return "blur"
    if b == "title": return "blur"
    if a == "title": return "zoom"
    if b == "end": return "blur"
    if b == "features" or b == "grid": return "rise"
    if b == "montage": return "cut"
    if a == "montage": return "blur"
    if a == "shot" and b == "shot": return "push" if template == "tour" else ["slide", "blur", "wipe"][i % 3]
    return "fade"


def bpm_of(P, template):
    m = P.cfg["music"]
    if m.get("bpm"): return float(m["bpm"])
    mood = m.get("mood") or "auto"
    if mood == "auto": mood = TEMPLATE_MOOD.get(template, "keys")
    return float(MOOD_BPM.get(mood, 100))


def durations(P, sb, vo_durs):
    """-> list of (scene, dur, vo_dur)"""
    template = sb.get("template", "launch")
    scenes = [s for s in sb["scenes"] if s.get("enabled", True)]
    music_first = not sb.get("vo", True) or not vo_durs
    beat = 60.0 / bpm_of(P, template)
    out = []
    for i, s in enumerate(scenes):
        base = float(s.get("dur") or 3.0)
        vd = vo_durs.get(s["id"]) if vo_durs else None
        if vd:
            lead = 0.6 if i == 0 else LEAD
            tail = 1.5 if s["type"] == "end" else TAIL
            need = lead + vd + tail
            d = max(base if s.get("lock") else MIN_DUR.get(s["type"], 2.5), need)
        else:
            d = base
        if music_first and template in ("teaser", "social"):
            d = max(2, round(d / beat)) * beat
        out.append((s, round(d, 3), vd))
    return out


def estimate(P, sb, vo_durs):
    return sum(d for _, d, _ in durations(P, sb, vo_durs))


def hex2rgb(h):
    h = h.lstrip("#")
    if len(h) == 3: h = "".join(c * 2 for c in h)
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def rgb2hex(c): return "#%02x%02x%02x" % tuple(max(0, min(255, int(round(x)))) for x in c)


def palette3(colors):
    cs = [c for c in (colors or []) if isinstance(c, str) and re.match(r"^#?[0-9a-fA-F]{3,6}$", c)]
    cs = ["#" + c.lstrip("#") for c in cs]
    if not cs: return list(DEFAULT_COLORS)
    while len(cs) < 3:
        r, g, b = [x / 255 for x in hex2rgb(cs[-1])]
        h, l, s = colorsys.rgb_to_hls(r, g, b)
        h = (h + (0.11 if len(cs) == 1 else 0.13)) % 1.0
        cs.append(rgb2hex([x * 255 for x in colorsys.hls_to_rgb(h, min(0.6, max(0.45, l)), max(0.6, s))]))
    # keep them legible on both themes
    out = []
    for c in cs[:3]:
        r, g, b = [x / 255 for x in hex2rgb(c)]
        h, l, s = colorsys.rgb_to_hls(r, g, b)
        out.append(rgb2hex([x * 255 for x in colorsys.hls_to_rgb(h, min(0.62, max(0.42, l)), max(0.55, s))]))
    return out


def shot_info(P, sid, shot=None):
    """recorded footage for a shot (None when missing, or recorded from a different recipe)"""
    d = P.p("shots", sid)
    meta = read_json(os.path.join(d, "meta.json"), None)
    if meta and shot is not None and meta.get("recipe"):
        from .capture import recipe_hash
        if meta["recipe"] != recipe_hash(shot): return None
    if meta and (meta.get("frames") or meta.get("still")):
        info = {"frames": int(meta.get("frames") or 0), "fps": int(meta.get("fps") or 60), "vw": meta["viewport"][0], "vh": meta["viewport"][1],
                "markers": read_json(os.path.join(d, "markers.json"), {}) or {}, "still": bool(meta.get("still")),
                "proxy": os.path.isdir(os.path.join(d, "proxy")), "dir": "shots/%s/" % sid}
        cur = read_json(os.path.join(d, "cursor.json"), None)
        if cur: info["cursor"] = "shots/%s/cursor.json" % sid
        return info
    return None


def clip_map(info, dur, max_speed=1.35, mode="scene"):
    """choose source offset and speed for a clip of `dur` seconds"""
    if not info or info.get("still") or not info.get("frames"): return 0.0, 1.0
    fps = info["fps"]; n = info["frames"]; L = n / fps
    mk = info.get("markers") or {}
    nav = mk.get("click_nav")
    clicks = sorted(v / fps for k, v in mk.items() if k.startswith("click") and k != "click_nav")
    frm = 0.0
    if nav is not None and L - (nav / fps + 0.3) >= dur * 0.75:
        frm = nav / fps + 0.3                                 # open on the screen itself, not on the way there
        if mode == "montage" and clicks: frm = max(frm, clicks[0] - 0.35)
    elif mode == "montage" and clicks:
        frm = max(0.0, clicks[0] - 0.35)
    elif clicks and clicks[0] - 0.9 > 0 and L - (clicks[0] - 0.9) >= dur * 0.8:
        frm = max(0.0, clicks[0] - 0.9)
    avail = max(0.1, L - frm)
    speed = min(max_speed, max(0.85, avail / dur)) if mode == "scene" else 1.15
    return round(frm, 3), round(speed, 3)


def word_times(text, t0, span, anim, beat):
    ws = [w for w in re.split(r"\s+", re.sub(r"[*_~]", "", text.replace("|", " "))) if w]
    if not ws: return []
    if anim == "slam":
        step = beat if len(ws) * beat <= span * 0.7 else max(0.16, span * 0.6 / len(ws))
        return [round(t0 + 0.05 + i * step, 3) for i in range(len(ws))]
    step = min(0.12, span * 0.4 / len(ws))
    return [round(t0 + 0.15 + i * step, 3) for i in range(len(ws))]


def _norm(w): return re.sub(r"[^a-z0-9]", "", w.lower())


def spoken_times(text, seg):
    """when each on-screen word is spoken in the voice-over (words appear as they are said); None if they don't match"""
    shown = [w for w in re.split(r"\s+", re.sub(r"[*_~]", "", text.replace("|", " "))) if w]
    said = [w for w in re.split(r"\s+", re.sub(r"[*_~|]", " ", seg["text"])) if w]
    if not shown or not said: return None
    tot = sum(len(w) + 1 for w in said); acc = 0; at = []
    for w in said:
        at.append(seg["start"] + (seg["end"] - seg["start"]) * acc / tot); acc += len(w) + 1
    out, j, hits = [], 0, 0
    for w in shown:
        k = next((i for i in range(j, len(said)) if _norm(said[i]) == _norm(w) and _norm(w)), None)
        if k is not None: out.append(round(at[k] - 0.08, 3)); j = k + 1; hits += 1
        else: out.append(round((out[-1] + 0.12) if out else seg["start"], 3))
    return out if hits >= max(1, 0.6 * len(shown)) else None


def theme(P, sb, scout):
    cfg = P.cfg; look = cfg["look"]; template = sb.get("template", "launch")
    mode = look.get("theme", "auto")
    if mode == "auto": mode = TEMPLATE_THEME.get(template, "light")
    cols = palette3((cfg["brand"].get("colors") or []) or ((scout or {}).get("colors") or {}).get("palette"))
    W, H = P.stage_size
    return {"mode": mode, "c1": cols[0], "c2": cols[1], "c3": cols[2], "bg": look.get("background", "aurora"), "font": look.get("font", "Inter"),
            "window": look.get("window", "macos"), "radius": look.get("radius", 22), "grain": bool(look.get("grain", True)), "W": W, "H": H}


def logo(P, facts, scout):
    b = P.cfg["brand"]
    for cand in [b.get("logo")] + [(scout or {}).get("logo_file")] + list((facts or {}).get("logos") or []):
        if not cand: continue
        path = cand if os.path.isabs(cand) else P.p(cand)
        if os.path.exists(path):
            ext = os.path.splitext(path)[1].lower() or ".png"
            dst = P.p("assets", "logo" + ext)
            if os.path.abspath(path) != os.path.abspath(dst):
                os.makedirs(P.p("assets"), exist_ok=True); shutil.copy(path, dst)
            return "assets/logo" + ext
    return ""


def display_url(P, sb, scout):
    b = sb.get("brand") or {}
    u = b.get("url") or ""
    if u and not re.search(r"github\.com|gitlab\.com", u):
        return re.sub(r"^https?://(www\.)?", "", u).rstrip("/")
    su = (scout or {}).get("url") or ""
    if su and not re.search(r"127\.0\.0\.1|localhost", su): return re.sub(r"^https?://(www\.)?", "", su).rstrip("/")
    return (b.get("name") or "app").replace(" ", "").lower()


def build(P, job=None, preview=False):
    sb = P.get("storyboard")
    if not sb: raise RuntimeError("no storyboard")
    facts = P.get("facts") or {}; scout = P.get("scout") or {}
    clips = (read_json(P.p("vo", "clips.json"), {}) or {}).get("clips") or {}
    cur = {s_["id"]: (s_.get("vo") or "").strip() for s_ in sb["scenes"]}
    stale = [k for k, v in clips.items() if (v.get("text") or "").strip() != cur.get(k, "")]
    clips = {k: v for k, v in clips.items() if k not in stale}        # a clip only plays under the line it was made for
    vo_durs = {k: v["dur"] for k, v in clips.items()} if sb.get("vo", True) and P.cfg["voice"].get("enabled", True) else {}
    template = sb.get("template", "launch")
    bpm = bpm_of(P, template); beat = 60.0 / bpm
    look = P.cfg["look"]; forced = look.get("transition", "auto")
    rows = durations(P, sb, vo_durs)
    shots = {s["id"]: s for s in sb.get("shots") or []}
    sinfo = {sid: shot_info(P, sid, shots[sid]) for sid in shots}
    t = 0.0; out = []; vo = []; sfx = []; hits = []
    for i, (s, d, vd) in enumerate(rows):
        sc = json.loads(json.dumps(s))
        sc["t0"] = round(t, 3); sc["t1"] = round(t + d, 3); sc["dur"] = d
        tr = s.get("transition") or "auto"
        if tr == "auto": tr = forced if forced not in ("auto", "", None) else (auto_transition(template, out[-1], sc, i) if out else "cut")
        if i == 0: tr = "cut"
        td = min(TR_DUR.get(tr, 0.5), d * 0.4, out[-1]["dur"] * 0.4 if out else 1)
        sc["tin"] = {"type": tr, "dur": round(td, 3)}
        if vd:
            st = t + (0.6 if i == 0 else LEAD)
            vo.append({"id": s["id"], "start": round(st, 3), "end": round(st + vd, 3), "text": s.get("vo", ""), "file": clips[s["id"]]["file"]})
        if sc["type"] == "shot" and sc.get("shot"):
            info = sinfo.get(sc["shot"]) or {}
            frm, speed = clip_map(info, d + td, 1.6 if template in ("teaser", "social") else 1.35)
            sc["clip"] = {"from": frm, "speed": speed}
            sc["info"] = info or None
            sc["thumb"] = (shots.get(sc["shot"]) or {}).get("thumb")
            sc["focus"] = (shots.get(sc["shot"]) or {}).get("focus")
            sc["label"] = (shots.get(sc["shot"]) or {}).get("label")
        if sc["type"] in ("montage", "grid"):
            items = []
            ids = [x for x in sc.get("shots") or [] if x in shots]
            n = max(1, len(ids))
            if sc["type"] == "montage":
                per = d / n
                if template in ("teaser", "social") or not vo_durs: per = max(beat, round(per / beat) * beat)
                for k, sid in enumerate(ids):
                    a = k * per; b = d if k == n - 1 else (k + 1) * per
                    info = sinfo.get(sid) or {}
                    frm, speed = clip_map(info, b - a, mode="montage")
                    items.append({"shot": sid, "a": round(a, 3), "b": round(b, 3), "from": frm, "speed": speed, "info": info or None,
                                  "thumb": shots[sid].get("thumb"), "focus": shots[sid].get("focus")})
            else:
                for sid in ids:
                    info = sinfo.get(sid) or {}
                    items.append({"shot": sid, "info": info or None, "thumb": shots[sid].get("thumb"), "mid": int((info.get("frames") or 0) * 0.6)})
            sc["items"] = items
        if sc["type"] == "hook":
            sc["times"] = word_times(sc.get("text", ""), t, d, sc.get("anim", "rise"), beat / (1 if bpm < 110 else 2) if template in ("teaser", "social") else 0.42)
            if vd and vo and vo[-1]["id"] == s["id"]:
                synced = spoken_times(sc.get("text", ""), vo[-1])
                if synced: sc["times"] = synced; sc["synced"] = True
            if sc.get("anim") == "slam": hits += [{"t": x, "kind": "hit"} for x in sc["times"]]
        if sc["type"] == "end": hits.append({"t": sc["t0"], "kind": "end"})
        if sc["type"] == "title": hits.append({"t": sc["t0"], "kind": "title"})
        if i > 0 and tr in ("zoom", "whip", "slide", "wipe", "push", "flip", "iris"):
            sfx.append({"t": round(t - td / 2, 3), "kind": "whoosh", "dur": td})
        if i > 0 and tr == "flash": sfx.append({"t": round(t, 3), "kind": "hit"})
        out.append(sc); t += d
    total = round(t, 3)
    # clicks from footage on screen
    for sc in out:
        segs = []
        if sc["type"] == "shot" and sc.get("info"): segs.append((sc["info"], sc["t0"], sc["t1"], sc["clip"]["from"], sc["clip"]["speed"]))
        if sc["type"] == "montage":
            for it in sc.get("items") or []:
                if it.get("info"): segs.append((it["info"], sc["t0"] + it["a"], sc["t0"] + it["b"], it["from"], it["speed"]))
        for info, a, b, frm, speed in segs:
            for k, f in (info.get("markers") or {}).items():
                if not k.startswith("click"): continue
                tt = a + (f / info["fps"] - frm) / speed
                if a + 0.05 <= tt < b - 0.02: sfx.append({"t": round(tt, 3), "kind": "click"})
    caps = []
    for v in vo:
        txt = re.sub(r"[*_~|]", "", v["text"]).strip()
        ws = txt.split(); tot = sum(len(w) + 1 for w in ws) or 1; acc = 0; wt = []
        for w in ws:
            wt.append(round(v["start"] + (v["end"] - v["start"]) * acc / tot, 3)); acc += len(w) + 1
        caps.append({"start": v["start"], "end": v["end"], "text": txt, "words": ws, "wt": wt})
    # brand edits made after planning flow into the film (title / end card / CTA)
    from .plan import brand as brand_now
    Bn = brand_now(P, facts, scout); old = sb.get("brand") or {}
    for sc in out:
        if sc["type"] in ("title", "end"):
            if sc.get("title") in (None, "", old.get("name")): sc["title"] = Bn["name"]
            if sc.get("tagline") in (None, old.get("tagline")) and Bn["tagline"]: sc["tagline"] = Bn["tagline"]
            if sc["type"] == "end" and sc.get("cta") in (None, old.get("cta")) and Bn["cta"]: sc["cta"] = Bn["cta"]
    sb = dict(sb); sb["brand"] = {k: Bn[k] for k in ("name", "tagline", "description", "url", "cta")}
    th = theme(P, sb, scout)
    tl = {"version": 1, "template": template, "W": th["W"], "H": th["H"], "fps": int(P.cfg["format"].get("fps") or 60), "duration": total,
          "bpm": bpm, "theme": th, "brand": dict(sb.get("brand") or {}, logo=logo(P, facts, scout), url_display=display_url(P, sb, scout)),
          "scenes": out, "vo": vo, "sfx": sorted(sfx, key=lambda x: x["t"]), "hits": hits, "captions": caps,
          "capstyle": P.cfg["look"].get("captions", "clean"), "preview": bool(preview),
          "vo_stale": [k for k in stale if cur.get(k)], "vo_missing": [k for k, v in cur.items() if v and k not in clips],
          "shot_status": {sid: ("ok" if sinfo[sid] else ("stale" if os.path.exists(P.p("shots", sid, "meta.json")) else "missing")) for sid in shots}}
    P.put("timeline", tl)
    if total > 60.5 and job: job.warn("The film is %.1fs long (the target is under 60s)." % total)
    return tl
