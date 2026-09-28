"""Isolated CPU translator. Normal operation forbids network connections."""
import argparse
import json
import os
from pathlib import Path
import sys


def configure(home, allow_download=False):
    home=Path(home).resolve()
    for key,value in {
        'ARGOS_PACKAGES_DIR':home/'packages',
        'XDG_DATA_HOME':home/'data',
        'XDG_CACHE_HOME':home/'cache',
        'XDG_CONFIG_HOME':home/'config',
        'ARGOS_DEVICE_TYPE':'cpu',
        'ARGOS_COMPUTE_TYPE':'int8',
        'ARGOS_CHUNK_TYPE':'MINISBD',
        'ARGOS_INTER_THREADS':'1',
        'ARGOS_INTRA_THREADS':'4',
    }.items():os.environ[key]=str(value)
    if not allow_download:
        def offline(event,args):
            if event in ('socket.connect','socket.getaddrinfo'):
                raise OSError('Argos offline mode: a required model file is missing. Repair the portable Argos pack.')
        sys.addaudithook(offline)


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--home',required=True)
    parser.add_argument('--prepare',action='store_true',help='Allow first-time sentence-model downloads while preparing a bundle')
    args=parser.parse_args()
    configure(args.home,args.prepare)
    from argostranslate.translate import get_translation_from_codes
    from opencc import OpenCC
    traditional=OpenCC('s2twp')
    request=json.load(sys.stdin)
    chunks=request.get('chunks')
    if not isinstance(chunks,list) or not chunks or any(not isinstance(t,str) for t in chunks):
        raise ValueError('Invalid translation input.')
    japanese_to_english=get_translation_from_codes('ja','en')
    english_to_traditional=get_translation_from_codes('en','zt')
    english=[];chinese=[]
    for text in chunks:
        en=japanese_to_english.translate(text)
        zh=traditional.convert(english_to_traditional.translate(en))
        if not en.strip() or not zh.strip():raise ValueError('Argos returned an empty translation.')
        english.append(en);chinese.append(zh)
    print('JP_READER_RESULT='+json.dumps({'en-US':'\n\n'.join(english),'zh-Hant':'\n\n'.join(chinese)},ensure_ascii=True),flush=True)


if __name__=='__main__':
    try:main()
    except Exception as error:
        print('JP_READER_RESULT='+json.dumps({'error':str(error)},ensure_ascii=True),flush=True)
        raise SystemExit(1)
