"""Reader for Windows 3.1 WinHelp (.hlp) files: topic text and embedded |bm images."""
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
