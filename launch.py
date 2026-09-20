"""Launch a portable reading library; OBS capture is optional."""
import argparse
import os
from pathlib import Path
import re
import socket
import subprocess
import sys
import json
import urllib.request
import webbrowser

ROOT = Path(__file__).resolve().parent


def profile_folder(name):
    if not re.fullmatch(r'[a-z0-9][a-z0-9_-]{0,63}', name):
        raise ValueError('Use 1–64 lowercase letters, numbers, hyphens or underscores.')
    if name.split('.')[0].upper() in {'CON', 'PRN', 'AUX', 'NUL', *('COM'+str(i) for i in range(1,10)), *('LPT'+str(i) for i in range(1,10))}:
        raise ValueError('That name is reserved by Windows. Choose another game name.')
    return ROOT / 'data' / name


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--profile', default='reading')
    parser.add_argument('--obs', action='store_true', help='Enable optional OBS capture')
    parser.add_argument('--port', type=int, default=18745)
    parser.add_argument('--no-browser', action='store_true')
    parser.add_argument('--no-capture', action='store_true')
    args = parser.parse_args()
    if not 1024 <= args.port <= 65535:
        parser.error('Port must be between 1024 and 65535.')
    name = args.profile
    if name is None:
        existing = sorted(p.name for p in (ROOT/'data').glob('*') if p.is_dir())
        print('JP Game Reader — one shared reader, separate game journals')
        print('Existing games: ' + (', '.join(existing) or '(none yet)'))
        name = input('Game profile, e.g. fortune-weave or my-new-vn: ').strip()
    try:
        folder = profile_folder(name)
    except ValueError as error:
        parser.error(str(error))
    with socket.socket() as probe:
        if probe.connect_ex(('127.0.0.1', args.port)) == 0:
            try:
                with urllib.request.urlopen(f'http://127.0.0.1:{args.port}/api/state', timeout=2) as response:
                    state=json.load(response)
                if state.get('workspace')==str(folder.resolve()) and state.get('capture_enabled')==(args.obs and not args.no_capture):
                    if not args.no_browser:webbrowser.open(f'http://127.0.0.1:{args.port}')
                    return 0
            except (OSError,ValueError):pass
            parser.error('Reader port is occupied. Stop the other reader before switching games, or choose --port.')
    folder.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ, JP_READER_DATA=str(folder))
    bundled_index=ROOT/'dictionaries'/'mdict-index.sqlite3'
    if bundled_index.exists():env['JP_READER_DICTIONARY_INDEX']=str(bundled_index)
    command = [sys.executable, str(ROOT/'journal.py'), '--database', str(folder/'sentences.sqlite3'), '--port', str(args.port)]
    command.extend(flag for flag in ('--no-browser', '--no-capture') if getattr(args, flag[2:].replace('-', '_')))
    if not args.obs and not args.no_capture:command.append('--no-capture')
    print(f'Library: {name}\nYour texts: {folder}\nReader: http://127.0.0.1:{args.port}', flush=True)
    return subprocess.call(command, cwd=ROOT, env=env)


if __name__ == '__main__':
    raise SystemExit(main())
