"""Deterministic frame-stepping recorder (generalised from QuantSkill's dev/video/recorder.py).

Headless Chromium can't screen-record smoothly, so we never record in real time.
Every frame: advance a fake clock (timers, rAF, Date, performance.now via
Playwright's clock API) and seek every Web Animation (CSS animations and
transitions) by the same dt, then take a screenshot. The footage is perfectly
smooth whatever the machine's speed.

Server-side apps (Shiny, Streamlit, ...) still answer in real time over their
websocket; `settle()` lets real time pass (while recording) until the app is idle.

Per shot folder:  f00000.jpg …, markers.json (named frame indices, e.g. clicks),
cursor.json (per-frame cursor [x, y, visible, pressed], normalised to the viewport),
meta.json (fps, viewport, dpr, frames).
"""
import base64, datetime, json, os, shutil, time

from .fonts import inter_woff2

CAPTURE_CSS = """
html,body{scroll-behavior:auto!important}
::-webkit-scrollbar{display:none!important;width:0!important;height:0!important}
*{scrollbar-width:none!important}
*,*::before,*::after{caret-color:transparent}
"""

ANIM_JS = r"""
(() => {
  try { document.startViewTransition = undefined; Document.prototype.startViewTransition = undefined; } catch (e) {}
  const st = { t: 0, map: new WeakMap() };
  let seed = (window.__drSeed || 20260312) >>> 0;
  Math.random = () => { seed = (seed + 0x6D2B79F5) >>> 0; let t = seed; t = Math.imul(t ^ (t >>> 15), t | 1); t ^= t + Math.imul(t ^ (t >>> 7), t | 61); return ((t ^ (t >>> 14)) >>> 0) / 4294967296; };
  const grab = (e) => { try { for (const a of e.target.getAnimations()) { if (!st.map.has(a)) { st.map.set(a, { base: 0, t0: st.t }); a.pause(); a.currentTime = 0; } } } catch (err) {} };
  document.addEventListener('animationstart', grab, true);
  document.addEventListener('transitionrun', grab, true);
  window.__drAdvance = (dt) => {
    st.t += dt;
    let n = 0;
    try {
      for (const a of document.getAnimations()) {
        n++;
        let s = st.map.get(a);
        if (!s) { s = { base: a.currentTime || 0, t0: st.t - dt }; st.map.set(a, s); try { a.pause(); } catch (e) {} }
        try { a.currentTime = s.base + (st.t - s.t0); } catch (e) {}
      }
    } catch (e) {}
    return n;
  };
  // is a server-backed app busy? (Shiny, Streamlit, generic spinners)
  window.__drBusy = () => {
    const d = document.documentElement;
    if (d.classList.contains('shiny-busy')) return true;
    if (document.querySelector('.recalculating, .shiny-output-busy')) return true;
    if (document.querySelector('[data-testid="stStatusWidget"] [data-testid="stStatusWidgetRunningIcon"], .stSpinner')) return true;
    return false;
  };
})();
"""

CURSOR_JS = r"""
(() => {
  if (window.__drCur) return;
  const c = document.createElement('div'); c.id = '__drCursor';
  const style = window.__drCursorStyle || 'mac';
  const fill = style === 'light' ? '#fff' : '#111', stroke = style === 'light' ? '#111' : '#fff';
  c.innerHTML = '<svg width="30" height="30" viewBox="0 0 28 28"><path d="M6 3 L6 23 L11 18.5 L14.6 26 L18 24.4 L14.5 17 L21 17 Z" fill="' + fill + '" stroke="' + stroke + '" stroke-width="1.8" stroke-linejoin="round"/></svg><i></i>';
  c.style.cssText = 'position:fixed;left:0;top:0;z-index:2147483647;pointer-events:none;width:30px;height:30px;transform-origin:6px 3px;filter:drop-shadow(0 3px 6px rgba(0,0,0,.28));opacity:0;transition:none';
  const ring = c.querySelector('i');
  ring.style.cssText = 'position:absolute;left:-16px;top:-19px;width:44px;height:44px;border-radius:50%;background:' + (window.__drRing || 'rgba(0,113,227,.28)') + ';transform:scale(0);opacity:0;pointer-events:none';
  const mount = () => { const host = document.body || document.documentElement; if (host && !c.isConnected) host.appendChild(c); };
  if (document.documentElement) mount(); else document.addEventListener('DOMContentLoaded', mount);
  window.__drCur = { x: 0, y: 0 };
  window.__drCurSet = (x, y, press, ringT, vis) => {
    if (!c.isConnected) mount();
    c.style.opacity = vis; c.style.left = (x - 6) + 'px'; c.style.top = (y - 3) + 'px';
    const svg = c.querySelector('svg'); svg.style.transformOrigin = '6px 3px'; svg.style.transform = 'scale(' + (1 - 0.16 * press) + ')';
    if (ringT > 0 && ringT < 1) { ring.style.opacity = (1 - ringT) * 0.9; ring.style.transform = 'scale(' + (0.3 + ringT * 1.1) + ')'; }
    else { ring.style.opacity = 0; }
  };
})();
"""

