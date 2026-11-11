"""Optional AI copywriter: rewrites the storyboard's words (never its structure).

llm.provider:
  openai     OPENAI_API_KEY; llm.base_url for any OpenAI-compatible server
             (Ollama: http://localhost:11434/v1, LM Studio: http://localhost:1234/v1)
  anthropic  ANTHROPIC_API_KEY
The model gets the facts (README, page titles, headings, tabs) and the scene list, and
must answer with JSON. Only text fields are merged back, after validation.
"""
import json, os, re, urllib.request

from .util import DirectorError

TEXT_FIELDS = {"hook": ["text", "vo"], "title": ["title", "tagline", "vo"], "shot": ["headline", "caption", "vo"], "features": ["headline", "vo", "items"],
               "montage": ["caption", "vo"], "grid": ["headline", "vo"], "stat": ["value", "label", "vo"], "quote": ["text", "author", "vo"], "end": ["title", "tagline", "cta", "vo"]}

SYSTEM = """You are the copywriter of a short product launch film (under 60 seconds) for a software app.
Write crisp, concrete, benefit-led copy in the requested language. No hype words (revolutionary, game-changing, seamless, unlock, elevate).
On-screen text is short: headlines max 6 words; use *asterisks* around the 1-3 words to highlight with the brand gradient and _underscores_ for muted words.
Voice-over lines are natural spoken sentences, max 22 words each, and together read in the time available (about 2.6 words per second).
Never invent features, numbers or claims that are not supported by the facts. Keep the product name exactly as given.
Answer with JSON only."""


def _http(url, headers, body, timeout=90):
    req = urllib.request.Request(url, data=json.dumps(body).encode(), headers=dict(headers, **{"Content-Type": "application/json"}))
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r: return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        raise DirectorError("%s: HTTP %s %s" % (url.split("/")[2], e.code, e.read().decode(errors="replace")[:300]))


def complete(cfg, system, user):
    prov = cfg.get("provider"); model = cfg.get("model") or ""
    if prov == "anthropic":
        key = os.environ.get("ANTHROPIC_API_KEY")
        if not key: raise DirectorError("ANTHROPIC_API_KEY is not set")
        r = _http("https://api.anthropic.com/v1/messages", {"x-api-key": key, "anthropic-version": "2023-06-01"},
                  {"model": model or "claude-sonnet-4-5", "max_tokens": 2500, "system": system, "messages": [{"role": "user", "content": user}]})
        return "".join(b.get("text", "") for b in r.get("content", []))
    base = (cfg.get("base_url") or os.environ.get("OPENAI_BASE_URL") or "https://api.openai.com/v1").rstrip("/")
    key = os.environ.get("OPENAI_API_KEY", "")
    if "api.openai.com" in base and not key: raise DirectorError("OPENAI_API_KEY is not set")
    body = {"model": model or ("gpt-4.1-mini" if "openai.com" in base else "llama3.1"), "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}], "temperature": 0.7}
    if "openai.com" in base: body["response_format"] = {"type": "json_object"}
    r = _http(base + "/chat/completions", {"Authorization": "Bearer " + key} if key else {}, body)
    return r["choices"][0]["message"]["content"]


def rewrite(P, sb, B, scout, facts, job):
    cfg = P.cfg; film = cfg["film"]
    views = [{"label": v["label"], "headings": [s["text"] for s in v.get("sections", [])][:6], "inputs": [i.get("label") for i in v.get("inputs", [])][:6],
              "outputs": [o["kind"] for o in v.get("outputs", [])][:6]} for v in (scout or {}).get("views", [])][:8]
    shots = {s["id"]: s.get("label") for s in sb["shots"]}
    scenes = []
    for s in sb["scenes"]:
        d = {"id": s["id"], "type": s["type"], "seconds": s.get("dur")}
        if s.get("shot"): d["screen"] = shots.get(s["shot"])
        for k in TEXT_FIELDS.get(s["type"], []):
            if s.get(k): d[k] = s[k]
        scenes.append(d)
    rd = (facts or {}).get("readme") or {}
    brief = {"product": B["name"], "tagline": B["tagline"], "description": B["description"][:900], "readme_summary": rd.get("paragraph", "")[:900],
             "features": B["features"][:8], "screens": views, "film": {"template": sb["template"], "tone": film.get("tone"), "audience": film.get("audience"),
             "language": film.get("language", "en"), "voice_over": sb.get("vo", True), "max_seconds": 58}, "scenes": scenes}
    user = ("Rewrite the words of this storyboard. Keep every scene id and type; fill the same fields (skip 'vo' when voice_over is false). "
            "For 'features' scenes, items is a list of {title (max 3 words), text (max 12 words), icon (one of chart, bolt, lock, users, globe, layers, check, clock, search, code, download, sparkles, map, table, target, sliders)}. "
            "Reply as {\"brand\": {\"tagline\": ...}, \"scenes\": [{\"id\": ..., fields...}]}.\n\n" + json.dumps(brief, ensure_ascii=False))
    raw = complete(cfg.get("llm") or {}, SYSTEM, user)
    m = re.search(r"\{.*\}", raw, re.S)
    if not m: raise DirectorError("the model did not return JSON")
    data = json.loads(m.group(0))
    by = {s["id"]: s for s in sb["scenes"]}
    n = 0
    for s in data.get("scenes", []):
        tgt = by.get(s.get("id"))
        if not tgt: continue
        for k in TEXT_FIELDS.get(tgt["type"], []):
            v = s.get(k)
            if v is None: continue
            if k == "items":
                if isinstance(v, list) and v and all(isinstance(i, dict) for i in v):
                    tgt["items"] = [{"title": str(i.get("title", ""))[:40], "text": str(i.get("text", ""))[:120], "icon": str(i.get("icon") or "sparkles")} for i in v[:4]]; n += 1
            elif isinstance(v, str) and v.strip():
                tgt[k] = v.strip()[:240]; n += 1
    tag = (data.get("brand") or {}).get("tagline")
    if isinstance(tag, str) and tag.strip() and not cfg["brand"].get("tagline"):
        sb["brand"]["tagline"] = tag.strip()[:80]
    job.log("AI copywriter updated %d fields" % n)
    return sb
