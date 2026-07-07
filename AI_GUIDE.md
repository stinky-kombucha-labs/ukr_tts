# AI Guide: tts_new

Self-contained Ukrainian TTS pipeline. It no longer depends on the old
`/home/user/PycharmProjects/tts` project (engine is vendored in `vendor/`,
weights live in `models/`); the old project may still be consulted as a
reference but must never be modified.

## Data flow

```
input/<novel>/*.txt
  └─ prepare ──▶ work/<novel>/prepared/*.txt   (one ~450-char TTS segment per line)
       └─ synth ──▶ output/<novel>/*.mp3       (atomic tmp+rename, then verified)
            └─ on success: input txt ─▶ work/<novel>/processed/, prepared txt removed
reports: work/<novel>/reports/*.json|md        failures: work/<novel>/failed/
```

## Modules (`src/tts_new/`)

- `config.py` — reads `config.json`, frozen dataclasses.
- `paths.py` — folder layout, novel discovery (subfolders of `input|work|output`).
- `text.py` — cleaning + legacy segmentation (packs sentences up to
  `target_chars`). Prepared text must contain only Ukrainian letters, digits
  and punctuation: Roman numerals → digits, known abbreviations → dictionary
  pronunciations, other acronyms → letter names, single Latin letters →
  letter names ("Ікс"), Latin words → transliteration, symbols (%, °C, №, +,
  =) → words. Raw Latin would be mangled by the engine ("XIV" → "ксів").
- `quality.py` — reports TTS risks: long lines, Latin/mixed/CJK, risky symbols.
- `prepare.py` — input → prepared + quality report; applies user word
  replacements from `glossary.json` (exact and stem rules) before cleaning.
- `audio_engine.py` — adapter over vendored `ukrainian_tts` (chdir to `models/`
  because upstream `config.yaml` uses relative paths).
- `synthesize.py` — planning (skip verified MP3s), parallel workers, atomic
  writes, consume-on-success, incremental manifest.
- `integrity.py` — every known chapter must have a healthy MP3.
- `cli.py` — `doctor|prepare|synth|verify|full`; no args = `run.action`.

## Invariants — keep these true

- An MP3 appears in `output/` only complete and decode-verified (tmp+rename).
- Source txt leaves `input/` only after its MP3 is verified.
- A failed segment fails the whole chapter loudly (reports + `failed/`);
  never ship a chapter with missing lines.
- Segmentation stays at proven `target_chars=450`; never feed the model one
  huge line per chapter.
- The pipeline reports Latin/mixed-script text but never invents
  transliterations — fix the source in the translation project.
- `vendor/ukrainian_tts` is upstream code: do not edit, replace wholesale.
- `deps/` (gitignored) holds pip overrides that must shadow the venv —
  currently `ukrainian-word-stress==1.1.1`; `audio_engine` puts it on
  `sys.path` ahead of site-packages.
- Do not commit `input/`, `output/`, `work/`, `models/` (see `.gitignore`).
- Do not modify `/home/user/PycharmProjects/tts`.

## Performance notes (RTX 5080, 16 cores)

1 worker ≈ RTF 0.046; 3 workers saturate the GPU (~1.9× throughput,
RTF ≈ 0.024); 6 workers give no further gain. `audio.workers=3` is the tuned
default; CPU thread env vars are capped per worker in `synthesize._worker`.
