"""Original music + sound design, synthesised with numpy (no samples, nothing to license).

Instruments come from QuantSkill's dev/video/music.py; the composer is new: it reads the
resolved timeline (scene cuts, hits, transitions, clicks, voice-over) and writes a score
that fits the film. Moods: pulse, keys, ambient, drive, lofi, cinematic, bright.
A custom track (music.file) can replace the score; sound design is kept on top.

Writes audio/music.wav (the bed), audio/sfx.wav (clicks, whooshes, hits) and, via mix(),
audio/mix.wav (ducked bed + voice-over + sfx) used by the live preview and the final film.
"""
import json, os, re

import numpy as np
from scipy import signal

from . import ff as FF
from .util import DirectorError, read_json

SR = 48000
RNG = np.random.default_rng(2026)


def n2f(n):  # midi -> Hz
    return 440.0 * 2 ** ((n - 69) / 12)


def env_adsr(n, a, d, s, r, sr=SR, hold=None):
    a, d, r = int(a * sr), int(d * sr), int(r * sr)
    hold = n - a - d - r if hold is None else int(hold * sr)
    hold = max(0, hold)
    e = np.concatenate([np.linspace(0, 1, max(1, a), endpoint=False), np.linspace(1, s, max(1, d), endpoint=False), np.full(hold, s), np.linspace(s, 0, max(1, r))])
    return np.pad(e, (0, max(0, n - len(e))))[:n]


_SAW_TABLES = {}


def _saw_table(k, size=4096):
    """one cycle of a band-limited sawtooth with k harmonics (cached)"""
    if k not in _SAW_TABLES:
        x = np.arange(size) / size
        tab = np.zeros(size)
        for h in range(1, k + 1): tab += np.sin(2 * np.pi * h * x) / h
        _SAW_TABLES[k] = np.append(tab, tab[0]) * (2 / np.pi)      # guard sample for interpolation
    return _SAW_TABLES[k]


def saw(f, n, phase=0.0, sr=SR):
    """band-limited sawtooth (wavetable; same waveform as summing the harmonics, much faster).
    A phase offset of the harmonic series is a time shift: sin(2*pi*h*f*t + h*phase) = sin(2*pi*h*f*(t + phase/(2*pi*f)))."""
    k = int(min(60, (sr / 2 - 200) / max(f, 1)))
    if k < 1: return np.zeros(n)
    tab = _saw_table(k); size = len(tab) - 1
    pos = (f * np.arange(n) / sr + phase / (2 * np.pi)) % 1.0 * size
    i = pos.astype(np.int64); frac = pos - i
    return tab[i] * (1 - frac) + tab[i + 1] * frac


def lp(x, fc, order=2):
    return signal.sosfilt(signal.butter(order, min(fc, SR / 2 - 100), "lp", fs=SR, output="sos"), x)


def hp(x, fc, order=2):
    return signal.sosfilt(signal.butter(order, fc, "hp", fs=SR, output="sos"), x)


def bp(x, lo, hi, order=2):
    return signal.sosfilt(signal.butter(order, [lo, min(hi, SR / 2 - 100)], "bp", fs=SR, output="sos"), x)


def sweep_lp(x, f0, f1, curve=2.0, blocks=64):
    """time-varying low-pass (block-wise, crossfaded)"""
    n = len(x); out = np.zeros(n); B = n // blocks + 1
    zi = None; sos_prev = None
    for i in range(blocks):
        a, b = i * B, min(n, (i + 1) * B)
        if a >= n: break
        p = (i / max(1, blocks - 1)) ** curve
        fc = f0 * (f1 / f0) ** p
        sos = signal.butter(2, min(fc, SR / 2 - 200), "lp", fs=SR, output="sos")
        if zi is None: zi = signal.sosfilt_zi(sos) * x[a]
        out[a:b], zi = signal.sosfilt(sos, x[a:b], zi=zi)
    return out


class Track:
    def __init__(self, dur):
        self.n = int(dur * SR) + SR * 3
        self.bus = {k: np.zeros((2, self.n)) for k in ("drums", "bass", "music", "fx", "verb")}

    def put(self, bus, x, t, pan=0.0, gain=1.0, send=0.0):
        i = int(round(t * SR))
        if i >= self.n: return
        x = x[: self.n - i]
        l, r = np.cos((pan + 1) * np.pi / 4), np.sin((pan + 1) * np.pi / 4)
        self.bus[bus][0, i:i + len(x)] += x * gain * l * 1.414
        self.bus[bus][1, i:i + len(x)] += x * gain * r * 1.414
        if send:
            self.bus["verb"][0, i:i + len(x)] += x * gain * send * l
            self.bus["verb"][1, i:i + len(x)] += x * gain * send * r


