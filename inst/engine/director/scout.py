"""Scout: open the running app in a browser and map it.

Writes scout.json:
  meta    title, description, og tags, favicon, theme-color, framework, dark/light
  colors  brand palette (computed styles + screenshot palette)
  views   [{id, label, kind: home|tab|page, reach: {url, tab}, thumb, height, sections,
            inputs, buttons, outputs, focus}]
and thumbnails in scout/*.jpg (1440x810 at DPR 1; used by the UI and the planner).
"""
import colorsys, json, os, re, time, urllib.parse

from .util import DirectorError

# --------------------------------------------------------------------------- page model (runs in the page)
MODEL_JS = r"""
() => {
  const vis = (e) => { if (!e || !e.getBoundingClientRect) return false; const r = e.getBoundingClientRect(); const s = getComputedStyle(e);
    return r.width > 3 && r.height > 3 && s.visibility !== 'hidden' && s.display !== 'none' && parseFloat(s.opacity) > 0.05; };
  const box = (e) => { const r = e.getBoundingClientRect(); return [Math.round(r.left), Math.round(r.top + scrollY), Math.round(r.width), Math.round(r.height)]; };
  const txt = (e) => ((e.getAttribute && (e.getAttribute('aria-label') || e.getAttribute('title'))) || e.innerText || e.value || '').trim().replace(/\s+/g, ' ').slice(0, 70);
  const uniq = (sel) => { try { return document.querySelectorAll(sel).length === 1; } catch (e) { return false; } };
  const cssPath = (e) => {
    if (e.id && /^[A-Za-z][\w-]*$/.test(e.id) && uniq('#' + e.id)) return '#' + e.id;
    const parts = []; let cur = e;
    for (let depth = 0; cur && cur.nodeType === 1 && depth < 5; depth++) {
      let p = cur.tagName.toLowerCase();
      if (cur.id && /^[A-Za-z][\w-]*$/.test(cur.id) && !/\d{3,}/.test(cur.id)) { parts.unshift('#' + cur.id); break; }
      const par = cur.parentElement;
      if (par) { const same = [...par.children].filter(x => x.tagName === cur.tagName); if (same.length > 1) p += ':nth-of-type(' + (same.indexOf(cur) + 1) + ')'; }
      parts.unshift(p); cur = par;
      const s = parts.join(' > '); if (uniq(s)) return s;
    }
    return parts.join(' > ');
  };
  const W = innerWidth, H = innerHeight;
  const out = { url: location.href, title: document.title, vw: W, vh: H,
    height: Math.max(document.documentElement.scrollHeight, document.body ? document.body.scrollHeight : 0),
    framework: window.Shiny ? 'shiny' : (document.querySelector('[data-testid="stApp"]') ? 'streamlit' : (document.querySelector('gradio-app') ? 'gradio' : 'web')) };
  const meta = (n) => { const m = document.querySelector('meta[name="' + n + '"], meta[property="' + n + '"]'); return m ? m.content : ''; };
  out.meta = { description: meta('description'), ogTitle: meta('og:title'), ogDescription: meta('og:description'), ogSite: meta('og:site_name'),
               ogImage: meta('og:image'), themeColor: meta('theme-color'), lang: document.documentElement.lang || '' };
  const icons = [...document.querySelectorAll('link[rel~="icon"], link[rel="apple-touch-icon"], link[rel="shortcut icon"]')].map(l => ({ href: l.href, sizes: l.sizes ? l.sizes.value : '', rel: l.rel }));
  out.icons = icons;
  const logoImg = [...document.querySelectorAll('header img, nav img, .navbar img, .navbar-brand img, [class*="logo" i] img, img[class*="logo" i], img[alt*="logo" i], img[src*="logo" i]')].filter(vis)[0];
  out.logo = logoImg ? logoImg.src : '';
  const logoSvg = [...document.querySelectorAll('.navbar-brand svg, [class*="brand" i] svg, [class*="logo" i] svg, header a svg, nav a svg')].filter(vis).find(s => { const r = s.getBoundingClientRect(); return r.width >= 16 && r.height >= 16 && s.querySelectorAll('*').length >= 2; });
  if (logoSvg) { const c = logoSvg.cloneNode(true); c.setAttribute('xmlns', 'http://www.w3.org/2000/svg'); if (!c.getAttribute('viewBox')) { const r = logoSvg.getBoundingClientRect(); c.setAttribute('viewBox', '0 0 ' + r.width + ' ' + r.height); }
    c.removeAttribute('class'); c.setAttribute('width', '512'); c.setAttribute('height', '512'); out.logoSvg = c.outerHTML; }
  const brand = document.querySelector('.navbar-brand, [class*="brand" i], header [class*="logo" i]');
  out.brandText = brand ? txt(brand) : '';
  // tabs / navigation: bootstrap/bslib tabs, role=tab, SPA routes (#/x) and short links inside nav / header / sidebars
  const tabSel = '.nav-link, [role="tab"], .navbar-nav a, .nav a, [data-bs-toggle="tab"], [data-toggle="tab"], [data-bs-toggle="pill"], .tabbable a, [data-baseweb="tab"], .stTabs button, .sidebar-menu a, .shiny-tab-input a';
  const navSel = 'nav a, header a, [role="navigation"] a, aside a, .sidebar a, [role="tablist"] button, nav button[data-path], nav button[data-value], [class*="nav" i] > a';
  const isSection = (e) => { const h = e.getAttribute('href') || '';
    if (e.matches('[data-bs-toggle], [data-toggle], [role="tab"], [data-value]')) return false;
    const tgt = /^#[A-Za-z][\w-]*$/.test(h) && document.getElementById(h.slice(1));
    return !!tgt && !tgt.matches('.tab-pane, [role="tabpanel"]'); };
  const seenT = new Set();
  const navEls = [...new Set([...document.querySelectorAll(tabSel), ...document.querySelectorAll(navSel)])];
  out.tabs = navEls.filter(vis).filter(e => !isSection(e) && !e.closest('.dropdown-menu')).map(e => {
      const href = e.getAttribute('href') || '';
      let kind = 'tab';
      if (href && !href.startsWith('#') && !href.startsWith('javascript')) {
        try { const u = new URL(e.href, location.href); if (u.origin !== location.origin) return null; if (u.pathname === location.pathname && !u.hash) return null; kind = u.pathname !== location.pathname ? 'page' : 'tab'; } catch (err) { return null; }
      }
      if (href === '#' && !e.matches(tabSel)) return null;
      return { text: txt(e), box: box(e), href: href, kind: kind, dropdown: e.classList.contains('dropdown-toggle'),
               active: e.classList.contains('active') || e.classList.contains('is-active') || e.getAttribute('aria-selected') === 'true' || e.getAttribute('aria-current') === 'page' };
    }).filter(t => t && t.text && t.text.length < 32 && !/logo|home page|skip to/i.test(t.text) && !t.dropdown && !seenT.has(t.text) && seenT.add(t.text));
  out.tabs = out.tabs.filter((t, i) => { const e = navEls.filter(vis).find(x => txt(x) === t.text); return !(e && (e.matches('.navbar-brand, [class*="brand" i]') || e.querySelector('img, svg') && txt(e).length > 0 && /home/i.test(e.getAttribute('aria-label') || ''))); });
  // internal links (multi-page sites)
  const seenL = new Set([location.pathname]);
  out.links = [...document.querySelectorAll('header a[href], nav a[href], .navbar a[href], [role="navigation"] a[href], a[href]')].filter(vis).map(a => {
      try { const u = new URL(a.href, location.href); if (u.origin !== location.origin || u.hash && u.pathname === location.pathname) return null;
            if (/\.(pdf|zip|png|jpe?g|svg|csv|xlsx?)$/i.test(u.pathname) || /logout|signout|sign-out|delete/i.test(u.pathname)) return null;
            if (seenL.has(u.pathname)) return null; seenL.add(u.pathname); return { text: txt(a), path: u.pathname + u.search, box: box(a) }; } catch (e) { return null; } })
    .filter(x => x && x.text && x.text.length < 40).slice(0, 12);
  // inputs
  const inputs = [];
  document.querySelectorAll('.irs').forEach(e => { if (!vis(e)) return; const inp = e.parentElement && e.parentElement.querySelector('input.js-range-slider, input[data-type]');
    const lab = e.closest('.form-group, .shiny-input-container'); inputs.push({ type: 'slider', css: inp && inp.id ? '#' + inp.id : cssPath(e), label: lab ? txt(lab.querySelector('label') || lab).slice(0, 50) : '', box: box(e) }); });
  document.querySelectorAll('input[type="range"]').forEach(e => { if (vis(e)) inputs.push({ type: 'range', css: cssPath(e), label: txt(e.closest('label, .form-group, div') || e).slice(0, 50), box: box(e) }); });
  document.querySelectorAll('.selectize-control').forEach(e => { if (!vis(e)) return; const sel = e.parentElement && e.parentElement.querySelector('select');
    const lab = e.closest('.form-group, .shiny-input-container'); inputs.push({ type: 'selectize', css: sel && sel.id ? '#' + sel.id : cssPath(e), label: lab ? txt(lab.querySelector('label') || lab).slice(0, 50) : '', box: box(e),
      options: sel ? [...sel.options].map(o => o.text).slice(0, 12) : [] }); });
  document.querySelectorAll('select').forEach(e => { if (!vis(e)) return; inputs.push({ type: 'select', css: cssPath(e), label: e.labels && e.labels[0] ? txt(e.labels[0]) : '', box: box(e), options: [...e.options].map(o => o.text).slice(0, 12) }); });
  document.querySelectorAll('input[type="text"]:not(.js-range-slider):not(.irs-hidden-input), input[type="search"], input[type="email"], input:not([type]), textarea').forEach(e => { if (!vis(e) || e.closest('.selectize-control, .irs')) return;
    inputs.push({ type: 'text', css: cssPath(e), label: (e.labels && e.labels[0] ? txt(e.labels[0]) : '') || e.placeholder || '', placeholder: e.placeholder || '', box: box(e) }); });
  document.querySelectorAll('input[type="number"]').forEach(e => { if (vis(e)) inputs.push({ type: 'number', css: cssPath(e), label: e.labels && e.labels[0] ? txt(e.labels[0]) : '', box: box(e) }); });
  document.querySelectorAll('input[type="checkbox"], input[type="radio"]').forEach(e => { const l = e.closest('label') || (e.labels && e.labels[0]); const t = l || e; if (vis(t)) inputs.push({ type: e.type, css: cssPath(t), label: txt(t), box: box(t) }); });
  out.inputs = inputs.slice(0, 40);
  // buttons
  const seenB = new Set();
  out.buttons = [...document.querySelectorAll('button, .btn, a.btn, [role="button"], input[type="submit"], input[type="button"]')].filter(vis)
    .filter(e => !e.closest('.nav, .navbar-nav, [role="tablist"], .selectize-control, .irs'))
    .map(e => ({ text: txt(e), css: cssPath(e), box: box(e), primary: /primary|cta|main/i.test(e.className) }))
    .filter(b => b.text && b.text.length < 40 && !/delete|remove|logout|log out|sign out|reset|clear|close|cancel|dismiss|×/i.test(b.text) && !seenB.has(b.text) && seenB.add(b.text)).slice(0, 20);
  // outputs / visual blocks (camera focus candidates)
  const outs = [];
  document.querySelectorAll('.shiny-plot-output, .html-widget, .plotly, .js-plotly-plot, .leaflet-container, .dataTables_wrapper, .reactable, canvas, svg, table, img, video, .card, .value-box, .bslib-value-box, [data-testid="stPlotlyChart"], [data-testid="stVegaLiteChart"], [data-testid="stDataFrame"]')
    .forEach(e => { if (!vis(e)) return; const b = box(e); if (b[2] < 180 || b[3] < 110) return; if (e.tagName === 'svg' && e.closest('.html-widget, .plotly, .shiny-plot-output')) return;
      if (e.tagName === 'IMG' && e.closest('a.navbar-brand, header')) return;
      outs.push({ kind: e.classList.contains('shiny-plot-output') ? 'plot' : (e.tagName === 'TABLE' || e.classList.contains('dataTables_wrapper') || e.classList.contains('reactable') ? 'table' : (e.classList.contains('card') || e.classList.contains('value-box') || e.classList.contains('bslib-value-box') ? 'card' : e.tagName.toLowerCase())),
                  css: cssPath(e), box: b, area: b[2] * b[3] }); });
  outs.sort((a, b) => b.area - a.area);
  out.outputs = outs.slice(0, 16);
  // lead paragraph: the first substantial paragraph in the main content (great voice-over material)
  const lead = [...document.querySelectorAll('main p, [role="main"] p, .tab-pane.active p, .container p, .container-fluid p, section p, p, .lead')].filter(vis).map(e => e.innerText.trim().replace(/\s+/g, ' ')).find(t => t.length > 50 && t.length < 600);
  out.lead = lead || '';
  // headings / sections
  out.sections = [...document.querySelectorAll('h1, h2, h3')].filter(vis).map(e => ({ tag: e.tagName.toLowerCase(), text: txt(e), y: box(e)[1] })).filter(s => s.text).slice(0, 30);
  // colours
  const col = (e, p) => { if (!e) return null; const v = getComputedStyle(e)[p]; return v && v !== 'rgba(0, 0, 0, 0)' && v !== 'transparent' ? v : null; };
  const q = (s) => [...document.querySelectorAll(s)].filter(vis).slice(0, 6);
  const bgEl = document.querySelector('main, .main, .container-fluid, body');
  out.colors = { bg: col(document.body, 'backgroundColor') || col(document.documentElement, 'backgroundColor') || 'rgb(255, 255, 255)', fg: col(document.body, 'color'),
    main: col(bgEl, 'backgroundColor'),
    accents: [].concat(q('.btn-primary, button[type="submit"], .btn, button').map(e => col(e, 'backgroundColor')),
                       q('a').map(e => col(e, 'color')), q('.navbar, header, nav').map(e => col(e, 'backgroundColor')),
                       q('.nav-link.active, [aria-selected="true"]').map(e => col(e, 'color')), q('h1, h2').map(e => col(e, 'color')),
                       q('.irs-bar, .irs-single, .progress-bar, .badge').map(e => col(e, 'backgroundColor'))).filter(Boolean) };
  // colour statistics: what the eye sees (backgrounds by area, gradient stops, text, svg fills)
  const stats = {}; const addc = (c, w) => { if (!c || /rgba\(0, 0, 0, 0\)|transparent/.test(c)) return; stats[c] = (stats[c] || 0) + w; };
  [...document.querySelectorAll('body *')].slice(0, 2500).forEach(e => {
    const r = e.getBoundingClientRect(); if (r.width < 2 || r.height < 2 || r.top > H * 1.5 || r.bottom < 0) return;
    const cs = getComputedStyle(e); if (cs.visibility === 'hidden' || cs.display === 'none' || parseFloat(cs.opacity) < .1) return;
    const area = Math.min(r.width * r.height, W * H * .25);
    addc(cs.backgroundColor, area / 1000);
    if (cs.backgroundImage && cs.backgroundImage !== 'none') (cs.backgroundImage.match(/rgba?\([^)]+\)/g) || []).forEach(c => addc(c, area / 2500));
    if (e.childNodes.length && [...e.childNodes].some(n => n.nodeType === 3 && n.textContent.trim())) addc(cs.color, parseFloat(cs.fontSize) * Math.min(80, e.textContent.length) / 40);
    if (e.tagName === 'stop') addc(e.getAttribute('stop-color') || cs.stopColor, 40);
    if (e instanceof SVGElement && cs.fill && cs.fill !== 'none') addc(cs.fill, area / 1500 + 4);
    if (cs.borderTopWidth !== '0px' && cs.borderTopStyle !== 'none') addc(cs.borderTopColor, 2);
  });
  out.colorStats = Object.entries(stats).sort((a, b) => b[1] - a[1]).slice(0, 60);
  // hero / main focus: the largest visible output, else the main content box
  const main = document.querySelector('main, [role="main"], .main-panel, .tab-content, .container, .container-fluid, #app, #root, body');
  out.mainBox = main ? box(main) : [0, 0, W, H];
  return out;
}
"""

