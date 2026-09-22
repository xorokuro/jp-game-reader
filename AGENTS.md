# Working on this reader

- The user prohibits GitHub Actions usage because their included minutes are exhausted.
  Do not enable, dispatch, rerun, or add automatic workflow triggers. Keep changes
  code-only or validate locally; do not use a paid cloud build substitute. Any future
  Actions usage requires new explicit user authorization. Use [skip ci] on code commits.
  On 2026-09-22 the user authorized a one-off source-only public build in
  xorokuro/japanese-reader-ios-build, followed by disabling Actions and making that
  repository private again. This does not authorize builds in private repositories
  or ongoing automated builds.

This is the shared base for Japanese learning across pasted text, books, articles and games. Read README.md and
ROADMAP.md before changing it. Keep paste-first reading and offline dictionaries usable without OBS or LM Studio.
Extend this application with profiles and adapters;
avoid creating game-specific copies of the whole codebase.

- Keep personal journals, dictionaries, model files, screenshots and secrets out of Git.
- Preserve original Japanese text and user edits through capture/translation changes.
- Do not point tests at a real journal, stop a user's running reader, or migrate their
  original Fortune Weave installation as a side effect of a code change.
- Run `python -m unittest -v test_profiles test_reader test_translation_backends` for profile or journal lifecycle changes.
- Keep the server bound to loopback and preserve Host/Origin checks.
- Current capture requires a visible OBS projector; direct OBS capture is planned,
  not implemented. Keep documentation honest about tested compatibility.
- Prefer game-neutral code and per-profile settings to hard-coded titles or paths.

- Translation providers are registered in translation_backends.py. Keep Argos fully
  offline during normal use, with all model/cache paths under its portable folder.