# ------------------------------------------------------------------ instruments
def kick(punch=1.0):
    n = int(0.55 * SR); t = np.arange(n) / SR
    f = 46 + 120 * np.exp(-t * 38) + 30 * np.exp(-t * 200)
    ph = 2 * np.pi * np.cumsum(f) / SR
    body = np.sin(ph) * np.exp(-t * 6.5)
    click = hp(RNG.standard_normal(n), 2500) * np.exp(-t * 300) * 0.25
    return np.tanh((body + click * punch) * 1.6) * 0.9


def clap():
    n = int(0.45 * SR); t = np.arange(n) / SR
    nz = RNG.standard_normal(n)
    e = np.zeros(n)
    for k, d in enumerate([0, 0.011, 0.022]):
        i = int(d * SR); e[i:] += np.exp(-(t[: n - i]) * 95) * (0.8 if k < 2 else 1.0)
    e += np.exp(-t * 16) * 0.35
    return bp(nz * e, 900, 4200) * 1.4


def hat(open_=False):
    n = int((0.28 if open_ else 0.06) * SR); t = np.arange(n) / SR
    x = hp(RNG.standard_normal(n), 7500, 4) * np.exp(-t * (14 if open_ else 80))
    return x * 0.6


def snare():
    n = int(0.3 * SR); t = np.arange(n) / SR
    body = np.sin(2 * np.pi * 190 * t) * np.exp(-t * 30) * 0.6
    nz = bp(RNG.standard_normal(n), 1500, 9000) * np.exp(-t * 22)
    return (body + nz) * 0.8


def sub(note, dur, glide_from=None):
    n = int(dur * SR); t = np.arange(n) / SR
    f = np.full(n, n2f(note))
    if glide_from is not None: f = n2f(note) + (n2f(glide_from) - n2f(note)) * np.exp(-t * 30)
    ph = 2 * np.pi * np.cumsum(f) / SR
    x = np.sin(ph) + 0.18 * np.sin(2 * ph)
    return np.tanh(1.4 * x) * env_adsr(n, 0.004, 0.08, 0.85, 0.05)


def pluck(note, dur=0.35, bright=5000, detune=0.08):
    n = int(dur * SR); t = np.arange(n) / SR
    f = n2f(note)
    x = saw(f * (1 + detune / 100), n) + saw(f * (1 - detune / 100), n, 1.3) * 0.8 + np.sin(2 * np.pi * f * t) * 0.4
    cut = 400 + bright * np.exp(-t * 14)
    # approximate time-varying filter: mix of bright and dark versions
    w = np.exp(-t * 14)
    x = lp(x, bright) * w + lp(x, 700) * (1 - w)
    return x * env_adsr(n, 0.002, 0.18, 0.25, 0.12) * 0.35


def pad_chord(notes, dur, cutoff=2200, attack=0.6, release=0.9, voices=3):
    n = int(dur * SR); out = np.zeros(n)
    for k, m in enumerate(notes):
        f = n2f(m)
        for v in range(voices):
            d = (v - (voices - 1) / 2) * 0.11
            out += saw(f * 2 ** (d / 12), n, phase=RNG.uniform(0, 6.28))
    out = lp(out / (len(notes) * voices), cutoff, 2)
    return out * env_adsr(n, attack, 0.4, 0.85, release)


def felt_piano(note, dur=2.5, vel=0.8):
    n = int(dur * SR); t = np.arange(n) / SR; f = n2f(note)
    x = np.zeros(n)
    for h, (amp, dec) in enumerate([(1, 2.2), (0.45, 3.2), (0.22, 4.5), (0.12, 6), (0.07, 8), (0.04, 10)], start=1):
        inh = h * (1 + 0.0004 * h * h)
        x += amp * np.sin(2 * np.pi * f * inh * t + RNG.uniform(0, 1)) * np.exp(-t * dec * (0.7 + 0.3 * vel))
    att = np.minimum(1, t / 0.006)
    hammer = lp(RNG.standard_normal(n), 2500) * np.exp(-t * 120) * 0.05
    return lp((x * att + hammer) * vel, 2800 + 1800 * vel) * 0.3


def riser(dur, f0=300, f1=9000):
    n = int(dur * SR); t = np.arange(n) / SR
    nz = RNG.standard_normal(n)
    x = sweep_lp(hp(nz, 200), f0, f1, curve=1.6) * (t / dur) ** 2.2
    tone_f = 220 * 2 ** (2.5 * (t / dur) ** 1.5)
    tone = np.sin(2 * np.pi * np.cumsum(tone_f) / SR) * (t / dur) ** 2.5 * 0.15
    return (x * 0.5 + tone)


def impact(size=1.0):
    n = int(2.6 * SR); t = np.arange(n) / SR
    boom = np.sin(2 * np.pi * np.cumsum(38 + 60 * np.exp(-t * 9)) / SR) * np.exp(-t * 2.2)
    nz = lp(RNG.standard_normal(n), 3000) * np.exp(-t * 7) * 0.5
    return np.tanh((boom + nz) * 1.5 * size) * 0.9


