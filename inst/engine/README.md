# DirectoR engine

This is the Python engine behind the DirectoR studio. It grew out of QuantSkill's `dev/video` pipeline,
which was hand-scripted for one app. Here the same pipeline is made generic: the hand-made `teaser.js`
and `launch.js` are replaced by a data-driven storyboard → timeline → stage pipeline.

```sh
pip install -r requirements.txt && python -m playwright install chromium     # + ffmpeg
python -m director doctor                                                    # what's installed, which voices work
```

A project is a folder with a `project.json`:

```json
{"name": "Orbit", "source": {"kind": "git", "value": "https://github.com/you/orbit"}, "film": {"template": "launch"}}
```

Then, from this folder:

```sh
python -m director auto -p /path/to/project --quality final        # everything: scout → plan → voice → capture → music → render
python -m director scout -p …                                      # or one step at a time
python -m director plan -p … --template teaser
python -m director voice -p …            [--line s3]               # one line only: a preview
python -m director capture -p …          [--shots shot1,shot2] [--missing-only]
python -m director timeline -p …                                   # storyboard -> timeline.json + stage/ + preview.html
python -m director music -p …
python -m director render -p … --quality draft|final [--aspect 9:16]
python -m director stills -p … --times 1,5.5,12 --out /tmp/stills
```

While a step runs, it reports progress in `status.json`, and it appends to `log.txt`.

| Module | Role | Came from |
|---|---|---|
| `source.py` | fetch (git / zip / folder), detect the app kind, learn facts (README, DESCRIPTION…), launch on a free port | new |
| `scout.py` | explore the running app: tabs, pages, inputs, outputs, headings, colours, logo | new |
| `plan.py` | templates, copy (features matched to screens), shot recipes | new (replaces hand-written timelines) |
| `llm.py` | optional AI copywriter (OpenAI-compatible or Anthropic) | new |
| `recorder.py` | deterministic frame-stepping recorder, cursor, lite effects for heavy pages | QuantSkill `recorder.py`, generalised |
| `capture.py` | runs shot recipes in parallel browsers, proxies, imports media | QuantSkill `shots.py`, generalised |
| `voice.py` | 8 voice providers, cache, polish, auto fallback | QuantSkill `vo.py`, extended |
| `timeline.py` | resolves scene times, clip mapping, transitions, SFX, captions, theme | QuantSkill `launch.js` `T()` warping, generalised |
| `music.py` | synthesised score (7 moods) following the cut, sound design, mix and ducking | QuantSkill `music.py` instruments + new composer |
| `render.py` | stage → frames → H.264, in parallel | QuantSkill `render.py` |
| `mux.py` | loudness, captions (SRT + burned), poster, script | QuantSkill `make.py` (mux) |
| `stage/` | `stage.js` engine (scenes, 12 transitions), `film.js` scene library, `preview.js` live player | QuantSkill `stage.js`, extended |
