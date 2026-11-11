"""Voice-over: one clip per scene line, cleaned up, cached, with durations.

Providers (voice.provider):
  human       your recordings: vo/human/<scene id>.(wav|m4a|mp3|webm|ogg|aiff|flac)  (record them in the app)
  say         macOS built-in speech (Premium / Enhanced voices sound best)
  edge        Microsoft Edge neural voices (free, online; pip install edge-tts)
  openai      OpenAI TTS (OPENAI_API_KEY), gpt-4o-mini-tts with tone instructions
  elevenlabs  ElevenLabs (ELEVENLABS_API_KEY)
  piper       Piper neural TTS, offline (pip install piper-tts; voices download on first use)
  pico        SVOX Pico, offline (pip install ttspico)
  espeak      eSpeak NG, offline (robotic; last resort)
  auto        the first available of: human, say, edge, piper, pico, espeak

Writes vo/<scene>.wav (48 kHz mono, -19 dBFS speech) and vo/clips.json.
"""
import hashlib, json, os, re, shutil, subprocess, sys, tempfile, urllib.request

import numpy as np
from scipy import signal

from . import ff as FF
from .util import DirectorError, read_json, write_json, which

SR = 48000
HUMAN_EXT = (".wav", ".m4a", ".mp3", ".webm", ".ogg", ".aiff", ".aif", ".flac", ".mp4")
MAX_FILM = 59.5

CATALOG = {
    "edge": ["en-US-AvaNeural", "en-US-AndrewNeural", "en-US-EmmaNeural", "en-US-BrianNeural", "en-US-AriaNeural", "en-US-GuyNeural",
             "en-US-JennyNeural", "en-GB-SoniaNeural", "en-GB-RyanNeural", "en-AU-NatashaNeural", "en-AU-WilliamNeural", "en-IN-NeerjaNeural",
             "de-DE-KatjaNeural", "de-DE-ConradNeural", "fr-FR-DeniseNeural", "fr-FR-HenriNeural", "es-ES-ElviraNeural", "it-IT-ElsaNeural",
             "pt-BR-FranciscaNeural", "nl-NL-ColetteNeural", "ja-JP-NanamiNeural"],
    "openai": ["coral", "alloy", "ash", "ballad", "echo", "fable", "nova", "onyx", "sage", "shimmer", "verse"],
    "elevenlabs": ["Rachel:21m00Tcm4TlvDq8ikWAM", "Adam:pNInz6obpgDQGcFmaJgB", "Antoni:ErXwobaYiN019PkySvjV", "Sarah:EXAVITQu4vr4xnSDxMaL",
                   "Josh:TxGEqnHWrfWFTfGW9XjX", "Elli:MF3mGyEYCl7XYWbV9V6O", "Domi:AZnzlk1XvdvUeBnXmlld", "Sam:yoZ06aMxZJJ28mfd3POQ"],
    "piper": ["en_US-lessac-medium", "en_US-amy-medium", "en_US-ryan-high", "en_US-hfc_female-medium", "en_US-joe-medium",
              "en_GB-alba-medium", "en_GB-northern_english_male-medium", "en_GB-cori-high", "de_DE-thorsten-high", "fr_FR-siwis-medium", "es_ES-davefx-medium"],
    "pico": ["en-US", "en-GB", "de-DE", "es-ES", "fr-FR", "it-IT"],
    "espeak": ["en-us", "en-gb", "en-us+f3", "en-gb+m3", "de", "fr", "es", "it"],
}
SAY_PREFS = ["Ava (Premium)", "Zoe (Premium)", "Evan (Premium)", "Serena (Premium)", "Jamie (Premium)", "Ava (Enhanced)", "Zoe (Enhanced)",
             "Evan (Enhanced)", "Serena (Enhanced)", "Allison (Enhanced)", "Samantha (Enhanced)", "Daniel (Enhanced)", "Samantha", "Daniel", "Karen", "Alex"]


# ------------------------------------------------------------------ availability
def _mod(name):
    try:
        __import__(name); return True
    except Exception:  # noqa: BLE001
        return False


