# Japanese Reader for iPhone and iPad

Native SwiftUI companion to the Windows reader. Requires iOS/iPadOS 17.4 or newer.
Reads the same portable dictionary index and original MDX/MDD files directly,
using SQLite and zlib. No PC connection, Python, OBS, or LM Studio is needed for
reading, dictionary lookup, notes, or prompt creation after importing dictionaries.

## Install from Windows

The personal deliverable folder contains `JapaneseReader.ipa` and
`Japanese-Reader-iPhone-Dictionaries.zip`. The IPA is an unsigned device build;
opening it in Files alone does not install it.

1. Install **AltStore Classic** using its official Windows instructions:
   https://faq.altstore.io/altstore-classic/how-to-install-altstore-windows
   Follow its prerequisites for Apple iTunes/iCloud, connect the iPhone, trust the
   computer, and enable Developer Mode when requested. Enter your Apple account
   only in the installation software; it is never needed by Japanese Reader.
2. Save `JapaneseReader.ipa` to the iPhone's Files app (Google Drive → Share →
   Save to Files is one route). In AltStore, open **My Apps**, tap **+**, and choose
   the IPA. Keep AltServer running on your Windows computer during installation.
3. Open **Japanese Reader** once so its folder is created in Files.
4. Download `Japanese-Reader-iPhone-Dictionaries.zip` to local iPhone storage.
   Allow **at least 20 GB free** while downloading/unpacking; the installed
   dictionaries occupy about 8.4 GB. If using the app's copying import instead of
   moving the folder in Files, allow about **30 GB** temporarily.
5. In Files, tap the ZIP to unpack it. Find the inner folder named **dictionaries**
   containing `mdict-index.sqlite3` and `sources`. Move that folder into
   **On My iPhone → Japanese Reader**. Do not rename it or move only the index.
   If Files wraps extraction in another folder, move its inner `dictionaries`.
   Apple ZIP instructions: https://support.apple.com/102532
6. Open the reader → **Library → Refresh dictionaries**. It should list **17**
   collections. Alternatively choose **Import dictionaries folder** and select
   the extracted folder; this copies it and requires extra free space.
7. After confirming lookups work, the downloaded ZIP and extra extracted copy
   may be removed to reclaim space. Keep the installed `dictionaries` folder.

Free Apple signing expires after **7 days**. Keep AltServer available and refresh
the app through AltStore before expiry. This is an Apple signing limitation, not
a dictionary download requirement. Re-signing an update with the same app ID
should preserve its data; do not uninstall as an update step.
Apple's limits: https://developer.apple.com/help/account/basics/about-your-developer-account

## Use

Paste into **Read → Paste / edit**, tap **Read**, then long-press/select Japanese
in **Read / select words**. Matches appear underneath; tap one for its definition.
You can also type a word in **Look up**. Search supports exact matches and prefix
suggestions, not Japanese conjugation analysis: try the dictionary form if needed.

**Auto-save passages** defaults to **off**. Pasted text stays temporary until you
choose **Save**. With the toggle on, tapping **Read** saves the complete passage;
typing/pasting alone never creates a stream of saved drafts. The toggle is remembered
after restarting. Turning it off does not delete earlier saved passages.

**Save** always lets you keep a single passage, even with auto-save off. Library shows
saved passages first, with dates, notes, and a search field. Swipe a saved passage left
to delete it, or use **Edit**. **Undo delete** restores the most recent deletion during
the current session. **Delete all saved passages** asks before removing all passages
and notes. Deleting saved passages does not remove dictionary files.

**Export saved texts** opens the iPhone share sheet for the JSON library, ready to save
to Files or your preferred storage app. It includes saved passages and notes only.

**Copy learning prompt** copies the passage and selected word for any AI app.
**Translate** uses Apple's system translation panel; Apple may require language
downloads. Its translation capability and available languages depend on the phone.
The Windows Argos runtime and LM Studio do **not** run inside this iOS app.
No background PC translation service is required or configured.

Dictionary-authored scripts and external network access are disabled. An app-owned isolated selection observer supports automatic lookup without changing the selected range. Supplied
images/fonts and supported audio formats are read locally. iOS may not play every
legacy audio format (for example Speex). Source dictionaries that rely on scripts
can display differently. Entry links open a new dictionary search.

## Back up / transfer

Copy `reading-library.json` from **Files → On My iPhone → Japanese Reader** to
Drive or another safe location. Deleting the app deletes its local data, including
imported dictionaries. Windows journals and iPhone libraries do not automatically
sync; this release uses a separate iPhone reading library.

## Build and verification

On a Mac with Xcode and Homebrew: `bash ios/build.sh` produces
`ios/build/JapaneseReader.ipa`. The private GitHub workflow builds on macOS,
runs a synthetic dictionary-engine test, and checks reading/library persistence
and missing-dictionary handling in an iPhone simulator. Its artifact expires in
14 days; the local delivered copy does not expire, though Apple signing does.

The full personal dictionary ZIP is created locally by `package_dictionaries.py`;
all 127 files and 17 collections are included, with a SHA-256 manifest and full
ZIP CRC verification. Dictionaries are never included in Git or CI artifacts.
Physical iPhone installation, full-size import, Apple translation, and real-device
media playback still require testing on the user's iPhone.

## Version 1.2

A system Paste button inserts clipboard text without opening the keyboard. The reading screen scrolls, keeps a 220-point editor, and uses a compact title. Read and Done are available above the keyboard. Install the updated IPA over the existing app with the same Apple account to preserve dictionaries and saved passages.

### Colors and dictionary choices
Library → Colors & contrast offers any accent color and an optional custom reading background. Reading text chooses black/white for contrast; accent links adjust for system light/dark surfaces. Dictionary entry HTML retains its own styles.

Library offers per-dictionary toggles and Edit → drag handles for lookup order. Preferences persist. Add dictionary pack imports another indexed folder alongside existing dictionaries, without replacing or redownloading them. Packs contain mdict-index.sqlite3 plus their referenced source files; raw MDX/MDD alone are not yet indexed on the phone. Use export_dictionary_pack.py to export a single dictionary from a portable indexed collection. Extract its ZIP in Files, then select dictionary-pack using Add dictionary pack.

## Version 1.3
Automatic selection lookup no longer resigns the reader's first responder. Adjusting a highlight searches the new selection while keeping its handles. Dictionary entry pages also support selection lookup, with results below the original page. Selection-triggered searches do not dismiss or reload the entry; opening a result explicitly navigates to that entry.
