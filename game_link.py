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

* Atlus BMD (ペルソナ３ リロード, P3R.exe; Unreal Engine 4). Each page on screen has a small "message work"
  that points at the loaded message file and the page; works are found by scanning small memory regions
  (cheaply: first where works were seen before). game_link_index.json (beside the 台本, written by the game's
  patch tool) says which file a loaded message file is.
  台本 rows: ``source`` = message file, ``id`` = "<index>:<name>#<page>".

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
import array
import ctypes
import hashlib
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
    _kernel.QueryFullProcessImageNameW.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR,
                                                  ctypes.POINTER(wintypes.DWORD)]
    _kernel.QueryFullProcessImageNameW.restype = wintypes.BOOL
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

    def image_path(self):
        """Full path of the game's .exe ('' if Windows does not say)."""
        size = wintypes.DWORD(32768)
        buffer = ctypes.create_unicode_buffer(size.value)
        if self.handle and _kernel.QueryFullProcessImageNameW(self.handle, 0, buffer, ctypes.byref(size)):
            return buffer.value
        return ''

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

    def committed(self, address, size):
        """The readable, committed parts of [address, address + size) as (base, size)."""
        info, end, parts, at = _MBI(), address + size, [], address
        while at < end:
            if not _kernel.VirtualQueryEx(self.handle, ctypes.c_void_p(at), ctypes.byref(info), ctypes.sizeof(info)):
                break
            base, length = info.BaseAddress or 0, info.RegionSize
            if length <= 0:
                break
            if info.State == MEM_COMMIT and info.Protect & READABLE and not info.Protect & (PAGE_GUARD | UNCACHED):
                lo, hi = max(at, base), min(end, base + length)
                if hi > lo:
                    parts.append((lo, hi - lo))
            at = base + length
        return parts

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