def whoosh(dur=0.5, up=True):
    n = int(dur * SR); t = np.arange(n) / SR
    nz = RNG.standard_normal(n)
    e = np.sin(np.pi * t / dur) ** 2
    f0, f1 = (500, 6000) if up else (6000, 500)
    x = sweep_lp(hp(nz, 300), f0, f1, curve=1.0, blocks=32)
    return x * e * 0.35


def tick():
    n = int(0.05 * SR); t = np.arange(n) / SR
    return np.sin(2 * np.pi * 2400 * t) * np.exp(-t * 120) * 0.3


def ui_click():
    n = int(0.04 * SR); t = np.arange(n) / SR
    blip = np.sin(2 * np.pi * 1750 * t) * np.exp(-t * 260)
    nz = bp(RNG.standard_normal(n), 2000, 7000) * np.exp(-t * 400) * 0.5
    return (blip + nz) * 0.5


def reverb_ir(t60=2.2, pre=0.02):
    n = int(t60 * SR); t = np.arange(n) / SR
    irs = []
    for ch in range(2):
        nz = RNG.standard_normal(n) * np.exp(-6.9 * t / t60)
        nz = lp(nz, 6000) ; nz[: int(pre * SR)] = 0
        irs.append(nz / np.sqrt((nz ** 2).sum()))
    return irs


def sidechain_env(n, kicks, depth=0.6, rel=0.22):
    g = np.ones(n)
    for k in kicks:
        i = int(k * SR); m = int(rel * SR)
        if i >= n: continue
        seg = 1 - depth * (1 - (np.arange(min(m, n - i)) / m)) ** 2
        g[i:i + len(seg)] = np.minimum(g[i:i + len(seg)], seg)
    return g


def mixdown(tr, kicks, duck=None, sc_depth=0.55, master=0.9):
    ir = reverb_ir()
    verb = np.stack([signal.fftconvolve(tr.bus["verb"][c], ir[c])[: tr.n] for c in range(2)])
    g = sidechain_env(tr.n, kicks, sc_depth)
    mix = tr.bus["drums"] + tr.bus["fx"] + (tr.bus["bass"] + tr.bus["music"] + verb * 0.5) * g
    if duck is not None: mix = mix * duck
    mix = hp(mix, 28)
    peak = np.max(np.abs(mix)) + 1e-9
    mix = np.tanh(mix / peak * 1.25) / np.tanh(1.25) * master
    return mix




# ------------------------------------------------------------------ extra instruments
def bell(note, dur=1.6, vel=0.8):
    n = int(dur * SR); t = np.arange(n) / SR; f = n2f(note)
    x = (np.sin(2 * np.pi * f * t) + 0.5 * np.sin(2 * np.pi * f * 2.76 * t) * np.exp(-t * 3) + 0.25 * np.sin(2 * np.pi * f * 5.4 * t) * np.exp(-t * 6))
    return x * np.exp(-t * 2.2) * np.minimum(1, t / 0.003) * vel * 0.22


def tom(note=45, dur=0.9, vel=1.0):
    n = int(dur * SR); t = np.arange(n) / SR
    f = n2f(note) * (1 + 0.6 * np.exp(-t * 25))
    body = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * 4.5)
    nz = lp(RNG.standard_normal(n), 1800) * np.exp(-t * 30) * 0.3
    return np.tanh((body + nz) * 1.4) * vel * 0.8


def saw_bass(note, dur, cutoff=900):
    n = int(dur * SR); f = n2f(note)
    x = saw(f, n) * 0.7 + saw(f * 1.005, n, 0.7) * 0.5 + np.sin(2 * np.pi * f * np.arange(n) / SR) * 0.6
    return lp(x, cutoff, 2) * env_adsr(n, 0.004, 0.12, 0.7, 0.05) * 0.45


def crackle(dur):
    n = int(dur * SR)
    x = np.zeros(n)
    k = RNG.random(n) < 0.0009
    x[k] = RNG.uniform(-1, 1, k.sum())
    x = bp(x, 1200, 9000) * 0.5 + lp(RNG.standard_normal(n), 400) * 0.015
    return x


def shaker():
    n = int(0.09 * SR); t = np.arange(n) / SR
    return bp(RNG.standard_normal(n), 5000, 14000) * np.sin(np.pi * t / 0.09) ** 2 * 0.35


