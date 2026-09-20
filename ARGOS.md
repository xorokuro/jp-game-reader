# Argos offline translation

The personal Windows x64 pack includes Argos Translate 1.11.0 and its dependencies,
a separate Python 3.13 runtime, Japanese→English 1.1 and English→Traditional Chinese
1.9 model packages, MiniSBD Japanese/English sentence models, and OpenCC s2twp.
It runs on the CPU and does not require an LLM server. Model quality is independent
of the dictionary collection. Traditional Chinese goes through English.

## Use

1. Open **Translation engine · 翻譯引擎**.
2. Choose **Argos Translate · offline CPU** and its language package.
3. Click **Use selection**, then **Open + translate locally** or **Translate this text**.

Choose **LM Studio · local LLM** in the same selector to return to your LLM.
Engine changes are blocked during active translation. Already saved translations
are not changed merely by switching engines. Automatic translation remains opt-in.

## Portability and verification

Keep `translation/argos/` together with the reader. It includes `runtime/`,
`site-packages/`, `packages/`, `data/` (sentence models), and an integrity inventory
in `ready.json`. Cache and configuration stay inside this folder. Normal worker
processes reject network connections; model downloads happen only during bundle
preparation. The main reader can still connect to a local LM Studio server when
that engine is selected.

`argos_worker.py --prepare` is a build-time switch that allows the initial sentence
model downloads. Do not use it for ordinary reading. The released personal pack
was warmed and then translated test passages with network connections blocked.
Application-local Microsoft runtime DLLs are included in the private pack;
the other physical laptop has not been tested.

## Rebuild or extend

Dependencies are pinned in `argos-requirements.txt` for the Windows CPython 3.13
pack. Install them into an isolated folder, not the user's global Python. Use the
official language packages from the Argos index, preserve their metadata and
licenses, configure the portable paths before importing Argos, then prepare and
test offline with the worker. `build_portable.py --argos-pack PATH` includes a
prepared pack when creating a new portable reader.

Add future providers to `translation_backends.ENGINES`. Each provider supplies
`options`, `ready`, `select`, and `translate`. Translation results use `en-US` and
`zh-Hant` keys; journal storage and stale-result protection remain shared. Keep
heavy imports in a worker so missing dependencies cannot prevent reading or lookup.

Upstream:
- https://github.com/argosopentech/argos-translate
- https://github.com/argosopentech/argospm-index
- https://github.com/yichen0831/opencc-python

The private portable pack contains binaries and models; GitHub contains only the
reader source, integration, dependency list, documentation and tests.
