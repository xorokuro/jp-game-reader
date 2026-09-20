# Japanese Reader

A general-purpose, local Japanese reading workspace. Paste articles, novels,
messages or game dialogue; select words for automatic dictionary search; save
notes; copy learning prompts; optionally translate with a local LLM.
OBS is an optional input, not a requirement.

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

## Translation and prompts

- **Local AI available:** start LM Studio's server on port 1234. The reader detects
  it and prefers an already loaded model on first use. Open **Optional local AI
  translation** to select/load another downloaded model. Click **Open + translate
  locally**, or translate the currently displayed text. Automatic translation is
  opt-in. Text stays on this computer.
- **No local AI:** offline reading and dictionaries still work. Click **Copy learning
  prompt** or **Copy word explanation prompt**, then paste into your preferred AI
  chat. Using an online chat requires internet and your own login. No extension is
  needed. The existing structured study prompt can produce translations to paste
  back into the journal using **貼上並儲存翻譯**.
- Up to 12,000 source characters per pasted block. Longer translation inputs are
  processed in chunks; model quality/context limits still apply. All chunks must
  complete before translation is saved. Original text remains saved on failure.
- A local model and LM Studio are **not bundled**. A laptop without them cannot
  produce local AI translations until they are installed; all other core reading
  features remain usable.

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

The full personal folder is approximately 8.5 GB. Use a USB drive with at least
10 GB free (a 16 GB or larger drive is practical), preferably exFAT or NTFS. Copy
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
personal text, credentials and runtime binaries are excluded. The personal USB
folder contains the runtime plus all dictionary files referenced by your original
index, including source media and CSS. It starts with an empty reading library;
your original Fortune Weave installation and saved texts are untouched.

For source-only installs, use Python 3.12+ and run `python launch.py`. An existing
compatible dictionary index can be set with `JP_READER_DICTIONARY_INDEX`.
`build_portable.py --help` describes building a personal bundle from your own index.
The builder checks the official Python runtime checksum, verifies copied files,
and rewrites dictionary paths relative to the bundle.

## Verification

Run `python -m unittest -v test_profiles test_reader` for profile, paste, preferences,
chunked translation, missing-model and relative-path checks. Run
`runtime\python.exe verify_bundle.py` in a personal bundle to verify every copied
dictionary file and sample definitions/media. See [ROADMAP.md](ROADMAP.md).