FIND_JS = r"""
(t) => {
  const vis = (e) => { const r = e.getBoundingClientRect(); const s = getComputedStyle(e); return r.width > 2 && r.height > 2 && s.visibility !== 'hidden' && s.display !== 'none'; };
  const norm = (s) => (s || '').trim().replace(/\s+/g, ' ').toLowerCase();
  const SEL = { tab: '.nav-link, [role="tab"], .navbar-nav a, .nav a, [data-bs-toggle="tab"], [data-toggle="tab"], [data-bs-toggle="pill"], .tabbable a, [data-baseweb="tab"], .stTabs button, .sidebar-menu a, nav a, header a, [role="navigation"] a, aside a, .sidebar a, [role="tablist"] button, nav button',
    button: 'button, .btn, a.btn, [role="button"], input[type="submit"], input[type="button"]', link: 'a[href]',
    any: 'a, button, [role="button"], [role="tab"], .nav-link, label, h1, h2, h3, h4, p, span, div, li, td, input, select, textarea' };
  let els = [];
  if (t.css) { try { els = [...document.querySelectorAll(t.css)]; } catch (e) { els = []; } }
  if (!els.length || t.text) {
    const base = els.length ? els : [...document.querySelectorAll(SEL[t.kind] || SEL.any)];
    if (t.text) {
      const want = norm(t.text);
      let exact = base.filter(e => norm(e.innerText || e.value || e.getAttribute('aria-label')) === want && vis(e));
      if (!exact.length) exact = base.filter(e => norm(e.innerText || e.value).includes(want) && vis(e));
      // prefer the innermost match
      exact = exact.filter(e => !exact.some(o => o !== e && e.contains(o)));
      els = exact;
    } else els = base;
  }
  els = els.filter(vis);
  const e = els[Math.min(t.nth || 0, Math.max(0, els.length - 1))];
  if (!e) return null;
  // ionRangeSlider: target the handle
  let tgt = e;
  if (t.kind === 'slider' || (e.classList && e.classList.contains('js-range-slider'))) {
    const c = e.closest('.shiny-input-container, .form-group') || e.parentElement; const h = c && c.querySelector('.irs-handle.single, .irs-handle.from, .irs-handle');
    const line = c && c.querySelector('.irs-line');
    if (h && line) { const hr = h.getBoundingClientRect(), lr = line.getBoundingClientRect();
      return { x: hr.left + hr.width / 2, y: hr.top + hr.height / 2, w: hr.width, h: hr.height, line: [lr.left, lr.top + lr.height / 2, lr.width], slider: true }; }
  }
  if (e.classList && e.classList.contains('selectize-control')) tgt = e.querySelector('.selectize-input') || e;
  if (e.tagName === 'SELECT' && e.nextElementSibling && e.nextElementSibling.classList.contains('selectize-control')) tgt = e.nextElementSibling.querySelector('.selectize-input');
  const r = tgt.getBoundingClientRect();
  return { x: r.left + r.width / 2, y: r.top + r.height / 2, w: r.width, h: r.height, tag: e.tagName.toLowerCase() };
}
"""


