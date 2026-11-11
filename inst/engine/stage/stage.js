/* DirectoR stage engine: a small deterministic motion-graphics runtime.
   Everything on screen is a pure function of t (seconds). Stage.render(t) is called once per
   output frame by render.py (which screenshots the page), and in real time by the live preview.
   Scenes are groups with transitions between them; scene builders live in film.js.            */
(function () {
  'use strict';
  var E = {
    lin: function (x) { return x; },
    in: function (x) { return x * x * x; },
    out: function (x) { return 1 - Math.pow(1 - x, 3); },
    out5: function (x) { return 1 - Math.pow(1 - x, 5); },
    io: function (x) { return x < .5 ? 4 * x * x * x : 1 - Math.pow(-2 * x + 2, 3) / 2; },
    io2: function (x) { return x < .5 ? 2 * x * x : 1 - Math.pow(-2 * x + 2, 2) / 2; },
    expo: function (x) { return x >= 1 ? 1 : 1 - Math.pow(2, -10 * x); },
    back: function (x) { var c1 = 1.70158, c3 = c1 + 1; return 1 + c3 * Math.pow(x - 1, 3) + c1 * Math.pow(x - 1, 2); },
    spring: function (x) { return x >= 1 ? 1 : 1 - Math.exp(-6.5 * x) * Math.cos(11 * x); },
    smooth: function (x) { return x * x * (3 - 2 * x); }
  };
  var clamp = function (x, a, b) { return Math.max(a, Math.min(b, x)); };
  var lerp = function (a, b, p) { return a + (b - a) * p; };
  var prog = function (t, a, b, ease) { var p = clamp((t - a) / Math.max(1e-6, b - a), 0, 1); return ease ? (E[ease] || ease)(p) : p; };
  /* keyframes: [[t, value(s), ease-into-this-key], ...]; values are numbers or objects of numbers */
  function kf(t, keys) {
    if (t <= keys[0][0]) return keys[0][1];
    for (var i = 1; i < keys.length; i++) {
      if (t <= keys[i][0]) {
        var a = keys[i - 1], b = keys[i], p = (t - a[0]) / Math.max(1e-6, b[0] - a[0]);
        p = (E[b[2] || 'io'] || b[2])(p);
        if (typeof a[1] === 'number') return lerp(a[1], b[1], p);
        var o = {}, k;
        for (k in b[1]) o[k] = lerp(a[1][k] !== undefined ? a[1][k] : b[1][k], b[1][k], p);
        for (k in a[1]) if (o[k] === undefined) o[k] = a[1][k];
        return o;
      }
    }
    return keys[keys.length - 1][1];
  }
  function el(tag, cls, html, parent) { var e = document.createElement(tag); if (cls) e.className = cls; if (html != null) e.innerHTML = html; if (parent) parent.appendChild(e); return e; }
  function hexA(hex, a) { var h = (hex || '#888').replace('#', ''); if (h.length === 3) h = h.replace(/./g, '$&$&');
    return 'rgba(' + parseInt(h.substr(0, 2), 16) + ',' + parseInt(h.substr(2, 2), 16) + ',' + parseInt(h.substr(4, 2), 16) + ',' + a + ')'; }
  function noise(t, seed) { return Math.sin(t * 1.3 + seed) * 0.6 + Math.sin(t * 0.71 + seed * 2.1) * 0.4; }

  var TL, root, W, H, U, PORTRAIT, SQUARE, scenes = [], bgUpdate = null, flashEl, wipeEl, grainEl, capEl, punches = [], flashes = [], pendingImgs = [];
  var PREVIEW = false, PROXY = false;

  /* ------------------------------------------------------------ theme */
  function applyTheme(th) {
    var dark = th.mode === 'dark' || th.mode === 'brand';
    var s = root.style;
    s.setProperty('--c1', th.c1); s.setProperty('--c2', th.c2); s.setProperty('--c3', th.c3);
    s.setProperty('--U', U); s.setProperty('--radius', th.radius == null ? 22 : th.radius);
    var fonts = { Inter: "'Inter'", System: "-apple-system, 'SF Pro Display', 'Segoe UI', Roboto", Serif: "'Iowan Old Style', 'Palatino Linotype', Georgia, serif", Mono: "'SF Mono', 'JetBrains Mono', Menlo, Consolas, monospace", Rounded: "ui-rounded, 'SF Pro Rounded', 'Nunito', 'Inter'" };
    s.setProperty('--font', fonts[th.font] || fonts.Inter);
    if (th.mode === 'brand') {
      s.setProperty('--bg', 'linear-gradient(135deg,' + th.c1 + ',' + th.c2 + ' 55%,' + th.c3 + ')'); s.setProperty('--fg', '#fff'); s.setProperty('--muted', 'rgba(255,255,255,.72)');
    } else if (dark) {
      s.setProperty('--bg', '#050507'); s.setProperty('--fg', '#f5f5f7'); s.setProperty('--muted', '#8e8e93');
    } else {
      s.setProperty('--bg', '#f5f5f7'); s.setProperty('--fg', '#1d1d1f'); s.setProperty('--muted', '#86868b');
    }
    s.setProperty('--card', dark ? 'rgba(255,255,255,.07)' : '#fff');
    s.setProperty('--edge', dark ? 'rgba(255,255,255,.12)' : 'rgba(0,0,0,.06)');
    s.setProperty('--cardShadow', dark ? '0 30px 80px -30px rgba(0,0,0,.6)' : '0 30px 80px -30px rgba(16,24,64,.28)');
    s.setProperty('--shadowA', dark ? '.55' : '.28');
    s.setProperty('--dot', dark ? 'rgba(255,255,255,.16)' : 'rgba(0,0,0,.13)');
    s.setProperty('--spot', dark ? hexA(th.c2, .35) : hexA(th.c1, .18));
    s.setProperty('--glowA', hexA(th.c2, .5));
    root.dataset.mode = th.mode;
  }

  /* ------------------------------------------------------------ background */
  function background(th) {
    var b = el('div', 'bgl', null, root); b.style.zIndex = 0;
    var dark = th.mode !== 'light', kind = th.bg || 'aurora', glows = [];
    if (kind !== 'solid') {
      var a = dark ? [.30, .26, .20] : [.24, .20, .15];
      if (th.mode === 'brand') a = [.35, .3, .3];
      var specs = [[th.c1, .13, .14, 1.1, 0], [th.c2, .86, .23, 1.0, 2], [th.c3, .52, .97, 1.2, 4]];
      if (kind === 'mesh') specs.push([th.c1, .9, .85, .9, 6], [th.c3, .1, .7, .8, 8]);
      specs.forEach(function (g, i) {
        var d = el('div', 'glow', null, b), size = Math.max(W, H) * 0.75 * g[3];
        d.style.width = size + 'px'; d.style.height = size + 'px';
        d.style.background = 'radial-gradient(circle, ' + (th.mode === 'brand' ? 'rgba(255,255,255,' + (.18 - i * .03) + ')' : hexA(g[0], a[i % 3] * (kind === 'mesh' ? 1.35 : 1))) + ' 0%, transparent 62%)';
        glows.push({ e: d, x: g[1] * W, y: g[2] * H, s: size, ph: g[4] });
      });
    }
    if (kind === 'grid') el('div', 'gridpat', null, b);
    if (kind === 'spotlight') el('div', 'spot', null, b);
    bgUpdate = function (t) {
      glows.forEach(function (g) {
        var x = g.x + Math.sin(t * .21 + g.ph) * 160 * U, y = g.y + Math.cos(t * .17 + g.ph) * 120 * U;
        g.e.style.transform = 'translate(' + (x - g.s / 2).toFixed(1) + 'px,' + (y - g.s / 2).toFixed(1) + 'px)';
      });
    };
  }

  /* ------------------------------------------------------------ transitions */
  var OUT_ON_TOP = { zoom: 1, blur: 0, fade: 0 };
  function fx() { return { o: 1, tf: '', fl: '', clip: '' }; }
  var TR = {
    cut: { i: function () {}, o: function () {} },
    fade: { i: function (f, p) { f.o *= p; }, o: function (f, p) { f.o *= 1 - p; } },
    blur: { i: function (f, p) { var q = E.out(p); f.o *= q; f.fl += ' blur(' + ((1 - q) * 26 * U).toFixed(1) + 'px)'; f.tf += ' scale(' + lerp(1.05, 1, q).toFixed(4) + ')'; },
            o: function (f, p) { f.o *= 1 - E.io(p); f.fl += ' blur(' + (E.in(p) * 26 * U).toFixed(1) + 'px)'; f.tf += ' scale(' + lerp(1, 1.03, p).toFixed(4) + ')'; } },
    zoom: { i: function (f, p) { var q = E.out5(p); f.o *= clamp(p * 2.2, 0, 1); f.tf += ' scale(' + lerp(.86, 1, q).toFixed(4) + ')'; f.fl += ' blur(' + ((1 - q) * 8 * U).toFixed(1) + 'px)'; },
            o: function (f, p) { var q = E.in(p); f.o *= 1 - clamp((p - .25) / .75, 0, 1); f.tf += ' scale(' + lerp(1, 1.5, q).toFixed(4) + ')'; f.fl += ' blur(' + (q * 14 * U).toFixed(1) + 'px)'; } },
    slide: { i: function (f, p) { f.tf += ' translateX(' + ((1 - E.io(p)) * W).toFixed(1) + 'px)'; },
             o: function (f, p) { var q = E.io(p); f.tf += ' translateX(' + (-q * W * .3).toFixed(1) + 'px) scale(' + lerp(1, .94, q).toFixed(4) + ')'; f.o *= 1 - q * .6; } },
    push: { i: function (f, p) { f.tf += ' translateX(' + ((1 - E.io(p)) * W).toFixed(1) + 'px)'; }, o: function (f, p) { f.tf += ' translateX(' + (-E.io(p) * W).toFixed(1) + 'px)'; } },
    whip: { i: function (f, p) { f.tf += ' translateX(' + ((1 - E.io(p)) * W * 1.05).toFixed(1) + 'px)'; f.fl += ' blur(' + (Math.sin(Math.PI * p) * 30 * U).toFixed(1) + 'px)'; },
            o: function (f, p) { f.tf += ' translateX(' + (-E.io(p) * W * 1.05).toFixed(1) + 'px)'; f.fl += ' blur(' + (Math.sin(Math.PI * p) * 30 * U).toFixed(1) + 'px)'; } },
    rise: { i: function (f, p) { var q = E.out5(p); f.tf += ' translateY(' + ((1 - q) * H * .22).toFixed(1) + 'px)'; f.o *= clamp(p * 1.6, 0, 1); },
            o: function (f, p) { var q = E.io(p); f.tf += ' translateY(' + (-q * H * .08).toFixed(1) + 'px)'; f.o *= 1 - q; } },
    flash: { i: function (f, p) { f.o *= p >= .5 ? 1 : 0; }, o: function (f, p) { f.o *= p < .5 ? 1 : 0; } },
    wipe: { i: function (f, p) { var q = E.io(p); f.clip = 'inset(0 0 0 ' + ((1 - q) * 100).toFixed(2) + '%)'; }, o: function (f, p) { f.tf += ' translateX(' + (-E.io(p) * W * .12).toFixed(1) + 'px)'; } },
    iris: { i: function (f, p) { var q = E.io(p); f.clip = 'circle(' + (q * 75).toFixed(2) + '% at 50% 50%)'; }, o: function (f, p) { f.tf += ' scale(' + lerp(1, 1.06, p).toFixed(4) + ')'; } },
    flip: { i: function (f, p) { var q = E.out(clamp((p - .5) * 2, 0, 1)); f.o *= p >= .5 ? 1 : 0; f.tf += ' perspective(' + (2400 * U) + 'px) rotateY(' + ((1 - q) * -80).toFixed(2) + 'deg)'; },
            o: function (f, p) { var q = E.in(clamp(p * 2, 0, 1)); f.o *= p < .5 ? 1 : 0; f.tf += ' perspective(' + (2400 * U) + 'px) rotateY(' + (q * 80).toFixed(2) + 'deg)'; } }
  };

  /* ------------------------------------------------------------ global punches / flashes */
  function punch(t, amt, dur) { punches.push([t, amt || .025, dur || .35]); }
  function flash(t, dur, color, peak) { flashes.push([t, dur || .3, color || '#fff', peak == null ? .85 : peak]); }

  /* ------------------------------------------------------------ images: render mode waits for decode, preview swaps when loaded */
  var cache = {};
  function setImg(img, src) {
    if (img.__want === src) return;
    img.__want = src;
    if (!PREVIEW) { img.src = src; pendingImgs.push(img); return; }
    if (cache[src] === true) { img.src = src; return; }
    if (img.__loading) return;
    var load = function (s) {
      img.__loading = true;
      var im = new Image(); im.decoding = 'async';
      im.onload = im.onerror = function () { cache[s] = true; img.__loading = false; img.src = s; if (img.__want !== s) load(img.__want); };
      im.src = s;
    };
    load(src);
  }

  /* ------------------------------------------------------------ init + render */
  function init(tl, opts) {
    TL = tl; opts = opts || {};
    PREVIEW = !!(opts.preview || tl.preview);
    PROXY = PREVIEW || (opts.scale && opts.scale <= 0.55);      // previews and drafts use the half-size proxy frames
    W = tl.W; H = tl.H; U = Math.min(W, H) / 1080; PORTRAIT = H > W * 1.1; SQUARE = !PORTRAIT && W < H * 1.2;
    root = document.getElementById('stage');
    root.innerHTML = ''; root.style.width = W + 'px'; root.style.height = H + 'px';
    if (opts.scale && opts.scale !== 1 && !document.getElementById('scaler')) {   // draft renders: same layout, fewer pixels
      var sc0 = document.createElement('div'); sc0.id = 'scaler'; sc0.style.cssText = 'position:absolute;left:0;top:0;transform-origin:0 0;transform:scale(' + opts.scale + ')';
      root.parentNode.insertBefore(sc0, root); sc0.appendChild(root);
    }
    scenes = []; punches = []; flashes = [];
    applyTheme(tl.theme);
    background(tl.theme);
    var ctx = { W: W, H: H, U: U, PORTRAIT: PORTRAIT, SQUARE: SQUARE, TL: tl, theme: tl.theme, brand: tl.brand, preview: PREVIEW };
    tl.scenes.forEach(function (sc, i) {
      var g = el('div', 'scene', null, root); g.dataset.id = sc.id; g.style.zIndex = 10 + i;   // visible while building: layout needs real measurements
      var nxt0 = tl.scenes[i + 1]; sc.tout = nxt0 && nxt0.tin ? nxt0.tin.type : 'cut';
      var build = (window.SCENES || {})[sc.type];
      var upd = null;
      try { upd = build ? build(sc, g, ctx) : null; } catch (err) { console.error('scene ' + sc.id + ' (' + sc.type + '): ' + err); }
      g.classList.add('hidden');
      var nxt = tl.scenes[i + 1];
      scenes.push({ sc: sc, g: g, upd: upd, i: i, tin: sc.tin || { type: 'cut', dur: 0 }, tout: nxt ? (nxt.tin || { type: 'cut', dur: 0 }) : { type: 'cut', dur: 0 } });
      if (sc.tin && sc.tin.type === 'flash' && i > 0) flash(sc.t0, .32, '#fff', tl.theme.mode === 'light' ? .9 : .8);
    });
    (tl.hits || []).forEach(function (h) { if (h.kind === 'hit') punch(h.t, .02, .28); if (h.kind === 'end') punch(h.t, .035, .6); });
    wipeEl = el('div', 'wipebar', null, root); wipeEl.style.width = (90 * U) + 'px';
    flashEl = el('div', 'flash', null, root);
    grainEl = null;
    if (tl.theme.grain && PREVIEW) grainEl = el('div', 'grain', null, root);   // final renders add grain in the encoder (far cheaper)
    capEl = el('div', 'caps hidden', null, root);
    capEl.style.fontSize = (PORTRAIT ? 54 : 40) * U + 'px'; capEl.style.bottom = (PORTRAIT ? H * .08 : 46 * U) + 'px';
    if (tl.capstyle === 'bold') { capEl.classList.add('bold'); capEl.style.fontSize = (PORTRAIT ? 74 : 56) * U + 'px'; capEl.style.bottom = PORTRAIT ? (H * .075) + 'px' : (110 * U) + 'px'; }
    window.DURATION = tl.duration;
  }

  var showCaps = false;
  function captions(t) {
    if (!showCaps || !TL.captions) { capEl.classList.add('hidden'); return; }
    var c = null; TL.captions.forEach(function (x) { if (t >= x.start - .05 && t < x.end + .25) c = x; });
    if (!c) { capEl.classList.add('hidden'); return; }
    capEl.classList.remove('hidden');
    if (TL.capstyle === 'bold') {
      // 3-word chunks, current word highlighted
      var k = 0; for (var i = 0; i < c.wt.length; i++) if (t >= c.wt[i]) k = i;
      var a = Math.floor(k / 3) * 3;
      capEl.innerHTML = '<span>' + c.words.slice(a, a + 3).map(function (w, j) { return a + j === k ? '<b>' + w + '</b>' : w; }).join(' ') + '</span>';
    } else capEl.innerHTML = '<span>' + c.text + '</span>';
  }

  function render(t) {
    pendingImgs = [];
    if (bgUpdate) bgUpdate(t);
    var wipeX = null;
    scenes.forEach(function (S) {
      var sc = S.sc, a = sc.t0 - S.tin.dur / 2, b = sc.t1 + S.tout.dur / 2;
      var on = t >= a && t < b;
      if (!on) { if (!S.hidden) { S.g.classList.add('hidden'); S.hidden = true; } return; }
      if (S.hidden !== false) { S.g.classList.remove('hidden'); S.hidden = false; }
      var f = fx(), z = 10 + S.i;
      if (S.tin.dur > 0 && t < sc.t0 + S.tin.dur / 2) {
        var p = clamp((t - a) / S.tin.dur, 0, 1);
        (TR[S.tin.type] || TR.fade).i(f, p);
        if (S.tin.type === 'wipe') wipeX = (1 - E.io(p)) * W;
      }
      if (S.tout.dur > 0 && t > sc.t1 - S.tout.dur / 2) {
        var q = clamp((t - (sc.t1 - S.tout.dur / 2)) / S.tout.dur, 0, 1);
        (TR[S.tout.type] || TR.fade).o(f, q);
        if (OUT_ON_TOP[S.tout.type]) z = 100 + S.i;
      }
      var g = S.g.style;
      g.opacity = f.o.toFixed(3); g.transform = f.tf; g.filter = f.fl || 'none'; g.clipPath = f.clip || 'none'; g.zIndex = z;
      if (S.upd) { try { S.upd(t - sc.t0, t); } catch (err) { if (!S.err) { console.error('scene ' + sc.id + ': ' + err); S.err = 1; } } }
    });
    if (wipeX !== null) { wipeEl.style.opacity = 1; wipeEl.style.transform = 'translateX(' + (wipeX - 45 * U).toFixed(1) + 'px) skewX(-8deg)'; } else wipeEl.style.opacity = 0;
    var s = 1;
    punches.forEach(function (p) { if (t >= p[0] && t < p[0] + p[2]) s += p[1] * Math.pow(1 - (t - p[0]) / p[2], 2); });
    var fo = 0, fc = '#fff';
    flashes.forEach(function (f) { if (t >= f[0] - f[1] * .35 && t < f[0] + f[1]) { var d = t - f[0]; var v = d < 0 ? 1 + d / (f[1] * .35) : 1 - d / f[1]; if (f[3] * v > fo) { fo = f[3] * v; fc = f[2]; } } });
    flashEl.style.opacity = fo.toFixed(3); flashEl.style.background = fc;
    var sceneHost = root; sceneHost.style.transform = (root.__base || '') + (s !== 1 ? ' scale(' + s.toFixed(4) + ')' : '');
    if (grainEl) grainEl.style.transform = 'translate(' + ((Math.floor(t * 24) * 37) % 97 - 48) + 'px,' + ((Math.floor(t * 24) * 61) % 89 - 44) + 'px)';
    captions(t);
    if (PREVIEW) return Promise.resolve(true);
    var imgs = pendingImgs.slice();
    return Promise.all(imgs.map(function (im) { return im.complete && im.naturalWidth ? Promise.resolve() : (im.decode ? im.decode().catch(function () {}) : Promise.resolve()); }))
      .then(function () { return document.fonts.ready; }).then(function () { return true; });
  }

  window.Stage = { E: E, kf: kf, prog: prog, clamp: clamp, lerp: lerp, el: el, hexA: hexA, noise: noise, setImg: setImg, punch: punch, flash: flash,
    init: init, render: render, captions: function (on) { showCaps = !!on; }, get W() { return W; }, get H() { return H; }, get U() { return U; },
    get root() { return root; }, get TL() { return TL; }, get preview() { return PREVIEW; }, get proxy() { return PROXY; } };
})();
