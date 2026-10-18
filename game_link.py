"""Follow the line a running game is showing by reading its memory (no OCR).

Read-only: the reader opens the game process with query + read rights only and
calls ReadProcessMemory. It never writes to, injects into or pauses the game.
Windows only; other platforms report the link as unavailable.

Engines are small adapters. Each one reports where the line on screen is in the
game's own script, as the key (``source|id``) of that line in an extracted 台本.

Supported engines:

* Pal (CRYSTALiA's ディメンション凸ラバース!! and other games built on dll\\Pal.dll).
  The script VM keeps the current line as a byte offset into TEXT.DAT; the
  4-byte header of that entry is the line number. The VM context is found by
  scanning for the loaded TEXT.DAT buffer ("_TEXT_LIST__") and the context
  field that points at it, verified by the script buffer ("Sv20").
  台本 rows: ``source`` "main", ``id`` = the engine's line number.

* Kaleido (M2's Kaleido ADV Workshop with Squirrel scripts, 64-bit; tested with
  STEINS;GATE RE:BOOT, sgre_steam.exe). The scene player (class ScenePlayer in
  envplayer.nut) keeps the line on screen in two fields: curSceneName
  ("resg01_06.ks*start" = scenario file + label) and curTextId (1-based index
  into that scene's texts). The player is found by the types of its
  consecutive fields curSceneName … outlineCur; after the title screen or a
  load the game makes a new player, which is found again by itself.
  台本 rows: ``source`` "scenario/<file>", ``id`` "<label>#<0-based index>"
  (the layout of the scenario extraction, e.g. "scenario/resg01_06.ks|*start#15").

Command line (diagnostic): ``python game_link.py [--pid N] [--process NAME] [--script script.json]``
prints each new line as you advance the game.
"""
import argparse
import ctypes
import json
import os
import re
import struct
import sys
import time

if os.name == 'nt':
    from ctypes import wintypes
    _kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    _kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    _kernel.OpenProcess.restype = wintypes.HANDLE
    _kernel.ReadProcessMemory.argtypes = [wintypes.HANDLE, ctypes.c_void_p, ctypes.c_void_p,
                                          ctypes.c_size_t, ctypes.POINTER(ctypes.c_size_t)]
    _kernel.ReadProcessMemory.restype = wintypes.BOOL
    _kernel.VirtualQueryEx.restype = ctypes.c_size_t
    _kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    _kernel.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
    _kernel.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
    _kernel.CreateToolhelp32Snapshot.restype = wintypes.HANDLE

    class _MBI(ctypes.Structure):
        # PartitionId only exists in the 64-bit layout of MEMORY_BASIC_INFORMATION.
        _fields_ = [('BaseAddress', ctypes.c_void_p), ('AllocationBase', ctypes.c_void_p),
                    ('AllocationProtect', wintypes.DWORD)] + \
                   ([('PartitionId', wintypes.WORD)] if ctypes.sizeof(ctypes.c_void_p) == 8 else []) + \
                   [('RegionSize', ctypes.c_size_t), ('State', wintypes.DWORD),
                    ('Protect', wintypes.DWORD), ('Type', wintypes.DWORD)]

    _kernel.VirtualQueryEx.argtypes = [wintypes.HANDLE, ctypes.c_void_p, ctypes.POINTER(_MBI), ctypes.c_size_t]

    class _PROCESSENTRY32W(ctypes.Structure):
        _fields_ = [('dwSize', wintypes.DWORD), ('cntUsage', wintypes.DWORD), ('th32ProcessID', wintypes.DWORD),
                    ('th32DefaultHeapID', ctypes.c_void_p), ('th32ModuleID', wintypes.DWORD),
                    ('cntThreads', wintypes.DWORD), ('th32ParentProcessID', wintypes.DWORD),
                    ('pcPriClassBase', ctypes.c_long), ('dwFlags', wintypes.DWORD),
                    ('szExeFile', ctypes.c_wchar * 260)]

    _kernel.Process32FirstW.argtypes = [wintypes.HANDLE, ctypes.POINTER(_PROCESSENTRY32W)]
    _kernel.Process32NextW.argtypes = [wintypes.HANDLE, ctypes.POINTER(_PROCESSENTRY32W)]