class AtlusBmdEngine:
    """Atlus message scripts in Unreal Engine 4 (ペルソナ３ リロード, P3R.exe).

    To show a message the game converts its message file into a little-endian copy (header "MSG1",
    self-relative offsets) and makes small "message works" pointing at pages of it:
        -9  0x28 while its message is open
        -8  u64 1
        +0  start of the copy
        +8  start of the page (inside the copy)
        +32 bytes 01 01 20 00, then the text colour (field messages: unset = FFFFFFFF until shown)
        +40 u32 kind: 1 field message, tutorial, movie subtitle; 9 event; 0 choice
        +44 u32 state: 0 for the pages of the open message; 5 for the backlog's copy of a page
        +52 bit 16 set while a page's line is still to come or playing (not what is on screen)
    Events make a work for every page when the message opens; tutorials do too and move one of them from page
    to page; field messages make the next page's work (uncoloured) when a page is shown. When a page is shown the
    game also adds it to the backlog (a work with state 5), so the page on screen is the open page whose backlog
    copy appeared last; for messages without a backlog (tutorials, system messages, movie subtitles) it is the open
    page that a work appeared on, moved to, was coloured or stopped waiting last (at the same moment: the page more
    works point at, then the earlier page).
    Works are made and freed message by message, so the engine finds them by scanning memory. A work is a
    160-byte object of Unreal's small-object allocator, which keeps objects of one size together in 64 KB pages
    whose first bytes say the size (u16), the pool and E3. So every poll the engine reads the ~100 pages of
    160-byte objects (only where a work can start; a few ms), and every few seconds it looks for new such
    pages (region list + page headers, ~0.1 s). Should works turn up elsewhere (another allocator), a slow scan of
    all small regions still finds them and their pages are read every poll too.
    Which file a copy came from is looked up in game_link_index.json (written beside the 台本 by the game's patch
    tool): fingerprints of the message names and of each page's Japanese -> the file. A bilingual patch only
    adds a line after the Japanese, so the fingerprints are the same with or without one.
    台本 rows: ``source`` = the file ("Xrd777/Events/.../BMD_Event_Main_100_040_B"), ``id`` = "<index>:<name>#<page>".
    """
    name = 'Atlus BMD'
    exes = ('p3r.exe',)
    games = ('ペルソナ３ リロード',)
    MARK = b'\x01\x01\x20\x00'               # 32 bytes after the (copy, page) pair of a message work
    PATCH_MARK = b'\xfe\xf2\x01\x16\x01'     # colour 21: where a bilingual patch's added line starts
    SMALL = 0x10000                          # full scans read only regions up to this size
    PAGE = 0x10000                           # small objects live in 64 KB pages; works are remembered by page
    SIZES = (160,)                           # size of a work as an allocator object (more are learned)
    MARK_AT = 56                             # where MARK is in the object (24 bytes before the pair + 32)
    CANARY = 0xE3                            # 4th byte of an allocator page
    POOL_EVERY = 3.0                         # seconds between looks for new allocator pages of works' size
    WAITS = (1.0, 2.0, 3.0, 5.0)             # seconds between full scans while nothing is on screen
    RESCAN = 5.0                             # ... and while something is (a new work may be in a new page)
    SLOW = 30.0                              # ... once allocator pages of works are known (just in case)
    SOONEST = 0.5                            # a look right away when the line on screen goes away
    MAX_PAGES = 128
    VARS = {(4, 1): '〈主人公〉', (4, 2): '〈主人公〉', (4, 3): '〈名前〉', (4, 4): '〈アイテム〉', (2, 4): '〈数〉',
            (1, 3): '〈ボタン〉', (4, 30): '〈能力〉', (4, 31): '〈ランク〉'}

    def __init__(self, process):
        self.process = process
        self.full_index, self.first_index = self.load_index()
        self.parsed = {}                     # (copy start, first 64 bytes) -> parsed copy or None
        self.pages = {}                      # 64 KB pages where works were seen -> last seen
        self.sizes = set(self.SIZES)         # allocator object sizes that hold works
        self.pool = {}                       # allocator pages of those sizes -> object size
        self.next_pool = 0.0
        self.last_look = -1.0
        self.works = {}                      # pair address -> work (see work) + since when it is so
        self.next_full = 0.0
        self.last_full = -1.0
        self.misses = 0
        self.shown_at = None                 # pair address of the line reported last
        self.debug = bool(os.environ.get('GAME_LINK_DEBUG'))

    # ---- the index written by the patch tool ----
    @staticmethod
    def index_folders():
        here = os.path.dirname(os.path.abspath(__file__))
        roots = [os.path.join(here, 'scripts'), os.path.join(here, 'data', 'reading', 'scripts'),
                 os.path.join(here, 'saved_sentences', 'scripts')]
        found = []
        for root in roots:
            if os.path.isdir(root):
                found += [os.path.join(root, sub) for sub in sorted(os.listdir(root))]
        try:
            import script_library                   # scripts listed in scripts/paths.txt or JP_READER_SCRIPTS
            found += [str(p) for p in script_library.folders()]
        except Exception:
            pass
        return found

    @classmethod
    def load_index(cls):
        full, first = {}, {}
        for folder in cls.index_folders():
            path = os.path.join(folder, 'game_link_index.json')
            if not os.path.isfile(path):
                continue
            try:
                with open(path, encoding='utf-8') as f:
                    data = json.load(f)
            except (OSError, ValueError):
                continue
            full.update(data.get('full', {}))
            first.update(data.get('fingerprints', {}))
        return full, first

    @classmethod
    def detect(cls, process):
        """The engine for P3R.exe (message works appear once a message is shown)."""
        try:
            exe = re.split(r'[\\/]', process.image_path() or '')[-1].lower()
        except AttributeError:
            exe = ''
        if exe not in cls.exes and not process.find(b'MSG1', limit=1):
            return None
        return cls(process)

    def describe(self):
        files = len(set(self.full_index.values()) | set(self.first_index.values()))
        return f'索引 {files} 個台詞檔' if files else '找不到 game_link_index.json（請重新安裝台本）'

    # ---- message text ----
    @staticmethod
    def tokens(raw):
        """(kind, bytes) pieces of a page: 't' text run, 'f' function token, 'z' end."""
        i, n = 0, len(raw)
        while i < n:
            b = raw[i]
            if b == 0xFE and i + 1 < n and raw[i + 1] & 0xF0 == 0xF0:
                size = 1 + (raw[i + 1] & 0x0F) * 2
                yield 'f', raw[i:i + size]
                i += size
            elif b == 0:
                yield 'z', b'\0'
                return
            else:
                j = n
                for stop in (raw.find(b'\0', i + 1), raw.find(b'\xfe', i + 1)):
                    if stop != -1 and stop < j:
                        j = stop
                yield 't', raw[i:j]
                i = j

    @classmethod
    def japanese(cls, raw):
        """The Japanese bytes of a page: no control codes, up to a bilingual patch's line, no newline at the end."""
        out = bytearray()
        for kind, piece in cls.tokens(raw):
            if kind == 'f' and piece == cls.PATCH_MARK:
                break
            if kind == 't':
                out += piece
        return bytes(out).rstrip(b'\r\n')

    @classmethod
    def first_line(cls, raw):
        """The first line of a page's Japanese (at most 32 bytes)."""
        out = bytearray()
        for kind, piece in cls.tokens(raw):
            if kind == 't':
                cut = min((at for at in (piece.find(b'\n'), piece.find(b'\r')) if at != -1), default=-1)
                if cut != -1:
                    out += piece[:cut]
                    break
                out += piece
                if len(out) >= 32:
                    break
        return bytes(out[:32])

    @classmethod
    def visible(cls, raw):
        """Japanese of one page for reading: control codes removed, names as 〈…〉, a patch's added line dropped."""
        out = bytearray()
        for kind, piece in cls.tokens(raw):
            if kind == 'f':
                if piece == cls.PATCH_MARK:
                    break
                fid = piece[2] if len(piece) > 2 else 0
                var = cls.VARS.get((fid >> 5, fid & 0x1F))
                if var:
                    out += var.encode('utf-8')
            elif kind == 't':
                out += piece
        return out.decode('utf-8', 'replace').replace('\r', '').strip('\n').strip()

    # ---- converted message files ----
    def copy_at(self, start):
        """(file, {page start: (index, name, page number, speaker)}, data) of the copy at ``start``, or None."""
        head = self.process.read(start, 64)
        if not head or len(head) < 64 or head[8:12] != b'MSG1':
            return None
        key = (start, head)
        if key in self.parsed:
            return self.parsed[key]
        size, count = struct.unpack_from('<I', head, 4)[0], struct.unpack_from('<I', head, 0x18)[0]
        result = None
        data = self.process.read(start, size) if 32 < size < 0x800000 and count <= 5000 else None
        if data and len(data) == size:
            try:
                result = self.parse_copy(data, start)
            except (struct.error, ValueError, IndexError):
                result = None
        self.parsed[key] = result
        if len(self.parsed) > 64:
            self.parsed.pop(next(iter(self.parsed)))
        return result

    @staticmethod
    def page_ends(data, head, starts):
        """Where each page ends: the next page of the message; the last one by the text size after the page
        table (stored little- or big-endian, so both are tried), else at its 0 terminator."""
        if not starts:
            return []
        at = head + 4 * len(starts)
        for size in struct.unpack_from('<I', data, at)[0], struct.unpack_from('>I', data, at)[0]:
            end = at + 4 + size
            if starts[-1] < end <= len(data):
                return starts[1:] + [end]
        zero = data.find(b'\0', starts[-1])
        return starts[1:] + [zero + 1 if zero != -1 else len(data)]

    def parse_copy(self, data, base):
        ptr = lambda at: at + struct.unpack_from('<I', data, at)[0]
        count = struct.unpack_from('<I', data, 0x18)[0]
        dialogs = []
        for k in range(count):
            kind = struct.unpack_from('<I', data, 0x20 + 8 * k)[0]
            o = ptr(0x20 + 8 * k + 4)
            name = data[o:o + 24].split(b'\0')[0]
            if kind == 0:
                pages, speaker = struct.unpack_from('<HH', data, o + 24)
                head = o + 28
            else:
                pages, speaker, head = struct.unpack_from('<H', data, o + 26)[0], 0xFFFF, o + 32
            starts = [ptr(head + 4 * j) for j in range(pages)]
            dialogs.append((k, name, starts, self.page_ends(data, head, starts), speaker))
        full, first = hashlib.sha1(), hashlib.sha1()
        where = {}
        so = 0x20 + 8 * count
        names_at, names = ptr(so), struct.unpack_from('<I', data, so + 4)[0]
        speakers = [data[ptr(names_at + 4 * k):data.index(b'\0', ptr(names_at + 4 * k))] for k in range(min(names, 2000))]
        for k, name, starts, ends, speaker in dialogs:
            full.update(name + b'|')
            first.update(name + b'|')
            for j, (a, b) in enumerate(zip(starts, ends)):
                page = data[a:b]
                full.update(self.japanese(page) + b'#')
                first.update(self.first_line(page) + b'#')
                who = self.visible(speakers[speaker] + b'\0') if speaker < len(speakers) else ''
                where[base + a] = (k, name.decode('ascii', 'replace'), j, who, b - a)
        file = self.full_index.get(full.hexdigest()) or self.first_index.get(first.hexdigest())
        return file, where, data

    def line(self, start, page):
        copy = self.copy_at(start)
        if not copy:
            return None
        file, where, data = copy
        found = where.get(page)
        if not found:
            return None
        k, name, j, who, size = found
        text = self.visible(data[page - start:page - start + size])
        key = f'{file}|{k}:{name}#{j}' if file else f'?|{k}:{name}#{j}'
        short = (file or '?').rsplit('/', 1)[-1]
        return {'key': key, 'label': f'{short} {name}#{j}', 'number': k, 'text': text, 'speaker': who}

    # ---- finding message works ----
    def work(self, data, i):
        """The message work whose MARK is at data[i] as (copy start, page start, kind, uncoloured, waiting), or None.
        kind: 'open' (a page of the open message), 'log' (the backlog's copy of a shown page) or '' (other);
        waiting: bit 16, set while the page's line is still to come or playing."""
        if i < 48 or i + 24 > len(data):
            return None
        one, start, page = struct.unpack_from('<QQQ', data, i - 40)
        if one != 1 or not 0x10000 < start < page < start + 0x800000:
            return None
        live = data[i - 41] == 0x28                                            # set while its message is open
        what, state = struct.unpack_from('<II', data, i + 8)                   # what: 0 = choice
        white = struct.unpack_from('<I', data, i + 4)[0] == 0xFFFFFFFF         # colour not set (yet)
        waiting = bool(struct.unpack_from('<I', data, i + 20)[0] & 0x10000)
        kind = 'open' if live and state == 0 and what != 0 else 'log' if state == 5 else ''
        return start, page, kind, white, waiting

    def works_in(self, base, data):
        """{pair address: (copy start, page start, kind, uncoloured, waiting)} of the message works in ``data``."""
        found = {}
        i = data.find(self.MARK)
        while i != -1:
            if (base + i - 32) % 8 == 0:
                one = self.work(data, i)
                if one:
                    found[base + i - 32] = one
            i = data.find(self.MARK, i + 1)
        return found

    MARK_WORD = array.array('I', MARK)[0]             # MARK as one 4-byte word (pages are read as words)

    def pool_works(self, page, size, data):
        """Works in an allocator page of ``size``-byte objects, looking only where an object's MARK can be
        (objects are handed out from the end of the page: they start at 64 KB % size + k * size)."""
        first = self.PAGE % size + self.MARK_AT
        if size % 4 or first % 4 or len(data) != self.PAGE or array.array('I').itemsize != 4:
            return self.works_in(page, data)
        words = array.array('I')
        words.frombytes(data)
        column = words[first // 4::size // 4]
        found = {}
        if self.MARK_WORD in column:
            for k, word in enumerate(column):
                if word == self.MARK_WORD:
                    i = first + k * size
                    one = self.work(data, i)
                    if one:
                        found[page + i - 32] = one
        return found

    def object_size(self, page, at):
        """The object size of allocator page ``page`` if the work at ``at`` is one of its objects, else None.
        An allocator page starts with u16 object size, u8 pool, u8 E3."""
        head = self.process.read(page, 4)
        if not head or len(head) != 4 or head[3] != self.CANARY:
            return None
        size = struct.unpack_from('<H', head)[0]
        if size < self.MARK_AT + 32 or (at + 32 - self.MARK_AT - page - self.PAGE % size) % size:
            return None
        return size

    def look_for_pool(self):
        """Find the allocator pages of the sizes works have (64 KB regions); returns the ones new since last time.
        Pages already known are checked by every read in scan_known, so only the others' headers are read."""
        pool, new = {}, []
        for base, size in self.process.regions():
            if size != self.PAGE or base % self.PAGE:
                continue
            if base in self.pool:
                pool[base] = self.pool[base]
                continue
            head = self.process.read(base, 4)
            if head and len(head) == 4 and head[3] == self.CANARY and struct.unpack_from('<H', head)[0] in self.sizes:
                pool[base] = struct.unpack_from('<H', head)[0]
                new.append(base)
        self.pool = pool
        self.next_pool = time.monotonic() + self.POOL_EVERY
        return new

    def read_pool(self, pages):
        """Works in these allocator pages; pages given back or reused for objects of another size are dropped."""
        found = {}
        for page in pages:
            size = self.pool.get(page)
            data = self.process.read(page, self.PAGE) if size else None
            if not data or len(data) < 4 or data[3] != self.CANARY or struct.unpack_from('<H', data)[0] != size:
                self.pool.pop(page, None)
                continue
            found.update(self.pool_works(page, size, data))
        return found

    def scan_known(self):
        """Works in the allocator pages of works' size, and in other pages where works were seen."""
        found = self.read_pool(list(self.pool))
        committed = getattr(self.process, 'committed', None)
        for page in list(self.pages):
            if page in self.pool:
                continue
            for base, size in (committed(page, self.PAGE) if committed else [(page, self.PAGE)]):
                data = self.process.read(base, size)
                if data:
                    found.update(self.works_in(base, data))
        return found

    def scan_all(self, now):
        """Works in all small memory regions. Their pages are remembered: as allocator pages if they are (which
        also teaches the object size), else as pages to read every poll."""
        found = {}
        for base, size in self.process.regions():
            if size > self.SMALL:
                continue
            data = self.process.read(base, size)
            if not data:
                continue
            here = self.works_in(base, data)
            if here:
                found.update(here)
                for at in here:
                    page = at & ~(self.PAGE - 1)
                    if page in self.pool:
                        continue
                    size = self.object_size(page, at)
                    if size:
                        self.sizes.add(size)
                        self.pool[page] = size
                        self.pages.pop(page, None)
                    else:
                        self.pages[page] = now
        if len(self.pages) > self.MAX_PAGES:
            for page in sorted(self.pages, key=self.pages.get)[:len(self.pages) - self.MAX_PAGES]:
                del self.pages[page]
        return found

    def current(self):
        """The line on screen: {'key', 'label', 'number', 'text', 'speaker'} or None (see on_screen)."""
        now = time.monotonic()
        if now >= self.next_pool:
            self.look_for_pool()
        found = self.scan_known()
        gone = self.shown_at is not None and (found.get(self.shown_at) or (0, 0, ''))[2] != 'open'
        if gone and self.pool and now - self.last_look >= self.SOONEST:
            # the line went away: the next one may be in a page that only just became an allocator page
            self.last_look = now
            found.update(self.read_pool(self.look_for_pool()))
        if now >= self.next_full or (gone and not self.pool and now - self.last_full >= self.SOONEST):
            before = len(self.pages) + len(self.pool)
            found.update(self.scan_all(now))
            self.last_full = now
            if self.debug:
                print(f'[atlus] full scan {time.monotonic() - now:.2f}s{" (line gone)" if gone else ""}: {len(found)} works, '
                      f'{len(self.pages) + len(self.pool) - before} new pages, {len(self.pool)} allocator pages '
                      f'(sizes {sorted(self.sizes)}), {len(self.pages)} other pages', flush=True)
            showing = any(w[2] == 'open' for w in found.values())
            self.misses = 0 if showing else self.misses + 1
            if self.pool:
                wait = self.SLOW
            else:
                wait = self.RESCAN if showing else self.WAITS[min(self.misses, len(self.WAITS)) - 1]
            self.next_full = time.monotonic() + wait
        works = {}
        for at, w in found.items():
            old = self.works.get(at)
            works[at] = w + (old[5] if old and old[:5] == w else now,)
        self.works = works
        for start, page, at in self.on_screen(works):
            line = self.line(start, page)
            if line:
                if self.debug and at != self.shown_at:
                    print(f'[atlus] line from work {at:x}', flush=True)
                self.shown_at = at
                return line
        self.shown_at = None
        return None

    @staticmethod
    def on_screen(works):
        """(copy start, page start, a work's address) of the pages that may be on screen, most likely first.
        works: {address: (copy start, page start, kind, uncoloured, waiting, since)}."""
        pages = {}                                   # (copy, page) -> [backlog copy since, open work since, works, address]
        coloured = {w[0] for w in works.values() if w[2] == 'open' and not w[3]}
        for at, (start, page, kind, white, waiting, since) in works.items():
            if kind == 'open':
                p = pages.setdefault((start, page), [None, None, 0, at])
                p[2] += 1
                # without a backlog: not a field message's next page (uncoloured) or a line still to come
                if not (white and start in coloured) and not waiting:
                    p[1] = since if p[1] is None else max(p[1], since)
        for start, page, kind, white, waiting, since in works.values():
            p = pages.get((start, page)) if kind == 'log' else None
            if p:
                p[0] = since if p[0] is None else max(p[0], since)
        logged = {start for (start, page), p in pages.items() if p[0] is not None}
        ranked = []
        for (start, page), (log, opened, count, at) in pages.items():
            if start in logged:                          # a message with a backlog: only pages shown so far count
                if log is not None:
                    ranked.append(((log, 1, count, page), start, page, at))
            elif opened is not None:
                ranked.append(((opened, 0, count, -page), start, page, at))
        return [(start, page, at) for _, start, page, at in sorted(ranked, reverse=True)]


ENGINES = (PalEngine, KaleidoEngine, AtlusBmdEngine)
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
            raise LinkError('這個遊戲還不能直接讀取（目前支援：Pal 引擎、M2 Kaleido 引擎（STEINS;GATE RE:BOOT）、Atlus BMD（ペルソナ３ リロード））。'
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


def _letters(text):
    """Letters and digits only (the Reader compares a game line with a 台本 row the same way)."""
    import unicodedata
    return ''.join(c for c in unicodedata.normalize('NFKC', text) if c.isalnum())


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
                    mark = ''
                    if rows:
                        row = rows.get(key)
                        same = row and (not line['text'] or _letters(row.get('ja', '')) == _letters(line['text']))
                        mark = '✓ ' if same else ('✗ 台本的日文不同 ' if row else '✗ 台本裡沒有 ')
                    say(f"{mark}{line['label']}  [{line['speaker'] or '旁白'}]  {text}".replace('\n', ' / '))
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
