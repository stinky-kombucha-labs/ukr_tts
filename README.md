# tts_new

Self-contained pipeline that turns Ukrainian `.txt` chapters into verified MP3
audiobooks using the [ukrainian-tts](https://github.com/robinhad/ukrainian-tts)
model (voice `oleksa`, GPU).

Українською: див. [START_UA.md](START_UA.md).

## Layout

```
input/<novel>/*.txt      you drop chapters here (the queue)
output/<novel>/*.mp3     final audio
work/<novel>/            internal: prepared/, processed/, failed/, reports/
models/                  model weights (auto-downloaded on first run, ~430 MB)
vendor/ukrainian_tts/    vendored TTS engine
deps/                    pip overrides that shadow the venv (stress dict 1.1.1)
```

## Quickstart

1. Python 3.10+, ffmpeg, and `pip install -r requirements.txt`
   (or reuse an existing working venv).
2. Put chapters into `input/<novel>/00001.txt`, `00002.txt`, …
3. Run, in order (in PyCharm just click them, no arguments needed):
   - `10_prepare_text.py` — cleans text, splits it into TTS-safe ~450-char segments
   - `20_synthesize_audio.py` — renders MP3s, then verifies them
   - `30_verify_audio.py` — re-checks all MP3s (existence, size, duration)

`run.py` with no arguments executes `run.action` from `config.json`
(default `full` = prepare + synth + verify). CLI form:
`python run.py {doctor|prepare|synth|verify|full} [--novel N] [--workers W] [--force] [--limit K]`.

Run `python run.py doctor` first to check the environment.

## Crash safety

- MP3s are written to `*.mp3.tmp` and atomically renamed; stale `.tmp` files
  are removed on the next run.
- A chapter's source `.txt` is moved from `input/` to `work/<novel>/processed/`
  only after its MP3 is fully rendered and verified. Kill the process at any
  moment: finished chapters are kept, unfinished ones are re-rendered on the
  next run, nothing is ever half-done in `output/`.
- Existing MP3s are checked (decodable, size, duration) and skipped if healthy;
  use `--force` to re-render.
- A failed line stops that chapter (never a silently broken audiobook); the
  text is copied to `work/<novel>/failed/` and the error is reported in
  `work/<novel>/reports/`.

## Performance

Synthesis runs `audio.workers` parallel processes, each with its own model
instance on the GPU. On an RTX 5080 + 16-core CPU, 3 workers saturate the GPU
(~1 minute of audio per 1.5 s wall clock); more workers add nothing. Tune
`audio.workers` in `config.json` for your hardware.

## config.json

| Key | Meaning |
|-----|---------|
| `dirs.input/output/work` | pipeline folders (relative to the project) |
| `engine.voice` | `tetiana`, `mykyta`, `lada`, `dmytro`, `oleksa` |
| `engine.stress` | `dictionary` (recommended) or `model` |
| `engine.device` | `cuda` or `cpu` |
| `text.target_chars` | segment length the splitter packs to (proven: 450) |
| `audio.workers` | parallel synthesis processes |
| `audio.min_size_kb`, `audio.min_duration_sec` | verification thresholds |
| `run.action` | what argument-less `run.py` does: `doctor`/`prepare`/`synth`/`verify`/`full` |

## Input contract

UTF-8 `.txt`, one file per chapter, sequential names (`00001.txt`, …).
The pipeline removes translator/service noise, normalizes quotes/dashes and
converts `[]` to `()`.

Prepared text contains only Ukrainian letters, digits and punctuation —
everything else is converted to its spoken form at the prepare stage (visible
in `work/<novel>/prepared/`):

- Roman numerals → digits: `XIV` → `14`; single letters after section words
  too: `том I` → `том 1`
- known abbreviations → pronunciations: `NPC` → `НПС`, `CD` → `компакт-диск`
- other ALL-CAPS acronyms → letter names: `ZIP` → `зет-і-пе`
- single Latin letters → letter names: `Містер X` → `Містер Ікс`
- other Latin words → transliteration: `email` → `емаіл`
- symbols: `50%` → `50 відсотків`, `30°C` → `30 градусів за Цельсієм`,
  `№7` → `номер 7`, `+`/`=` → `плюс`/`дорівнює`

Exceptions: currency symbols (`$`, `€`, `₴`) are left to the engine, which
inflects them correctly; Latin glued to Cyrillic (`XЛОП`) and CJK are kept
and reported (`mixed_script_word`, `cjk_text`) — fix those upstream in the
translation project.

Custom word replacements live in `glossary.json` (applied before all other
processing, capitalization preserved): `"слово": "заміна"` replaces the exact
form, `"основ*": "нова-основа"` replaces the stem and keeps the grammatical
ending. Replacement counts appear in the prepare report.

## Stress dictionary

Word stress comes from `ukrainian-word-stress`. Version 1.1.1 has a richer
accent dictionary than 1.1.0 (fixes many "is in dictionary, but lacks accents"
warnings). If your venv has an older version, the project-local `deps/` folder
shadows it; recreate with
`pip install --target deps --no-deps ukrainian-word-stress==1.1.1`.
