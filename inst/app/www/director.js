/* DirectoR studio: client side */
(function () {
  'use strict';
  var DR = window.DR = {};
  function root(r) { if (r && r.jquery) r = r[0]; return r && r.querySelectorAll ? r : document; }   // Shiny passes jQuery scopes to bindings
  function $(s, r) { return root(r).querySelector(s); }
  function $$(s, r) {
    var R = root(r), out = Array.prototype.slice.call(R.querySelectorAll(s));
    if (R !== document && R.matches && R.matches(s)) out.unshift(R);
    return out;
  }
  function send(id, v, ev) { if (window.Shiny && Shiny.setInputValue) Shiny.setInputValue(id, v, ev ? { priority: 'event' } : undefined); }
  function esc(s) { return String(s == null ? '' : s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;'); }
  function debounce(fn, ms) { var t; return function () { var a = arguments, self = this; clearTimeout(t); t = setTimeout(function () { fn.apply(self, a); }, ms); }; }
  var ICON = {
    good: '<path d="m4.5 12.5 5 5 10-11"/>', bad: '<path d="M6 6l12 12M18 6 6 18"/>', warn: '<path d="M12 3.5 2.5 20h19z"/><path d="M12 10v4.5M12 17.2v.3"/>',
    info: '<circle cx="12" cy="12" r="9.5"/><path d="M12 11v5.5M12 7.8v.3"/>'
  };
  function ic(n, s) { return '<svg width="' + (s || 16) + '" height="' + (s || 16) + '" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">' + (ICON[n] || ICON.info) + '</svg>'; }

  /* ------------------------------------------------------------ custom inputs */
  document.addEventListener('DOMContentLoaded', function () {
    if (!window.Shiny) return;
    var choices = new Shiny.InputBinding();
    Object.assign(choices, {
      find: function (scope) { return $$('.dr-choices', scope); },
      getValue: function (el) { var a = el.querySelector('button.active'); return a ? a.getAttribute('data-value') : (el.getAttribute('data-value') || null); },
      setValue: function (el, v) { $$('button', el).forEach(function (b) { b.classList.toggle('active', b.getAttribute('data-value') === String(v)); }); el.setAttribute('data-value', v); },
      subscribe: function (el, cb) {
        el.__notify = cb;
        el.__cb = function (e) { if (e.target.closest('[data-preview]')) return;      // the play badge listens, it doesn't select
          var b = e.target.closest('button'); if (!b || !el.contains(b) || b.disabled) return; choices.setValue(el, b.getAttribute('data-value')); cb(); };
        el.addEventListener('click', el.__cb);
      },
      unsubscribe: function (el) { el.removeEventListener('click', el.__cb); },
      receiveMessage: function (el, m) {
        if (m.disabled) $$('button', el).forEach(function (b) { b.disabled = m.disabled.indexOf(b.getAttribute('data-value')) >= 0; });
        if (m.value != null) { choices.setValue(el, m.value); if (el.__notify) el.__notify(); }
      },
      getRatePolicy: function () { return { policy: 'direct' }; }
    });
    Shiny.inputBindings.register(choices, 'dr.choices');

    var color = new Shiny.InputBinding();
    Object.assign(color, {
      find: function (scope) { return $$('input.dr-color', scope); },
      getValue: function (el) { return el.value; },
      setValue: function (el, v) { el.value = v; },
      subscribe: function (el, cb) { el.__notify = cb; el.addEventListener('change', function () { cb(); }); el.addEventListener('input', function () { cb(true); }); },
      receiveMessage: function (el, m) { if (m.value) { el.value = m.value; if (el.__notify) el.__notify(); } },
      getRatePolicy: function () { return { policy: 'debounce', delay: 350 }; }
    });
    Shiny.inputBindings.register(color, 'dr.color');

    var sw = new Shiny.InputBinding();
    Object.assign(sw, {
      find: function (scope) { return $$('input.dr-switch', scope); },
      getValue: function (el) { return el.checked; },
      subscribe: function (el, cb) { el.__notify = cb; el.addEventListener('change', function () { cb(); }); },
      receiveMessage: function (el, m) { if (m.value != null) { el.checked = !!m.value; if (el.__notify) el.__notify(); } }
    });
    Shiny.inputBindings.register(sw, 'dr.switch');

    // title / omnibox / secrets: plain text inputs with a debounce
    var txt = new Shiny.InputBinding();
    Object.assign(txt, {
      find: function (scope) { return $$('input.title-in, input#lib_source, input.dr-secret', scope); },
      getValue: function (el) { return el.value; },
      subscribe: function (el, cb) { el.__notify = cb; el.addEventListener('input', function () { cb(true); }); el.addEventListener('change', function () { cb(); });
        el.addEventListener('keydown', function (e) { if (e.key === 'Enter') { cb(); if (el.id === 'lib_source') { var b = $('#lib_create'); b && b.click(); } else el.blur(); } }); },
      receiveMessage: function (el, m) { if (m.value != null && document.activeElement !== el) { el.value = m.value; if (el.__notify) el.__notify(); } },
      getRatePolicy: function () { return { policy: 'debounce', delay: 450 }; }
    });
    Shiny.inputBindings.register(txt, 'dr.text');
  });

  /* ------------------------------------------------------------ navigation */
  document.addEventListener('click', function (e) {
    var n = e.target.closest('[data-nav]');
    if (n && !n.classList.contains('disabled')) { send('nav', n.getAttribute('data-nav'), true); return; }
    var a = e.target.closest('[data-act]');
    if (a) {
      e.preventDefault();
      var payload = { act: a.getAttribute('data-act'), id: a.getAttribute('data-id'), arg: a.getAttribute('data-arg'), n: Math.random() };
      if (a.getAttribute('data-confirm') && !confirm(a.getAttribute('data-confirm'))) return;
      send(a.getAttribute('data-input') || 'ui_act', payload, true);
    }
  });
  function setNav(page) {
    $$('.dr-nav').forEach(function (b) { b.classList.toggle('active', b.getAttribute('data-nav') === page); });
  }

  /* ------------------------------------------------------------ server messages */
  function handlers() {
    Shiny.addCustomMessageHandler('dr-nav', function (m) {
      setNav(m.page);
      (m.done || []).forEach(function (k) { var b = $('#nav_' + k); b && b.classList.add('done'); });
      $$('.dr-nav').forEach(function (b) { var k = b.getAttribute('data-nav'); b.classList.toggle('done', (m.done || []).indexOf(k) >= 0); b.classList.toggle('disabled', !!m.locked && k !== 'lib'); });
      var pg = $('.dr-page'); if (pg && m.scroll !== false) pg.scrollTop = 0;
      document.body.classList.toggle('noproj', !!m.locked);
    });
    Shiny.addCustomMessageHandler('dr-toast', toast);
    Shiny.addCustomMessageHandler('dr-job', job);
    Shiny.addCustomMessageHandler('dr-log', function (m) { var p = $('#dr-dock pre.log'); if (p) { p.textContent = m.text || ''; p.scrollTop = p.scrollHeight; } });
    Shiny.addCustomMessageHandler('dr-player', function (m) {
      $$('iframe.dr-player').forEach(function (f) { try { f.contentWindow.postMessage(m, '*'); } catch (e) {} });
    });
    Shiny.addCustomMessageHandler('dr-set', function (m) {
      var el = document.getElementById(m.id); if (!el) return;
      if (el.type === 'checkbox') el.checked = !!m.value; else if (document.activeElement !== el) el.value = m.value == null ? '' : m.value;
    });
    Shiny.addCustomMessageHandler('dr-detect', function (m) { var el = $('#lib_detect'); if (el) el.innerHTML = m.html || ''; });
    Shiny.addCustomMessageHandler('dr-auto', function (m) { if (m.show) { $('#dr-auto').classList.add('show'); autoDismissed = false; } else $('#dr-auto').classList.remove('show'); });
    Shiny.addCustomMessageHandler('dr-download', function (m) { var a = document.createElement('a'); a.href = m.href; a.download = m.name || ''; document.body.appendChild(a); a.click(); a.remove(); });
  }
  if (window.Shiny && Shiny.addCustomMessageHandler) handlers(); else document.addEventListener('DOMContentLoaded', function () { handlers(); });

  /* ------------------------------------------------------------ toasts */
  function toast(m) {
    var box = $('#dr-toasts'); if (!box) return;
    var t = document.createElement('div'); t.className = 'toast-dr ' + (m.type || '');
    t.innerHTML = '<div class="ti">' + ic(m.type === 'good' ? 'good' : m.type === 'bad' ? 'bad' : m.type === 'warn' ? 'warn' : 'info') + '</div><div><div class="tt">' + esc(m.title || '') + '</div>' + (m.text ? '<div class="tx">' + esc(m.text) + '</div>' : '') + '</div>';
    box.appendChild(t);
    var life = m.life || (m.type === 'bad' ? 9000 : 4200);
    setTimeout(function () { t.classList.add('out'); setTimeout(function () { t.remove(); }, 320); }, life);
    t.addEventListener('click', function () { t.remove(); });
  }
  DR.toast = toast;

  /* ------------------------------------------------------------ job dock + autopilot overlay */
  var dockClosed = false, lastJob = null, autoDismissed = false;
  function fmt(s) { if (s == null || !isFinite(s)) return ''; s = Math.round(s); return s < 60 ? s + 's' : Math.floor(s / 60) + 'm ' + ('0' + (s % 60)).slice(-2) + 's'; }
  function job(st) {
    var d = $('#dr-dock'); if (!d) return;
    var key = (st.job || '') + st.started;
    if (key !== lastJob) { dockClosed = false; lastJob = key; }
    var running = st.state === 'running';
    d.classList.toggle('show', !dockClosed && (running || st.state === 'done' || st.state === 'error') && !st.hidden);
    d.classList.toggle('done', st.state === 'done'); d.classList.toggle('error', st.state === 'error');
    var p = Math.round((st.progress || 0) * 100);
    $('.ring', d).style.setProperty('--p', st.state === 'running' ? p : 100);
    $('.ring i', d).textContent = st.state === 'done' ? '✓' : st.state === 'error' ? '!' : p + '%';
    $('.nm', d).textContent = ({ scout: 'Scouting', plan: 'Writing', voice: 'Voice-over', capture: 'Recording', timeline: 'Timeline', music: 'Scoring', render: 'Rendering', auto: 'Autopilot', stills: 'Stills' })[st.job] || st.job || 'Working';
    $('.msg', d).textContent = st.state === 'error' ? (st.message || 'Failed') : (st.message || '');
    $('.bar i', d).style.width = (st.state === 'running' ? Math.max(2, p) : 100) + '%';
    $('.eta', d).textContent = running ? ((st.elapsed ? fmt(st.elapsed) + ' elapsed' : '') + (st.eta ? ' · ~' + fmt(st.eta) + ' left' : '')) : (st.elapsed ? 'took ' + fmt(st.elapsed) : '');
    var c = $('#job_cancel'); if (c) c.style.display = running ? '' : 'none';
    clearTimeout(d.__hide);
    if (st.state === 'done' && !d.classList.contains('logs')) d.__hide = setTimeout(function () { d.classList.remove('show'); dockClosed = true; }, 5000);
    // autopilot overlay
    var A = $('#dr-auto');
    if (A) {
      if (st.job === 'auto' && running && !autoDismissed) A.classList.add('show');
      if (st.job !== 'auto' || !running) A.classList.remove('show');
      if (st.job === 'auto') {
        var order = ['scout', 'plan', 'voice', 'capture', 'music', 'render'], cur = order.indexOf(st.phase);
        $$('.ph', A).forEach(function (x) { var i = order.indexOf(x.getAttribute('data-ph')); x.classList.toggle('on', i === cur); x.classList.toggle('ok', cur > i); });
        $('.msg', A).textContent = st.message || ''; $('.big i', A).style.width = Math.max(2, p) + '%';
        $('.eta', A).textContent = (st.eta ? '~' + fmt(st.eta) + ' left' : '');
      }
    }
  }
  DR.dockClose = function () { dockClosed = true; $('#dr-dock').classList.remove('show'); };
  DR.toggleLog = function () { var d = $('#dr-dock'); d.classList.toggle('logs'); send('want_log', d.classList.contains('logs') ? Math.random() : 0, true); };
  DR.autoHide = function () { autoDismissed = true; $('#dr-auto').classList.remove('show'); };

  /* ------------------------------------------------------------ story editing (plain inputs, one event) */
  var pend = {};
  var flush = debounce(function () {
    var keys = Object.keys(pend); if (!keys.length) return;
    var batch = keys.map(function (k) { return pend[k]; }); pend = {};
    send('story_edit', { edits: batch, n: Math.random() }, true);
  }, 380);
  function onEdit(e) {
    var el = e.target; if (!el.matches || !el.matches('[data-f]')) return;
    var card = el.closest('[data-scene]'); if (!card) return;
    var v = el.type === 'checkbox' ? el.checked : el.value;
    var k = card.getAttribute('data-scene') + '|' + el.getAttribute('data-f');
    pend[k] = { scene: card.getAttribute('data-scene'), f: el.getAttribute('data-f'), v: v };
    if (el.classList.contains('vo')) meter(el);
    flush();
  }
  document.addEventListener('input', onEdit); document.addEventListener('change', onEdit);
  function meter(el) {
    var m = el.closest('.scene') && el.closest('.scene').querySelector('.meter'); if (!m) return;
    var w = (el.value.trim().match(/\S+/g) || []).length, s = w / 2.6;
    m.textContent = w ? (w + ' words · ~' + s.toFixed(1) + 's') : 'no voice-over';
    m.classList.toggle('over', w > 26);
  }

  /* ------------------------------------------------------------ player <-> storyboard */
  var lastScene = null;
  addEventListener('message', function (e) {
    var d = e.data || {};
    if (d.type === 'dr:time') {
      if (d.scene !== lastScene) {
        lastScene = d.scene;
        $$('.scene[data-scene]').forEach(function (c) { c.classList.toggle('playing', c.getAttribute('data-scene') === d.scene); });
      }
    } else if (d.type === 'dr:ready') {
      send('player_ready', { duration: d.duration, n: Math.random() }, true);
    }
  });
  DR.seek = function (t, play) { $$('iframe.dr-player').forEach(function (f) { try { f.contentWindow.postMessage({ type: 'dr:seek', t: t, play: !!play }, '*'); } catch (e) {} }); };
  document.addEventListener('click', function (e) {
    var th = e.target.closest('[data-seek]');
    if (th) { DR.seek(parseFloat(th.getAttribute('data-seek')) + 0.01, true); }
  });

  /* ------------------------------------------------------------ shot flipbooks (hover to play proxy frames) */
  document.addEventListener('mouseover', function (e) {
    var f = e.target.closest('.flip[data-dir]'); if (!f || f.__play) return;
    var img = f.querySelector('img'); if (!img) return;
    var n = +f.getAttribute('data-n'), dir = f.getAttribute('data-dir'), still = img.src, i = 0;
    f.__play = setInterval(function () { i = (i + 2) % Math.max(2, n); img.src = dir + 'f' + String(i).padStart(5, '0') + '.jpg'; }, 1000 / 30);
    var stop = function () { clearInterval(f.__play); f.__play = null; img.src = still; f.removeEventListener('mouseleave', stop); };
    f.addEventListener('mouseleave', stop);
  });

  /* ------------------------------------------------------------ point picker (shot editor) */
  document.addEventListener('click', function (e) {
    var p = e.target.closest('.picker'); if (!p) return;
    var r = p.getBoundingClientRect(), fx = (e.clientX - r.left) / r.width, fy = (e.clientY - r.top) / r.height;
    var pt = p.querySelector('.pt') || p.appendChild(document.createElement('div')); pt.className = 'pt';
    pt.style.left = (fx * 100) + '%'; pt.style.top = (fy * 100) + '%';
    send(p.getAttribute('data-input') || 'pick_point', { fx: +fx.toFixed(4), fy: +fy.toFixed(4), n: Math.random() }, true);
  });

  /* ------------------------------------------------------------ microphone (human voice-over) */
  var rec = null, chunks = [], recBtn = null;
  DR.record = function (btn, scene) {
    if (rec && rec.state === 'recording') { rec.stop(); return; }
    if (!navigator.mediaDevices || !window.MediaRecorder) { toast({ type: 'bad', title: 'Recording is not supported in this browser' }); return; }
    navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: false, noiseSuppression: true, autoGainControl: false } }).then(function (stream) {
      chunks = []; recBtn = btn;
      rec = new MediaRecorder(stream);
      rec.ondataavailable = function (ev) { if (ev.data.size) chunks.push(ev.data); };
      rec.onstop = function () {
        stream.getTracks().forEach(function (t) { t.stop(); });
        btn.classList.remove('recording');
        var blob = new Blob(chunks, { type: rec.mimeType || 'audio/webm' });
        var fr = new FileReader();
        fr.onload = function () { send('vo_record', { scene: scene, mime: blob.type, data: String(fr.result).split(',')[1], n: Math.random() }, true); };
        fr.readAsDataURL(blob);
      };
      rec.start(); btn.classList.add('recording');
      toast({ title: 'Recording…', text: 'Read the line, then click again to stop.', life: 2500 });
    }).catch(function (err) { toast({ type: 'bad', title: 'Microphone unavailable', text: String(err) }); });
  };

  /* ------------------------------------------------------------ drag & drop on the library dropzone */
  document.addEventListener('dragover', function (e) { var z = e.target.closest && e.target.closest('.dropzone'); if (z) z.classList.add('over'); });
  document.addEventListener('dragleave', function (e) { var z = e.target.closest && e.target.closest('.dropzone'); if (z) z.classList.remove('over'); });
  document.addEventListener('drop', function () { $$('.dropzone').forEach(function (z) { z.classList.remove('over'); }); });

  /* ------------------------------------------------------------ sound previews (moods, sound effects, your track)
     One persistent <audio> element, unlocked by the first click (Safari only lets audio start from a user gesture).
     Bundled previews play straight from the click; if the browser can't decode MP3 (or the file fails),
     the server makes a WAV and we play that.                                                                  */
  var A = null, sndKey = null, sndFallback = null, unlocked = false;
  var SILENT = 'data:audio/wav;base64,UklGRiQAAABXQVZFZm10IBAAAAABAAEAQB8AAIA+AAACABAAZGF0YQAAAAA=';
  function audioEl() {
    if (A) return A;
    A = new Audio(); A.preload = 'auto';
    A.addEventListener('ended', function () {          // only a real end of playback (not the silent unlock clip, not a source change)
      if (!sndKey || A.src === SILENT || !(A.duration > 0) || A.currentTime < A.duration - 0.3) return;
      DR.stop();
    });
    A.addEventListener('error', function () {
      if (!sndKey || A.src === SILENT) return;
      var code = A.error ? A.error.code : 0, fb = sndFallback; sndFallback = null;
      if (fb) { fb(); return; }
      toast({ type: 'bad', title: 'Could not play the preview', text: (code === 2 ? 'Network error while loading the sound.' : code === 4 ? 'This browser cannot play this audio format.' : 'The sound could not be decoded.') + ' (code ' + code + ')' });
      DR.stop();
    });
    return A;
  }
  function unlock() {
    if (unlocked) return; unlocked = true;
    var a = audioEl(); try { a.src = SILENT; var p = a.play(); if (p && p.catch) p.catch(function () {}); } catch (e) {}
  }
  document.addEventListener('pointerdown', unlock, true); document.addEventListener('keydown', unlock, true);
  var canMp3 = (function () { try { return !!new Audio().canPlayType('audio/mpeg'); } catch (e) { return false; } })();
  function mark(key, cls, on) { if (!key) return; $$('[data-key="' + key + '"], [data-preview="' + key + '"]').forEach(function (e) { var card = e.closest('.dr-choices button') || e; card.classList.toggle(cls, on); }); }
  DR.stop = function () { if (A) { try { A.pause(); } catch (e) {} } if (sndKey) mark(sndKey, 'playing', false); sndKey = null; sndFallback = null; };
  DR.play = function (url, key, fallback) {
    var a = audioEl();
    DR.stop(); $$('.loading').forEach(function (e) { e.classList.remove('loading'); });
    sndKey = key || url; sndFallback = fallback || null;
    a.src = url;
    var p = a.play();
    if (p && p.catch) p.catch(function (err) {
      if (err && err.name === 'NotAllowedError') { toast({ type: 'warn', title: 'The browser blocked the sound', text: 'Click the preview again to listen.' }); DR.stop(); }
    });
    mark(sndKey, 'playing', true);
    $$('iframe.dr-player').forEach(function (f) { try { f.contentWindow.postMessage({ type: 'dr:pause' }, '*'); } catch (e) {} });   // don't talk over the film
  };
  function wavFromServer(name, key) { return function () { mark(key, 'loading', true); send('music_preview', { mood: name, key: key, wav: true, n: Math.random() }, true); }; }
  DR.playBundled = function (name, key) {           // name: a mood ("keys") or a sound effect ("sfx_click")
    var fb = wavFromServer(name.replace(/^sfx_/, ''), key);
    if (!canMp3) { fb(); return; }
    DR.play('drm/w/demos/' + (name.indexOf('sfx_') === 0 ? name : 'music_' + name) + '.mp3', key, fb);
  };
  DR.previewMood = function (mood, settings) {
    if (!mood) { var sel = $('#music_mood button.active'); mood = sel ? sel.getAttribute('data-value') : 'auto'; }
    if (sndKey === mood && !settings) { DR.stop(); return; }
    if (settings || mood === 'custom' || mood === 'auto') { send('music_preview', { mood: mood, key: mood, settings: !!settings, n: Math.random() }, true); return; }
    DR.playBundled(mood, mood);
  };
  document.addEventListener('click', function (e) {
    var b = e.target.closest('[data-preview]');
    if (b) { e.preventDefault(); e.stopPropagation(); DR.previewMood(b.getAttribute('data-preview')); return; }
    var sfx = e.target.closest('[data-sfx]');
    if (sfx) { var k = 'sfx-' + sfx.getAttribute('data-sfx'); if (sndKey === k) DR.stop(); else DR.playBundled('sfx_' + sfx.getAttribute('data-sfx'), k); return; }
    var mc = e.target.closest('#music_mood button');
    if (mc && !mc.disabled) { var v = mc.getAttribute('data-value'); if (v === 'none') DR.stop(); else if (sndKey !== v) DR.previewMood(v); }
  }, true);
  function playHandler() {
    Shiny.addCustomMessageHandler('dr-play', function (m) {
      if (m.loading != null) { $$('.loading').forEach(function (e) { e.classList.remove('loading'); }); if (m.loading) mark(m.loading, 'loading', true); return; }
      if (m.error) { $$('.loading').forEach(function (e) { e.classList.remove('loading'); }); toast({ type: 'bad', title: 'Preview failed', text: m.error }); return; }
      DR.play(m.url, m.key);
    });
  }
  if (window.Shiny && Shiny.addCustomMessageHandler) playHandler(); else document.addEventListener('DOMContentLoaded', playHandler);

  /* ------------------------------------------------------------ keyboard */
  addEventListener('keydown', function (e) {
    if (e.target.matches('input, textarea, select')) return;
    if (e.code === 'Space') { var f = $('iframe.dr-player'); if (f) { e.preventDefault(); try { f.contentWindow.postMessage({ type: 'dr:toggle' }, '*'); } catch (err) {} } }
  });

  DR.copy = function (text) { navigator.clipboard && navigator.clipboard.writeText(text); toast({ type: 'good', title: 'Copied', life: 1600 }); };
})();