PROCESS_QUERY_INFORMATION, PROCESS_VM_READ = 0x0400, 0x0010
MEM_COMMIT, MEM_PRIVATE = 0x1000, 0x20000
READABLE = 0x02 | 0x04 | 0x08 | 0x20 | 0x40 | 0x80     # PAGE_READONLY … PAGE_EXECUTE_WRITECOPY
PAGE_GUARD = 0x100
UNCACHED = 0x200 | 0x400                               # PAGE_NOCACHE, PAGE_WRITECOMBINE: slow, never script data
STILL_ACTIVE = 259
CHUNK = 16 * 1024 * 1024


class LinkError(Exception):
    """A user-facing reason why the game cannot be followed right now."""


def processes():
    """[(pid, exe name)] of running processes."""
    if os.name != 'nt':
        return []
    snap = _kernel.CreateToolhelp32Snapshot(0x2, 0)     # TH32CS_SNAPPROCESS
    if not snap or snap == wintypes.HANDLE(-1).value:
        return []
    rows = []
    try:
        entry = _PROCESSENTRY32W()
        entry.dwSize = ctypes.sizeof(entry)
        ok = _kernel.Process32FirstW(snap, ctypes.byref(entry))
        while ok:
            rows.append((entry.th32ProcessID, entry.szExeFile))
            ok = _kernel.Process32NextW(snap, ctypes.byref(entry))
    finally:
        _kernel.CloseHandle(snap)
    return rows


class Process:
    """Read-only view of another process's memory."""

    def __init__(self, pid):
        if os.name != 'nt':
            raise LinkError('遊戲連動只能在 Windows 上使用。')
        self.pid = int(pid)
        self.handle = _kernel.OpenProcess(PROCESS_QUERY_INFORMATION | PROCESS_VM_READ, False, self.pid)
        if not self.handle:
            raise LinkError('打不開遊戲程式（遊戲已關閉，或遊戲以系統管理員身分執行）。')

    def close(self):
        if self.handle:
            _kernel.CloseHandle(self.handle)
            self.handle = None

    def alive(self):
        code = wintypes.DWORD()
        return bool(self.handle) and _kernel.GetExitCodeProcess(self.handle, ctypes.byref(code)) and code.value == STILL_ACTIVE

    def read(self, address, size):
        buffer = ctypes.create_string_buffer(size)
        done = ctypes.c_size_t()
        if not _kernel.ReadProcessMemory(self.handle, ctypes.c_void_p(address), buffer, size, ctypes.byref(done)):
            return None
        return buffer.raw[:done.value]

    def u32(self, address):
        raw = self.read(address, 4)
        return struct.unpack('<I', raw)[0] if raw and len(raw) == 4 else None

    def regions(self, private_only=True):
        """Committed, readable regions as (base, size)."""
        info, address, limit = _MBI(), 0x10000, 0x7FFFFFFF0000
        while address < limit:
            if not _kernel.VirtualQueryEx(self.handle, ctypes.c_void_p(address), ctypes.byref(info), ctypes.sizeof(info)):
                break
            base, size = info.BaseAddress or 0, info.RegionSize
            if size <= 0:
                break
            if (info.State == MEM_COMMIT and info.Protect & READABLE and not info.Protect & (PAGE_GUARD | UNCACHED)
                    and (info.Type == MEM_PRIVATE or not private_only)):
                yield base, size
            address = base + size

    def find(self, needle, aligned=1, limit=8):
        """Addresses where ``needle`` occurs in private memory."""
        hits, keep = [], len(needle) - 1
        for base, size in self.regions():
            offset, tail = 0, b''
            while offset < size:
                data = self.read(base + offset, min(CHUNK, size - offset))
                if not data:
                    break
                block = tail + data
                start = base + offset - len(tail)
                at = block.find(needle)
                while at != -1:
                    if (start + at) % aligned == 0:
                        hits.append(start + at)
                        if len(hits) >= limit:
                            return hits
                    at = block.find(needle, at + 1)
                tail = block[-keep:] if keep else b''
                offset += len(data)
        return hits

    def scan(self, pattern, aligned=1, limit=32, overlap=1024):
        """Start addresses of matches of a compiled bytes regex in private memory.
        ``overlap`` must be at least the longest possible match."""
        hits = []
        for base, size in self.regions():
            offset = 0
            while offset < size:
                n = min(CHUNK, size - offset)
                data = self.read(base + offset, n + min(overlap, size - offset - n))
                if not data:
                    break
                for match in pattern.finditer(data):
                    if match.start() >= n:          # starts in the overlap: the next chunk reports it
                        break
                    at = base + offset + match.start()
                    if at % aligned == 0:
                        hits.append(at)
                        if len(hits) >= limit:
                            return hits
                offset += n
        return hits


