# Unified desktop reader

The desktop reader now combines the Fortune Weave desktop design and controls with
Japanese Reader's portable backend. Use one reading block and one dictionary panel.

- **Paste text** opens a temporary passage. **Edit text** enables typing and corrections in the same block; it is off by default.
  Selecting words in the reading block searches your dictionaries.
- **Save text / corrections** saves that passage explicitly. It does not turn on auto-save.
- **Read from** selects Pasted text, OBS projector, or a visible Game window.
  Press **Use this source**, then Recognize or enable automatic recognition.
  Switching sources pauses capture and preserves the passage currently being read.
- Capture uses Windows Japanese OCR on visible pixels. Keep the selected window's
  dialogue area uncovered. This is not game-memory text hooking, background capture,
  or a promise of support for every game's rendering mode. OBS remains the fallback.
- Manual retries require three stable OCR samples. Full-screen recognition remains available.
- **Automatically save new captured text** defaults on for OBS and game-window
  capture at startup and when selecting a source. Pasted passages require explicit saving. Existing library
  entries remain on disk. Temporary passages are not a permanent journal.
- **A / D** moves between dictionaries with results, skipping empty/error dictionaries
  and wrapping around. **Left / Right** and **Ctrl+Z / Ctrl+Shift+Z** navigate search history
  outside text fields. Shift selection and right-drag still select without lookup.
- Desktop appearance, dictionary zoom/order, ChatGPT/Claude helper integration,
  saved translation import, notes and batch controls are retained.
- LM Studio and Argos provider support is included. Argos requires its separate
  runtime/model pack; this source update does not duplicate or download that pack.

## Existing Fortune Weave installation

Start Reader.cmd detects an existing saved_sentences/sentences.sqlite3 and reuses
that library on port 18744. New portable installations use data/reading on port 18745.
An explicit --profile selects a separate library. The existing Start Live Reader.cmd
shortcut continues to work through restart_reader.py and reuses the running reader.
The update does not copy dictionaries or move personal journal records.

## iOS later

The existing native SwiftUI app under ios/ is unchanged. Its dictionary format and
reading/library concepts remain compatible. Desktop HTML/CSS is deliberately separate
from native SwiftUI/Palette styling, allowing an independent iPhone/iPad redesign.
No iOS build or GitHub Actions run is part of this merge.

## Validation

Run python -m unittest -v test_profiles test_reader test_translation_backends test_unified.
Validate JavaScript syntax with node --check. Browser checks cover paste, explicit save,
dictionary definitions and keyboard switching. Visible-window OCR was checked against
an OBS projector; native game rendering modes require testing with the actual game.

## Appearance and shortcuts (washi redesign)

- **主題 · Appearance** (top-right) opens a drawer with eight palette presets
  (和紙, 桜, 海辺, 墨, 抹茶, 夜の縁側, 紅葉, 星空), hand-drawn background doodle amount,
  paper grain, drifting petals, Japanese typeface (教科書體 / 黑體 / 明朝), sizes and
  optional custom paper/card/accent colours. Settings persist in `data/reading/preferences.json`.
  Dictionary entries follow the active palette.
- The dictionary sits beside the reading text, fills the window height and stays in view
  while scrolling; its definition page is level with the Japanese text box.
- Outside text fields: **R** recognizes the dialogue area, **Ctrl+R** recognizes the whole
  game screen (instead of reloading) while a capture source is active, **Q** cancels a
  recognition in progress (`POST /api/retry-cancel`), **?** shows all shortcuts.
- Setup panels are collected as tiles under 道具箱 · Tools & settings.

## 台本 · Game scripts

- List script folders (each with `script.json`, optional `annotations.json`) in
  `scripts/paths.txt`, one per line, or put them under `scripts/<name>/`. They stay out of Git.
- The **台本** tab beside 読む reads, searches (JA / EN / 繁中, Ctrl+K), filters by kind,
  language coverage, path or annotated lines, and jumps to `#n`. Lines load as you scroll.
- Selecting text in a line looks it up in your dictionaries. Each line can be opened in the
  reading card (and saved with its official translations), copied, or sent with a prompt
  to ChatGPT/Claude. Annotated lines show 精讀註解 (ruby, 直譯, 語彙, 文法), reloaded when
  `annotations.json` changes.
- OCR matching: captured text that matches the chosen script (auto = by game window title)
  is replaced by the exact script line and receives the official EN / 繁中 translations.

## Panel size and dictionary pages (book-style redesign)

- The reading/台本 card and the dictionary share one height. By default they fill the window
  under the top bar. Drag the grip under the panels to make both longer (up to 6000 px);
  drag the grip between them to give the dictionary more width. Double-click a grip, or
  focus it and use the arrow keys, to reset/adjust. Saved as `jp-reader-workspace-v1`.
- Dictionary entries keep each publisher's own layout (headword sizes, indents) and are
  re-coloured to the palette: serif book type, large headword, muted labels, and examples
  as an indented ink-blue phrase with the translation on the next line (`--e-ex`).
  **明 / ゴ** beside the zoom buttons switches serif and gothic (`jp-reader-dict-font`).
- Entry pages carry `data-dict="<code>"` on `<body>` for per-dictionary tweaks in
  `dictionary-entry.css`. Dictionary tabs show a short name; the full title is the tooltip.

## Yomitan dictionaries

- Yomitan/Yomichan `.zip` dictionaries work next to the MDX files. List them in
  `dictionaries/yomitan-paths.txt` (files or folders, `#` skips a line) or drop them into
  `dictionaries/yomitan/`. When the reader starts, new or changed zips are imported in the
  background into `dictionaries/yomitan-index.sqlite3` (Pixiv takes a minute or two); the
  chooser shows progress. `Import Yomitan dictionaries.cmd` runs the same import by hand.
  After importing, the zips are no longer needed; a missing source list never deletes the index.
- Word dictionaries (JMdict, Pixiv, surasura, 複合語起源 …) get their own tabs with the book
  styling: furigana headword, numbered senses, tag pills (hover for meaning), examples in
  `--e-ex`. Links inside an entry (Pixiv related articles, JPDB words) search every dictionary.
- All kanji dictionaries merge into one **漢字 · Kanji** tab: one card per kanji in the word
  (音/訓, 常用・学年・JLPT・画数・漢検 badges, kanji frequency ranks, JPDB reading shares and
  common words, 部首・構成, 字体/異体字, ja/zh Wiktionary, KANJIDIC index numbers).
- Word-frequency lists (青空文庫) are not tabs: their rank appears as a chip beside the word
  in the dictionary header (green = common ≤5,000, amber ≤20,000, grey = rarer).
- New Yomitan dictionaries are ticked once when they first appear (name lists such as
  Nico/Pixiv start unticked). Codes start with `YT_`; see `yomitan_library.py`.
