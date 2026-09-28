"""MDX 2.0 writer and indexer, compatible with jp-game-reader's mdict-index.sqlite3.

write_mdx(path, entries, title, description)
    entries: list of (key, html) — html may be '@@@LINK=target'. Keys may repeat.
index_mdx(mdx_path, db, code, name, root, css, rel_path)
    Parse any MDX 2.0 file (Encrypted 0 or 2, zlib/none record blocks) and insert its
    records/blocks rows into an open sqlite3 connection that has the reader's schema.
"""
import re, sqlite3, struct, zlib
from datetime import date

SCHEMA = '''
CREATE TABLE IF NOT EXISTS files(id INTEGER PRIMARY KEY,code TEXT,path TEXT,kind TEXT,size INTEGER,mtime INTEGER,encoding TEXT);
CREATE TABLE IF NOT EXISTS blocks(file INTEGER,start INTEGER,end INTEGER,offset INTEGER,size INTEGER,PRIMARY KEY(file,start));
CREATE TABLE IF NOT EXISTS records(id INTEGER PRIMARY KEY,file INTEGER,word TEXT,norm TEXT,start INTEGER,end INTEGER);
CREATE TABLE IF NOT EXISTS dictionaries(code TEXT PRIMARY KEY,name TEXT,root TEXT,css TEXT);
CREATE INDEX IF NOT EXISTS records_file_norm ON records(file,norm);
'''

# ----------------------------------------------------------------------------- helpers
def _block(data, compress=True):
    body = zlib.compress(data, 9) if compress else data
    return struct.pack('<I', 2 if compress else 0) + struct.pack('>I', zlib.adler32(data) & 0xffffffff) + body

def _unblock(raw):
    mode = struct.unpack('<I', raw[:4])[0]
    if mode == 0:
        return raw[8:]
    if mode == 2:
        return zlib.decompress(raw[8:])
    raise ValueError('Unsupported MDX block compression %d (LZO is not supported).' % mode)

_STRIP = re.compile(r'[ _=,.;:!?@%&#~`()\[\]<>{}/\\$+\-*^\'"\t|]')
def sort_key(key):
    """MDict orders keys case-insensitively with punctuation stripped (StripKey=Yes)."""
    return _STRIP.sub('', key).lower().encode('utf-8')

# ----------------------------------------------------------------------------- writer
def write_mdx(path, entries, title, description, stylesheet=''):
    items = sorted(((k, v) for k, v in entries), key=lambda kv: (sort_key(kv[0]), kv[0]))
    records, offsets, pos = [], [], 0
    for key, text in items:
        data = (text.rstrip('\r\n') + '\r\n').encode('utf-8') + b'\x00'
        offsets.append(pos); records.append(data); pos += len(data)

    header = ('<Dictionary GeneratedByEngineVersion="2.0" RequiredEngineVersion="2.0" Format="Html" '
              'KeyCaseSensitive="No" StripKey="Yes" Encrypted="0" RegisterBy="EMail" '
              f'Description="{_attr(description)}" Title="{_attr(title)}" Encoding="UTF-8" '
              f'CreationDate="{date.today():%Y-%m-%d}" Compact="Yes" Compat="Yes" Left="&lt;" Right="&gt;" '
              f'DataSourceFormat="106" StyleSheet="{_attr(stylesheet)}"/>\r\n\x00').encode('utf-16-le')
    out = bytearray(struct.pack('>I', len(header)) + header + struct.pack('<I', zlib.adler32(header) & 0xffffffff))

    # key blocks (~32 KB of keys each)
    key_blocks, info = [], bytearray()
    i = 0
    while i < len(items):
        chunk, size, first = bytearray(), 0, i
        while i < len(items) and size < 32768:
            k = items[i][0].encode('utf-8')
            chunk += struct.pack('>Q', offsets[i]) + k + b'\x00'; size = len(chunk); i += 1
        comp = _block(bytes(chunk))
        key_blocks.append(comp)
        fk, lk = items[first][0].encode('utf-8'), items[i - 1][0].encode('utf-8')
        info += struct.pack('>Q', i - first)
        info += struct.pack('>H', len(fk)) + fk + b'\x00' + struct.pack('>H', len(lk)) + lk + b'\x00'
        info += struct.pack('>QQ', len(comp), len(chunk))
    info_comp = _block(bytes(info))
    key_total = sum(len(b) for b in key_blocks)
    kh = struct.pack('>QQQQQ', len(key_blocks), len(items), len(info), len(info_comp), key_total)
    out += kh + struct.pack('>I', zlib.adler32(kh) & 0xffffffff) + info_comp
    for b in key_blocks:
        out += b

    # record blocks (~64 KB decompressed each)
    blocks, cur = [], bytearray()
    for r in records:
        cur += r
        if len(cur) >= 65536:
            blocks.append(bytes(cur)); cur = bytearray()
    if cur:
        blocks.append(bytes(cur))
    comp = [_block(b) for b in blocks]
    out += struct.pack('>QQQQ', len(blocks), len(items), 16 * len(blocks), sum(len(c) for c in comp))
    for c, b in zip(comp, blocks):
        out += struct.pack('>QQ', len(c), len(b))
    for c in comp:
        out += c
    with open(path, 'wb') as f:
        f.write(out)
    return len(items)

