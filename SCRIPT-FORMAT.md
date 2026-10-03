# Loading visual-novel scripts / 台本匯入格式

The **台本 · Script** tab supports any visual novel, not only STEINS;GATE.
It reads an already extracted, ordered UTF-8 JSON script. It does not open game
executables, encrypted archives, PDFs, EPUBs, CSVs or raw engine scripts directly.
Convert those into the format below first.

Need an AI assistant to extract your local game files? Copy the
[ready-to-use extraction prompt](EXTRACT-SCRIPT-PROMPT.md) and fill in your folders.

## Load and switch scripts

1. Open **台本 · Script → 載入台本 · Load script** and select a `.json` file.
2. Choose a loaded title in the **Script** dropdown to switch novels. Your reading
   position is remembered separately for each title. Switching clears search filters.
3. Use search, chapter/path filters, line numbers and dictionary lookup as usual.
4. **台本格式與範例 · Script format → 下載範例 JSON** downloads a working example.

Scripts are validated before saving. A bad file reports its first invalid line;
it does not replace or delete your existing scripts. A duplicate `script_id` is
rejected. To load a different edition, give it a new ID, such as `my-novel-v2`.
No application restart is needed after importing.

## Minimal example

```json
{
  "script_id": "my-novel",
  "game": "My Visual Novel",
  "rows": [
    {"ja": "今日はいい天気ですね。"},
    {"ja": "窓を開けると、涼しい風が入ってきた。"}
  ]
}
```

Use standard JSON: double quotes, no comments, no trailing commas. Save as UTF-8
(a UTF-8 BOM is accepted). Use `\n` inside a string for a line break and `\"`
for a literal quotation mark. Array order is reading order; the reader does not
sort by ID, chapter name or filename. This is a linear transcript, not a branching
visual-novel player. Put routes in the order you want to read or import them as
separate script IDs.

## Complete example

The following dialogue is an original sample, not an extract from a game.

```json
{
  "script_id": "sample-novel",
  "game": "Sample Visual Novel",
  "rows": [
    {
      "source": "chapter01",
      "id": "001",
      "kind": "dialogue",
      "speaker": "春",
      "ja": "今日はいい天気ですね。",
      "en": "The weather is lovely today.",
      "zh": "今天天氣真好。"
    },
    {
      "source": "chapter01",
      "id": "002",
      "kind": "dialogue",
      "speaker": "",
      "ja": "窓を開けると、涼しい風が入ってきた。"
    }
  ]
}
```

## Fields

| Field | Required? | Meaning |
| --- | --- | --- |
| `game` | Yes | Non-empty display title, up to 200 characters. Japanese and Chinese titles work. |
| `script_id` | No, recommended | Unique identifier, 1–64 lowercase ASCII letters, digits, `_` or `-`; begin with a letter or digit. If omitted, a stable identifier is generated from the title. `auto`, `off` and Windows device names such as `con` are reserved. |
| `rows` | Yes | Array of 1–200,000 line objects, in reading order. |
| `rows[].ja` | At least one language | Japanese text. English-only or Chinese-only lines also work; provide non-empty `ja`, `en` or `zh`. |
| `rows[].en` | No | English translation of this same line. Omit if unavailable. |
| `rows[].zh` | No | Traditional Chinese translation of this same line. Omit if unavailable. |
| `rows[].speaker` | No | Speaker name; omitted or empty for narration. |
| `rows[].source` | No | Chapter, route or original script filename. Defaults to `main`. Used by the path filter. |
| `rows[].id` | No | Original line ID. Text or integer; defaults to its 1-based array position. |
| `rows[].kind` | No | `dialogue`, `mail`, `tip`, `ui` or `extra`. Defaults to `dialogue`; use this for narration too. |

Each `(source, id)` pair must be unique **within a script**. Neither field may
contain `|`. Different scripts may reuse chapter names and line IDs: reading
links and OCR source links identify the owning script as well as the line.
Except for numeric line IDs, fields in the table must be strings, not `null`,
arrays or objects. Omit unavailable fields or use empty strings.

The upload limit is **64 MiB**, with a maximum of **100,000 characters per row
field**. Large works can be split into routes/volumes with distinct `script_id`s.
Translate and align lines before importing: the importer does not translate or
align separate language files. Unrecognized metadata is ignored by the importer.

Use visible text rather than HTML or engine control codes. The reader removes
short angle-bracket engine tags; the legacy `<tips,123,visible word>` form retains
the visible word. Standard JSON text and line breaks are the recommended format.

## Storage and moving to another laptop

The default reading library saves imported scripts in
`data/reading/scripts/<script_id>/script.json`. For another profile or a custom
`--database`, imports go in `scripts/` beside that database. Imports remain after
restarting, and are not uploaded to GitHub. Copy the library's script folders
when moving your reading materials to another laptop.

Existing folder-based scripts still work:

- `<reader folder>/scripts/<folder>/script.json`
- Paths listed one per line in `<reader folder>/scripts/paths.txt`
- Paths in `JP_READER_SCRIPTS`, separated by `;` on Windows

Those legacy paths are scanned when the reader starts. Restart after manually
adding folders. UI imports appear immediately. Prefer the documented object
format for new scripts; the legacy array-only format is supported only for
existing folder-based loads. Do not put personal game scripts into Git.

## Optional annotations and OCR matching

Advanced folder-based use can place `annotations.json` beside `script.json`:

```json
{"items": {"chapter01|001": {"ja_tr": "今天天氣真好。", "ruby": "今日（きょう）はいい天気（てんき）ですね。"}}}
```

Annotation keys use `source|id` within that script. The upload button imports the
script JSON only; add optional annotation files locally afterward. The importer
does not generate study notes.

In **Filters → OCR 對照台本**, choose a title explicitly to match OCR against that
script. Only `dialogue` and `mail` rows with Japanese text participate. Automatic
game-window matching is a best effort based on the script ID and window title;
use explicit selection when a title cannot be recognized.