# ------------------------------------------------------------------ harmony
PROGS = {
    "minor": [(47, [59, 62, 66, 69, 73]), (43, [59, 62, 66, 67, 71]), (38, [57, 62, 64, 66, 69]), (45, [57, 61, 64, 66, 69])],   # Bm9 Gmaj7 Dadd9 A6/9
    "major": [(36, [60, 64, 67, 71, 74]), (43, [59, 62, 67, 71, 74]), (45, [60, 64, 67, 69, 72]), (41, [60, 65, 69, 72, 76])],   # Cmaj9 G Am7 Fmaj7
    "dreamy": [(41, [57, 60, 64, 65, 69]), (40, [55, 59, 62, 64, 67]), (38, [57, 60, 62, 65, 69]), (36, [55, 59, 62, 64, 67])],  # Fmaj7 Em7 Dm7 Cmaj7
}
MOODS = {
    "pulse": {"bpm": 120, "harmony": "minor", "label": "Pulse", "blurb": "Punchy electronic, four-on-the-floor. Teasers."},
    "keys": {"bpm": 96, "harmony": "minor", "label": "Keys", "blurb": "Felt piano and a soft pulse. Under a voice-over."},
    "ambient": {"bpm": 80, "harmony": "dreamy", "label": "Ambient", "blurb": "Airy pads, no drums. Calm demos."},
    "drive": {"bpm": 128, "harmony": "minor", "label": "Drive", "blurb": "Synthwave energy: arps and saw bass."},
    "lofi": {"bpm": 84, "harmony": "dreamy", "label": "Lo-fi", "blurb": "Dusty chords, swing and vinyl crackle."},
    "cinematic": {"bpm": 90, "harmony": "minor", "label": "Cinematic", "blurb": "Drones, toms and big hits. Trailers."},
    "bright": {"bpm": 112, "harmony": "major", "label": "Bright", "blurb": "Upbeat pop: piano stabs, claps, bells."},
}
ARP = [0, 2, 4, 1, 3, 2, 4, 3]
TEMPLATE_MOOD = {"launch": "keys", "teaser": "pulse", "tour": "bright", "social": "drive", "demo": "ambient"}


def _memo(cache, fn, *args, **kw):
    k = (fn.__name__, args, tuple(sorted(kw.items())))
    if k not in cache: cache[k] = fn(*args, **kw)
    return cache[k]