CONSENT_JS = r"""
(() => {
  const words = /^(accept( all)?( cookies)?|allow( all)?( cookies)?|i agree|agree|got it|ok(ay)?|alle akzeptieren|tout accepter|aceptar( todo)?|accetta( tutto)?|continue)$/i;
  const cands = [...document.querySelectorAll('button, a[role=button], [role=button], input[type=button], input[type=submit]')];
  for (const b of cands) {
    const t = (b.innerText || b.value || '').trim();
    if (t.length < 30 && words.test(t)) {
      const r = b.getBoundingClientRect();
      if (r.width > 0 && r.height > 0) { b.click(); return t; }
    }
  }
  for (const s of ['#onetrust-banner-sdk', '.cc-window', '#cookie-banner', '.cookie-banner', '#CybotCookiebotDialog', '.fc-consent-root', '[aria-label*="cookie" i][role=dialog]'])
    document.querySelectorAll(s).forEach(e => e.remove());
  return null;
})()
"""


LITE_JS = r"""
(() => {
  if (!document.getElementById('dr-lite')) { const st = document.createElement('style'); st.id = 'dr-lite';
    st.textContent = '*{-webkit-backdrop-filter:none!important;backdrop-filter:none!important}'; (document.head || document.documentElement).appendChild(st); }
  let n = 0;
  for (const e of document.querySelectorAll('body *')) {
    if (e.__drLite) continue;
    const f = getComputedStyle(e).filter;
    const m = f && f !== 'none' && f.match(/blur\(([\d.]+)px\)/);
    if (m && parseFloat(m[1]) >= 14) {
      e.__drLite = 1; n++;
      e.style.setProperty('filter', f.replace(/blur\([\d.]+px\)/, 'blur(0px)'), 'important');
      const mask = 'radial-gradient(closest-side, #000 15%, rgba(0,0,0,.55) 50%, transparent 100%)';
      e.style.setProperty('-webkit-mask-image', mask, 'important'); e.style.setProperty('mask-image', mask, 'important');
    }
  }
  return n;
})()
"""


def ease_io(t):
    return 4 * t * t * t if t < 0.5 else 1 - (-2 * t + 2) ** 3 / 2


