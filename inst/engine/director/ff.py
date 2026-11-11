"""ffmpeg helpers: locate ffmpeg, pick an H.264 encoder, detect filters, decode audio."""
import functools, os, shutil, subprocess
import numpy as np

SR = 48000


def ffmpeg():
    exe = os.environ.get("FFMPEG") or shutil.which("ffmpeg")
    if not exe:
        for p in ("/opt/homebrew/bin/ffmpeg", "/usr/local/bin/ffmpeg"):
            if os.path.exists(p): return p
        raise RuntimeError("ffmpeg not found. Install it (macOS: brew install ffmpeg, Ubuntu: apt install ffmpeg) or set FFMPEG=/path/to/ffmpeg")
    return exe


def ffprobe():
    f = ffmpeg(); d = os.path.dirname(f)
    p = os.path.join(d, "ffprobe")
    return p if os.path.exists(p) else (shutil.which("ffprobe") or "ffprobe")


@functools.lru_cache(None)
def _list(kind):
    try:
        return subprocess.run([ffmpeg(), "-hide_banner", "-" + kind], capture_output=True, text=True).stdout
    except Exception:  # noqa: BLE001
        return ""


def has_encoder(name): return (" " + name + " ") in _list("encoders")


def has_filter(name): return (" " + name + " ") in _list("filters")


def h264(crf=16, preset="medium"):
    """encoder arguments: libx264 if available, else Apple VideoToolbox, else OpenH264"""
    if has_encoder("libx264"):
        return ["-c:v", "libx264", "-preset", preset, "-crf", str(crf), "-pix_fmt", "yuv420p"]
    if has_encoder("h264_videotoolbox"):
        return ["-c:v", "h264_videotoolbox", "-b:v", "14M", "-maxrate", "20M", "-profile:v", "high", "-pix_fmt", "yuv420p"]
    if has_encoder("libopenh264"):
        return ["-c:v", "libopenh264", "-b:v", "14M", "-pix_fmt", "yuv420p"]
    raise RuntimeError("This ffmpeg has no H.264 encoder (libx264 / h264_videotoolbox). Install a full build (brew install ffmpeg).")


def run(*args, quiet=True):
    cmd = [ffmpeg(), "-y"] + (["-loglevel", "error"] if quiet else []) + [str(a) for a in args]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError("ffmpeg failed: %s\n%s" % (" ".join(cmd[:12]) + " …", (r.stderr or "")[-1500:]))
    return r


def decode_audio(path, sr=SR, channels=1):
    """any audio/video file -> float64 array (channels x n) or (n,) for mono"""
    r = subprocess.run([ffmpeg(), "-v", "error", "-i", path, "-vn", "-ac", str(channels), "-ar", str(sr), "-f", "s16le", "-"],
                       capture_output=True)
    if r.returncode != 0:
        raise RuntimeError("could not decode %s: %s" % (os.path.basename(path), r.stderr.decode(errors="replace")[-400:]))
    a = np.frombuffer(r.stdout, np.int16).astype(np.float64) / 32768.0
    return a if channels == 1 else a.reshape(-1, channels).T


def duration(path):
    r = subprocess.run([ffprobe(), "-v", "error", "-show_entries", "format=duration", "-of", "default=nw=1:nk=1", path],
                       capture_output=True, text=True)
    try: return float(r.stdout.strip())
    except ValueError: return 0.0


def write_wav(path, x, sr=SR):
    """x: (n,) mono or (2, n) stereo float in -1..1"""
    import wave
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    x = np.asarray(x)
    ch = 1 if x.ndim == 1 else x.shape[0]
    data = np.clip(x if ch == 1 else x.T, -1, 1)
    w = wave.open(path, "wb"); w.setnchannels(ch); w.setsampwidth(2); w.setframerate(sr)
    w.writeframes((data * 32767).astype(np.int16).tobytes()); w.close()


def read_wav(path):
    """-> (channels x n float, sr); always 2-D"""
    import wave
    w = wave.open(path); ch = w.getnchannels(); sr = w.getframerate(); sw = w.getsampwidth()
    a = np.frombuffer(w.readframes(w.getnframes()), {2: np.int16, 4: np.int32}[sw]).astype(np.float64)
    a /= {2: 32768.0, 4: 2147483648.0}[sw]
    return a.reshape(-1, ch).T, sr