class PalEngine:
    """Pal engine (dll\\Pal.dll). Offsets are from the VM context (task data + 0x338)."""
    name = 'Pal'
    exes = ('totsulover.exe',)                     # found automatically; another Pal game can be picked in Read from
    games = ('ディメンション凸ラバース!!',)
    TEXT_PTR, TEXT_SIZE = 0x3F158, 0x3F168        # loaded TEXT.DAT buffer and its size
    SCRIPT_PTR = 0x55E94                           # loaded SCRIPT.SRC buffer ("Sv20")
    CURRENT = 0x4 + 0x1094                         # text window: TEXT.DAT offset of the line on screen
    NAME = 0x4 + 0x1090                            # … and of the speaker name (0x0FFFFFFF = none)

    def __init__(self, process):
        self.process = process
        self.context = self.text = self.size = self.count = None

    @classmethod
    def detect(cls, process):
        engine = cls(process)
        for text in process.find(b'_TEXT_LIST__', limit=4):
            count = process.u32(text + 12)
            if not count or count > 2000000:
                continue
            for field in process.find(struct.pack('<I', text), aligned=4, limit=256):
                context = field - cls.TEXT_PTR
                script = process.u32(context + cls.SCRIPT_PTR)
                size = process.u32(context + cls.TEXT_SIZE)
                if script and size and 16 < size < 0x10000000 and process.read(script, 4) == b'Sv20':
                    engine.context, engine.text, engine.size, engine.count = context, text, size, count
                    return engine
        return None

    def describe(self):
        return f'context=0x{self.context:08X} TEXT=0x{self.text:08X} size={self.size} lines={self.count}'

    def entry(self, offset):
        """(line number, raw cp932 text) of the TEXT.DAT entry at ``offset``."""
        if offset is None or not 16 <= offset < self.size - 4:
            return None
        raw = self.process.read(self.text + offset, min(2048, self.size - offset))
        if not raw or len(raw) < 5:
            return None
        number = struct.unpack_from('<I', raw)[0]
        if number >= self.count:
            return None
        end = raw.find(b'\0', 4)
        return number, raw[4:end if end != -1 else None]

    def current(self):
        """The line on screen: {'key', 'label', 'number', 'text', 'speaker'} or None (no line yet)."""
        found = self.entry(self.process.u32(self.context + self.CURRENT))
        if not found:
            return None
        number, raw = found
        name = self.entry(self.process.u32(self.context + self.NAME))
        return {'key': f'main|{number}', 'label': f'#{number}', 'number': number,
                'text': visible(raw), 'speaker': visible(name[1]) if name else ''}


