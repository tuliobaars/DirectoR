/* DirectoR live preview: plays the stage in real time inside the app (no render needed).
   postMessage API  parent -> player: {type:'dr:seek', t}, {type:'dr:play'}, {type:'dr:pause'}, {type:'dr:toggle'}, {type:'dr:captions', on}
                    player -> parent: {type:'dr:ready', duration, scenes}, {type:'dr:time', t, scene, playing}          */
(function () {
  'use strict';
  var TL, dur, stage, fit, audio = null, playing = false, t = 0, t0 = 0, w0 = 0, raf = 0, lastPost = 0, caps = false, muted = false, loop = true;
  function $(s) { return document.querySelector(s); }
  function fmt(x) { x = Math.max(0, x); var m = Math.floor(x / 60), s = x - m * 60; return m + ':' + (s < 10 ? '0' : '') + s.toFixed(1); }
  function sceneAt(x) { var id = null; TL.scenes.forEach(function (s) { if (x >= s.t0 && x < s.t1) id = s.id; }); return id; }
  var COLORS = { hook: '#f472b6', title: '#a78bfa', shot: '#60a5fa', features: '#34d399', montage: '#fbbf24', grid: '#22d3ee', stat: '#fb923c', quote: '#e879f9', end: '#c084fc' };

  function layout() {
    var W = TL.W, H = TL.H, bar = document.body.classList.contains('nobar') ? 0 : 56;
    var k = Math.min(innerWidth / W, (innerHeight - bar) / H);
    fit.style.width = W + 'px'; fit.style.height = H + 'px';
    fit.style.transform = 'translate(' + ((innerWidth - W * k) / 2) + 'px,' + ((innerHeight - bar - H * k) / 2) + 'px) scale(' + k + ')';
  }

  function ui() {
    var bar = document.createElement('div'); bar.id = 'pbar';
    bar.innerHTML = '<button id="pp" title="Play (space)"><svg viewBox="0 0 24 24"><path id="ppi" d="M7 4.5v15l13-7.5z"/></svg></button>' +
      '<div id="tc">0:00.0</div><div id="track"><div id="segs"></div><div id="prog"></div><div id="head"></div><div id="hover"></div></div>' +
      '<div id="td">' + fmt(dur) + '</div>' +
      '<button id="cc" title="Captions (c)">CC</button><button id="mu" title="Mute (m)"><svg viewBox="0 0 24 24"><path d="M4 9v6h4l5 4V5L8 9H4z"/><path id="mux" d="M16 9.5a4 4 0 0 1 0 5M18.5 7a7.5 7.5 0 0 1 0 10" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"/></svg></button>' +
      '<button id="fs" title="Fullscreen (f)"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M4 9V4h5M20 9V4h-5M4 15v5h5M20 15v5h-5"/></svg></button>';
    document.body.appendChild(bar);
    var segs = $('#segs');
    TL.scenes.forEach(function (s) {
      var d = document.createElement('i'); d.style.left = (s.t0 / dur * 100) + '%'; d.style.width = ((s.t1 - s.t0) / dur * 100) + '%';
      d.style.background = COLORS[s.type] || '#888'; d.title = s.type + (s.headline || s.text || s.title ? ': ' + String(s.headline || s.text || s.title).replace(/[*_~|]/g, '') : '');
      segs.appendChild(d);
    });
    (TL.vo || []).forEach(function (v) {
      var d = document.createElement('b'); d.style.left = (v.start / dur * 100) + '%'; d.style.width = ((v.end - v.start) / dur * 100) + '%'; segs.appendChild(d);
    });
    $('#pp').onclick = toggle;
    $('#cc').onclick = function () { setCaps(!caps); };
    $('#mu').onclick = function () { muted = !muted; if (audio) audio.muted = muted; $('#mu').classList.toggle('off', muted); };
    $('#fs').onclick = function () { if (document.fullscreenElement) document.exitFullscreen(); else document.documentElement.requestFullscreen && document.documentElement.requestFullscreen(); };
    var tr = $('#track'), drag = false;
    var at = function (e) { var r = tr.getBoundingClientRect(); return Math.max(0, Math.min(1, (e.clientX - r.left) / r.width)) * dur; };
    tr.addEventListener('pointerdown', function (e) { drag = true; tr.setPointerCapture(e.pointerId); seek(at(e)); });
    tr.addEventListener('pointermove', function (e) { var x = at(e); $('#hover').style.left = (x / dur * 100) + '%'; $('#hover').textContent = fmt(x); if (drag) seek(x); });
    tr.addEventListener('pointerup', function () { drag = false; });
  }
  function setCaps(on) { caps = !!on; Stage.captions(caps); $('#cc') && $('#cc').classList.toggle('on', caps); Stage.render(t); }

  function draw() {
    Stage.render(t);
    var p = t / dur * 100;
    if ($('#prog')) { $('#prog').style.width = p + '%'; $('#head').style.left = p + '%'; $('#tc').textContent = fmt(t); }
    var now = performance.now();
    if (now - lastPost > 90) { lastPost = now; try { parent.postMessage({ type: 'dr:time', t: t, scene: sceneAt(t), playing: playing }, '*'); } catch (e) {} }
  }
  function tick() {
    if (!playing) return;
    var wall = t0 + (performance.now() - w0) / 1000;
    t = wall;
    if (audio && !audio.paused && audio.readyState >= 2 && isFinite(audio.currentTime)) {
      var drift = audio.currentTime - wall;
      if (Math.abs(drift) > 0.25) { try { audio.currentTime = wall; } catch (e) {} }     // audio lost its place (e.g. seek before it loaded)
      else if (Math.abs(drift) > 0.02) { t0 += drift * 0.1; t = t0 + (performance.now() - w0) / 1000; }   // gently follow the audio clock
    }
    if (t >= dur) {
      if (loop) { seek(0); play(); return; }
      t = dur; pause();
    }
    draw(); raf = requestAnimationFrame(tick);
  }
  function play() {
    if (playing) return;
    if (t >= dur - 0.05) t = 0;
    playing = true; t0 = t; w0 = performance.now();
    if (audio) { try { audio.currentTime = t; var pr = audio.play(); if (pr && pr.catch) pr.catch(function () {}); } catch (e) {} }
    $('#ppi') && $('#ppi').setAttribute('d', 'M6.5 4.5h4v15h-4zM13.5 4.5h4v15h-4z');
    document.body.classList.add('playing');
    raf = requestAnimationFrame(tick);
  }
  function pause() {
    playing = false; cancelAnimationFrame(raf);
    if (audio) audio.pause();
    $('#ppi') && $('#ppi').setAttribute('d', 'M7 4.5v15l13-7.5z');
    document.body.classList.remove('playing');
    draw();
  }
  function toggle() { playing ? pause() : play(); }
  function seek(x) {
    t = Math.max(0, Math.min(dur, x)); t0 = t; w0 = performance.now();
    if (audio) { try { audio.currentTime = t; } catch (e) {} }
    draw();
  }

  /* hot reload: new timeline.js, same page (no flash, keeps the playhead) */
  function reload(attempt) {
    attempt = attempt || 0;
    var s = document.createElement('script');
    s.src = 'stage/timeline.js?v=' + Date.now();
    s.onerror = function () { s.remove(); if (attempt < 4) setTimeout(function () { reload(attempt + 1); }, 600 * (attempt + 1)); };
    s.onload = function () {
      if (!window.TL || !window.TL.scenes) { s.remove(); if (attempt < 4) setTimeout(function () { reload(attempt + 1); }, 600 * (attempt + 1)); return; }
      var keep = t, was = playing, oldAudio = window.AUDIO;
      if (playing) pause();
      TL = window.TL; dur = TL.duration;
      Stage.init(TL, { preview: true }); Stage.captions(caps);
      var bar = $('#pbar'); if (bar) bar.remove();
      ui(); layout(); $('#cc').classList.toggle('on', caps); $('#mu').classList.toggle('off', muted);
      if (window.AUDIO && (!audio || audio.__src !== window.AUDIO)) { if (audio) audio.pause(); audio = new Audio(window.AUDIO); audio.__src = window.AUDIO; audio.preload = 'auto'; audio.muted = muted; }
      if (!window.AUDIO && audio) { audio.pause(); audio = null; }
      seek(Math.min(keep, dur - 0.01));
      if (was) play();
      s.remove();
      try { parent.postMessage({ type: 'dr:ready', duration: dur, reloaded: true }, '*'); } catch (e) {}
    };
    document.head.appendChild(s);
  }

  function start() {
    TL = window.TL; dur = TL.duration;
    stage = document.getElementById('stage');
    fit = document.createElement('div'); fit.id = 'fit'; stage.parentNode.insertBefore(fit, stage); fit.appendChild(stage);
    if (/[?&]nobar/.test(location.search)) document.body.classList.add('nobar');
    if (window.AUDIO) { audio = new Audio(window.AUDIO); audio.__src = window.AUDIO; audio.preload = 'auto'; }
    ui(); layout(); addEventListener('resize', layout);
    fit.addEventListener('click', toggle);
    addEventListener('keydown', function (e) {
      if (e.target.tagName === 'INPUT') return;
      if (e.code === 'Space') { e.preventDefault(); toggle(); }
      else if (e.key === 'ArrowRight') seek(t + (e.shiftKey ? 5 : 1)); else if (e.key === 'ArrowLeft') seek(t - (e.shiftKey ? 5 : 1));
      else if (e.key === 'c') setCaps(!caps); else if (e.key === 'm') $('#mu').click(); else if (e.key === 'f') $('#fs').click();
      else if (e.key === 'Home') seek(0);
    });
    // open on a representative frame: a second into the first footage scene (else the settled hook)
    var first = TL.scenes.filter(function (x) { return x.type === 'shot'; })[0];
    var q = location.search.match(/[?&]t=([\d.]+)/); seek(q ? parseFloat(q[1]) : (first ? Math.min(first.t0 + 1.2, first.t1 - 0.1) : Math.min(dur * 0.3, 2.5)));
    if (/[?&]cc=1/.test(location.search)) setCaps(true);
    // warm the cache: the first frames of every clip
    TL.scenes.forEach(function (s) { if (s.thumb) { var im = new Image(); im.src = s.thumb; } });
    addEventListener('message', function (e) {
      var d = e.data || {};
      if (d.type === 'dr:seek') { seek(+d.t || 0); if (d.play) play(); }
      else if (d.type === 'dr:play') play(); else if (d.type === 'dr:pause') pause(); else if (d.type === 'dr:toggle') toggle();
      else if (d.type === 'dr:captions') setCaps(d.on);
      else if (d.type === 'dr:reload') { try { reload(0); } catch (e) { location.reload(); } }
    });
    try { parent.postMessage({ type: 'dr:ready', duration: dur, scenes: TL.scenes.map(function (s) { return { id: s.id, t0: s.t0, t1: s.t1, type: s.type }; }) }, '*'); } catch (e) {}
  }
  window.Player = { start: start, play: play, pause: pause, seek: seek, reload: reload };
})();