OPEN_MENU_JS = r"""
() => {
  // responsive layouts hide the navigation behind a menu button: open it (returns true if something was clicked)
  const vis = (e) => { const r = e.getBoundingClientRect(); const s = getComputedStyle(e); return r.width > 4 && r.height > 4 && s.visibility !== 'hidden' && s.display !== 'none'; };
  const btn = [...document.querySelectorAll('.navbar-toggler, button[aria-controls][aria-expanded="false"], button[aria-label*="menu" i], button[aria-label*="navigation" i], .hamburger, [data-bs-toggle="collapse"], [data-toggle="collapse"]')]
    .filter(vis).find(b => b.getAttribute('aria-expanded') !== 'true');
  if (!btn) return null;
  const r = btn.getBoundingClientRect(); return { x: r.left + r.width / 2, y: r.top + r.height / 2 };
}
"""


def parse_rgb(s):
    if not s: return None
    s = s.strip()
    if s.startswith("#"):
        h = s[1:]
        if len(h) in (3, 4): h = "".join(c * 2 for c in h[:3])
        try: return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))
        except ValueError: return None
    m = re.match(r"rgba?\(\s*([\d.]+)[,\s]+([\d.]+)[,\s]+([\d.]+)(?:[,/\s]+([\d.]+))?", s)
    if not m: return None
    a = float(m.group(4)) if m.group(4) else 1.0
    if a < 0.5: return None
    return tuple(int(float(m.group(i))) for i in (1, 2, 3))