class Recorder:
    def __init__(self, outdir, width=1440, height=810, scale=2.0, scheme="light", fps=60, quality=90,
                 cursor_style="mac", ring="rgba(0,113,227,.28)", hide_css="", font=False, dry=False, log=print, lite=False):
        self.fps = fps; self.dt = 1000.0 / fps; self.quality = quality; self.dry = dry; self.log = log; self.lite = lite
        self.vw, self.vh, self.scale = width, height, scale
        self.outdir = None; self.n = 0; self.cursor_track = []; self.cur = None
        from playwright.sync_api import sync_playwright
        self._pw = sync_playwright().start()
        self.browser = self._pw.chromium.launch(args=["--force-color-profile=srgb", "--font-render-hinting=none", "--hide-scrollbars",
                                                      "--disable-background-timer-throttling", "--autoplay-policy=no-user-gesture-required"])
        mobile = width < 600
        self.ctx = self.browser.new_context(viewport={"width": width, "height": height}, device_scale_factor=scale,
                                            color_scheme="dark" if scheme == "dark" else "light", reduced_motion="no-preference",
                                            is_mobile=mobile, has_touch=False, ignore_https_errors=True,
                                            user_agent=None if not mobile else "Mozilla/5.0 (iPhone; CPU iPhone OS 17_4 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Mobile/15E148 Safari/604.1")
        self.ctx.add_init_script("window.__drCursorStyle = %s; window.__drRing = %s;" % (json.dumps(cursor_style), json.dumps(ring)))
        self.ctx.add_init_script(ANIM_JS)
        self.ctx.add_init_script(CURSOR_JS)
        css = CAPTURE_CSS + (hide_css or "")
        self.ctx.add_init_script("document.addEventListener('DOMContentLoaded', () => { const s = document.createElement('style'); s.id = 'dr-capture-css'; s.textContent = %s; document.head.appendChild(s); });" % json.dumps(css))
        if font:
            f = inter_woff2()
            if f:
                b64 = base64.b64encode(f).decode()
                self.ctx.add_init_script("document.addEventListener('DOMContentLoaded', () => { const s = document.createElement('style'); s.textContent = \"@font-face{font-family:'Inter';src:url(data:font/woff2;base64,%s) format('woff2');font-weight:100 900}\"; document.head.appendChild(s); });" % b64)
        self.page = self.ctx.new_page()
        self.page.set_default_timeout(30000)
        self.cdp = self.ctx.new_cdp_session(self.page)
        self.page.clock.install(time=datetime.datetime(2026, 3, 12, 9, 40, 58))
        self.errors = []
        self.page.on("pageerror", lambda e: self.errors.append(str(e)[:300]))
        self._acc = 0.0; self._pending_cur = None
        # CDP returns CSS pixels unless asked for a scaled clip (device pixels cost more, so only when dpr > 1)
        self._shot_args = {"format": "jpeg", "quality": quality, "optimizeForSpeed": True}
        if scale and scale > 1: self._shot_args["clip"] = {"x": 0, "y": 0, "width": width, "height": height, "scale": scale}
        if outdir: self.set_out(outdir)

    # -- navigation / time --------------------------------------------------
    def goto(self, url, settle_ms=800, dismiss=True):
        from .net import harden, open_page, wait_ready
        if not getattr(self, "_hardened", False):
            harden(self.ctx, url, self.log); self._hardened = True
        self.page.clock.pause_at(datetime.datetime(2026, 3, 12, 9, 41, 0))
        open_page(self.page, url, self.log, timeout=120)
        # the fake clock is paused: let the app connect and compute while advancing it
        wait_ready(self.page, self.log, max_s=180, clock=lambda ms: self._tick(ms))
        try: self.page.evaluate("document.fonts.ready")
        except Exception: pass  # noqa: BLE001
        self.settle(max_ms=12000, min_ms=settle_ms, record=False)
        if dismiss:
            try:
                t = self.page.evaluate(CONSENT_JS)
                if t: self.log("  dismissed a consent banner (%s)" % t); self.idle(600)
            except Exception: pass  # noqa: BLE001
        self.apply_lite()

    def apply_lite(self):
        if not self.lite: return
        try: self.page.evaluate(LITE_JS)
        except Exception: pass  # noqa: BLE001

    def frame_cost(self, n=5):
        """average seconds per recorded frame on the current page (used to decide on lite effects)"""
        t = time.time()
        for _ in range(n):
            self._tick(self.dt)
            self.cdp.send("Page.captureScreenshot", self._shot_args)
        return (time.time() - t) / n

    def _tick(self, ms):
        self._acc += ms
        whole = int(self._acc)
        if whole > 0:
            try: self.page.clock.run_for(whole)
            except Exception: pass  # noqa: BLE001
            self._acc -= whole
        cur, self._pending_cur = self._pending_cur, None
        # one round-trip per frame: advance the animations and move the drawn cursor
        try: self.page.evaluate("(a) => { if (window.__drAdvance) window.__drAdvance(a[0]); if (a[1] && window.__drCurSet) window.__drCurSet(...a[1]); }", [ms, cur])
        except Exception: pass  # noqa: BLE001

    def idle(self, ms, step=50.0):
        """advance time without recording"""
        steps = max(1, int(round(ms / step)))
        for _ in range(steps): self._tick(ms / steps)

    def busy(self):
        try: return bool(self.page.evaluate("() => window.__drBusy ? window.__drBusy() : false"))
        except Exception: return False  # noqa: BLE001

    def settle(self, max_ms=6000, min_ms=0, record=True, quiet_ms=350):
        """let a server-backed app finish updating. Advances virtual time in step with real time."""
        t0 = time.time(); v = 0.0; quiet = 0.0
        step = self.dt if record else 50.0
        while True:
            if record: self.rec_frame()
            else: self._tick(step)
            v += step
            if self.busy(): quiet = 0.0
            else: quiet += step
            if v >= min_ms and quiet >= quiet_ms: break
            if v >= max_ms or time.time() - t0 > max_ms / 1000 * 4 + 10: break
            if not record: time.sleep(0.02)
        self.apply_lite()
        return v

    # -- output ---------------------------------------------------------------
    def set_out(self, outdir):
        if os.path.isdir(outdir): shutil.rmtree(outdir)
        os.makedirs(outdir); self.outdir = outdir; self.n = 0; self.cursor_track = []; self.markers = {}

    def mark(self, name):
        self.markers[name] = self.n

    def snap(self, path, fmt="jpeg", quality=88, full_page=False):
        if full_page:
            self.page.screenshot(path=path, type=fmt, quality=quality if fmt == "jpeg" else None, full_page=True); return
        d = self.cdp.send("Page.captureScreenshot", {"format": fmt, "quality": quality} if fmt == "jpeg" else {"format": fmt})
        with open(path, "wb") as f: f.write(base64.b64decode(d["data"]))

    def rec_frame(self):
        self._tick(self.dt)
        c = self.cur
        self.cursor_track.append([round(c.x / self.vw, 4), round(c.y / self.vh, 4), round(c.vis, 2), round(c.press, 2)] if c else [0.5, 0.5, 0, 0])
        if self.dry and self.n % 10:
            self.n += 1; return
        p = os.path.join(self.outdir, "f%05d.jpg" % self.n)
        d = self.cdp.send("Page.captureScreenshot", self._shot_args)
        with open(p, "wb") as f: f.write(base64.b64decode(d["data"]))
        self.n += 1

    def rec(self, ms, each=None):
        n = max(1, int(round(ms / self.dt)))
        for i in range(n):
            if each: each(i, n)
            self.rec_frame()

    def finish(self, extra=None):
        meta = {"fps": self.fps, "viewport": [self.vw, self.vh], "dpr": self.scale, "frames": self.n}
        if extra: meta.update(extra)
        json.dump(meta, open(os.path.join(self.outdir, "meta.json"), "w"))
        json.dump(self.markers, open(os.path.join(self.outdir, "markers.json"), "w"), indent=1)
        json.dump(self.cursor_track, open(os.path.join(self.outdir, "cursor.json"), "w"), separators=(",", ":"))

    # -- scripted helpers ------------------------------------------------------
    def js(self, code, arg=None):
        return self.page.evaluate(code, arg) if arg is not None else self.page.evaluate(code)

    def scroll_y(self):
        try: return float(self.js("() => window.scrollY || document.scrollingElement.scrollTop || 0"))
        except Exception: return 0.0  # noqa: BLE001

    def max_scroll(self):
        try: return float(self.js("() => Math.max(0, (document.scrollingElement || document.documentElement).scrollHeight - innerHeight)"))
        except Exception: return 0.0  # noqa: BLE001

    def scroll_rec(self, y_to, ms, record=True):
        y0 = self.scroll_y(); y_to = max(0.0, min(float(y_to), self.max_scroll()))
        def each(i, n):
            y = y0 + (y_to - y0) * ease_io((i + 1) / n)
            self.js("(y) => { window.scrollTo(0, y); window.dispatchEvent(new Event('scroll')); }", y)
        if record: self.rec(ms, each)
        else:
            self.js("(y) => window.scrollTo(0, y)", y_to); self.idle(200)

    def close(self):
        try: self.browser.close()
        except Exception: pass  # noqa: BLE001
        finally:
            try: self._pw.stop()
            except Exception: pass  # noqa: BLE001


