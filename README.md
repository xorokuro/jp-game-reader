# Japanese Reader

A general-purpose, local Japanese reading workspace. Paste articles, novels,
messages or game dialogue; select words for automatic dictionary search; save
notes; copy learning prompts; optionally translate with a local LLM.
OBS is an optional input, not a requirement.

## iPhone / iPad edition

The native iOS companion supports pasted text, offline MDX/MDD dictionaries,
saved passages and notes, learning prompts, and Apple's translation panel.
See [iPhone installation and build guide](ios/README.md). It uses the same personal
dictionary files, imported once. The Windows Argos runtime is not bundled in iOS.

## Portable Windows edition — start here

1. Copy the entire **Japanese Reader Portable** folder to your Windows laptop.
2. Double-click **Start Reader.cmd**.
3. Paste Japanese and click **Open text for reading**. Highlight a word in the
   reading panel to search the included dictionaries automatically.

No Python, OBS, LM Studio, browser extension or administrator installation is
needed for reading, dictionary lookup, notes, saved translations and prompt creation.
A normal browser opens at http://127.0.0.1:18745. The supplied runtime is Windows x64.
The personal bundle contains 17 dictionary collections and their supplied media.
Keep the complete folder together; dictionary paths remain valid after moving it.

## Translation engines

Open **Translation engine · 翻譯引擎**, choose an engine and model/package, then
click **Use selection**. Your engine selection is saved with the reading library.
Paste text and click **Open + translate locally**, or translate the current saved text.

- **Argos Translate · offline CPU:** bundled in the updated personal portable folder.
  Requires no LM Studio, LLM, GPU, installation or internet on the destination PC.
  Uses Japanese→English 1.1 and English→Traditional Chinese 1.9; the Chinese result
  goes through English, then OpenCC normalizes it to Traditional Chinese/Taiwan forms.
  This is machine translation, so names, nuance and wording may need correction.
  The bundled Argos runtime, dependencies and sentence models live in `translation/argos/`.
- **LM Studio · local LLM:** uses your LM Studio server on port 1234. Select a downloaded
  model and click **Use selection** to load it. This option still requires LM Studio
  and the chosen LLM on that laptop. No LLM is bundled.
- New libraries prefer Argos when its offline pack is present. Saved engine selections
  are respected; the app does not silently switch providers if one becomes unavailable.
- **Auto** fills missing translations. Manual translation replaces the displayed text's
  translations if the source/results did not change during the request. Originals
  remain saved on failure. Switching engines does not retranslate old entries by itself.
- Maximum 12,000 source characters per block. Longer passages are processed in chunks;
  all chunks must finish before results are saved. Argos starts a separate CPU process
  per job, so a cold start can take a few seconds. A very long job times out after 15 minutes.
- Dictionary lookup and learning prompts are independent of either engine. Copy a
  learning prompt into any chat you prefer; online chats require internet and your login.

See [ARGOS.md](ARGOS.md) for package details and adding future engines.

Select up to 10 characters to search automatically. Hold Shift while selecting
or right-drag to copy without triggering a lookup. Typed dictionary searches can
be longer. Inflected words may need to be searched by their dictionary form.

## Carry your workspace

Use **Save and close reader**, wait for its launcher window to close, then copy
this entire folder to USB and onto the other laptop. `data/reading/` holds your
texts, notes, translations, backups and preferences. Appearance and dictionary
choices are saved to disk and restored in the next browser. Browser sessions,
logins and synthetic voices are not copied. Recorded dictionary audio is included
where supplied. Copies on two laptops are independent, not automatically synced.
Use one latest copy to avoid conflicting journals.

The updated folder contains the dictionaries plus the Argos engine pack. Check its
size before copying; allow at least 12 GB free. A 16 GB or larger USB drive is practical,
preferably exFAT or NTFS. Copy
it to the laptop's internal drive for faster searches. See [START HERE.md](START%20HERE.md).

## Optional OBS and separate libraries

**Start JP Game Reader.cmd** enables OBS capture. OBS and Windows Japanese OCR
support are required only for this mode. Keep a windowed OBS projector's dialogue
area visible and adjust the crop settings. Direct OBS frame capture is future work.

For separate libraries: `runtime\python.exe launch.py --profile my-novel`.
For a game: `runtime\python.exe launch.py --profile my-game --obs`.
Close the running reader before switching libraries. Use a different `--port`
only if intentionally running multiple libraries.

## GitHub source vs personal USB bundle

GitHub contains application source, documentation and tests. Purchased dictionaries,
personal text, credentials, Argos packages and runtime binaries are excluded. The personal USB
folder contains the runtime plus all dictionary files referenced by your original
index, including source media and CSS. It starts with an empty reading library;
your original Fortune Weave installation and saved texts are untouched.

For source-only installs, use Python 3.12+ and run `python launch.py`. An existing
compatible dictionary index can be set with `JP_READER_DICTIONARY_INDEX`.
`build_portable.py --help` describes building a personal bundle from your own index.
The builder checks the official Python runtime checksum, verifies copied files,
and rewrites dictionary paths relative to the bundle.

## Verification

Run `python -m unittest -v test_profiles test_reader test_translation_backends` for profile, paste, preferences,
chunked translation, missing-model and relative-path checks. Run
`runtime\python.exe verify_bundle.py` in a personal bundle to verify every copied
dictionary file and sample definitions/media. See [ROADMAP.md](ROADMAP.md).
