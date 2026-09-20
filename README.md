# JP Game Reader

A reusable Windows Japanese-learning reader, adapted from Fortune Weave Live Reader.
One shared application, with a separate journal and capture settings for each game.

## Start

Requires Windows, Python 3.12+ (on PATH or through the Python launcher), OBS Studio,
and Windows Japanese OCR language support. The core uses Python's standard library.

1. In OBS, capture the game using Game Capture, Window Capture, or a capture card.
2. Open an OBS **Windowed Projector** for the game source or preview. Keep its dialogue area visible.
3. Double-click **Start JP Game Reader.cmd**. Enter a short game profile such as `fortune-weave` or `my-new-vn`.
4. The reader opens at http://127.0.0.1:18745. Adjust dialogue start and height under Recorder settings.
5. Enable automatic recognition or use manual recognition, and review OCR mistakes.
6. Use **Stop recorder** before switching profiles. Launch again and enter the next game name.

You can also run `python launch.py --profile my-new-vn`.
Manual journal mode: `python launch.py --profile my-new-vn --no-capture`.

## What is isolated by game

`data/<profile>/` holds the sentence database, notes, translations, crop settings,
backups, exports, and selected local translation model. Reusing the same profile
resumes that journal. All games share the same code and UI. Browser appearance
preferences remain shared. Profile names use lowercase ASCII letters, numbers,
hyphens and underscores; this is a first version of profile selection.

## Translation and dictionaries

The active translation provider is local LM Studio at `127.0.0.1:1234`.
Download and load a suitable model, start its local server, then select it in the
reader. The inherited default is `qwen/qwen3-14b`; it is not downloaded by this app.
Without LM Studio, OCR and the journal still work; translation pauses on failure.
Legacy DeepL helpers remain in the source but are not the default translator.
Online lookup and opening ChatGPT are explicit browser actions.

Dictionary data is not included. An existing compatible MDX index can be selected
with `JP_READER_DICTIONARY_INDEX`, pointing to `mdict-index.sqlite3`; its original
dictionary source files must remain in place. Otherwise local dictionaries are
empty. A fresh dictionary import wizard is future work.

## Existing Fortune Weave journal

Your original installation is independent and unchanged. This base starts with
empty profiles. To migrate later, stop both readers and copy the original
`saved_sentences` contents into `data/fortune-weave/` before launching that profile.
Keep a backup first. Do not upload the journal or dictionary files to GitHub.

## Current limits

This version reads visible OBS projector pixels. Covered or minimized projectors,
fast dialogue, stylized fonts, vertical text and multiple dialogue regions can
cause missed or inaccurate OCR. Compatibility depends on what OBS can capture
and OCR can read; support for every Japanese game is not guaranteed.

GitHub stores and versions the application source. Run the reader on your PC:
GitHub Pages cannot run its Windows OCR, local Python server or OBS integration.
See [ROADMAP.md](ROADMAP.md) for the recommended next steps.
