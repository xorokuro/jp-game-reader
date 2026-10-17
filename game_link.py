"""Follow the line a running game is showing by reading its memory (no OCR).

Read-only: the reader opens the game process with query + read rights only and
calls ReadProcessMemory. It never writes to, injects into or pauses the game.
Windows only; other platforms report the link as unavailable.

Engines are small adapters. Each one finds the game's own line number for the
text on screen, which matches the ``id`` of that line in an extracted 台本
(rows use ``source`` "main" and ``id`` = the engine's line number).

Supported engine:

* Pal (CRYSTALiA's ディメンション凸ラバース!! and other games built on dll\\Pal.dll).
  The script VM keeps the current line as a byte offset into TEXT.DAT; the
  4-byte header of that entry is the line number. The VM context is found by
  scanning for the loaded TEXT.DAT buffer ("_TEXT_LIST__") and the context
  field that points at it, verified by the script buffer ("Sv20").

Command line (diagnostic): ``python game_link.py [--pid N] [--process NAME]``
prints each new line as you advance the game.
"""
import argparse
import ctypes
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
            raise LinkError('Game link needs Windows.')
        self.pid = int(pid)
        self.handle = _kernel.OpenProcess(PROCESS_QUERY_INFORMATION | PROCESS_VM_READ, False, self.pid)
        if not self.handle:
            raise LinkError('Cannot open the game process (it closed, or runs as administrator).')

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
            if (info.State == MEM_COMMIT and info.Protect & READABLE and not info.Protect & PAGE_GUARD
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


class PalEngine:
    """Pal engine (dll\\Pal.dll). Offsets are from the VM context (task data + 0x338)."""
    name = 'Pal'
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
        """The line on screen: {'number', 'text', 'speaker'} or None (no line yet)."""
        found = self.entry(self.process.u32(self.context + self.CURRENT))
        if not found:
            return None
        number, raw = found
        name = self.entry(self.process.u32(self.context + self.NAME))
        return {'number': number, 'text': visible(raw), 'speaker': visible(name[1]) if name else ''}


ENGINES = (PalEngine,)
TAGS = re.compile(r'<r[^<>]*>|</r>|</?d\d*>|</?s\d*>|<[^<>]{0,40}>')


def visible(raw):
    """Readable Japanese from engine text: line breaks kept, ruby/size/dictionary tags removed.
    A Chinese subtitle line added by a bilingual patch (<br><sNN>…) is not part of the Japanese."""
    text = raw.decode('cp932', 'replace')
    text = re.split(r'<br><s(?:15|17|20)>', text, maxsplit=1)[0]
    text = text.replace('<br>', '\n')
    return TAGS.sub('', text).replace('%0', '').strip()


class Link:
    """Attach to one game process and report its current line."""

    def __init__(self, pid):
        self.process = Process(pid)
        self.engine = None
        for engine in ENGINES:
            self.engine = engine.detect(self.process)
            if self.engine:
                break
        if not self.engine:
            self.process.close()
            raise LinkError('This game is not supported for direct reading yet (supported: Pal engine games). '
                            'If it is still starting up, wait for the title screen and try again.')

    @property
    def pid(self):
        return self.process.pid

    def alive(self):
        return self.process.alive()

    def current(self):
        if not self.process.alive():
            raise LinkError('The game closed.')
        return self.engine.current()

    def close(self):
        self.process.close()


def main():
    parser = argparse.ArgumentParser(description='Print the line a running game shows (read-only).')
    parser.add_argument('--pid', type=int)
    parser.add_argument('--process', default='totsulover.exe')
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

    pid = args.pid or next((p for p, name in processes() if name.lower() == args.process.lower()), None)
    if not pid:
        say(f'找不到 {args.process}：請先開遊戲。')
        return 1
    started = time.monotonic()
    link = Link(pid)
    say(f'已連上 pid {pid}（{link.engine.name} 引擎）context=0x{link.engine.context:08X} TEXT=0x{link.engine.text:08X} '
        f'size={link.engine.size} lines={link.engine.count}  花 {time.monotonic() - started:.1f} 秒')
    last = None
    try:
        while not args.seconds or time.monotonic() - started < args.seconds:
            line = link.current()
            key = line and line['number']
            if key != last:
                last = key
                if line:
                    say(f"#{line['number']}  [{line['speaker'] or '旁白'}]  {line['text']}".replace('\n', ' / '))
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
