"""Direct local dictionary access: purchased MDX/MDD files and imported Yomitan zips.

No LogoVista process or installation. Yomitan dictionaries use codes starting with
YT_ (see yomitan_library.py); everything else is an MDX dictionary.
"""
import mdict_library
import yomitan_library


def _yomitan(code):
    return isinstance(code, str) and code.startswith('YT_')


def catalog():
    items = [{**d, 'kind': 'term', 'source': 'mdx'} for d in mdict_library.dictionaries()]
    return items + yomitan_library.dictionaries()


def catalog_status():
    return {k: yomitan_library.status[k] for k in ('importing', 'message', 'error')}


def search(word, codes=None):
    word = word.strip()
    if not word or len(word) > 120:
        raise ValueError('Enter a word of 1–120 characters.')
    if codes is not None and (not isinstance(codes, list) or any(not isinstance(c, str) for c in codes)):
        raise ValueError('Invalid dictionary selection.')
    results = [{**d, 'kind': 'term'} for d in mdict_library.search(word, codes)]
    try:
        extra, frequencies = yomitan_library.search(word, codes)
    except Exception as e:  # a half-written or damaged Yomitan index must not break MDX lookups
        extra, frequencies = [], []
        if yomitan_library.available():
            results.append({'code': 'YT_ERROR', 'name': 'Yomitan', 'kind': 'term', 'count': 0, 'exact': False, 'entries': [], 'error': str(e)})
    return {'dictionaries': results + extra, 'frequencies': frequencies}


def entry(code, entry_id, anchor=''):
    if _yomitan(code):
        return yomitan_library.entry(code, entry_id)
    return mdict_library.entry(code, entry_id)


def resolve(code, word):
    if _yomitan(code):
        return yomitan_library.resolve(code, word)
    return mdict_library.entry(code, word=word)


def labels(code, ids):
    if _yomitan(code):
        return yomitan_library.labels(code, ids)
    return mdict_library.labels(code, ids)


def media(code, name):
    if _yomitan(code):
        return yomitan_library.media(code, name)
    return mdict_library.media(code, name)
