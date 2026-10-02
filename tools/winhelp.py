"""Reader for Windows 3.1 WinHelp (.hlp) files: topic text and embedded |bm images."""
import bisect
import struct


def lz77(data, limit=None):
    out = bytearray()
    i = 0
    n = len(data)
    while i < n:
        flags = data[i]
        i += 1
        for bit in range(8):
            if i >= n:
                break
            if flags & (1 << bit):
                if i + 1 >= n:
                    i = n
                    break
                w = data[i] | (data[i + 1] << 8)
                i += 2
                length = (w >> 12) + 3
                pos = (w & 0xFFF) + 1
                for _ in range(length):
                    out.append(out[-pos] if pos <= len(out) else 0)
            else:
                out.append(data[i])
                i += 1
            if limit and len(out) >= limit:
                return bytes(out)
    return bytes(out)


def rle(data):
    out = bytearray()
    i = 0
    while i < len(data):
        b = data[i]
        i += 1
        if b & 0x80:
            out += data[i:i + (b & 0x7F)]
            i += b & 0x7F
        else:
            if i < len(data):
                out += bytes([data[i]]) * b
            i += 1
    return bytes(out)


class HLP:
    def __init__(self, path):
        self.d = open(path, 'rb').read()
        magic, dirstart, _ff, _size = struct.unpack_from('<IiiI', self.d, 0)
        assert magic == 0x00035F3F
        self.files = self._btree_leaves(dirstart + 9, self._dir_entry)
        sysd = self.file('|SYSTEM')
        _m, self.minor, self.major, _gd, self.flags = struct.unpack_from('<HHHIH', sysd, 0)
        self.compressed = self.minor > 16 and self.flags in (4, 8)
        self.blocksize = 2048 if self.flags == 8 else 4096
        self.phrases = self._load_phrases()

    def _dir_entry(self, d, p):
        e = d.index(b'\0', p)
        return d[p:e].decode('latin1'), struct.unpack_from('<i', d, e + 1)[0], e + 5

    def _btree_leaves(self, off, entry):
        d = self.d
        magic, flags, pagesize = struct.unpack_from('<HHH', d, off)
        assert magic == 0x293B
        root, _neg1, total, nlevels, nentries = struct.unpack_from('<hhhhi', d, off + 26)
        pages = off + 38
        page = root
        for _ in range(nlevels - 1):
            page = struct.unpack_from('<h', d, pages + page * pagesize + 4)[0]
        out = {}
        while page != -1:
            p = pages + page * pagesize
            _u, n, _prev, nxt = struct.unpack_from('<HhhH', d, p)
            nxt = struct.unpack_from('<h', d, p + 6)[0]
            q = p + 8
            for _ in range(n):
                k, v, q = entry(d, q)
                out[k] = v
            page = nxt
        return out

    def file(self, name):
        off = self.files[name]
        _res, used, _fl = struct.unpack_from('<IIB', self.d, off)
        return self.d[off + 9:off + 9 + used]

    def _load_phrases(self):
        if '|Phrases' not in self.files:
            return None
        d = self.file('|Phrases')
        num, _hundred = struct.unpack_from('<HH', d, 0)
        if self.minor <= 16:
            offs = struct.unpack_from('<%dH' % (num + 1), d, 4)
            data = d
            base = 4
            return [d[base + offs[i]:base + offs[i + 1]] for i in range(num)]
        size = struct.unpack_from('<I', d, 4)[0]
        offs = struct.unpack_from('<%dH' % (num + 1), d, 8)
        raw = lz77(d[8 + (num + 1) * 2:], size)
        base = (num + 1) * 2
        return [raw[offs[i] - base:offs[i + 1] - base] for i in range(num)]

    def unphrase(self, data):
        out = bytearray()
        i = 0
        while i < len(data):
            c = data[i]
            i += 1
            if 0 < c < 16 and self.phrases is not None and i < len(data):
                idx = 256 * (c - 1) + data[i]
                i += 1
                out += self.phrases[idx >> 1]
                if idx & 1:
                    out += b' '
            else:
                out.append(c)
        return bytes(out)

    def _blocks(self):
        d = self.file('|TOPIC')
        out = []
        for b in range(0, len(d), self.blocksize):
            blk = d[b + 12:b + self.blocksize]
            out.append(lz77(blk, 16384 - 12) if self.compressed else blk)
        return d, out

    def _read(self, blocks, pos, n):
        """Read n bytes at TOPICPOS pos, continuing into following blocks."""
        bi, off = divmod(pos, 0x4000) if self.compressed else divmod(pos, self.blocksize)
        off -= 12
        out = bytearray()
        while len(out) < n and bi < len(blocks):
            chunk = blocks[bi][off:off + n - len(out)]
            out += chunk
            bi += 1
            off = 0
        return bytes(out)

    def topics(self):
        """Yields (title, [paragraph strings])."""
        raw, blocks = self._blocks()
        pos = struct.unpack_from('<i', raw, 4)[0]  # FirstTopicLink of block 0
        cur = None
        seen = set()
        while pos not in seen and pos >= 0:
            seen.add(pos)
            hdr = self._read(blocks, pos, 21)
            if len(hdr) < 21:
                break
            bsize, dlen2, _prev, nxt, dlen1, rtype = struct.unpack_from('<iiiiiB', hdr, 0)
            if bsize <= 0:
                break
            rec = self._read(blocks, pos, bsize)
            ld2c = rec[dlen1:bsize]
            ld2 = self.unphrase(ld2c) if dlen2 > len(ld2c) else ld2c
            if rtype == 2:
                if cur:
                    yield cur
                cur = (ld2.split(b'\0')[0].decode('latin1'), [])
            elif rtype in (0x20, 0x23) and cur is not None:
                parts = [q.decode('latin1') for q in ld2.split(b'\0')]
                cur[1].append(' '.join(q for q in parts if q))
            if nxt <= pos and nxt != -1:
                pass
            pos = nxt
        if cur:
            yield cur

    # ---- images -----------------------------------------------------------
    def images(self, name):
        """Decode an SHG/MRB |bm file into a list of PIL images."""
        from PIL import Image
        d = self.file(name)
        magic, n = struct.unpack_from('<HH', d, 0)
        out = []
        for k in range(n):
            po = struct.unpack_from('<I', d, 4 + 4 * k)[0]
            ptype, pack = d[po], d[po + 1]
            p = po + 2
            if ptype not in (5, 6):
                continue

            def cul(p):
                w = struct.unpack_from('<H', d, p)[0]
                if w & 1:
                    return struct.unpack_from('<I', d, p)[0] >> 1, p + 4
                return w >> 1, p + 2

            def cus(p):
                b = d[p]
                if b & 1:
                    return struct.unpack_from('<H', d, p)[0] >> 1, p + 2
                return b >> 1, p + 1
            _xdpi, p = cul(p)
            _ydpi, p = cul(p)
            planes, p = cus(p)
            bpp, p = cus(p)
            w, p = cul(p)
            h, p = cul(p)
            ncol, p = cul(p)
            _imp, p = cul(p)
            csize, p = cul(p)
            _hs, p = cul(p)
            coff, _hoff = struct.unpack_from('<II', d, p)
            p += 8
            pal = []
            if ptype == 6 and bpp <= 8:
                nc = ncol or (1 << bpp)
                for i in range(nc):
                    bb, gg, rr, _ = d[p + 4 * i:p + 4 * i + 4]
                    pal.append((rr, gg, bb))
            elif bpp == 1:
                pal = [(0, 0, 0), (255, 255, 255)]
            raw = d[po + coff:po + coff + csize]
            if pack == 1:
                raw = rle(raw)
            elif pack == 2:
                raw = lz77(raw)
            elif pack == 3:
                raw = rle(lz77(raw))
            stride = ((w * bpp + 31) // 32) * 4 if ptype == 6 else ((w * bpp + 15) // 16) * 2
            img = Image.new('RGB', (w, h))
            px = img.load()
            for y in range(h):
                row = raw[(h - 1 - y) * stride:(h - y) * stride] if ptype == 6 else raw[y * stride:(y + 1) * stride]
                for x in range(w):
                    if bpp == 24:
                        b0 = x * 3
                        if b0 + 2 < len(row):
                            px[x, y] = (row[b0 + 2], row[b0 + 1], row[b0])
                        continue
                    bit = x * bpp
                    if bit // 8 >= len(row):
                        continue
                    v = (row[bit // 8] >> (8 - bpp - bit % 8)) & ((1 << bpp) - 1)
                    px[x, y] = pal[v] if v < len(pal) else (255, 0, 255)
            out.append(img)
        return out



# ---- structured topics (paragraphs, fonts, hotspots) ---------------------
def btree(d, entry):
    """Leaf entries of a B-tree held in internal file data d; entry(d, pos) -> (key, value, next)."""
    magic, _flags, pagesize = struct.unpack_from('<HHH', d, 0)
    assert magic == 0x293B
    root, _n1, _total, nlevels, _nentries = struct.unpack_from('<hhhhi', d, 26)
    page = root
    for _ in range(nlevels - 1):
        page = struct.unpack_from('<h', d, 38 + page * pagesize + 4)[0]
    out = []
    while page != -1:
        p = 38 + page * pagesize
        _u, n, _prev, nxt = struct.unpack_from('<Hhhh', d, p)
        q = p + 8
        for _ in range(n):
            k, v, q = entry(d, q)
            out.append((k, v))
        page = nxt
    return out


class Reader:
    """Reads LinkData1: plain and WinHelp-compressed integers."""

    def __init__(self, d):
        self.d, self.p = d, 0

    def _u(self, fmt, n):
        v = struct.unpack_from(fmt, self.d, self.p)[0]
        self.p += n
        return v

    def byte(self):
        return self._u('<B', 1)

    def word(self):
        return self._u('<H', 2)

    def short(self):
        return self._u('<h', 2)

    def long(self):
        return self._u('<i', 4)

    def cushort(self):
        return self._u('<H', 2) >> 1 if self.d[self.p] & 1 else self._u('<B', 1) >> 1

    def csshort(self):
        return self._u('<H', 2) // 2 - 0x4000 if self.d[self.p] & 1 else self._u('<B', 1) // 2 - 0x40

    def culong(self):
        return self._u('<I', 4) >> 1 if self.d[self.p] & 1 else self._u('<H', 2) >> 1

    def cslong(self):
        return self._u('<I', 4) // 2 - 0x40000000 if self.d[self.p] & 1 else self._u('<H', 2) // 2 - 0x4000


def fonts(h):
    """|FONT descriptors: bold, italic, size (points) and colour of each font number."""
    d = h.file('|FONT')
    nf, nd, fo, do = struct.unpack_from('<HHHH', d, 0)
    out = []
    for i in range(nd):
        p = do + i * 11
        attr, half = d[p], d[p + 1]
        out.append({'b': bool(attr & 1), 'i': bool(attr & 2), 'size': half / 2.0,
                    'color': '#%02x%02x%02x' % tuple(d[p + 5:p + 8])})
    return out


def _paragraph_info(r):
    r.byte()
    r.byte()
    r.word()                                   # id
    bits = r.word()
    for bit in (1,):
        if bits & bit:
            r.cslong()
    for bit in (2, 4, 8, 0x10, 0x20, 0x40):    # spacing above/below/lines, indents
        if bits & bit:
            r.csshort()
    if bits & 0x100:                           # border
        r.byte()
        r.word()
    if bits & 0x200:                           # tab stops
        for _ in range(r.csshort()):
            if r.cushort() & 0x4000:
                r.cushort()


def rich_topics(h):
    """[{title, paras}]: each paragraph a list of runs [text, style], or [None, {bm, align}] for a
    picture; style holds b, i, size, color and link / popup (the target topic's title)."""
    font = fonts(h)
    ctx = dict(btree(h.file('|CONTEXT'),
                     lambda d, q: (struct.unpack_from('<I', d, q)[0], struct.unpack_from('<i', d, q + 4)[0], q + 8)))

    def title_entry(d, q):
        e = d.index(b'\0', q + 4)
        return struct.unpack_from('<i', d, q)[0], d[q + 4:e].decode('latin1'), e + 1
    titles = sorted(btree(h.file('|TTLBTREE'), title_entry))
    offsets = [o for o, _t in titles]

    def target(hsh):
        off = ctx.get(hsh)
        if off is None:
            return None
        i = bisect.bisect_right(offsets, off) - 1
        return titles[i][1] if i >= 0 else None

    raw, blocks = h._blocks()
    pos = struct.unpack_from('<i', raw, 4)[0]
    seen = set()
    cur = None
    out = []
    while pos not in seen and pos >= 0:
        seen.add(pos)
        hdr = h._read(blocks, pos, 21)
        if len(hdr) < 21:
            break
        bsize, dlen2, _prev, nxt, dlen1, rtype = struct.unpack_from('<iiiiiB', hdr, 0)
        if bsize <= 0:
            break
        rec = h._read(blocks, pos, bsize)
        ld2 = rec[dlen1:bsize]
        if dlen2 > len(ld2):
            ld2 = h.unphrase(ld2)
        if rtype == 2:
            cur = {'title': ld2.split(b'\0')[0].decode('latin1'), 'paras': []}
            out.append(cur)
        elif rtype in (0x20, 0x23) and cur is not None:
            _display(rec[21:dlen1], ld2, rtype, cur['paras'], font, target)
        pos = nxt
    return out


def _display(ld1, ld2, rtype, paras, font, target):
    """Decode one text record: the commands in ld1 interleaved with the strings in ld2."""
    r = Reader(ld1)
    r.culong()                                 # topic size
    r.cushort()                                # topic length
    texts = ld2.split(b'\0')
    ti = 0
    widths = []
    if rtype == 0x23:                          # table: columns
        ncol, ttype = r.byte(), r.byte()
        if ttype in (0, 2):
            r.short()
        for _ in range(ncol):
            widths.append(r.short())
            widths[-1] += r.short()            # gap
    style = {}
    link = None
    para = []

    def emit(txt):
        if txt:
            st = dict(style)
            if link:
                st[link[0]] = link[1]
            para.append([txt, st])
    while True:
        if rtype == 0x23:                      # table cell
            col = r.short()
            if col == -1:
                break
            r.word()
            r.byte()
            if col == 0 and para:
                paras.append(para)
                para = []
            elif col > 0:
                while para and para[-1][0] in ('\t', '\n'):
                    para.pop()
                para.append(['\t', {'cell': widths}])
        _paragraph_info(r)
        while True:
            if ti < len(texts):
                emit(texts[ti].decode('latin1'))
                ti += 1
            c = r.byte()
            if c == 0xFF:
                break
            if c == 0x20:
                r.long()
            elif c == 0x21:
                r.word()
            elif c == 0x80:                    # font
                fn = r.word()
                style = dict(font[fn]) if fn < len(font) else {}
            elif c == 0x81:
                emit('\n')
            elif c == 0x82:                    # end of paragraph
                if rtype == 0x23:
                    emit('\n')
                else:
                    paras.append(para)
                    para = []
            elif c == 0x83:
                emit('\t')
            elif c in (0x86, 0x87, 0x88):      # picture: inline, left, right
                kind = r.byte()
                size = r.cslong()
                if kind == 0x22:
                    r.cushort()
                start = r.p
                if kind in (0x03, 0x22):
                    r.word()
                    para.append([None, {'bm': r.word(), 'align': {0x86: 'inline', 0x87: 'left', 0x88: 'right'}[c]}])
                r.p = start + size
            elif c == 0x89:                    # end of hotspot
                link = None
            elif c == 0x8B:
                emit('\xa0')
            elif c == 0x8C:
                emit('-')
            elif c in (0xC8, 0xCC):            # macro
                r.p += r.short()
            elif c in (0xE0, 0xE1):            # WinHelp 3.0 topic number
                r.long()
                link = None
            elif c in (0xE2, 0xE3, 0xE6, 0xE7):   # popup / jump by context hash
                link = ('popup' if c in (0xE2, 0xE6) else 'link', target(struct.unpack_from('<I', ld1, r.p)[0]))
                r.p += 4
            elif c in (0xEA, 0xEB, 0xEE, 0xEF):   # into another file
                r.p += r.word()
                link = None
            else:
                raise ValueError('unknown WinHelp command %02x' % c)
        if rtype != 0x23:
            break
    if para:
        paras.append(para)
