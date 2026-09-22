# Unified desktop reader

The desktop reader now combines the Fortune Weave desktop design and controls with
Japanese Reader's portable backend. Use one reading block and one dictionary panel.

- **Paste text** opens a temporary passage. **Type / edit text** opens its editor.
  Selecting words in the reading block searches your dictionaries.
- **Save this text** saves that passage explicitly. It does not turn on auto-save.
- **Read from** selects Pasted text, OBS projector, or a visible Game window.
  Press **Use this source**, then Recognize or enable automatic recognition.
  Switching sources pauses capture and preserves the passage currently being read.
- Capture uses Windows Japanese OCR on visible pixels. Keep the selected window's
  dialogue area uncovered. This is not game-memory text hooking, background capture,
  or a promise of support for every game's rendering mode. OBS remains the fallback.
- Manual retries require three stable OCR samples. Full-screen recognition remains available.
- **Automatically save new captured text** is off at startup. Enable it for saved
  capture history, automatic translations, and batch collection. Existing library
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