def compose(tl, mood="keys", harmony=None, bpm=None, seed=7, transpose=0):
    """-> (stereo bed, kick times)"""
    global RNG
    RNG = np.random.default_rng(seed)
    M = MOODS.get(mood, MOODS["keys"])
    bpm = float(bpm or tl.get("bpm") or M["bpm"]); b = 60 / bpm; bar = 4 * b
    prog = [(r + transpose, [n + transpose for n in ns]) for r, ns in PROGS[harmony or M["harmony"]]]
    dur = float(tl["duration"]); tr = Track(dur); kicks = []; C = {}
    sc = tl["scenes"]
    body_types = ("shot", "montage", "features", "grid", "stat")
    t_drop = next((s["t0"] for s in sc if s["type"] in body_types), min(dur * 0.3, 2 * bar))
    t_end = next((s["t0"] for s in sc if s["type"] == "end"), max(t_drop + bar, dur - 3.5))
    # snap the drop to the beat grid (teasers are already on the grid)
    t_drop = round(t_drop / b) * b if abs(t_drop - round(t_drop / b) * b) < 0.08 else t_drop
    nb = int(dur / bar) + 2
    on = lambda t: t_drop - 0.02 <= t < t_end - 0.05
    pre_end = lambda t: t_end - 2 * b <= t < t_end
    # ---------------------------------------------------------------- per mood
    for k in range(nb):
        t0 = k * bar
        if t0 >= t_end - 0.05: break
        root, ch = prog[k % 4]
        body = t0 + bar > t_drop
        if mood == "pulse":
            cut = 900 if t0 + bar <= t_drop else 3200
            tr.put("music", _memo(C, pad_chord, tuple(ch[:4]), bar + 0.3, cutoff=cut, attack=0.25 if body else 1.0, release=0.4), t0, gain=0.22, send=0.35)
            for j in range(16):
                tt = t0 + j * b / 4
                if tt >= t_end - 0.05: break
                if tt < 2 * b and t_drop > 2 * b: continue
                m = ch[ARP[j % 8] % len(ch)] + (12 if j % 8 in (4, 5) else 0)
                tr.put("music", _memo(C, pluck, m, 0.3, bright=2500 if tt < t_drop else 6000), tt, gain=0.2 if tt < t_drop else 0.26, pan=(0.35 if j % 2 else -0.35), send=0.25)
            for j in range(4):
                tt = t0 + j * b
                if on(tt) and not pre_end(tt):
                    tr.put("drums", kick(), tt, gain=0.95); kicks.append(tt)
                    if j % 2 == 1: tr.put("drums", clap(), tt, gain=0.5, pan=0.05, send=0.25)
                    for q in range(4):
                        tr.put("drums", hat(open_=(q == 2)), tt + q * b / 4, gain=(0.22 if q == 2 else 0.16) * (1.15 if q % 2 else 0.9), pan=0.25 if q % 2 else -0.2)
                elif tt < t_drop and tt >= t_drop - 2 * bar:
                    tr.put("fx", tick(), tt, gain=0.18 + 0.3 * (1 - (t_drop - tt) / (2 * bar)), pan=-0.3 if j % 2 else 0.3)
            for j in range(8):
                tt = t0 + j * b / 2
                if on(tt) and not pre_end(tt):
                    tr.put("bass", sub(root - 12 + (12 if j in (3, 7) else 0), b / 2 * 0.9), tt, gain=0.42)
        elif mood in ("keys",):
            tr.put("music", _memo(C, pad_chord, tuple(ch[:4]), bar + 0.6, cutoff=1500 if t0 < t_drop else 2400, attack=0.9, release=1.0, voices=2), t0, gain=0.16, send=0.4)
            for j in range(8):
                tt = t0 + j * b / 2
                if tt >= t_end - 0.1: break
                m = ch[[0, 2, 4, 2, 1, 3, 4, 3][j] % len(ch)]
                tr.put("music", _memo(C, felt_piano, m, 1.8, 0.55 + 0.15 * (j % 4 == 0)), tt, gain=0.42, send=0.45, pan=(-0.25 if j % 2 else 0.25))
            for j in range(4):
                tt = t0 + j * b
                if not on(tt): continue
                tr.put("drums", kick(0.3), tt, gain=0.3); kicks.append(tt)
                for q in range(2): tr.put("drums", hat(), tt + q * b / 2 + b / 4, gain=0.07, pan=0.3)
                if j % 2 == 1: tr.put("drums", clap(), tt, gain=0.1, send=0.3)
                tr.put("bass", sub(root - 12, b * 0.9), tt, gain=0.2)
        elif mood == "ambient":
            tr.put("music", _memo(C, pad_chord, tuple(ch[:4]), bar + 1.5, cutoff=1300 if t0 < t_drop else 2000, attack=1.6, release=1.8, voices=3), t0, gain=0.2, send=0.6)
            rng = np.random.default_rng(seed * 100 + k)
            for j in rng.choice(8, 3 if body else 2, replace=False):
                tt = t0 + j * b / 2
                if tt >= t_end - 0.1: continue
                tr.put("music", _memo(C, felt_piano, ch[int(rng.integers(0, len(ch)))] + 12, 3.0, 0.5), tt, gain=0.36, send=0.7, pan=float(rng.uniform(-.4, .4)))
            if body and k % 2 == 0: tr.put("bass", sub(root - 12, bar * 2), t0, gain=0.16)
            if body:
                for j in range(0, 8, 2):
                    tt = t0 + j * b / 2
                    if tt < t_end - .1: tr.put("music", _memo(C, bell, ch[(j // 2) % len(ch)] + 24, 1.6, 0.5), tt, gain=0.14, send=0.8, pan=(-.5 if j % 4 else .5))
        elif mood == "drive":
            tr.put("music", _memo(C, pad_chord, tuple(ch[:4]), bar + 0.3, cutoff=1200 if t0 < t_drop else 2800, attack=0.3, release=0.5), t0, gain=0.18, send=0.3)
            for j in range(16):
                tt = t0 + j * b / 4
                if tt >= t_end - 0.05: break
                m = ch[[0, 1, 2, 4, 2, 1, 3, 2][j % 8] % len(ch)] + 12
                tr.put("music", _memo(C, pluck, m, 0.22, bright=1800 if tt < t_drop else 5200, detune=0.15), tt, gain=0.17, pan=(0.3 if j % 2 else -0.3), send=0.2)
            for j in range(8):
                tt = t0 + j * b / 2
                if t0 + bar > t_drop - bar and tt < t_end - 0.05 and not pre_end(tt):
                    tr.put("bass", _memo(C, saw_bass, root - 12 + (12 if j % 2 else 0), b / 2 * 0.85, 700 if tt < t_drop else 1100), tt, gain=0.5)
            for j in range(4):
                tt = t0 + j * b
                if on(tt) and not pre_end(tt):
                    tr.put("drums", kick(), tt, gain=0.9); kicks.append(tt)
                    if j % 2 == 1: tr.put("drums", snare(), tt, gain=0.4, send=0.3); tr.put("drums", clap(), tt, gain=0.3)
                    tr.put("drums", hat(open_=True), tt + b / 2, gain=0.14, pan=0.2)
        elif mood == "lofi":
            sw = 0.58
            tr.put("music", lp(_memo(C, pad_chord, tuple(ch[:4]), bar + 0.4, cutoff=1100, attack=0.4, release=0.8, voices=2), 1400), t0, gain=0.14, send=0.3)
            for j, (pos, vel) in enumerate(((0, .6), (1.5, .45), (2.5, .5))):
                tt = t0 + pos * b
                if tt >= t_end - .1: continue
                for nn in ch[:4]:
                    tr.put("music", lp(_memo(C, felt_piano, nn, 1.6, vel), 1800), tt + 0.012 * ch.index(nn), gain=0.3, send=0.3, pan=-0.1)
            if body:
                for j in range(8):
                    beat = j // 2; off = (j % 2) * sw
                    tt = t0 + (beat + off) * b
                    if tt < t_end - .05 and not pre_end(tt): tr.put("drums", hat(), tt, gain=0.09 if j % 2 else 0.12, pan=0.25)
                for pos in (0, 2.5):
                    tt = t0 + pos * b
                    if on(tt) and not pre_end(tt): tr.put("drums", kick(0.4), tt, gain=0.55); kicks.append(tt)
                for pos in (1, 3):
                    tt = t0 + pos * b
                    if on(tt) and not pre_end(tt): tr.put("drums", lp(snare(), 3500), tt, gain=0.32, send=0.2)
                tr.put("bass", sub(root - 12, bar * 0.95), t0, gain=0.26)
        elif mood == "cinematic":
            tr.put("music", _memo(C, pad_chord, tuple([root, root + 7, root + 12]), bar + 1.0, cutoff=700 if t0 < t_drop else 1500, attack=1.5, release=1.2, voices=3), t0, gain=0.26, send=0.5)
            tr.put("music", _memo(C, pad_chord, tuple(ch[1:4]), bar + 1.0, cutoff=2200, attack=1.8, release=1.5, voices=3), t0, gain=0.12 if body else 0.05, send=0.6)
            if body:
                for pos in (0, 2, 3.5):
                    tt = t0 + pos * b
                    if on(tt) and not pre_end(tt): tr.put("drums", tom(40 if pos == 0 else 43, 1.0, 0.9 if pos == 0 else 0.6), tt, gain=0.55, send=0.35); kicks.append(tt)
                tr.put("bass", sub(root - 12, bar), t0, gain=0.2)
        else:  # bright
            tr.put("music", _memo(C, pad_chord, tuple(ch[:4]), bar + 0.3, cutoff=2600, attack=0.4, release=0.5, voices=2), t0, gain=0.1, send=0.3)
            for j in range(8):
                tt = t0 + j * b / 2
                if tt >= t_end - .05: break
                if j % 2 == 1 and body:
                    for q, nn in enumerate(ch[1:4]): tr.put("music", _memo(C, felt_piano, nn, 0.5, 0.75), tt + q * 0.006, gain=0.3, pan=0.15, send=0.15)
                tr.put("music", _memo(C, bell, ch[[0, 2, 4, 3, 2, 4, 1, 3][j] % len(ch)] + 12, 1.2, 0.8), tt, gain=0.18 if body else 0.22, pan=(-0.35 if j % 2 else 0.35), send=0.4)
            for j in range(4):
                tt = t0 + j * b
                if on(tt) and not pre_end(tt):
                    if j in (0, 2): tr.put("drums", kick(0.8), tt, gain=0.7); kicks.append(tt)
                    else: tr.put("drums", clap(), tt, gain=0.42, send=0.2)
                    tr.put("drums", shaker(), tt + b / 2, gain=0.5, pan=0.3); tr.put("drums", shaker(), tt, gain=0.3, pan=-0.3)
                    tr.put("bass", sub(root - 12, b * 0.8), tt, gain=0.32)
    # ---------------------------------------------------------------- lifts, hits, ending
    if mood in ("pulse", "drive", "bright", "cinematic"):
        tr.put("fx", riser(min(3.5, max(1.0, t_drop - 0.3))), max(0.0, t_drop - min(3.5, max(1.0, t_drop - 0.3))), gain=0.28 if mood != "bright" else 0.14)
        tr.put("fx", impact(1.0 if mood != "bright" else 0.6), t_drop, gain=0.6, send=0.3)
    if mood in ("pulse", "drive"):
        for i in range(8):
            t = t_end - 2 * b + i * b / 4
            if t > 0: tr.put("drums", snare(), t, gain=0.08 + 0.26 * i / 8, pan=(i % 2 - .5) * .3)
    rdur = min(2.4, max(1.0, t_end - t_drop - 0.5))
    tr.put("fx", riser(rdur, 400, 7000 if mood != "ambient" else 4000), t_end - rdur, gain=0.24 if mood not in ("ambient", "lofi") else 0.12)
    tr.put("fx", impact(0.8 if mood not in ("ambient", "lofi") else 0.45), t_end, gain=0.55 if mood not in ("ambient", "lofi") else 0.3, send=0.5)
    root, ch = prog[2]
    tail = dur - t_end
    tr.put("music", pad_chord(ch + [ch[0] + 12], max(1.0, tail), cutoff=3500 if mood != "lofi" else 1600, attack=0.05, release=2.5), t_end, gain=0.32, send=0.6)
    tr.put("bass", sub(root - 12, min(2.5, max(0.5, tail))), t_end, gain=0.4)
    for j, m in enumerate([ch[0] + 12, ch[2] + 12, ch[4] + 12, ch[0] + 24]):
        tr.put("music", felt_piano(m, 4.0, 0.85), t_end + j * (b / 2 if mood in ("pulse", "drive") else 0.22), gain=0.6, send=0.55, pan=(j - 1.5) * 0.2)
    if mood == "lofi": tr.put("fx", crackle(dur), 0, gain=0.5)
    sc_depth = {"pulse": 0.55, "drive": 0.5, "keys": 0.3, "bright": 0.35, "lofi": 0.3, "cinematic": 0.25, "ambient": 0.0}[mood]
    mix = mixdown(tr, kicks, sc_depth=sc_depth, master=0.85)
    n = int(dur * SR); mix = mix[:, :n]
    if mix.shape[1] < n: mix = np.pad(mix, ((0, 0), (0, n - mix.shape[1])))
    f = int(min(1.6, dur * 0.1) * SR); mix[:, -f:] *= np.linspace(1, 0, f) ** 2
    return mix


def sfx(tl, custom_music=False, enabled=True):
    dur = float(tl["duration"]); n = int(dur * SR)
    tr = Track(dur)
    if enabled:
        for e in tl.get("sfx") or []:
            if e["kind"] == "click": tr.put("fx", ui_click(), e["t"], gain=0.3, pan=0.1)
            elif e["kind"] == "whoosh": tr.put("fx", whoosh(max(0.3, min(0.7, e.get("dur", .5) + .2))), e["t"] - 0.1, gain=0.3, pan=-0.15)
            elif e["kind"] == "hit": tr.put("fx", impact(0.5), e["t"], gain=0.25, send=0.3)
        for h in tl.get("hits") or []:
            if h["kind"] == "hit": tr.put("fx", tick(), h["t"], gain=0.2)
        if custom_music:
            for h in tl.get("hits") or []:
                if h["kind"] == "end": tr.put("fx", impact(0.8), h["t"], gain=0.45, send=0.4)
    out = tr.bus["fx"] + signal.fftconvolve(tr.bus["verb"][0], reverb_ir()[0])[: tr.n] * 0.3
    return out[:, :n] if out.shape[1] >= n else np.pad(out, ((0, 0), (0, n - out.shape[1])))


def custom_track(path, dur, offset=0.0):
    a = FF.decode_audio(path, SR, 2)
    i0 = int(max(0, offset) * SR); n = int(dur * SR)
    a = a[:, i0:i0 + n]
    if a.shape[1] < n:   # loop short tracks with a crossfade
        reps = [a]
        while sum(x.shape[1] for x in reps) < n: reps.append(a)
        a = np.concatenate(reps, axis=1)[:, :n]
    f = int(min(2.0, dur * 0.1) * SR); a[:, -f:] *= np.linspace(1, 0, f) ** 2
    fi = int(0.05 * SR); a[:, :fi] *= np.linspace(0, 1, fi)
    return a


def rms(a): return float(np.sqrt(np.mean(a ** 2)) + 1e-12)


def music(P, job):
    tl = P.get("timeline")
    if not tl: raise DirectorError("Build the timeline first.")
    m = P.cfg["music"]
    mood = m.get("mood") or "auto"
    if mood == "auto": mood = TEMPLATE_MOOD.get(tl.get("template"), "keys")
    os.makedirs(P.p("audio"), exist_ok=True)
    custom = m.get("file") and mood == "custom"
    if mood == "custom" and not m.get("file"): raise DirectorError("Choose a music file, or pick one of the built-in moods.")
    if custom:
        path = m["file"] if os.path.isabs(m["file"]) else P.p(m["file"])
        job.msg("Fitting your track (%s)…" % os.path.basename(path))
        bed = custom_track(path, tl["duration"], float(m.get("offset") or 0))
    elif mood == "none":
        bed = np.zeros((2, int(tl["duration"] * SR)))
    else:
        key = m.get("key") or "auto"
        harmony = None if key == "auto" else key
        job.msg("Composing %s at %d BPM…" % (MOODS[mood]["label"], tl.get("bpm") or MOODS[mood]["bpm"]))
        bed = compose(tl, mood, harmony, tl.get("bpm"), int(m.get("seed") or 7), int(m.get("transpose") or 0))
    FF.write_wav(P.p("audio", "music.wav"), bed)
    job.progress(0.8, "Sound design…")
    fx = sfx(tl, custom_music=bool(custom) or mood == "none", enabled=m.get("sfx", True))
    FF.write_wav(P.p("audio", "sfx.wav"), fx)
    return mix(P, job)


def mix(P, job=None):
    """bed (ducked under the voice) + voice-over + sound design -> audio/mix.wav"""
    tl = P.get("timeline"); m = P.cfg["music"]
    n = int(float(tl["duration"]) * SR)
    def load(p):
        if not os.path.exists(p): return np.zeros((2, n))
        x, sr = FF.read_wav(p)
        if x.shape[0] == 1: x = np.vstack([x[0], x[0]])
        x = x[:, :n]
        return np.pad(x, ((0, 0), (0, n - x.shape[1]))) if x.shape[1] < n else x
    bed = load(P.p("audio", "music.wav")); fx = load(P.p("audio", "sfx.wav"))
    vo = np.zeros(n)
    for seg in tl.get("vo") or []:
        p = P.p(seg["file"])
        if not os.path.exists(p): continue
        x, _ = FF.read_wav(p); x = x[0]
        i = int(seg["start"] * SR); x = x[: max(0, n - i)]
        vo[i:i + len(x)] += x
    has_vo = bool(np.any(vo))
    # bed level: the ducked bed sits ~17 dB under the speech (-19 dBFS RMS); without a voice-over it is the star
    d = float(m.get("duck") or 10)
    target = (-36.0 + d) if has_vo else -17.0
    if rms(bed) > 1e-6: bed = bed * 10 ** ((target - 20 * np.log10(rms(bed))) / 20)
    bed *= 10 ** (float(m.get("volume") or 0) / 20)
    if has_vo:
        duck = np.ones(n)
        for seg in tl["vo"]:
            a, z = int((seg["start"] - 0.2) * SR), int((seg["end"] + 0.3) * SR)
            duck[max(0, a):min(n, z)] = 10 ** (-d / 20)
        # lift before the voice comes in and under the end card
        k = int(0.25 * SR); win = np.hanning(2 * k); win /= win.sum()
        duck = signal.fftconvolve(np.pad(duck, k, mode="edge"), win, mode="same")[k:-k][:n]
        bed = bed * duck
    out = bed + fx * (0.9 if has_vo else 1.0) + np.vstack([vo, vo])
    pk = np.max(np.abs(out)) + 1e-9
    out = out / max(1.0, pk / 0.95)
    FF.write_wav(P.p("audio", "mix.wav"), out)
    return {"has_vo": has_vo, "peak": round(float(pk), 3)}


# ------------------------------------------------------------------ previews (the Sound page)
SFX_DEMOS = {"click": lambda: ui_click(), "whoosh": lambda: whoosh(0.55), "hit": lambda: impact(0.7), "riser": lambda: riser(1.8, 400, 7000), "tick": lambda: tick()}


def demo_timeline(bpm):
    """a 10-second mini film: hook (with hits), two shots (clicks, a transition), end card"""
    b = 60.0 / bpm; t1 = round(4 * b / b) * b
    d = max(9.5, 20 * b)
    sh1, sh2, end = 4 * b, 10 * b, 14 * b
    return {"duration": round(d, 3), "bpm": bpm,
            "scenes": [{"type": "hook", "t0": 0, "t1": sh1}, {"type": "shot", "t0": sh1, "t1": sh2}, {"type": "shot", "t0": sh2, "t1": end}, {"type": "end", "t0": end, "t1": d}],
            "hits": [{"t": 0.05, "kind": "hit"}, {"t": b, "kind": "hit"}, {"t": end, "kind": "end"}],
            "sfx": [{"t": sh1 - 0.25, "kind": "whoosh", "dur": 0.5}, {"t": sh1 + 1.3, "kind": "click"}, {"t": sh2 - 0.25, "kind": "whoosh", "dur": 0.5}, {"t": sh2 + 1.1, "kind": "click"}]}


def demo(out_dir, mood, harmony="auto", seed=7, transpose=0, bpm=0, with_sfx=True):
    """write (or reuse) a preview of a mood; returns the file name"""
    os.makedirs(out_dir, exist_ok=True)
    if mood in SFX_DEMOS:
        name = "sfx_%s.wav" % mood
        path = os.path.join(out_dir, name)
        if not os.path.exists(path):
            x = SFX_DEMOS[mood]()
            pad = np.zeros(int(0.25 * SR))
            x = np.concatenate([pad, x, pad]) * 0.9 / (np.max(np.abs(x)) + 1e-9)
            FF.write_wav(path, np.vstack([x, x]))
        return name
    if mood not in MOODS: raise DirectorError("unknown mood %s" % mood)
    bpm = float(bpm or MOODS[mood]["bpm"])
    name = "music_%s_%s_%d_%d_%d%s.wav" % (mood, harmony or "auto", int(seed), int(transpose), int(bpm), "_fx" if with_sfx else "")
    path = os.path.join(out_dir, name)
    if os.path.exists(path): return name
    tl = demo_timeline(bpm)
    x = compose(tl, mood, None if harmony in (None, "", "auto") else harmony, bpm, int(seed), int(transpose))
    if with_sfx: x = x + sfx(tl) * 0.8
    x = x * (10 ** (-16 / 20) / (np.sqrt(np.mean(x ** 2)) + 1e-9))          # comparable loudness across moods
    x = x / max(1.0, np.max(np.abs(x)) / 0.95)
    tmp = path + ".part.wav"; FF.write_wav(tmp, x); os.replace(tmp, path)
    return name
