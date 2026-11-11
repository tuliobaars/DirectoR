/* DirectoR film: scene builders. Each builder(sc, g, C) fills the scene group g and returns
   update(lt, t) where lt = seconds since the scene's nominal start (negative during the
   incoming transition). All motion is a function of time only.                             */
(function () {
  'use strict';
  var S = window.Stage, E = S.E, kf = S.kf, prog = S.prog, clamp = S.clamp, lerp = S.lerp, el = S.el;
  var SC = window.SCENES = {};
  var CUR = window.CURSORS || {};
  var LOCK = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4"><rect x="5" y="11" width="14" height="10" rx="2.5"/><path d="M8 11V7.5a4 4 0 0 1 8 0V11"/></svg>';
  var ICONS = {
    chart: '<path d="M4 20V10M10 20V4M16 20v-7M22 20H2"/>', bolt: '<path d="M13 2 4 14h7l-1 8 9-12h-7l1-8Z"/>',
    lock: '<rect x="4" y="11" width="16" height="10" rx="2.5"/><path d="M8 11V7a4 4 0 0 1 8 0v4"/>',
    users: '<circle cx="9" cy="8" r="3.5"/><path d="M2.5 20a6.5 6.5 0 0 1 13 0M16 4.5a3.5 3.5 0 0 1 0 7M18.5 20a6.5 6.5 0 0 0-3-5.5"/>',
    globe: '<circle cx="12" cy="12" r="9.5"/><path d="M2.5 12h19M12 2.5c3 3.2 3 15.8 0 19M12 2.5c-3 3.2-3 15.8 0 19"/>',
    layers: '<path d="m12 3 9.5 5-9.5 5-9.5-5L12 3Z"/><path d="m2.5 13 9.5 5 9.5-5"/>', check: '<circle cx="12" cy="12" r="9.5"/><path d="m7.5 12.5 3 3 6-7"/>',
    clock: '<circle cx="12" cy="12" r="9.5"/><path d="M12 6.5V12l3.5 2.5"/>', search: '<circle cx="10.5" cy="10.5" r="7"/><path d="m21 21-5.5-5.5"/>',
    code: '<path d="m8 7-5 5 5 5M16 7l5 5-5 5M14 4l-4 16"/>', download: '<path d="M12 3v12m0 0-5-5m5 5 5-5M4 20h16"/>',
    sparkles: '<path d="M12 3v4M12 17v4M3 12h4M17 12h4M6 6l2.5 2.5M15.5 15.5 18 18M6 18l2.5-2.5M15.5 8.5 18 6"/>',
    map: '<path d="M9 4 3 6.5v13L9 17l6 2.5 6-2.5v-13L15 6.5 9 4Z"/><path d="M9 4v13M15 6.5v13"/>',
    table: '<rect x="3" y="4" width="18" height="16" rx="2"/><path d="M3 10h18M3 15h18M9 4v16"/>',
    target: '<circle cx="12" cy="12" r="9.5"/><circle cx="12" cy="12" r="5.5"/><circle cx="12" cy="12" r="1.5"/>',
    sliders: '<path d="M4 6h10M18 6h2M4 12h4M12 12h8M4 18h12M20 18h0"/><circle cx="16" cy="6" r="2"/><circle cx="10" cy="12" r="2"/><circle cx="18" cy="18" r="2"/>'
  };
  function icon(name) { return '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">' + (ICONS[name] || ICONS.sparkles) + '</svg>'; }
  function esc(s) { return String(s == null ? '' : s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;'); }

  /* ------------------------------------------------------------ markup: *grad* _muted_ ~warm~ | newline */
  function parse(text) {
    var lines = [], cur = [], cls = '', buf = '';
    var flush = function () { if (buf) { cur.push([buf, cls]); buf = ''; } };
    String(text || '').replace(/\s*\|\s*|\n/g, '\u2028').split('').forEach(function (ch) {
      if (ch === '\u2028') { flush(); lines.push(cur); cur = []; return; }
      if (ch === '*' || ch === '_' || ch === '~') { var c = { '*': 'grad', '_': 'muted', '~': 'warm' }[ch]; flush(); cls = cls === c ? '' : c; return; }
      buf += ch;
    });
    flush(); lines.push(cur);
    return lines.filter(function (l) { return l.length; });
  }
  function plain(text) { return String(text || '').replace(/[*_~|]/g, ' ').replace(/\s+/g, ' ').trim(); }

  /* ------------------------------------------------------------ kinetic text */
  function Kin(parent, o) {
    var U = S.U;
    var e = el('div', 'L', null, parent);
    var box = el('div', 'T ' + (o.align === 'left' ? 'left ' : '') + (o.cls || ''), null, e);
    var size = o.size * U;
    box.style.fontSize = size + 'px'; box.style.fontWeight = o.weight || 700; box.style.lineHeight = o.lh || 1.05;
    if (o.ls != null) box.style.letterSpacing = o.ls + 'em';
    if (o.color) box.style.color = o.color;
    if (o.align === 'left') { box.style.left = (o.x || 0) + 'px'; box.style.right = 'auto'; box.style.width = (o.maxW || S.W * .5) + 'px'; box.style.padding = '0'; }
    else if (o.maxW) { box.style.left = ((S.W - o.maxW) / 2) + 'px'; box.style.right = 'auto'; box.style.width = o.maxW + 'px'; box.style.padding = '0'; }
    var words = [];
    if (o.step) {
      var ln0 = null;
    }
    parse(o.text).forEach(function (line, li) {
      var ln = el('span', 'ln', null, box);
      if (li === 0 && o.step) { var sn = el('span', 'w stepnum', String(o.step), ln); words.push({ el: sn, line: 0 }); }
      line.forEach(function (pc) {
        var toks = o.by === 'char' ? pc[0].split('') : pc[0].split(/(\s+)/).filter(function (x) { return x.length; });
        toks.forEach(function (tk) {
          var w = el('span', 'w ' + (pc[1] || ''), esc(tk), ln);
          if (/\S/.test(tk)) words.push({ el: w, line: li });
        });
      });
    });
    // fit: shrink until the block fits maxW x maxH
    var maxW = o.maxW || S.W * .88, maxH = o.maxH || S.H * .6;
    for (var k = 0; k < 24; k++) {
      var wide = 0; box.querySelectorAll('.ln').forEach(function (l) { wide = Math.max(wide, l.scrollWidth); });
      if (box.offsetHeight <= maxH && wide <= maxW + 2) break;
      size *= 0.93; box.style.fontSize = size + 'px';
    }
    var y = o.y == null ? S.H / 2 : o.y;
    box.style.top = y + 'px'; box.style.transform = o.anchor === 'top' ? '' : 'translateY(-50%)';
    var stag = o.stagger == null ? .07 : o.stagger, dur = o.dur || .6, anim = o.anim || 'rise';
    var times = o.times;
    function update(lt, t) {
      var len = o.len == null ? 1e9 : o.len;
      words.forEach(function (w, i) {
        var st = times ? times[Math.min(i, times.length - 1)] - o.t0 : (o.delay || 0) + i * stag + (o.lineGap || 0) * w.line;
        var p = clamp((lt - st) / dur, 0, 1), q, tr = '', op = 1, bl = 0;
        if (anim === 'rise') { q = E.out5(p); tr = 'translateY(' + ((1 - q) * .55).toFixed(3) + 'em)'; op = E.out(p); bl = (1 - E.out(p)) * 14 * U; }
        else if (anim === 'pop') { q = E.back(p); tr = 'scale(' + lerp(.4, 1, q).toFixed(3) + ')'; op = clamp(p * 3, 0, 1); }
        else if (anim === 'slam') { q = E.out5(p); tr = 'scale(' + lerp(1.9, 1, q).toFixed(3) + ')'; op = clamp(p * 4, 0, 1); bl = (1 - q) * 18 * U; }
        else if (anim === 'blur') { q = E.out(p); op = q; bl = (1 - q) * 24 * U; tr = 'scale(' + lerp(1.08, 1, q).toFixed(4) + ')'; }
        else if (anim === 'type') { op = lt >= st ? 1 : 0; }
        else if (anim === 'drop') { q = E.spring(p); tr = 'translateY(' + ((1 - q) * -.8).toFixed(3) + 'em)'; op = clamp(p * 3, 0, 1); }
        if (o.out && o.out !== 'none') {
          var od = o.outDur || .3, ot = len - od, po = clamp((lt - ot) / od, 0, 1);
          if (po > 0) {
            if (o.out === 'up') { tr += ' translateY(' + (-E.in(po) * .4).toFixed(3) + 'em)'; op *= 1 - E.in(po); }
            else if (o.out === 'scale') { tr += ' scale(' + lerp(1, 1.25, E.in(po)).toFixed(3) + ')'; op *= 1 - po; bl += po * 16 * U; }
            else op *= 1 - po;
          }
        }
        w.el.style.transform = tr; w.el.style.opacity = op.toFixed(3); w.el.style.filter = bl > .3 ? 'blur(' + bl.toFixed(1) + 'px)' : 'none';
      });
      if (o.boxMove) box.style.transform = (o.anchor === 'top' ? '' : 'translateY(-50%) ') + o.boxMove(lt);
    }
    return { el: e, box: box, update: update, height: function () { return box.offsetHeight; }, size: function () { return size; } };
  }

  /* ------------------------------------------------------------ footage: source + camera */
  function pad5(n) { return String(n).padStart(5, '0'); }
  function Source(info, thumb) {
    // info: {dir, frames, fps, vw, vh, markers, still, proxy}
    var ok = info && (info.frames > 0 || info.still);
    return {
      ok: ok, info: info, ar: ok ? info.vw / info.vh : 16 / 9, fps: ok ? info.fps : 60, n: ok ? info.frames : 1,
      src: function (tau) {
        if (!ok) return thumb || '';
        if (info.still) return info.dir + 'still.jpg';
        var fi = clamp(Math.floor(tau * info.fps + 1e-6), 0, info.frames - 1);
        if (S.proxy && info.proxy) { fi -= fi % 2; return info.dir + 'proxy/f' + pad5(fi) + '.jpg'; }
        return info.dir + 'f' + pad5(fi) + '.jpg';
      }
    };
  }

  /* camera paths in source time tau: {s, x, y} (zoom, focus point 0..1) */
  var camCache = {};
  function cameraFor(shotId, src, mode, focus, amt) {
    var info = src.info;
    var fc = focus ? [focus[0] + focus[2] / 2, focus[1] + focus[3] / 2] : [.5, .45];
    fc = [clamp(fc[0], .2, .8), clamp(fc[1], .2, .8)];
    if (!src.ok || info.still || mode === 'static') {
      return function (tau, lt, dur) { return mode === 'static' ? { s: 1, x: .5, y: .5 } : { s: 1 + .07 * clamp(lt / Math.max(1, dur), 0, 1), x: fc[0], y: fc[1] }; };
    }
    if (mode === 'push') return function (tau, lt, dur) { var p = E.io(clamp(lt / Math.max(1, dur), 0, 1)); return { s: lerp(1, 1.14, p), x: lerp(.5, fc[0], p), y: lerp(.5, fc[1], p) }; };
    if (mode === 'pan') return function () { return { s: 1.04, x: .5, y: .5 }; };
    var key = shotId + ':' + mode + ':' + amt;
    if (!camCache[key]) {
      var track = CUR[shotId] || [], n = info.frames, fps = info.fps, dt = 1 / fps;
      var clicks = []; for (var k in (info.markers || {})) if (/^click/.test(k) && k !== 'click_nav') clicks.push(info.markers[k] / fps);
      var xs = new Float32Array(n), ys = new Float32Array(n), zs = new Float32Array(n);
      var x = fc[0], y = fc[1], vx = 0, vy = 0, z = 1, vz = 0, w = 3.2, wz = 2.6;
      for (var i = 0; i < n; i++) {
        var tau = i / fps, c = track[i];
        var tx = fc[0], ty = fc[1];
        if (c && c[2] > .5) { tx = c[0]; ty = c[1]; if (mode === 'follow') { tx = lerp(tx, .5, .45); ty = lerp(ty, .45, .45); } }
        var zt = 1;
        if (mode === 'follow') zt = 1 + amt * .9;
        for (var j = 0; j < clicks.length; j++) {
          var d = tau - clicks[j];
          var b = d < -1.2 ? 0 : d < -.35 ? E.smooth((d + 1.2) / .85) : d < 1.4 ? 1 : d < 2.4 ? 1 - E.smooth((d - 1.4) / 1) : 0;
          zt = Math.max(zt, 1 + amt * b);
        }
        // critically damped springs
        var ax = w * w * (tx - x) - 2 * w * vx, ay = w * w * (ty - y) - 2 * w * vy, az = wz * wz * (zt - z) - 2 * wz * vz;
        vx += ax * dt; vy += ay * dt; vz += az * dt; x += vx * dt; y += vy * dt; z += vz * dt;
        xs[i] = x; ys[i] = y; zs[i] = z;
      }
      camCache[key] = { xs: xs, ys: ys, zs: zs, n: n, fps: fps };
    }
    var cp = camCache[key];
    return function (tau, lt, dur) {
      var i = clamp(Math.floor(tau * cp.fps), 0, cp.n - 1);
      var drift = 1 + .03 * clamp(lt / Math.max(1, dur), 0, 1);
      return { s: cp.zs[i] * drift, x: cp.xs[i], y: cp.ys[i] };
    };
  }

  /* browser window (or full-bleed frame) showing footage */
  function Win(parent, o) {
    var C = o.C, U = S.U, th = C.theme;
    var src = Source(o.info, o.thumb);
    var chrome = o.chrome || th.window || 'macos';
    var full = !!o.full;
    var Wd = o.w, bar = (full || chrome === 'none' || chrome === 'glass' || chrome === 'phone') ? 0 : Math.round(44 * U * (Wd / (1560 * U)));
    bar = bar ? Math.max(28 * U, Math.min(52 * U, bar)) : 0;
    var pad = chrome === 'glass' ? 10 * U : chrome === 'phone' ? 16 * U : 0;
    var Hd = o.h || Math.round((Wd - 2 * pad) / src.ar + bar + 2 * pad);
    var e = el('div', 'L', null, parent);
    e.style.perspective = (2400 * U) + 'px';
    var win = el('div', 'win ' + (full ? 'full ' : '') + (chrome === 'minimal' ? 'minimal ' : '') + (chrome === 'glass' ? 'glass ' : '') + (chrome === 'phone' ? 'phone ' : '') + (th.mode !== 'light' ? 'dark' : ''), null, e);
    if (chrome === 'none' && !full) win.style.borderRadius = (th.radius * .8 * U) + 'px';
    win.style.width = Wd + 'px'; win.style.height = Hd + 'px';
    win.style.marginLeft = (-Wd / 2) + 'px'; win.style.marginTop = (-Hd / 2) + 'px';
    if (bar) {
      var b = el('div', 'bar', '<i></i><i></i><i></i><div class="url">' + LOCK + '<b>' + esc(C.brand.url_display || '') + '</b></div>', win);
      b.style.height = bar + 'px';
    }
    if (chrome === 'phone') el('div', 'notch', null, win);
    var view = el('div', 'view', null, win);
    view.style.top = (bar + pad) + 'px'; view.style.left = pad + 'px'; view.style.right = pad + 'px'; view.style.bottom = pad + 'px';
    var VW = Wd - 2 * pad, VH = Hd - bar - 2 * pad;
    var img = el('img', null, null, view); img.decoding = 'sync';
    // displayed image size (cover)
    var iw, ih; if (src.ar > VW / VH) { ih = VH; iw = VH * src.ar; } else { iw = VW; ih = VW / src.ar; }
    img.style.width = iw + 'px'; img.style.height = ih + 'px';
    var sheen = chrome !== 'none' && !full ? el('div', 'sheen', null, win) : null;
    var cam0 = cameraFor(o.shot, src, o.camera || 'auto', o.focus, o.amt == null ? .45 : o.amt), base = o.base || 1;
    var cam = base === 1 ? cam0 : function (tau, lt, dur) { var c = cam0(tau, lt, dur); return { s: c.s * base, x: c.x, y: c.y }; };
    var clip = o.clip || { from: 0, speed: 1 };
    return {
      el: e, win: win, w: Wd, h: Hd, src: src,
      update: function (lt, dur, pose) {
        var tau = (clip.from || 0) + Math.max(0, lt) * (clip.speed || 1);
        S.setImg(img, src.src(tau));
        var c = cam(tau, lt, dur);
        var s = Math.max(1, c.s), fx = c.x, fy = c.y;
        var tx = clamp(VW / 2 - fx * iw * s, VW - iw * s, 0), ty = clamp(VH / 2 - fy * ih * s, VH - ih * s, 0);
        img.style.transform = 'translate(' + tx.toFixed(2) + 'px,' + ty.toFixed(2) + 'px) scale(' + s.toFixed(4) + ')';
        var p = pose || {};
        win.style.transform = 'translate3d(' + (p.x || 0).toFixed(1) + 'px,' + (p.y || 0).toFixed(1) + 'px,' + (p.z || 0).toFixed(1) + 'px) rotateX(' + (p.rx || 0).toFixed(2) + 'deg) rotateY(' + (p.ry || 0).toFixed(2) + 'deg) rotateZ(' + (p.rz || 0).toFixed(2) + 'deg) scale(' + (p.s == null ? 1 : p.s).toFixed(4) + ')';
        e.style.opacity = p.o == null ? 1 : p.o;
        if (sheen) { var sp = clamp((lt - .15) / 1.1, 0, 1); sheen.style.opacity = sp > 0 && sp < 1 ? Math.sin(sp * Math.PI) * .9 : 0; sheen.style.transform = 'translateX(' + lerp(-60, 60, sp) + '%)'; }
      }
    };
  }

  function sceneBg(sc, g, C) {
    if (!sc.bg) return;
    var b = el('div', 'L', null, g);
    var th = C.theme;
    if (sc.bg === 'dark') b.style.background = 'radial-gradient(ellipse 80% 70% at 50% 40%, ' + S.hexA(th.c2, .22) + ', transparent 70%), #050507';
    else if (sc.bg === 'light') b.style.background = '#f5f5f7';
    else if (sc.bg === 'brand') b.style.background = 'linear-gradient(135deg,' + th.c1 + ',' + th.c2 + ' 55%,' + th.c3 + ')';
    if (sc.bg === 'dark' || sc.bg === 'brand') g.style.color = '#f5f5f7';
  }

  /* ------------------------------------------------------------ scenes */
  SC.hook = function (sc, g, C) {
    sceneBg(sc, g, C);
    var n = plain(sc.text).split(' ').length;
    var size = C.PORTRAIT ? (n <= 3 ? 190 : 150) : (n <= 3 ? 168 : n <= 6 ? 128 : 100);
    var k = Kin(g, { text: sc.text, size: size, weight: 750, lh: 1.02, ls: -.045, t0: sc.t0, len: sc.dur, times: sc.times, anim: sc.anim || 'rise', dur: sc.anim === 'slam' ? .32 : .65,
                     out: (sc.tout === 'cut' ? 'scale' : 'none'), outDur: .22, maxW: C.W * .86, maxH: C.H * .62, cls: sc.bg === 'dark' ? 'on-dark' : '' });
    var sub = sc.sub ? Kin(g, { text: sc.sub, size: 40, weight: 550, cls: 'muted', y: C.H / 2 + k.height() / 2 + 70 * C.U, t0: sc.t0, delay: .5, stagger: .03, anim: 'blur', maxW: C.W * .7 }) : null;
    return function (lt) { k.update(lt); if (sub) sub.update(lt); k.box.style.transform = 'translateY(-50%) scale(' + lerp(1, 1.035, clamp(lt / sc.dur, 0, 1)).toFixed(4) + ')'; };
  };

  function logoEl(parent, C, size) {
    var lg = el('div', 'logo', null, parent);
    lg.style.width = size + 'px'; lg.style.height = size + 'px';
    if (C.brand.logo) { lg.classList.add('img'); var im = el('img', null, null, lg); im.src = C.brand.logo; S.setImg(im, C.brand.logo); }
    else {
      lg.classList.add('mono');
      var nm = (C.brand.name || 'A').replace(/[^A-Za-z0-9 ]/g, '').trim(), ini = nm.split(/\s+/).length > 1 ? nm.split(/\s+/).map(function (w) { return w[0]; }).join('').slice(0, 2) : nm.slice(0, 1);
      lg.innerHTML = '<span style="font-size:' + (size * .48) + 'px;line-height:1">' + esc(ini.toUpperCase()) + '</span><div class="shine"></div>';
    }
    return lg;
  }

  SC.title = function (sc, g, C) {
    sceneBg(sc, g, C);
    var U = C.U, ls = (C.PORTRAIT ? 200 : 170) * U;
    var lg = logoEl(g, C, ls);
    var cy = C.H / 2;
    var name = Kin(g, { text: sc.title || C.brand.name, size: C.PORTRAIT ? 170 : 150, weight: 750, by: 'char', stagger: .035, dur: .55, t0: sc.t0, y: cy + 40 * U, maxW: C.W * .84, maxH: C.H * .3 });
    var tag = sc.tagline ? Kin(g, { text: autoEmph(sc.tagline), size: C.PORTRAIT ? 64 : 56, weight: 650, stagger: .09, dur: .6, delay: .55, t0: sc.t0, y: cy + 40 * U + name.height() / 2 + 70 * U, maxW: C.W * .8, cls: 'fg' }) : null;
    var ly = cy + 40 * U - name.height() / 2 - ls - 40 * U;
    lg.style.left = (C.W / 2 - ls / 2) + 'px'; lg.style.top = ly + 'px';
    var sh = lg.querySelector('.shine');
    return function (lt) {
      var q = prog(lt, 0, .75, 'back');
      lg.style.transform = 'scale(' + (.3 + .7 * q).toFixed(4) + ') rotate(' + ((1 - q) * -22).toFixed(2) + 'deg)';
      lg.style.opacity = clamp(lt * 5, 0, 1);
      if (sh) sh.style.transform = 'translateX(' + lerp(-60, 60, prog(lt, .5, 1.4, 'io')) + '%)';
      name.update(lt); if (tag) tag.update(lt);
    };
  };

  function autoEmph(s) {
    s = String(s || '');
    if (/[*_~]/.test(s)) return s;
    var w = s.trim().split(/\s+/);
    if (w.length < 2) return '*' + s + '*';
    var k = w.length > 4 ? 2 : 1;
    return w.slice(0, w.length - k).join(' ') + ' *' + w.slice(w.length - k).join(' ') + '*';
  }

  SC.shot = function (sc, g, C) {
    sceneBg(sc, g, C);
    var U = C.U, W = C.W, H = C.H, dur = sc.dur;
    var src0 = Source(sc.info, sc.thumb);
    var layout = sc.layout || 'window';
    if (layout === 'split' && (C.PORTRAIT || C.SQUARE)) layout = 'window';
    if (layout === 'phone' && src0.ar > 1) layout = C.PORTRAIT ? 'window' : 'tilt';
    if (layout === 'full' && C.PORTRAIT && src0.ar > 1) layout = 'window';          // desktop footage in a vertical film: keep the whole UI readable
    var hl = sc.headline, cap = sc.caption, step = sc.step;
    var parts = [], win, pose, text = null, sub = null, pill = null;
    var cam = sc.camera || 'auto', amt = .45;
    if (layout === 'full') {
      if (C.PORTRAIT) { cam = cam === 'auto' ? 'follow' : cam; amt = .25; }
      win = Win(g, { C: C, info: sc.info, thumb: sc.thumb, w: W, h: H, full: true, chrome: 'none', shot: sc.shot, camera: cam, focus: sc.focus, clip: sc.clip, amt: amt * .8 });
      win.el.style.zIndex = 1;
      pose = function (lt) { var q = prog(lt, 0, .5, 'out'); return { s: lerp(1.04, 1, q) }; };
      if (hl) {
        var scr = el('div', 'scrim', null, g); scr.style.top = 0; scr.style.height = (H * .34) + 'px'; scr.style.zIndex = 2;
        scr.style.background = 'linear-gradient(180deg, rgba(0,0,0,.55), transparent)';
        text = Kin(g, { text: hl, step: step, size: C.PORTRAIT ? 84 : 68, weight: 700, y: C.PORTRAIT ? H * .13 : 110 * U, t0: sc.t0, maxW: W * .86, maxH: H * .2, color: '#fff' });
        text.el.style.zIndex = 3;
      }
    } else {
      var ww, cx = W / 2, cy = H / 2, tY = 0;
      var wh = null;
      if (C.PORTRAIT) { ww = W * .92; cy = hl ? H * .575 : H * .5; tY = H * .17; if (src0.ar > 1 && layout !== 'phone') wh = H * .52; }
      else if (C.SQUARE) { ww = W * .84; cy = hl ? H * .57 : H * .5; tY = H * .14; }
      else if (layout === 'split') { ww = W * .6; cx = W * .655; tY = H / 2; }
      else { ww = hl ? W * .78 : W * .82; cy = hl ? H / 2 + 62 * U : H / 2; tY = 118 * U; }
      if (layout === 'phone') { ww = Math.min(W * (C.PORTRAIT ? .62 : .3), H * (C.PORTRAIT ? .74 : .8) * src0.ar); if (C.PORTRAIT) { cy = H * .57; tY = H * .1; } }
      win = Win(g, { C: C, info: sc.info, thumb: sc.thumb, w: ww, h: wh, shot: sc.shot, camera: cam, focus: sc.focus, clip: sc.clip, amt: wh ? .3 : amt * .85,
                     chrome: layout === 'phone' ? 'phone' : null });
      // keep the window inside the frame
      var maxH = (C.PORTRAIT ? H * (layout === 'phone' ? .8 : .64) : H * (hl ? .74 : .86));
      var fit = Math.min(1, maxH / win.h);
      win.el.style.left = (cx - W / 2) + 'px'; win.el.style.top = (cy - H / 2) + 'px';
      if (hl && layout !== 'split') text = Kin(g, { text: hl, step: step, size: C.PORTRAIT ? 80 : 72, weight: 700, y: tY, t0: sc.t0, delay: .05, maxW: W * .88, maxH: C.PORTRAIT ? H * .22 : H * .16 });
      if (layout === 'split') {
        text = Kin(g, { text: hl || plain(sc.label || ''), step: step, size: 86, weight: 750, align: 'left', x: W * .06, maxW: W * .28, maxH: H * .5, y: H * .44, t0: sc.t0, anim: 'rise' });
        if (sc.sub || sc.vo) sub = Kin(g, { text: '_' + plain(sc.sub || sc.vo) + '_', size: 30, weight: 500, lh: 1.35, ls: -.01, align: 'left', x: W * .06, maxW: W * .28, maxH: H * .3, y: H * .44 + text.height() / 2 + 30 * U, anchor: 'top', t0: sc.t0, delay: .4, stagger: .012, dur: .5, anim: 'blur' });
      }
      var base = fit;
      if (layout === 'window' || layout === 'split') pose = function (lt) {
        return kf(lt, [[0, { s: base * 1.03, y: 30 * U, o: 0 }], [.6, { s: base, y: 0, o: 1 }, 'out5'], [dur, { s: base * 1.02, y: 0, o: 1 }, 'lin']]); };
      else if (layout === 'tilt') pose = function (lt) {
        return kf(lt, [[0, { s: base * .84, y: 150 * U, rx: 24, o: 1 }], [1.1, { s: base, y: 0, rx: 0 }, 'out5'], [dur, { s: base * 1.04, y: 0, rx: 0 }, 'lin']]); };
      else if (layout === 'float') pose = function (lt) {
        var q = prog(lt, 0, 1.2, 'out5');
        return { s: base * lerp(.9, .97, q) * (1 + .012 * Math.sin(lt * .9)), rx: lerp(18, 9, q) + Math.sin(lt * .7) * 1.5, ry: lerp(-24, -12, q) + Math.sin(lt * .5) * 4, rz: lerp(3, 1.5, q), y: lerp(90 * U, 0, q), x: -lt * 4 * U, o: clamp(lt * 3, 0, 1) }; };
      else if (layout === 'phone') pose = function (lt) { var q = prog(lt, 0, .9, 'out5'); return { s: base * lerp(.9, 1, q), y: lerp(180 * U, 0, q), rz: lerp(-4, 0, q), o: clamp(lt * 3, 0, 1) }; };
      else pose = function () { return { s: base }; };
    }
    if (cap) {
      pill = el('div', 'pill ' + (C.theme.mode === 'light' ? 'light' : ''), '<span class="dot"></span>' + esc(plain(cap)), g);
      pill.style.fontSize = (C.PORTRAIT ? 46 : 34) * U + 'px'; pill.style.bottom = (C.PORTRAIT ? H * .16 : 70 * U) + 'px'; pill.style.zIndex = 5;
    }
    return function (lt) {
      win.update(lt, dur, pose(lt));
      if (text) text.update(lt); if (sub) sub.update(lt);
      if (pill) { var q = prog(lt, .15, .6, 'out5'); pill.style.opacity = q; pill.style.transform = 'translateX(-50%) translateY(' + ((1 - q) * 30 * U).toFixed(1) + 'px) scale(' + lerp(.92, 1, q).toFixed(3) + ')'; }
    };
  };

  SC.features = function (sc, g, C) {
    sceneBg(sc, g, C);
    var U = C.U, W = C.W, H = C.H, items = (sc.items || []).slice(0, 4), n = Math.max(1, items.length);
    var head = sc.headline ? Kin(g, { text: sc.headline, size: C.PORTRAIT ? 84 : 76, weight: 700, y: C.PORTRAIT ? H * .14 : 150 * U, t0: sc.t0, maxW: W * .86 }) : null;
    var cols = C.PORTRAIT ? 1 : (C.SQUARE ? (n > 2 ? 2 : n) : n), rows = Math.ceil(n / cols);
    var gap = 36 * U, areaW = W * (C.PORTRAIT ? .84 : .88), tw = (areaW - gap * (cols - 1)) / cols;
    var areaTop = C.PORTRAIT ? H * .26 : (head ? 300 * U : 200 * U), areaH = H - areaTop - (C.PORTRAIT ? H * .1 : 110 * U);
    var th = Math.min((areaH - gap * (rows - 1)) / rows, C.PORTRAIT ? 330 * U : 400 * U);
    var tops = areaTop + (areaH - (th * rows + gap * (rows - 1))) / 2;
    var tiles = items.map(function (it, i) {
      var t = el('div', 'tile', null, g), c = i % cols, r = Math.floor(i / cols);
      var inRow = Math.min(cols, n - r * cols), rowW = inRow * tw + (inRow - 1) * gap;      // centre an incomplete last row
      t.style.width = tw + 'px'; t.style.height = th + 'px'; t.style.left = ((W - rowW) / 2 + c * (tw + gap)) + 'px'; t.style.top = (tops + r * (th + gap)) + 'px';
      var hues = [['var(--c1)', 'var(--c2)'], ['var(--c2)', 'var(--c3)'], ['var(--c3)', 'var(--c1)'], ['var(--c1)', 'var(--c3)']][i % 4];
      t.innerHTML = '<div class="ic" style="background:linear-gradient(135deg,' + hues[0] + ',' + hues[1] + ')">' + icon(it.icon) + '</div><h3>' + esc(it.title || '') + '</h3><p>' + esc(it.text || '') + '</p>';
      if (C.PORTRAIT) { t.style.display = 'grid'; t.style.gridTemplateColumns = (90 * U) + 'px 1fr'; t.style.columnGap = (30 * U) + 'px'; t.style.alignContent = 'center';
        t.querySelector('.ic').style.gridRow = '1 / span 2'; t.querySelector('h3').style.margin = '0 0 ' + (8 * U) + 'px'; }
      // bigger type when there is room; shrink text that doesn't fit
      var h3 = t.querySelector('h3'), p = t.querySelector('p'), fs = C.PORTRAIT ? 26 : (cols <= 3 ? 28 : 24);
      p.style.fontSize = fs * U + 'px'; h3.style.fontSize = fs * 1.9 * U + 'px';
      for (var k = 0; k < 10 && t.scrollHeight > th + 2; k++) { fs *= .92; p.style.fontSize = fs * U + 'px'; h3.style.fontSize = fs * 1.9 * U + 'px'; }
      return t;
    });
    return function (lt) {
      if (head) head.update(lt);
      tiles.forEach(function (t, i) {
        var q = prog(lt, .25 + i * .12, .95 + i * .12, 'out5');
        t.style.opacity = clamp(q * 1.4, 0, 1);
        t.style.transform = 'perspective(' + (1800 * U) + 'px) translateY(' + ((1 - q) * 120 * U).toFixed(1) + 'px) rotateX(' + ((1 - q) * 18).toFixed(2) + 'deg) translateY(' + (Math.sin(lt * 1.1 + i) * 4 * U).toFixed(1) + 'px)';
      });
    };
  };

  SC.montage = function (sc, g, C) {
    sceneBg(sc, g, C);
    var items = (sc.items || []).map(function (it) {
      var w = Win(g, { C: C, info: it.info, thumb: it.thumb, w: C.W, h: C.H, full: true, chrome: 'none', shot: it.shot, camera: 'follow', focus: it.focus, clip: { from: it.from, speed: it.speed }, amt: C.PORTRAIT ? .2 : .12 });
      w.el.classList.add('hidden'); return { w: w, a: it.a, b: it.b };
    });
    var cap = sc.caption ? el('div', 'pill ' + (C.theme.mode === 'light' ? 'light' : ''), '<span class="dot"></span>' + esc(plain(sc.caption)), g) : null;
    if (cap) { cap.style.fontSize = (34 * C.U) + 'px'; cap.style.bottom = (70 * C.U) + 'px'; cap.style.zIndex = 9; }
    return function (lt) {
      items.forEach(function (it, i) {
        var on = (lt >= it.a || i === 0) && (lt < it.b || i === items.length - 1);
        it.w.el.classList.toggle('hidden', !on);
        if (on) { var l = lt - it.a, q = prog(l, 0, .45, 'out5'); it.w.update(l, it.b - it.a, { s: lerp(1.09, 1, q) }); }
      });
      if (cap) cap.style.opacity = prog(lt, .1, .4);
    };
  };

  SC.grid = function (sc, g, C) {
    sceneBg(sc, g, C);
    var U = C.U, W = C.W, H = C.H;
    var host = el('div', 'L', null, g); host.style.perspective = (2600 * U) + 'px';
    var plane = el('div', null, null, host); plane.style.position = 'absolute'; plane.style.left = '50%'; plane.style.top = '50%'; plane.style.transformStyle = 'preserve-3d';
    var items = sc.items || [];
    var cols = C.PORTRAIT ? 3 : 4, cw = (C.PORTRAIT ? 620 : 640) * U, ch = cw * 9 / 16, gap = 44 * U, rows = C.PORTRAIT ? 6 : 4;
    var cards = [];
    for (var r = 0; r < rows; r++) for (var c = 0; c < cols; c++) {
      var it = items[(r * cols + c + r) % Math.max(1, items.length)] || {};
      var card = el('div', 'win ' + (C.theme.mode !== 'light' ? 'dark' : ''), null, plane);
      card.style.width = cw + 'px'; card.style.height = ch + 'px'; card.style.left = ((c - cols / 2) * (cw + gap) + (r % 2) * cw * .5) + 'px'; card.style.top = ((r - rows / 2) * (ch + gap)) + 'px';
      card.style.margin = '0'; card.style.borderRadius = (18 * U) + 'px';
      var im = el('img', null, null, card); im.style.width = '100%'; im.style.height = '100%'; im.style.objectFit = 'cover';
      var info = it.info, src = info && info.frames ? info.dir + (S.proxy && info.proxy ? 'proxy/' : '') + 'f' + pad5(Math.max(0, (it.mid || 0) - (it.mid || 0) % 2)) + '.jpg' : (info && info.still ? info.dir + 'still.jpg' : it.thumb);
      if (src) S.setImg(im, src);
      cards.push({ e: card, d: Math.abs(r - rows / 2 + .5) + Math.abs(c - cols / 2 + .5) });
    }
    var head = sc.headline ? Kin(g, { text: sc.headline, size: C.PORTRAIT ? 96 : 92, weight: 750, t0: sc.t0, y: H / 2, maxW: W * .8 }) : null;
    var scr = null;
    if (head) { scr = el('div', 'L', null, g); scr.style.background = 'radial-gradient(ellipse 50% 34% at 50% 50%, ' + (C.theme.mode === 'light' ? 'rgba(245,245,247,.94)' : 'rgba(5,5,7,.88)') + ', transparent 100%)'; head.el.style.zIndex = 5; scr.style.zIndex = 4; }
    return function (lt) {
      var p = clamp(lt / sc.dur, 0, 1);
      plane.style.transform = 'translate(' + (-lerp(0, 160, p) * U) + 'px,' + (-lerp(-60, 60, p) * U) + 'px) rotateX(' + 32 + 'deg) rotateZ(' + -14 + 'deg) scale(' + lerp(.92, 1.02, E.io(p)) + ')';
      cards.forEach(function (cd) { var q = prog(lt, cd.d * .06, cd.d * .06 + .6, 'out5'); cd.e.style.opacity = q; cd.e.style.transform = 'translateZ(' + ((1 - q) * -400 * U).toFixed(1) + 'px)'; });
      if (head) head.update(lt - .35);
      if (scr) scr.style.opacity = prog(lt, .2, .7);
    };
  };

  SC.stat = function (sc, g, C) {
    sceneBg(sc, g, C);
    var U = C.U, m = String(sc.value || '0').match(/^([^\d-]*)(-?[\d.,]+)(.*)$/) || ['', '', String(sc.value || ''), ''];
    var target = parseFloat(String(m[2]).replace(/,/g, '')) || 0, dec = (String(m[2]).split('.')[1] || '').length;
    var big = el('div', 'T', null, g); big.style.top = (C.H / 2 - 40 * U) + 'px'; big.style.transform = 'translateY(-50%)';
    big.style.fontSize = (C.PORTRAIT ? 300 : 280) * U + 'px'; big.style.fontWeight = 800; big.style.letterSpacing = '-.06em'; big.style.lineHeight = 1;
    var num = el('span', 'grad', '', big);
    var lab = Kin(g, { text: sc.label || '', size: 56, weight: 650, cls: 'muted', y: C.H / 2 + 150 * U, t0: sc.t0, delay: .5, maxW: C.W * .8 });
    return function (lt) {
      var q = prog(lt, .1, 1.4, 'expo');
      num.textContent = m[1] + (target * q).toLocaleString('en-US', { minimumFractionDigits: dec, maximumFractionDigits: dec }) + m[3];
      big.style.opacity = clamp(lt * 4, 0, 1); big.style.transform = 'translateY(-50%) scale(' + lerp(.85, 1, prog(lt, 0, .8, 'out5')) + ')';
      lab.update(lt);
    };
  };

  SC.quote = function (sc, g, C) {
    sceneBg(sc, g, C);
    var U = C.U;
    var q = el('div', 'quote grad', '\u201C', g); q.style.fontSize = 340 * U + 'px'; q.style.left = (C.W / 2 - 90 * U) + 'px'; q.style.top = (C.H * .12) + 'px';
    var k = Kin(g, { text: sc.text || '', size: C.PORTRAIT ? 70 : 64, weight: 650, lh: 1.18, t0: sc.t0, stagger: .04, maxW: C.W * .78, maxH: C.H * .5 });
    var a = Kin(g, { text: '_' + (sc.author || '') + '_', size: 34, weight: 600, y: C.H / 2 + k.height() / 2 + 70 * U, t0: sc.t0, delay: .8, anim: 'blur' });
    return function (lt) { q.style.opacity = prog(lt, 0, .5); q.style.transform = 'scale(' + lerp(.6, 1, prog(lt, 0, .7, 'back')) + ')'; k.update(lt); a.update(lt); };
  };

  SC.end = function (sc, g, C) {
    sceneBg(sc, g, C);
    var U = C.U, W = C.W, H = C.H, ls = (C.PORTRAIT ? 200 : 160) * U;
    var glow = el('div', 'L', null, g); glow.style.background = 'radial-gradient(circle at 50% 46%, ' + S.hexA(C.theme.c2, C.theme.mode === 'light' ? .22 : .35) + ', transparent 45%)';
    var lg = logoEl(g, C, ls);
    var name = Kin(g, { text: sc.title || C.brand.name, size: C.PORTRAIT ? 180 : 168, weight: 750, by: 'char', stagger: .035, dur: .5, t0: sc.t0, delay: .25, y: H / 2 + 10 * U, maxW: W * .86, maxH: H * .3 });
    var tag = sc.tagline ? Kin(g, { text: autoEmph(sc.tagline), size: C.PORTRAIT ? 72 : 70, weight: 650, stagger: .12, dur: .6, delay: .9, t0: sc.t0, y: H / 2 + 10 * U + name.height() / 2 + 75 * U, maxW: W * .84 }) : null;
    var ly = H / 2 + 10 * U - name.height() / 2 - ls - 36 * U;
    lg.style.left = (W / 2 - ls / 2) + 'px'; lg.style.top = ly + 'px';
    var cta = null;
    if (sc.cta) { cta = el('div', 'cta', '<i></i>' + esc(sc.cta), g); cta.style.fontSize = (C.PORTRAIT ? 40 : 32) * U + 'px'; cta.style.top = (H / 2 + 10 * U + name.height() / 2 + (tag ? 190 : 90) * U) + 'px'; }
    var note = sc.note ? Kin(g, { text: '_' + sc.note + '_', size: 26, weight: 600, y: H - 90 * U, t0: sc.t0, delay: 1.6, stagger: .02, anim: 'blur' }) : null;
    var sh = lg.querySelector('.shine');
    return function (lt) {
      var q = prog(lt, 0, .7, 'back');
      lg.style.transform = 'scale(' + (.3 + .7 * q).toFixed(4) + ') rotate(' + ((1 - q) * -25).toFixed(2) + 'deg)'; lg.style.opacity = clamp(lt * 5, 0, 1);
      if (sh) sh.style.transform = 'translateX(' + lerp(-60, 60, prog(lt, .6, 1.6, 'io')) + '%)';
      glow.style.opacity = prog(lt, 0, 1.2, 'out') * (0.85 + .15 * Math.sin(lt * 2));
      glow.style.transform = 'scale(' + lerp(.7, 1.05, prog(lt, 0, 2.5, 'out')) + ')';
      name.update(lt); if (tag) tag.update(lt); if (note) note.update(lt);
      if (cta) { var c = prog(lt, 1.3, 1.9, 'out5'); cta.style.opacity = c; cta.style.transform = 'translateX(-50%) translateY(' + ((1 - c) * 24 * U).toFixed(1) + 'px)'; }
    };
  };
})();