def hexc(rgb): return "#%02x%02x%02x" % tuple(max(0, min(255, int(c))) for c in rgb)


def vivid(rgb):
    h, l, s = colorsys.rgb_to_hls(*[c / 255 for c in rgb])
    return s * (1 - abs(2 * l - 1)), h, l, s


def screenshot_palette(path, k=8):
    try:
        from PIL import Image
        im = Image.open(path).convert("RGB").resize((240, 135))
        q = im.quantize(colors=k, method=Image.Quantize.MEDIANCUT)
        pal = q.getpalette()[: k * 3]; counts = sorted(q.getcolors(), reverse=True)
        return [(c, tuple(pal[i * 3:i * 3 + 3])) for c, i in counts]
    except Exception:  # noqa: BLE001
        return []


def pick_palette(colors, shots):
    """three brand colours: vivid, distinct hues (what the eye sees on the page, then screenshot palette)"""
    cands = []
    for c, w in colors.get("stats", []):
        rgb = parse_rgb(c)
        if rgb: cands.append((min(4.0, 0.6 + w / 40.0), rgb))
    for s in colors.get("accents", []):
        rgb = parse_rgb(s)
        if rgb: cands.append((1.5, rgb))
    for shot in shots[:3]:
        for count, rgb in screenshot_palette(shot):
            cands.append((min(2.0, count / 3000.0), rgb))
    scored = []
    for w, rgb in cands:
        v, h, l, s = vivid(rgb)
        if v < 0.28 or l < 0.18 or l > 0.82: continue
        scored.append((v * w, h, rgb))
    scored.sort(reverse=True)
    out = []
    for sc, h, rgb in scored:
        if all(min(abs(h - h2), 1 - abs(h - h2)) > 0.07 for _, h2, _ in out): out.append((sc, h, rgb))
        if len(out) == 3: break
    # order for the smoothest gradient, starting from the coolest colour
    import itertools
    def hd(a, b): d = abs(a - b); return min(d, 1 - d)
    best = min(itertools.permutations(out), key=lambda o: sum(hd(o[i][1], o[i + 1][1]) for i in range(len(o) - 1)) + 0.02 * abs(o[0][1] - 0.62)) if len(out) > 1 else out
    return [hexc(x[2]) for x in best]