def pico_dir():
    cands = [os.environ.get("PICO_LANG_DIR", ""), os.path.expanduser("~/.local/share/pico"), "/usr/share/pico/lang", "/usr/local/share/pico/lang"]
    try:
        import ttspico
        base = os.path.dirname(ttspico.__file__)
        cands += [os.path.join(base, "lang"), os.path.join(base, "picopi", "pico", "lang")]
    except Exception:  # noqa: BLE001
        pass
    for c in cands:
        if c and os.path.isdir(c) and glob_any(c, "*_ta.bin"): return c.rstrip("/") + "/"
    return None


def glob_any(d, pat):
    import glob
    return bool(glob.glob(os.path.join(d, pat)))


def espeak_bin(): return which("espeak-ng") or which("espeak")


def say_voices():
    if not which("say"): return []
    out = subprocess.run(["say", "-v", "?"], capture_output=True, text=True).stdout
    vs = []
    for line in out.splitlines():
        m = re.match(r"^(.+?)\s{2,}([a-z]{2}[_-][A-Z]{2})\s", line)
        if m: vs.append((m.group(1).strip(), m.group(2)))
    return vs


def piper_dir():
    d = os.environ.get("PIPER_VOICES") or os.path.join(os.path.expanduser("~"), ".cache", "director", "piper")
    os.makedirs(d, exist_ok=True); return d


def available():
    """provider -> {ok, why, voices}"""
    out = {}
    out["human"] = {"ok": True, "why": "Record or upload one clip per line", "voices": []}
    sv = say_voices()
    en = [n for n, l in sv if l.startswith("en")]
    pref = [p for p in SAY_PREFS if p in en]
    out["say"] = {"ok": bool(sv), "why": "macOS only" if not sv else "%d English voices" % len(en), "voices": pref + [n for n in en if n not in pref]}
    out["edge"] = {"ok": _mod("edge_tts"), "why": "pip install edge-tts (needs internet)" if not _mod("edge_tts") else "Neural voices, free, online", "voices": CATALOG["edge"]}
    out["openai"] = {"ok": bool(os.environ.get("OPENAI_API_KEY")), "why": "Set OPENAI_API_KEY" if not os.environ.get("OPENAI_API_KEY") else "gpt-4o-mini-tts", "voices": CATALOG["openai"]}
    out["elevenlabs"] = {"ok": bool(os.environ.get("ELEVENLABS_API_KEY")), "why": "Set ELEVENLABS_API_KEY" if not os.environ.get("ELEVENLABS_API_KEY") else "eleven_multilingual_v2", "voices": CATALOG["elevenlabs"]}
    out["piper"] = {"ok": _mod("piper"), "why": "pip install piper-tts (voices download on first use)" if not _mod("piper") else "Offline neural", "voices": CATALOG["piper"]}
    pd = pico_dir()
    out["pico"] = {"ok": _mod("ttspico") and bool(pd), "why": "pip install ttspico (+ PICO_LANG_DIR)" if not (_mod("ttspico") and pd) else "Offline, clear but synthetic", "voices": CATALOG["pico"]}
    out["espeak"] = {"ok": bool(espeak_bin()), "why": "apt install espeak-ng" if not espeak_bin() else "Offline, robotic", "voices": CATALOG["espeak"]}
    return out


def choose(kind, human_complete=False, av=None):
    av = av or available()
    if kind and kind != "auto":
        if kind == "human" or av.get(kind, {}).get("ok"): return kind
        raise DirectorError("Voice '%s' is not available: %s" % (kind, av.get(kind, {}).get("why", "unknown provider")))
    if human_complete: return "human"
    for k in ("say", "edge", "piper", "pico", "espeak"):
        if av[k]["ok"]: return k
    raise DirectorError("No voice available. Record your own lines, or install one: pip install edge-tts (online) / piper-tts / ttspico, or espeak-ng.")


