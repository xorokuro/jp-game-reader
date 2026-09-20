# General Japanese reading foundation

## Architecture

Pasted text → reading library → offline dictionaries / optional local AI / learning prompts.

Optional game / console → OBS → OCR → the same reading library.

Keep a single repository and application for all games. Add profiles and adapters
instead of copying or forking the whole application per game. Use GitHub template
repositories only for genuinely different applications built from this foundation.

## Delivered portable reader

- Selectable Argos Translate and LM Studio providers; engine choice persists per library.
- Bundled offline CPU translation routes ja→en and en→zt, with Traditional Chinese normalization.
- Provider registry allows future engines without rebuilding the reading interface.

- Paste-first reading with offline auto dictionary lookup and copyable prompts.
- Optional local LLM translation with long-block chunking and no-model support.
- Windows runtime, 17 personal dictionaries, relative paths and integrity manifest.
- Appearance/dictionary preferences travel with the folder.

## Earlier baseline

- Existing reader source preserved in version control with private runtime data excluded.
- Neutral branding, portable launcher, and separate per-game database/crop/model settings.
- Existing local OCR, review, journal, notes, local translation and dictionary reader.

## Optional game capture improvements

Add an authenticated, local OBS WebSocket capture adapter using
`GetSourceScreenshot`, keeping projector capture as a fallback. Let the user
select the OBS source from a preview and draw the dialogue region. Keep passwords
outside version control. Poll at a modest rate and skip unchanged frames.
This should remove the need for an unobstructed projector, provided OBS is still
producing frames for the source. Test source inactivity, black frames, disconnects,
reconnects and resolution changes before making it the default.

Official protocol: https://github.com/obsproject/obs-websocket/blob/master/docs/generated/protocol.md
OBS game capture guide: https://obsproject.com/kb/game-capture-source

## Friendly reading libraries

Replace the terminal selector with a game library. Store display name, OBS source,
normalized crop rectangles, speaker region, OCR language/orientation, and timing.
Show active game prominently. Allow separate presets for dialogue, menus and
vertical text. Profile switching must stop capture and drain translation jobs
before changing the active journal. Store sentence origins explicitly if later
merging profiles into a single searchable library.

## Better learning flow

Add a global capture hotkey, quick correction, furigana, word segmentation,
dictionary hover, and optional sentence audio/screenshot attachment. Add Anki
export with Japanese, reading, meaning, context, and source game. Keep study export
deliberate so accidental OCR does not flood flashcards. Preserve original OCR
alongside edits. Add a dictionary import/setup flow without bundling dictionaries.

## Swappable OCR and translation

Retain Windows OCR as the lightweight default. Define OCR adapters returning text,
boxes and confidence, then evaluate alternatives on user-supplied game screenshots.
Support local translation and optional official cloud APIs through one queue;
cloud use should clearly identify which text leaves the PC. Add bounded context
and game glossaries to improve names and speaker consistency.

## Distribution follow-ups

Add a setup checker, signed/packageable Windows release, versioned data migrations,
automated backup/restore checks, and a tested update flow. Keep application updates
separate from personal data. Test at least a normal VN, stylized RPG, vertical-text
game, and console capture-card source. Do not claim universal game support from
one successful test.

## Completion checks for future changes

- A fresh install starts without dictionaries, models or credentials.
- The same sentence in two games cannot mix their notes or translation jobs.
- Switching/resizing an OBS source does not silently capture the wrong region.
- A covered projector still works with the direct OBS adapter (future work).
- Failed OCR or translation never deletes the original sentence.
- No personal journals, dictionary content, credentials or screenshots enter Git.