def luminance(rgb):
    return 0.2126 * rgb[0] / 255 + 0.7152 * rgb[1] / 255 + 0.0722 * rgb[2] / 255


# --------------------------------------------------------------------------- the scout
SETTLE_INIT = """
(() => {
  window.__drLastMut = 0;
  const start = () => { try { new MutationObserver(() => { window.__drLastMut = performance.now(); })
      .observe(document.documentElement, { subtree: true, childList: true, attributes: true, characterData: true }); } catch (e) {} };
  if (document.documentElement) start(); else document.addEventListener('DOMContentLoaded', start);
})();
"""

BUSY_JS = """() => {
  const d = document.documentElement;
  if (document.readyState !== 'complete') return 'loading';
  if (d.classList.contains('shiny-busy') || document.querySelector('.recalculating, .shiny-output-busy, .stSpinner')) return 'server';
  try { for (const a of document.getAnimations()) { const t = a.effect && a.effect.getComputedTiming ? a.effect.getComputedTiming() : null;
        if (a.playState === 'running' && t && isFinite(t.endTime) && t.endTime < 4000) return 'anim'; } } catch (e) {}
  if (window.__drLastMut && performance.now() - window.__drLastMut < 220) return 'dom';
  return '';
}"""


def wait_idle(page, max_s=8.0, quiet_s=0.5, min_s=0.3):
    t0 = time.time(); quiet_since = None
    while time.time() - t0 < max_s:
        try: busy = page.evaluate(BUSY_JS)
        except Exception: busy = ""  # noqa: BLE001
        if busy: quiet_since = None
        elif quiet_since is None: quiet_since = time.time()
        if quiet_since and time.time() - quiet_since >= quiet_s and time.time() - t0 >= min_s: return True
        time.sleep(0.08)
    return False


