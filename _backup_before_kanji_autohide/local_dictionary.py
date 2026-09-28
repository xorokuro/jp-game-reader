"""Direct local MDX/MDD access, with no LogoVista process or installation."""
import mdict_library

def catalog():return mdict_library.dictionaries()
def search(word,codes=None):
    word=word.strip()
    if not word or len(word)>120:raise ValueError('Enter a word of 1–120 characters.')
    if codes is not None and (not isinstance(codes,list) or any(not isinstance(c,str) for c in codes)):raise ValueError('Invalid dictionary selection.')
    return {'dictionaries':mdict_library.search(word,codes)}
def entry(code,entry_id,anchor=''):return mdict_library.entry(code,entry_id)
def media(code,name):return mdict_library.media(code,name)