class KaleidoEngine:
    """M2 Kaleido ADV Workshop (Squirrel VM, 64-bit), e.g. STEINS;GATE RE:BOOT.

    Squirrel values (SQObjectPtr) are 16 bytes: a 4-byte type tag, padding and an
    8-byte value; integers are 32-bit. A class instance stores its fields as
    consecutive values in declaration order. Strings (SQString) keep their byte
    length at +0x28 and their UTF-8 text at +0x38.
    """
    name = 'Kaleido'
    exes = ('sgre_steam.exe',)                     # found automatically; another Kaleido game can be picked in Read from
    games = ('STEINS;GATE RE:BOOT',)
    NULL, INTEGER, BOOL, STRING = 0x01000001, 0x05000002, 0x01000008, 0x08000010
    # ScenePlayer fields from curSceneName on (envplayer.nut): 0 curSceneName, 1 curSceneId, 2 curSceneInfo,
    # 3 curSceneSelect, 4 curTextStart, 5 cur, 6 curPoint, 7 curLine, 8 curTextId, 9 curReaded, 10 curEvent,
    # 11 curSelectIdx, 12 saveText, 13 saveTextInit, 14 outlineMode, 15 outlineCur.
    SLOTS, SCENE, TEXT = 16, 0, 8
    TYPES = {3: BOOL, 4: INTEGER, 8: INTEGER, 9: BOOL, 10: BOOL, 11: INTEGER, 14: BOOL, 15: INTEGER}
    FIRST = min(TYPES)                             # the search pattern starts at this field
    PATTERN = None                                 # set below the class: the type tags of fields FIRST … max(TYPES)
    MARK = b'curTextId'                            # the field name, interned as a Squirrel string
    SCENE_NAME = re.compile(r'[^\s*\x00]{1,160}(?:\*[^\s*\x00]{0,160})?')
    LONGEST_WAIT = 4.0                             # seconds between searches while no line is shown

    def __init__(self, process):
        self.process = process
        self.player = None                         # address of the curSceneName field
        self.next_search = 0.0
        self.misses = 0

    @classmethod
    def detect(cls, process):
        """The engine when the game runs Kaleido's scene player script, else None. The player
        itself may not exist yet (title screen); ``current`` keeps looking for it."""
        for at in process.find(cls.MARK + b'\0', limit=8):
            if process.u32(at - 0x38 + 0x28) == len(cls.MARK):
                engine = cls(process)
                engine.locate()
                return engine
        return None

    def describe(self):
        return f'player=0x{self.player:X}' if self.player is not None else '等待進入劇情（標題畫面時找不到台詞）'

    def string(self, address):
        """Text of the Squirrel string at ``address``, or None."""
        size = self.process.u32(address + 0x28)
        if size is None or not 0 < size <= 512:
            return None
        body = self.process.read(address + 0x38, size + 1)
        if not body or len(body) != size + 1 or body[size] != 0:
            return None
        try:
            return body[:size].decode('utf-8')
        except UnicodeDecodeError:
            return None

    def read_line(self, field):
        """The line the player at ``field`` shows; None while it shows none; False if ``field`` is not a player."""
        raw = self.process.read(field, self.SLOTS * 16) if field is not None else None
        if not raw or len(raw) < self.SLOTS * 16:
            return False
        tag = lambda slot: struct.unpack_from('<I', raw, 16 * slot)[0]
        if any(tag(slot) != kind for slot, kind in self.TYPES.items()):
            return False
        if tag(self.SCENE) == self.NULL:
            return None
        if tag(self.SCENE) != self.STRING:
            return False
        scene = self.string(struct.unpack_from('<Q', raw, 16 * self.SCENE + 8)[0])
        if not scene or not self.SCENE_NAME.fullmatch(scene):
            return False
        number = struct.unpack_from('<i', raw, 16 * self.TEXT + 8)[0] - 1    # curTextId is 1-based
        if number < 0:
            return None
        storage, star, label = scene.partition('*')
        storage = storage.replace('\\', '/').rsplit('/', 1)[-1]
        label = star + label
        return {'key': f'scenario/{storage}|{label}#{number}', 'label': f'{storage} {label}#{number}',
                'number': number, 'text': '', 'speaker': ''}

    def locate(self):
        """Search memory for the scene player; prefer one that shows a line."""
        best, best_line = None, False
        for at in self.process.scan(self.PATTERN, aligned=8, limit=64, overlap=256):
            field = at - 16 * self.FIRST
            line = self.read_line(field)
            if line is not False and (best is None or (line and not best_line)):
                best, best_line = field, line
        self.player = best
        return best_line

    def current(self):
        """The line on screen: {'key', 'label', 'number', 'text', 'speaker'} or None (no line yet)."""
        line = self.read_line(self.player)
        if line:
            self.misses = 0
            return line
        # No line: on the title screen, while loading, or the player was replaced (after a load
        # the game makes a new one and empties the old). Search again, at most every 0.5–4 s.
        now = time.monotonic()
        if now < self.next_search:
            return None
        line = self.locate()
        self.misses = 0 if line else self.misses + 1
        self.next_search = now + min(self.LONGEST_WAIT, 0.5 * 2 ** self.misses)
        return line or None


KaleidoEngine.PATTERN = re.compile(b''.join(
    re.escape(struct.pack('<I', KaleidoEngine.TYPES[slot])) + b'.{12}' if slot in KaleidoEngine.TYPES else b'.{16}'
    for slot in range(KaleidoEngine.FIRST, max(KaleidoEngine.TYPES) + 1)), re.S)
ENGINES = (PalEngine, KaleidoEngine)
TAGS = re.compile(r'<r[^<>]*>|</r>|</?d\d*>|</?s\d*>|<[^<>]{0,40}>')


def engines_for(exe=''):
    """Engines in the order to try them: those known for this executable first."""
    exe = (exe or '').lower()
    return sorted(ENGINES, key=lambda engine: exe not in engine.exes)


def known_exes():
    """Executables of games the engines know: game link finds these by itself."""
    return {exe for engine in ENGINES for exe in engine.exes}