CONSENT = None


def scout(P, job, url):
    from playwright.sync_api import sync_playwright
    from .recorder import CONSENT_JS
    cfg = P.cfg; vw, vh = P.viewport
    outdir = P.d("scout")
    for f in os.listdir(outdir):
        if f.endswith(".jpg"): os.remove(os.path.join(outdir, f))
    res = {"url": url, "viewport": [vw, vh], "views": []}
    with sync_playwright() as pw:
        b = pw.chromium.launch(args=["--hide-scrollbars", "--force-color-profile=srgb"])
        ctx = b.new_context(viewport={"width": vw, "height": vh}, device_scale_factor=1, ignore_https_errors=True,
                            color_scheme="dark" if cfg["capture"].get("scheme") == "dark" else "light",
                            is_mobile=vw < 600)
        ctx.add_init_script(SETTLE_INIT)
        from .net import harden, open_page, wait_ready
        harden(ctx, url, job.log)
        page = ctx.new_page(); page.set_default_timeout(30000)
        errs = []; page.on("pageerror", lambda e: errs.append(str(e)[:200]))
        job.progress(0.05, "Opening %s…" % url)
        try:
            open_page(page, url, job.log, timeout=120)
        except Exception as e:  # noqa: BLE001
            raise DirectorError("Could not open %s: %s" % (url, str(e).splitlines()[0]))
        wait_ready(page, job.log, max_s=240, progress=lambda m: job.msg("Opening the app: " + m))
        wait_idle(page, 12, 0.8, 1.2)
        try:
            t = page.evaluate(CONSENT_JS)
            if t: job.log("dismissed consent banner: %s" % t); time.sleep(0.6)
        except Exception: pass  # noqa: BLE001
        base = page.url
        try:
            cdp = ctx.new_cdp_session(page); ts = []
            cdp.send("Page.captureScreenshot", {"format": "jpeg", "quality": 90, "optimizeForSpeed": True})      # warm-up
            for _ in range(5):
                tw = time.time(); cdp.send("Page.captureScreenshot", {"format": "jpeg", "quality": 90, "optimizeForSpeed": True}); ts.append(time.time() - tw)
            res["frame_cost"] = round(sorted(ts)[len(ts) // 2], 3)
        except Exception: pass  # noqa: BLE001
        def open_menu():
            if vw >= 992: return False
            try:
                bb = page.evaluate(OPEN_MENU_JS)
                if bb: page.mouse.click(bb["x"], bb["y"]); time.sleep(0.5); wait_idle(page, 3, 0.3, 0.3); return True
            except Exception: pass  # noqa: BLE001
            return False
        if open_menu(): job.log("opened the navigation menu (narrow layout)")
        m0 = page.evaluate(MODEL_JS)
        res["meta"] = m0["meta"]; res["title"] = m0["title"]; res["icons"] = m0["icons"]; res["logo"] = m0["logo"]
        res["brandText"] = m0["brandText"]; res["framework"] = m0["framework"]; res["logoSvg"] = m0.get("logoSvg", "")

        sigs = set()
        def sig(model):
            return json.dumps([[x["text"] for x in model["sections"][:8]], len(model["inputs"]), len(model["outputs"]), round(model["height"] / 40), (model.get("lead") or "")[:80]])

        def add_view(vid, label, kind, reach, model):
            sg = sig(model)
            if sg in sigs and kind != "home":
                job.log("  %s looks like a screen we already have; skipped" % label); return None
            sigs.add(sg)
            thumb = os.path.join(outdir, vid + ".jpg")
            page.screenshot(path=thumb, type="jpeg", quality=82)
            v = {"id": vid, "label": label, "kind": kind, "reach": reach, "thumb": "scout/%s.jpg" % vid,
                 "height": model["height"], "vh": model["vh"], "sections": model["sections"][:12], "inputs": model["inputs"],
                 "buttons": model["buttons"], "outputs": model["outputs"], "tabs": [t["text"] for t in model["tabs"]], "lead": model.get("lead", ""),
                 "colors": model["colors"], "mainBox": model["mainBox"], "colorStats": model.get("colorStats", [])}
            res["views"].append(v); return v

        home = add_view("home", res["title"] or "Home", "home", {"url": urllib.parse.urlparse(base).path or "/"}, m0)
        # ---- tabs
        tabs = [t for t in m0["tabs"] if not t["active"]][:7]
        for i, t in enumerate(tabs):
            job.progress(0.15 + 0.6 * i / max(1, len(tabs)), "Exploring tab “%s”…" % t["text"])
            try:
                bb = page.evaluate(FIND_JS, {"kind": "tab", "text": t["text"]})
                if not bb and open_menu(): bb = page.evaluate(FIND_JS, {"kind": "tab", "text": t["text"]})
                if not bb: continue
                page.mouse.click(bb["x"], bb["y"])
                page.mouse.move(5, vh - 5)
                time.sleep(0.3); wait_idle(page, 10, 0.6, 0.8)
                if urllib.parse.urlparse(page.url).path != urllib.parse.urlparse(base).path:
                    # the "tab" was a page link: treat it as a page
                    m = page.evaluate(MODEL_JS)
                    add_view("v%d" % (i + 1), t["text"], "page", {"url": urllib.parse.urlparse(page.url).path}, m)
                    open_page(page, base, job.log); wait_ready(page, job.log, max_s=90); wait_idle(page, 8, 0.6, 0.6)
                    continue
                page.evaluate("window.scrollTo(0,0)")
                m = page.evaluate(MODEL_JS)
                add_view("v%d" % (i + 1), t["text"], "tab", {"url": home["reach"]["url"], "tab": t["text"]}, m)
            except Exception as e:  # noqa: BLE001
                job.warn("tab %s: %s" % (t["text"], str(e).splitlines()[0][:100]))
        # ---- internal pages (multi-page websites), when there are few tabs
        if len(res["views"]) < 4:
            links = [l for l in m0["links"] if l["text"] not in {t["text"] for t in m0["tabs"]} or True][:6]
            for i, l in enumerate(links):
                if len(res["views"]) >= 7: break
                job.progress(0.75 + 0.15 * i / max(1, len(links)), "Visiting %s…" % l["path"])
                try:
                    open_page(page, urllib.parse.urljoin(base, l["path"]), job.log, timeout=45)
                    wait_ready(page, job.log, max_s=60); wait_idle(page, 8, 0.6, 0.8)
                    m = page.evaluate(MODEL_JS)
                    if any(v["reach"].get("url") == l["path"] for v in res["views"]): continue
                    add_view("p%d" % (i + 1), l["text"], "page", {"url": l["path"]}, m)
                except Exception as e:  # noqa: BLE001
                    job.warn("page %s: %s" % (l["path"], str(e).splitlines()[0][:100]))
        # ---- colours + theme
        shots = [os.path.join(P.root, v["thumb"]) for v in res["views"]]
        stats = {}
        for v in res["views"]:
            for c, w in v.get("colorStats") or []: stats[c] = stats.get(c, 0) + w
        pal = pick_palette({"accents": sum([v["colors"]["accents"] for v in res["views"]], []), "stats": sorted(stats.items(), key=lambda x: -x[1])[:80]}, shots)
        bg = parse_rgb(m0["colors"]["bg"]) or (255, 255, 255)
        res["colors"] = {"palette": pal, "bg": hexc(bg), "dark": luminance(bg) < 0.4}
        res["errors"] = errs[:10]
        b.close()
    # ---- a favicon / logo we can use on the end card
    res["logo_file"] = fetch_logo(P, res, job)
    P.put("scout", res)
    return res


def fetch_logo(P, res, job):
    import urllib.request
    cands = []
    if res.get("logo"): cands.append(res["logo"])
    elif res.get("logoSvg"):
        dst = P.p("scout", "logo.svg"); open(dst, "w", encoding="utf-8").write(res["logoSvg"]); return "scout/logo.svg"
    icons = sorted(res.get("icons") or [], key=lambda i: -int((re.findall(r"\d+", i.get("sizes") or "0") or ["0"])[0]))
    cands += [i["href"] for i in icons if "apple-touch" in i.get("rel", "")] + [i["href"] for i in icons]
    for u in cands:
        if not u or u.startswith("data:") and "svg" not in u: continue
        try:
            ext = ".svg" if (".svg" in u.lower() or "svg" in u[:30]) else ".png"
            dst = P.p("scout", "logo" + ext)
            if u.startswith("data:"):
                import base64
                head, data = u.split(",", 1)
                raw = base64.b64decode(data) if ";base64" in head else urllib.parse.unquote(data).encode()
            else:
                with urllib.request.urlopen(urllib.request.Request(u, headers={"User-Agent": "Mozilla/5.0 DirectoR"}), timeout=8) as r:
                    raw = r.read(3_000_000)
            if len(raw) < 100: continue
            if ext == ".png":
                from PIL import Image
                import io
                im = Image.open(io.BytesIO(raw))
                if max(im.size) < 32: continue
                im.convert("RGBA").save(dst)
            else:
                open(dst, "wb").write(raw)
            return "scout/logo" + ext
        except Exception:  # noqa: BLE001
            continue
    return ""