# ------------------------------------------------------------------ providers -> (mono float, sr)
def _decode(path): return FF.decode_audio(path, SR, 1), SR


def tts_say(text, voice, rate):
    v = voice or next(iter(available()["say"]["voices"]), None) or "Samantha"
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "vo.aiff")
        subprocess.run(["say", "-v", v, "-r", str(int(178 * rate)), "-o", p, text], check=True)
        return _decode(p)


def tts_edge(text, voice, rate):
    import asyncio, edge_tts
    v = voice or "en-US-AvaNeural"
    pct = int(round((rate - 1) * 100))
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "vo.mp3")
        async def go():
            await edge_tts.Communicate(text, v, rate=("%+d%%" % pct)).save(p)
        asyncio.run(go())
        return _decode(p)


def _post(url, headers, body, timeout=120):
    req = urllib.request.Request(url, data=json.dumps(body).encode(), headers=dict(headers, **{"Content-Type": "application/json"}))
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r: return r.read()
    except urllib.error.HTTPError as e:
        raise DirectorError("%s answered %s: %s" % (url.split("/")[2], e.code, e.read().decode(errors="replace")[:300]))


def tts_openai(text, voice, rate, tone=""):
    key = os.environ.get("OPENAI_API_KEY")
    if not key: raise DirectorError("OPENAI_API_KEY is not set")
    base = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")
    body = {"model": os.environ.get("DIRECTOR_OPENAI_TTS_MODEL", "gpt-4o-mini-tts"), "input": text, "voice": voice or "coral",
            "response_format": "wav", "speed": max(0.25, min(4.0, rate))}
    if tone: body["instructions"] = tone
    raw = _post(base + "/audio/speech", {"Authorization": "Bearer " + key}, body)
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "vo.wav"); open(p, "wb").write(raw); return _decode(p)


def tts_elevenlabs(text, voice, rate):
    key = os.environ.get("ELEVENLABS_API_KEY")
    if not key: raise DirectorError("ELEVENLABS_API_KEY is not set")
    vid = (voice or CATALOG["elevenlabs"][0]).split(":")[-1]
    body = {"text": text, "model_id": os.environ.get("DIRECTOR_ELEVEN_MODEL", "eleven_multilingual_v2"),
            "voice_settings": {"stability": 0.45, "similarity_boost": 0.8, "style": 0.15, "speed": max(0.7, min(1.2, rate))}}
    raw = _post("https://api.elevenlabs.io/v1/text-to-speech/%s?output_format=mp3_44100_128" % vid, {"xi-api-key": key, "Accept": "audio/mpeg"}, body)
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "vo.mp3"); open(p, "wb").write(raw); return _decode(p)


def piper_model(name):
    d = piper_dir(); onnx = os.path.join(d, name + ".onnx")
    if os.path.exists(onnx) and os.path.exists(onnx + ".json"): return onnx
    m = re.match(r"^([a-z]{2})_([A-Z]{2})-(.+)-(x_low|low|medium|high)$", name)
    if not m: raise DirectorError("piper voice name should look like en_US-lessac-medium")
    lang, reg, spk, q = m.groups()
    base = "https://huggingface.co/rhasspy/piper-voices/resolve/main/%s/%s_%s/%s/%s/%s" % (lang, lang, reg, spk, q, name)
    for ext in (".onnx", ".onnx.json"):
        with urllib.request.urlopen(base + ext + "?download=true", timeout=300) as r, open(onnx.replace(".onnx", "") + ext + ".part", "wb") as f:
            shutil.copyfileobj(r, f)
        os.replace(onnx.replace(".onnx", "") + ext + ".part", onnx.replace(".onnx", "") + ext)
    return onnx


_PIPER = {}


def tts_piper(text, voice, rate):
    import wave
    from piper import PiperVoice
    name = voice or "en_US-lessac-medium"
    if name not in _PIPER: _PIPER[name] = PiperVoice.load(piper_model(name))
    pv = _PIPER[name]
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "vo.wav")
        with wave.open(p, "wb") as wf:
            try:
                from piper import SynthesisConfig
                pv.synthesize_wav(text, wf, syn_config=SynthesisConfig(length_scale=1.0 / max(0.5, rate)))
            except ImportError:
                pv.synthesize(text, wf, length_scale=1.0 / max(0.5, rate))
        return _decode(p)


