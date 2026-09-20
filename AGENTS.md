# Working on this reader

This is the shared base for Japanese learning across pasted text, books, articles and games. Read README.md and
ROADMAP.md before changing it. Keep paste-first reading and offline dictionaries usable without OBS or LM Studio.
Extend this application with profiles and adapters;
avoid creating game-specific copies of the whole codebase.

- Keep personal journals, dictionaries, model files, screenshots and secrets out of Git.
- Preserve original Japanese text and user edits through capture/translation changes.
- Do not point tests at a real journal, stop a user's running reader, or migrate their
  original Fortune Weave installation as a side effect of a code change.
- Run `python -m unittest -v test_profiles test_reader` for profile or journal lifecycle changes.
- Keep the server bound to loopback and preserve Host/Origin checks.
- Current capture requires a visible OBS projector; direct OBS capture is planned,
  not implemented. Keep documentation honest about tested compatibility.
- Prefer game-neutral code and per-profile settings to hard-coded titles or paths.