def _attr(s):
    return s.replace('&', '&amp;').replace('"', '&quot;').replace('<', '&lt;').replace('>', '&gt;')

# ----------------------------------------------------------------------------- reader / indexer
def _ripemd128(message):
    def f(j, x, y, z):
        return [x ^ y ^ z, (x & y) | (~x & z), (x | ~y) ^ z, (x & z) | (y & ~z)][j // 16] & 0xffffffff
    K = [0, 0x5A827999, 0x6ED9EBA1, 0x8F1BBCDC]; KK = [0x50A28BE6, 0x5C4DD124, 0x6D703EF3, 0]
    r = [0,1,2,3,4,5,6,7,8,9,10,11,12,13,14,15, 7,4,13,1,10,6,15,3,12,0,9,5,2,14,11,8,
         3,10,14,4,9,15,8,1,2,7,0,6,13,11,5,12, 1,9,11,10,0,8,12,4,13,3,7,15,14,5,6,2]
    rr = [5,14,7,0,9,2,11,4,13,6,15,8,1,10,3,12, 6,11,3,7,0,13,5,10,14,15,8,12,4,9,1,2,
          15,5,1,3,7,14,6,9,11,8,12,2,10,0,4,13, 8,6,4,1,3,11,15,0,5,12,2,13,9,7,10,14]
    s = [11,14,15,12,5,8,7,9,11,13,14,15,6,7,9,8, 7,6,8,13,11,9,7,15,7,12,15,9,11,7,13,12,
         11,13,6,7,14,9,13,15,14,8,13,6,5,12,7,5, 11,12,14,15,14,15,9,8,9,14,5,6,8,6,5,12]
    ss = [8,9,9,11,13,15,15,5,7,7,8,11,14,14,12,6, 9,13,15,7,12,8,9,11,7,7,12,7,6,15,13,11,
          9,7,15,11,8,6,6,14,12,13,5,14,13,13,7,5, 15,5,8,11,14,14,6,14,6,9,12,9,12,5,15,8]
    rol = lambda x, n: ((x << n) | (x >> (32 - n))) & 0xffffffff
    h = [0x67452301, 0xEFCDAB89, 0x98BADCFE, 0x10325476]
    msg = bytearray(message); ml = len(message) * 8
    msg.append(0x80)
    while len(msg) % 64 != 56:
        msg.append(0)
    msg += struct.pack('<Q', ml)
    for i in range(0, len(msg), 64):
        X = struct.unpack('<16I', msg[i:i + 64])
        A, B, C, D = h; AA, BB, CC, DD = h
        for j in range(64):
            T = rol((A + f(j, B, C, D) + X[r[j]] + K[j // 16]) & 0xffffffff, s[j]); A, D, C, B = D, C, B, T
            T = rol((AA + f(63 - j, BB, CC, DD) + X[rr[j]] + KK[j // 16]) & 0xffffffff, ss[j]); AA, DD, CC, BB = DD, CC, BB, T
        T = (h[1] + C + DD) & 0xffffffff
        h[1] = (h[2] + D + AA) & 0xffffffff; h[2] = (h[3] + A + BB) & 0xffffffff
        h[3] = (h[0] + B + CC) & 0xffffffff; h[0] = T
    return struct.pack('<4I', *h)

def _decrypt_key_info(data):
    key = _ripemd128(data[4:8] + struct.pack('<L', 0x3695))
    out, prev = bytearray(data[:8]), 0x36
    for i, b in enumerate(data[8:]):
        t = ((b >> 4) | (b << 4)) & 0xff
        out.append(t ^ prev ^ (i & 0xff) ^ key[i % len(key)]); prev = b
    return bytes(out)

def read_header(f):
    size = struct.unpack('>I', f.read(4))[0]
    text = f.read(size).decode('utf-16-le', errors='replace')
    f.read(4)
    return dict(re.findall(r'(\w+)="((?:.|\r|\n)*?)"', text))

def iter_mdx(path):
    """(key, start, end) rows in the decompressed record stream, record blocks, and key encoding.
    Works for .mdx and .mdd (resource archives: UTF-16 keys such as '\\\\audio\\\\x.mp3')."""
    is_mdd = str(path).lower().endswith('.mdd')
    with open(path, 'rb') as f:
        head = read_header(f)
        if is_mdd:
            head['Encoding'] = 'UTF-16'
        if float(head.get('GeneratedByEngineVersion', '2.0')) < 2.0:
            raise ValueError('Only MDX 2.0 files are supported.')
        enc = (head.get('Encrypted', '0') or '0').strip()
        encrypted = 0 if enc.lower() in ('no', '0', '') else (2 if enc.lower() == 'yes' else int(enc))
        if encrypted & 1:
            raise ValueError('Record-encrypted MDX (registration required) is not supported.')
        encoding = head.get('Encoding', 'UTF-8') or 'UTF-8'
        encoding = 'utf-8' if encoding.upper() in ('UTF-8', '') else ('utf-16-le' if encoding.upper().startswith('UTF-16') else encoding.lower())
        nb, ne, info_decomp, info_size, key_size = struct.unpack('>QQQQQ', f.read(40)); f.read(4)
        info = f.read(info_size)
        if encrypted & 2:
            info = _decrypt_key_info(info)
        info = _unblock(info)
        pos, sizes = 0, []
        width = 2 if encoding == 'utf-16-le' else 1
        for _ in range(nb):
            pos += 8
            n = struct.unpack('>H', info[pos:pos + 2])[0]; pos += 2 + (n + 1) * width
            n = struct.unpack('>H', info[pos:pos + 2])[0]; pos += 2 + (n + 1) * width
            csize, dsize = struct.unpack('>QQ', info[pos:pos + 16]); pos += 16
            sizes.append(csize)
        keys = []
        for csize in sizes:
            data = _unblock(f.read(csize)); p = 0
            while p < len(data):
                off = struct.unpack('>Q', data[p:p + 8])[0]; p += 8
                if width == 2:
                    q = p
                    while data[q:q + 2] != b'\x00\x00':
                        q += 2
                    k = data[p:q].decode('utf-16-le', errors='replace'); p = q + 2
                else:
                    q = data.index(b'\x00', p); k = data[p:q].decode(encoding, errors='replace'); p = q + 1
                keys.append((k, off))
        nrb, nre, rinfo, rsize = struct.unpack('>QQQQ', f.read(32))
        rb = [struct.unpack('>QQ', f.read(16)) for _ in range(nrb)]
        offset, start, blocks = f.tell(), 0, []
        for csize, dsize in rb:
            blocks.append((start, start + dsize, offset, csize))
            offset += csize; start += dsize
        total = start
    rows = []
    for i, (k, off) in enumerate(keys):
        end = keys[i + 1][1] if i + 1 < len(keys) else total
        rows.append((k, off, end))
    return rows, blocks, encoding

def index_mdd(mdd_path, db, code, rel_path):
    """Add one .mdd (media) file of dictionary `code` to an open reader index (keys stored like the reader expects:
    forward slashes, no leading slash, casefolded)."""
    import os
    rows, blocks, _ = iter_mdx(mdd_path)
    st = os.stat(mdd_path)
    cur = db.execute('INSERT INTO files(code,path,kind,size,mtime,encoding) VALUES(?,?,?,?,?,?)',
                     (code, rel_path, '.mdd', st.st_size, st.st_mtime_ns, 'binary'))
    fid = cur.lastrowid
    db.executemany('INSERT INTO blocks(file,start,end,offset,size) VALUES(?,?,?,?,?)', [(fid, s_, e, o, c) for s_, e, o, c in blocks])
    db.executemany('INSERT INTO records(file,word,norm,start,end) VALUES(?,?,?,?,?)',
                   [(fid, k, k.replace('\\', '/').lstrip('/').casefold(), s_, e) for k, s_, e in rows])
    return fid, len(rows)

def index_mdx(mdx_path, db, code, name, root, css, rel_path, normalize):
    """Replace dictionary `code` in an open reader index with the contents of mdx_path."""
    import os
    rows, blocks, encoding = iter_mdx(mdx_path)
    old = [r[0] for r in db.execute('SELECT id FROM files WHERE code=?', (code,))]
    for fid in old:
        db.execute('DELETE FROM records WHERE file=?', (fid,))
        db.execute('DELETE FROM blocks WHERE file=?', (fid,))
    db.execute('DELETE FROM files WHERE code=?', (code,))
    if db.execute('SELECT 1 FROM dictionaries WHERE code=?', (code,)).fetchone():
        db.execute('UPDATE dictionaries SET name=?,root=?,css=? WHERE code=?', (name, root, css, code))  # keeps its list position
    else:
        db.execute('INSERT INTO dictionaries(code,name,root,css) VALUES(?,?,?,?)', (code, name, root, css))
    st = os.stat(mdx_path)
    cur = db.execute('INSERT INTO files(code,path,kind,size,mtime,encoding) VALUES(?,?,?,?,?,?)',
                     (code, rel_path, '.mdx', st.st_size, st.st_mtime_ns, encoding))
    fid = cur.lastrowid
    db.executemany('INSERT INTO blocks(file,start,end,offset,size) VALUES(?,?,?,?,?)', [(fid, s, e, o, c) for s, e, o, c in blocks])
    db.executemany('INSERT INTO records(file,word,norm,start,end) VALUES(?,?,?,?,?)', [(fid, k, normalize(k), s, e) for k, s, e in rows])
    return fid, len(rows)