def tts_pico(text, voice, rate):
    import ttspico
    e = ttspico.TtsEngine(voice or "en-US", lang_dir=pico_dir())
    e.rate = int(100 * rate); e.pitch = 100
    buf = bytearray()
    e.speak(text, lambda fmt, audio, fin: buf.extend(audio))
    return np.frombuffer(bytes(buf), np.int16).astype(np.float64) / 32768.0, 16000


def tts_espeak(text, voice, rate):
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "vo.wav")
        subprocess.run([espeak_bin(), "-v", voice or "en-us", "-s", str(int(160 * rate)), "-w", p, text], check=True, capture_output=True)
        return _decode(p)


PROVIDERS = {"say": tts_say, "edge": tts_edge, "openai": tts_openai, "elevenlabs": tts_elevenlabs, "piper": tts_piper, "pico": tts_pico, "espeak": tts_espeak}
SYNTHETIC = {"pico", "espeak"}          # get the "studio" EQ / exciter / room treatment


# ------------------------------------------------------------------ polish (from QuantSkill's vo.py)
def trim(a, sr, thr=0.012, pad=0.04):
    idx = np.where(np.abs(a) > thr)[0]
    if not len(idx): return a
    return a[max(0, idx[0] - int(pad * sr)): min(len(a), idx[-1] + int(pad * 2 * sr))]


def peaking(f0, gain_db, q, sr):
    A = 10 ** (gain_db / 40); w = 2 * np.pi * f0 / sr; al = np.sin(w) / (2 * q)
    b = [1 + al * A, -2 * np.cos(w), 1 - al * A]; a = [1 + al / A, -2 * np.cos(w), 1 - al / A]
    return np.array(b) / a[0], np.array(a) / a[0]


def compress(x, sr, thr_db=-20, ratio=2.6, att=0.004, rel=0.08):
    env = np.abs(x)
    # envelope follower: attack/release one-pole, done in blocks of 32 samples for speed
    blk = 32; nb = len(x) // blk + 1
    pk = np.array([env[i * blk:(i + 1) * blk].max(initial=0) for i in range(nb)])
    a_att = np.exp(-blk / (att * sr)); a_rel = np.exp(-blk / (rel * sr))
    lvl = np.empty(nb); l = 0.0
    for i, e in enumerate(pk):
        l = a_att * l + (1 - a_att) * e if e > l else a_rel * l + (1 - a_rel) * e
        lvl[i] = l
    db = 20 * np.log10(lvl + 1e-9)
    gr = np.where(db < thr_db, 0, (db - thr_db) * (1 - 1 / ratio))
    g = np.repeat(10 ** (-gr / 20), blk)[: len(x)]
    g = signal.lfilter([0.05], [1, -0.95], g) / 1.0
    return x * np.clip(g, 0, 1)


def room(x, sr, seed=7, t60=0.35, wet=0.07):
    rng = np.random.default_rng(seed); n = int(t60 * sr)
    ir = rng.standard_normal(n) * np.exp(-6.9 * np.arange(n) / n)
    ir = signal.lfilter(*signal.butter(2, 5000 / (sr / 2)), ir)
    ir[: int(0.012 * sr)] = 0; ir /= np.sqrt((ir ** 2).sum())
    return x + wet * signal.fftconvolve(x, ir)[: len(x)]


