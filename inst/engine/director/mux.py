"""Final deliverables: audio mux + loudness, captions (SRT + burned-in), poster, script.

out/<name>.mp4            the film (H.264 + AAC 48 kHz, +faststart)
out/<name>_captions.mp4   captions burned in (needs libass), when there is a voice-over
out/<name>.srt            captions sidecar
out/<name>_poster.jpg     poster frame (the end card)
out/<name>_script.txt     voice-over script with timings
Loudness: -14 LUFS without voice-over (social/streaming), -16 LUFS with speech; true peak -1 dBTP.
"""
import json, os, re, shutil

from . import ff as FF
from .fonts import inter_ttf
from .util import DirectorError, read_json, slugify, write_json, now_iso


def fmt_srt(t):
    h = int(t // 3600); m = int(t % 3600 // 60); s = t % 60
    return "%02d:%02d:%02d,%03d" % (h, m, int(s), min(999, round((s - int(s)) * 1000)))


def fmt_ass(t): return "%d:%02d:%05.2f" % (int(t // 3600), int(t % 3600 // 60), t % 60)


def split2(txt, limit):
    if len(txt) <= limit: return txt
    words = txt.split(); best = None
    for k in range(1, len(words)):
        l1, l2 = " ".join(words[:k]), " ".join(words[k:])
        d = abs(len(l1) - len(l2))
        if best is None or d < best[0]: best = (d, l1, l2)
    return best[1] + "\\N" + best[2]


def ass_color(hexc, alpha=0):
    h = hexc.lstrip("#")
    return "&H%02X%s%s%s" % (alpha, h[4:6], h[2:4], h[0:2])


def captions(tl):
    caps = tl.get("captions") or []
    W, H = tl["W"], tl["H"]; portrait = H > W
    style = tl.get("capstyle", "clean")
    srt = []
    for i, c in enumerate(caps, 1):
        srt.append("%d\n%s --> %s\n%s\n" % (i, fmt_srt(max(0, c["start"] - 0.05)), fmt_srt(c["end"] + 0.25), c["text"]))
    U = min(W, H) / 1080
    if style == "bold":
        fs = int((78 if portrait else 62) * U); mv = int(H * (0.075 if portrait else 0.1))
        hi = ass_color(tl["theme"]["c3"])
        head_style = "Style: Cap,Inter,%d,&H00FFFFFF,%s,&H00000000,&H64000000,-1,0,0,0,100,100,0,0,1,%d,2,2,80,80,%d,1" % (fs, hi, max(3, int(6 * U)), mv)
    else:
        fs = int((50 if portrait else 40) * U); mv = int(H * (0.08 if portrait else 0.043))
        head_style = "Style: Cap,Inter,%d,&H00FFFFFF,&H00FFFFFF,&H64141414,&H64141414,0,0,0,0,100,100,0,0,3,%d,0,2,%d,%d,%d,1" % (fs, int(14 * U), int(W * .1), int(W * .1), mv)
    ev = []
    for c in caps:
        a, b = max(0, c["start"] - 0.05), c["end"] + 0.25
        if style == "bold":
            ws, wt = c["words"], c["wt"]
            for k in range(0, len(ws), 3):
                chunk = ws[k:k + 3]; t0 = wt[k]; t1 = wt[k + 3] if k + 3 < len(wt) else c["end"] + 0.2
                parts = []
                for j, w in enumerate(chunk):
                    ta = wt[k + j]; tb = wt[k + j + 1] if k + j + 1 < len(wt) else c["end"]
                    parts.append("{\\k%d}%s" % (max(1, int(round((tb - ta) * 100))), w.upper()))
                ev.append("Dialogue: 0,%s,%s,Cap,,0,0,0,,%s" % (fmt_ass(t0), fmt_ass(t1), " ".join(parts)))
        else:
            ev.append("Dialogue: 0,%s,%s,Cap,,0,0,0,,%s" % (fmt_ass(a), fmt_ass(b), split2(c["text"], 34 if portrait else 62)))
    head = """[Script Info]
ScriptType: v4.00+
PlayResX: %d
PlayResY: %d
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
%s

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
""" % (W, H, head_style)
    return "\n".join(srt), head + "\n".join(ev) + "\n"


def out_name(P, tl):
    b = (tl.get("brand") or {}).get("name") or P.cfg.get("name") or "film"
    return "%s_%s_%ds%s" % (slugify(b).replace("-", ""), tl.get("template", "film"), int(round(tl["duration"])),
                            "" if tl["W"] > tl["H"] else ("_vertical" if tl["H"] > tl["W"] * 1.1 else "_square"))


def mux(P, job, video, quality="final"):
    tl = P.get("timeline")
    od = P.d("out")
    name = out_name(P, tl) + ("_draft" if quality == "draft" else "")
    mixp = P.p("audio", "mix.wav")
    if not os.path.exists(mixp):
        from .music import mix
        mix(P, job)
    has_vo = bool(tl.get("vo"))
    lufs = -16 if has_vo else -14
    out = os.path.join(od, name + ".mp4")
    job.progress(0.1, "Mixing and normalising the audio (%d LUFS)…" % lufs)
    FF.run("-i", video, "-i", mixp, "-filter_complex", "[1:a]loudnorm=I=%d:TP=-1.0:LRA=11[a]" % lufs, "-map", "0:v", "-map", "[a]",
           "-c:v", "copy", "-c:a", "aac", "-b:a", "256k" if quality == "final" else "160k", "-ar", "48000", "-t", "%.3f" % tl["duration"], "-movflags", "+faststart", out)
    files = {"video": "out/" + name + ".mp4"}
    # poster: middle of the end card (or 40% in)
    end = next((s for s in tl["scenes"] if s["type"] == "end"), None)
    tp = (end["t0"] + min(2.2, end["dur"] * 0.7)) if end else tl["duration"] * 0.4
    poster = os.path.join(od, name + "_poster.jpg")
    try:
        FF.run("-ss", "%.3f" % tp, "-i", out, "-frames:v", "1", "-q:v", "2", poster)
        files["poster"] = "out/" + name + "_poster.jpg"
        # a mid-film thumbnail for the library
        thumb = os.path.join(od, name + "_thumb.jpg")
        first_shot = next((s for s in tl["scenes"] if s["type"] == "shot"), None)
        tt = (first_shot["t0"] + first_shot["dur"] * 0.6) if first_shot else tl["duration"] * 0.3
        FF.run("-ss", "%.3f" % tt, "-i", out, "-frames:v", "1", "-vf", "scale=640:-2", "-q:v", "3", thumb)
        files["thumb"] = "out/" + name + "_thumb.jpg"
    except Exception as e:  # noqa: BLE001
        job.warn("poster not made: %s" % str(e).splitlines()[0][:120])
    if has_vo and tl.get("captions"):
        srt, ass = captions(tl)
        open(os.path.join(od, name + ".srt"), "w", encoding="utf-8").write(srt)
        files["srt"] = "out/" + name + ".srt"
        with open(os.path.join(od, name + "_script.txt"), "w", encoding="utf-8") as f:
            f.write("%s: voice-over script (%s)\n\n" % ((tl.get("brand") or {}).get("name", ""), (read_json(P.p("vo", "clips.json"), {}) or {}).get("voice", "")))
            for c in tl["captions"]: f.write("[%05.2f-%05.2f]  %s\n" % (c["start"], c["end"], c["text"]))
        files["script"] = "out/" + name + "_script.txt"
        if quality == "final" or tl.get("capstyle") == "bold":
            if FF.has_filter("ass"):
                job.progress(0.5, "Burning in captions…")
                ass_p = P.p("render", "captions.ass"); open(ass_p, "w", encoding="utf-8").write(ass)
                fonts = inter_ttf(P.p("render", "fonts"))
                esc = lambda p: "'" + p.replace("'", "\\'") + "'"
                vf = "ass=filename=%s" % esc(ass_p) + (":fontsdir=%s" % esc(fonts) if fonts else "")
                cap = os.path.join(od, name + "_captions.mp4")
                try:
                    FF.run(*(["-i", out, "-vf", vf] + FF.h264(18 if quality == "final" else 24, "medium" if quality == "final" else "veryfast") + ["-c:a", "copy", "-movflags", "+faststart", cap]))
                    files["captions"] = "out/" + name + "_captions.mp4"
                except Exception as e:  # noqa: BLE001
                    job.warn("the captioned version could not be made (%s); the film and the .srt are fine" % str(e).splitlines()[0][:120])
            else:
                job.warn("this ffmpeg has no libass: the captioned version was skipped (the .srt is written)")
    man = read_json(os.path.join(od, "manifest.json"), {"renders": []}) or {"renders": []}
    size = [tl["W"], tl["H"]]
    try:
        import subprocess
        r = subprocess.run([FF.ffprobe(), "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height", "-of", "csv=p=0", out], capture_output=True, text=True)
        size = [int(x) for x in r.stdout.strip().split(",")[:2]]
    except Exception: pass  # noqa: BLE001
    entry = {"name": name, "quality": quality, "created": now_iso(), "duration": tl["duration"], "template": tl.get("template"),
             "size": size, "files": files, "bytes": os.path.getsize(out)}
    man["renders"] = [r for r in man["renders"] if r.get("name") != name] + [entry]
    write_json(os.path.join(od, "manifest.json"), man)
    return entry