class Cursor:
    """Synthetic macOS-like cursor that also drives the real mouse (so hover states are real)."""

    def __init__(self, rec, x=None, y=None, hidden=False):
        self.r = rec; self.x = x if x is not None else rec.vw * 0.62; self.y = y if y is not None else rec.vh * 0.7
        self.vis = 0.0; self.press = 0.0; self.hidden = hidden
        rec.cur = self
        self.install()

    def install(self):
        try: self.r.js(CURSOR_JS)
        except Exception: pass  # noqa: BLE001

    def _apply(self, ring=0.0):
        """queued: drawn by the recorder's next frame tick (saves a browser round-trip per frame)"""
        if self.hidden: return
        self.r._pending_cur = [self.x, self.y, self.press, ring, self.vis]

    def _run(self, ms, each, record):
        if record: self.r.rec(ms, each)
        else:
            n = max(1, int(round(ms / self.r.dt)))
            for i in range(n): each(i, n); self.r._tick(self.r.dt)

    def show(self, ms=250, record=True):
        def each(i, n): self.vis = (i + 1) / n; self._apply()
        self._run(ms, each, record)

    def hide(self, ms=250, record=True):
        def each(i, n): self.vis = 1 - (i + 1) / n; self._apply()
        self._run(ms, each, record)

    def move(self, xy, ms=600, record=True, arc=0.12):
        x0, y0 = self.x, self.y; x1, y1 = xy
        mx, my = (x0 + x1) / 2 - (y1 - y0) * arc, (y0 + y1) / 2 + (x1 - x0) * arc
        def each(i, n):
            t = ease_io((i + 1) / n)
            self.x = (1 - t) ** 2 * x0 + 2 * (1 - t) * t * mx + t * t * x1
            self.y = (1 - t) ** 2 * y0 + 2 * (1 - t) * t * my + t * t * y1
            try: self.r.page.mouse.move(self.x, self.y)
            except Exception: pass  # noqa: BLE001
            self._apply()
        self._run(ms, each, record)

    def drift(self, ms=1500, record=True, radius=22):
        """a gentle, natural wander while the viewer reads the screen"""
        import math
        cx, cy = self.x, self.y
        def each(i, n):
            t = (i + 1) / n
            self.x = cx + radius * math.sin(t * 2.1 + 0.4) * t; self.y = cy + radius * 0.6 * math.sin(t * 3.3) * t
            self._apply()
        self._run(ms, each, record)

    def click(self, record=True, hold_ms=90, after_ms=260, mark=None, real=True):
        def down(i, n): self.press = (i + 1) / n; self._apply()
        self._run(hold_ms, down, record)
        if mark: self.r.mark(mark)
        if real:
            try: self.r.page.mouse.down(); self.r.page.mouse.up()
            except Exception as e: self.r.log("  click failed: %s" % str(e)[:100])  # noqa: BLE001
        self.install()
        def up(i, n):
            t = (i + 1) / n; self.press = max(0, 1 - t * 2.5); self._apply(ring=t)
        self._run(after_ms, up, record)
        self.press = 0; self._apply()

    def drag(self, xy_from, xy_to, ms=1200, record=True, mark=None):
        self.move(xy_from, 450, record)
        def down(i, n): self.press = (i + 1) / n; self._apply()
        self._run(90, down, record)
        if mark: self.r.mark(mark)
        try: self.r.page.mouse.down()
        except Exception: pass  # noqa: BLE001
        x0, y0 = self.x, self.y; x1, y1 = xy_to
        def each(i, n):
            t = ease_io((i + 1) / n)
            self.x = x0 + (x1 - x0) * t; self.y = y0 + (y1 - y0) * t
            try: self.r.page.mouse.move(self.x, self.y)
            except Exception: pass  # noqa: BLE001
            self._apply()
        self._run(ms, each, record)
        try: self.r.page.mouse.up()
        except Exception: pass  # noqa: BLE001
        def up(i, n): self.press = max(0, 1 - (i + 1) / n * 2); self._apply()
        self._run(200, up, record)