def polish(a, sr, synthetic=True):
    if sr != SR: a = signal.resample_poly(a, SR, sr)
    a = signal.sosfilt(signal.butter(2, 85, "hp", fs=SR, output="sos"), a)
    if synthetic:
        a = signal.lfilter(*peaking(250, -2.0, 1.0, SR), a)
        a = signal.lfilter(*peaking(3200, 3.0, 1.1, SR), a)
        band = signal.sosfilt(signal.butter(4, [3000, 7500], "bp", fs=SR, output="sos"), a)
        air = signal.sosfilt(signal.butter(4, 8000, "hp", fs=SR, output="sos"), np.tanh(band * 6) / 6)
        a = a + 0.35 * air
    a = a / (np.max(np.abs(a)) + 1e-9) * 0.7
    a = compress(a, SR)
    if synthetic: a = room(a, SR)
    return a


def rms_db(a):
    loud = a[np.abs(a) > 0.02]
    return 20 * np.log10(np.sqrt(np.mean(loud ** 2)) + 1e-9) if len(loud) else -60


# ------------------------------------------------------------------ speech text
def camel_split(w):
    return re.sub(r"(?<=[a-z])(?=[A-Z])", " ", w)


def speech_text(text, lexicon, brand_name="", spell=False):
    t = text or ""
    t = re.sub(r"[*_~|]", " ", t)                                        # markup
    t = t.replace("—", ", ").replace("–", ", ").replace("…", "...").replace("&", " and ")
    for k, v in sorted((lexicon or {}).items(), key=lambda kv: -len(kv[0])):
        if k: t = re.sub(r"(?<!\w)%s(?!\w)" % re.escape(k), v, t)
    if brand_name and brand_name not in (lexicon or {}) and re.search(r"[a-z][A-Z]", brand_name):
        t = re.sub(r"(?<!\w)%s(?!\w)" % re.escape(brand_name), camel_split(brand_name), t)
    if spell:   # robotic engines read "PDF" as a word; spell short acronyms out
        t = re.sub(r"\b([A-Z]{2,4})s?\b", lambda m: " ".join(m.group(1)) if m.group(1) not in ("OK", "NASA", "GIF", "JSON", "SaaS") else m.group(1), t)
    return re.sub(r"\s+", " ", t).strip()


def parse_lexicon(s):
    out = {}
    for line in (s or "").splitlines():
        if "=" in line:
            k, v = line.split("=", 1)
            if k.strip(): out[k.strip()] = v.strip()
    return out


def human_file(P, sid):
    for ext in HUMAN_EXT:
        p = P.p("vo", "human", sid + ext)
        if os.path.exists(p): return p
    return None


# ------------------------------------------------------------------ synthesis with cache
def synth_line(P, provider, voice, rate, text, sid, tone="", job=None):
    if provider == "human":
        f = human_file(P, sid)
        if not f: raise DirectorError("No recording for scene %s" % sid)
        a, sr = _decode(f)
        return polish(trim(a, sr), sr, synthetic=False)
    key = hashlib.sha1(json.dumps([provider, voice, round(rate, 3), text, tone]).encode()).hexdigest()[:16]
    cache = P.p("vo", "cache", key + ".wav")
    if os.path.exists(cache):
        x, _ = FF.read_wav(cache); return x[0]
    fn = PROVIDERS[provider]
    a, sr = fn(text, voice, rate, tone) if provider == "openai" else fn(text, voice, rate)
    a = polish(trim(a, sr), sr, synthetic=provider in SYNTHETIC)
    a *= 10 ** ((-19 - rms_db(a)) / 20)
    a = np.clip(a, -0.98, 0.98)
    FF.write_wav(cache, a)
    return a


def first_working(P, provider, scenes, v, lex, name, job):
    """auto mode: try the preferred voice on a short line; fall back to the next available one (e.g. no internet for Edge)"""
    av = available(); order = [k for k in ("say", "edge", "piper", "pico", "espeak") if av[k]["ok"]]
    order = order[order.index(provider):] if provider in order else order
    probe = speech_text(min((s["vo"] for s in scenes), key=len)[:80], lex, name)
    for k in order:
        try:
            synth_line(P, k, v.get("voice") if v.get("provider") == k else None, float(v.get("rate") or 1.0), probe, "probe")
            return k
        except Exception as e:  # noqa: BLE001
            job.warn("voice '%s' is not working here (%s); trying the next one" % (k, str(e).splitlines()[0][:120] if str(e) else e.__class__.__name__))
    raise DirectorError("No voice worked. Record your own lines, or check the engine (voices need internet or local models).")