def supported_games():
    return '、'.join(game for engine in ENGINES for game in engine.games)


def candidates(alive, pid=None, exe='', skip=()):
    """(pid, exe) of the processes to try for game link, best first.

    ``alive`` is [(pid, exe)] of running processes. The process picked in Read from comes first (by pid,
    or by executable name after the game restarted); then every running game an engine knows, so game
    link works without picking a window, and after switching to another supported game. ``skip`` holds
    (pid, lower-case exe) of processes already found not to be a readable game (a window picked by mistake)."""
    exe = (exe or '').lower()
    known = known_exes()
    first = [(p, n) for p, n in alive if p == pid and (not exe or n.lower() == exe)]
    first += [(p, n) for p, n in alive if exe and n.lower() == exe]
    found = []
    for p, n in first + [(p, n) for p, n in alive if n.lower() in known]:
        if (p, n) not in found and (p, n.lower()) not in skip:
            found.append((p, n))
    return found


def visible(raw):
    """Readable Japanese from engine text: line breaks kept, ruby/size/dictionary tags removed.
    A Chinese subtitle line added by a bilingual patch (<br><sNN>…) is not part of the Japanese."""
    text = raw.decode('cp932', 'replace')
    text = re.split(r'<br><s(?:15|17|20)>', text, maxsplit=1)[0]
    text = text.replace('<br>', '\n')
    return TAGS.sub('', text).replace('%0', '').strip()


class Link:
    """Attach to one game process and report its current line."""

    def __init__(self, pid, exe=''):
        self.process = Process(pid)
        self.engine = None
        for engine in engines_for(exe):
            self.engine = engine.detect(self.process)
            if self.engine:
                break
        if not self.engine:
            self.process.close()
            raise LinkError('這個遊戲還不能直接讀取（目前支援：Pal 引擎、M2 Kaleido 引擎，例如 STEINS;GATE RE:BOOT）。'
                            '如果遊戲還在啟動，等標題畫面出現後會自動再試。')

    @property
    def pid(self):
        return self.process.pid

    def alive(self):
        return self.process.alive()

    def current(self):
        if not self.process.alive():
            raise LinkError('遊戲已關閉。重開遊戲後會自動重新連上。')
        return self.engine.current()

    def close(self):
        self.process.close()


def main():
    parser = argparse.ArgumentParser(description='Print the line a running game shows (read-only).')
    parser.add_argument('--pid', type=int)
    parser.add_argument('--process', help='executable name (default: the first running supported game)')
    parser.add_argument('--script', help='a 台本 script.json: also print the Japanese of each line')
    parser.add_argument('--seconds', type=float, default=0, help='stop after this many seconds (0 = until Ctrl+C)')
    parser.add_argument('--log', help='also append lines to this UTF-8 file')
    args = parser.parse_args()
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    log = open(args.log, 'a', encoding='utf-8') if args.log else None

    def say(text):
        print(text, flush=True)
        if log:
            log.write(text + '\n'); log.flush()

    rows = {}
    if args.script:
        data = json.loads(open(args.script, encoding='utf-8-sig').read())
        rows = {f"{r.get('source', '')}|{r.get('id', '')}": r for r in (data['rows'] if isinstance(data, dict) else data)}
    known = {exe for engine in ENGINES for exe in engine.exes}
    running = processes()
    wanted = args.process.lower() if args.process else None
    pid, exe = args.pid, args.process or ''
    if not pid:
        pid, exe = next(((p, name) for p, name in running if (name.lower() == wanted if wanted else name.lower() in known)),
                        (None, exe))
    if not pid:
        say(f'找不到 {args.process or "支援的遊戲"}：請先開遊戲。')
        return 1
    started = time.monotonic()
    link = Link(pid, exe)
    say(f'已連上 pid {pid}（{link.engine.name} 引擎）{link.engine.describe()}  花 {time.monotonic() - started:.1f} 秒')
    last = None
    try:
        while not args.seconds or time.monotonic() - started < args.seconds:
            line = link.current()
            key = line and line['key']
            if key != last:
                last = key
                if line:
                    text = line['text'] or rows.get(key, {}).get('ja', '（台本裡沒有這句）' if rows else '')
                    say(f"{line['label']}  [{line['speaker'] or '旁白'}]  {text}".replace('\n', ' / '))
            time.sleep(0.1)
    except LinkError as error:
        say(str(error))
    except KeyboardInterrupt:
        pass
    finally:
        link.close()
        if log:
            log.close()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