def voice(P, job, line=None):
    """synthesize all lines (or one line for a preview)"""
    from .timeline import estimate
    cfg = P.cfg; v = cfg["voice"]; sb = P.get("storyboard")
    if not sb: raise DirectorError("Plan the film first.")
    scenes = [s for s in sb["scenes"] if s.get("enabled", True) and (s.get("vo") or "").strip()]
    os.makedirs(P.p("vo"), exist_ok=True)
    lex = parse_lexicon(v.get("lexicon", ""))
    name = (sb.get("brand") or {}).get("name", "")
    human_ok = bool(scenes) and all(human_file(P, s["id"]) for s in scenes)
    provider = choose(v.get("provider", "auto"), human_ok)
    if v.get("provider", "auto") == "auto":
        v = dict(v, voice="")                     # a voice name picked for another provider doesn't apply
        if provider != "human" and scenes: provider = first_working(P, provider, scenes, v, lex, name, job)
    tone = v.get("tone") or {"confident": "Warm, confident product-launch narrator. Clear, upbeat, not salesy.", "calm": "Calm, friendly, measured.",
                             "energetic": "Energetic and punchy, like a product teaser.", "playful": "Playful and bright."}.get(cfg["film"].get("tone", ""), "")
    rate = float(v.get("rate") or 1.0)
    if line:
        s = next((x for x in sb["scenes"] if x["id"] == line), None)
        if not s or not (s.get("vo") or "").strip(): raise DirectorError("Scene %s has no voice-over line." % line)
        job.msg("Synthesizing line %s with %s…" % (line, provider))
        a = synth_line(P, provider, v.get("voice"), rate, speech_text(s["vo"], lex, name, provider in SYNTHETIC), line, tone, job)
        FF.write_wav(P.p("vo", "preview_%s.wav" % line), a)
        return {"preview": "vo/preview_%s.wav" % line, "dur": round(len(a) / SR, 2), "provider": provider}
    if not v.get("enabled", True) or not sb.get("vo", True) or not scenes:
        write_json(P.p("vo", "clips.json"), {"voice": "none", "clips": {}})
        return {"voice": "none"}
    label = provider + (" · " + v["voice"] if v.get("voice") else "")
    for attempt in range(6):
        clips = {}
        for i, s in enumerate(scenes):
            job.progress(i / len(scenes), "Voice: line %d/%d (%s)…" % (i + 1, len(scenes), provider))
            try:
                a = synth_line(P, provider if provider != "human" or human_file(P, s["id"]) else "human", v.get("voice"), rate, speech_text(s["vo"], lex, name, provider in SYNTHETIC), s["id"], tone, job)
            except DirectorError: raise
            except Exception as e:  # noqa: BLE001
                raise DirectorError("Voice '%s' failed on line %s: %s" % (provider, s["id"], str(e).splitlines()[0][:200] if str(e) else e.__class__.__name__))
            FF.write_wav(P.p("vo", s["id"] + ".wav"), a)
            clips[s["id"]] = {"file": "vo/%s.wav" % s["id"], "dur": round(len(a) / SR, 3), "text": s["vo"]}
        total = estimate(P, sb, {k: c["dur"] for k, c in clips.items()})
        if total <= MAX_FILM or provider == "human" or rate >= 1.3: break
        rate = round(rate * 1.06 + 0.01, 3)
        job.msg("Film would run %.1fs; speeding the voice up to %.2fx…" % (total, rate))
    if total > MAX_FILM:
        job.warn("The film runs %.1fs with this script (limit %.0fs). Shorten some lines or remove a scene." % (total, MAX_FILM))
    write_json(P.p("vo", "clips.json"), {"voice": label, "provider": provider, "rate": rate, "clips": clips, "total": round(total, 2)})
    return {"voice": label, "total": round(total, 2), "rate": rate}
