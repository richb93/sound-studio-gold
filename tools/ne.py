"""Minimal reader for 16-bit Windows NE executables: segments, entry table and resources."""
import struct

RT_NAMES = {1: 'CURSOR', 2: 'BITMAP', 3: 'ICON', 4: 'MENU', 5: 'DIALOG', 6: 'STRING',
            7: 'FONTDIR', 8: 'FONT', 9: 'ACCELERATOR', 10: 'RCDATA', 12: 'GROUP_CURSOR',
            14: 'GROUP_ICON', 16: 'VERSION'}


class NE:
    def __init__(self, path):
        self.data = open(path, 'rb').read()
        d = self.data
        self.ne = struct.unpack_from('<I', d, 0x3C)[0]
        assert d[self.ne:self.ne + 2] == b'NE'
        h = self.ne
        (self.entry_off, self.entry_len) = struct.unpack_from('<HH', d, h + 4)
        self.seg_count = struct.unpack_from('<H', d, h + 0x1C)[0]
        self.mod_count = struct.unpack_from('<H', d, h + 0x1E)[0]
        seg_tab, res_tab, resname_tab, modref_tab, imp_tab = struct.unpack_from('<HHHHH', d, h + 0x22)
        self.nonres_off = struct.unpack_from('<I', d, h + 0x2C)[0]
        self.align = struct.unpack_from('<H', d, h + 0x32)[0]
        self.cs_ip = struct.unpack_from('<I', d, h + 0x14)[0]
        self.segments = []
        for i in range(self.seg_count):
            off, ln, fl, mn = struct.unpack_from('<HHHH', d, h + seg_tab + i * 8)
            self.segments.append({'offset': off << self.align, 'length': ln or 0x10000,
                                  'flags': fl, 'minalloc': mn})
        self.modrefs = []
        for i in range(self.mod_count):
            o = struct.unpack_from('<H', d, h + modref_tab + i * 2)[0]
            n = d[h + imp_tab + o]
            self.modrefs.append(d[h + imp_tab + o + 1:h + imp_tab + o + 1 + n].decode('latin1'))
        self.imp_tab = h + imp_tab
        self.resources = self._read_resources(h + res_tab) if res_tab != resname_tab else []
        self.resident_names = self._names(h + resname_tab)
        self.nonresident_names = self._names(self.nonres_off) if self.nonres_off else []

    def _names(self, off):
        d = self.data
        out = []
        while d[off]:
            n = d[off]
            out.append((d[off + 1:off + 1 + n].decode('latin1'), struct.unpack_from('<H', d, off + 1 + n)[0]))
            off += n + 3
        return out

    def _read_resources(self, off):
        d = self.data
        base = off
        shift = struct.unpack_from('<H', d, off)[0]
        off += 2
        out = []
        while True:
            tid = struct.unpack_from('<H', d, off)[0]
            if tid == 0:
                break
            cnt = struct.unpack_from('<H', d, off + 2)[0]
            off += 8
            tname = RT_NAMES.get(tid & 0x7FFF, tid & 0x7FFF) if tid & 0x8000 else self._pstr(base + tid)
            for _ in range(cnt):
                ro, rl, fl, rid, _h, _u = struct.unpack_from('<HHHHHH', d, off)
                off += 12
                name = rid & 0x7FFF if rid & 0x8000 else self._pstr(base + rid)
                out.append({'type': tname, 'id': name, 'data': d[ro << shift:(ro << shift) + (rl << shift)]})
        return out

    def _pstr(self, off):
        n = self.data[off]
        return self.data[off + 1:off + 1 + n].decode('latin1')

    def find(self, rtype, rid=None):
        return [r for r in self.resources if r['type'] == rtype and (rid is None or r['id'] == rid)]

    def get(self, rtype, rid):
        r = self.find(rtype, rid)
        return r[0]['data'] if r else None

    def segment_data(self, idx):
        """Segment idx is 1-based; returns (code bytes, relocation bytes)."""
        s = self.segments[idx - 1]
        d = self.data
        if s['offset'] == 0:
            return b'', []
        ln = s['length'] if s['length'] != 0x10000 or True else 0x10000
        code = d[s['offset']:s['offset'] + ln]
        relocs = []
        if s['flags'] & 0x100:
            ro = s['offset'] + ln
            n = struct.unpack_from('<H', d, ro)[0]
            for i in range(n):
                relocs.append(struct.unpack_from('<BBHHH', d, ro + 2 + i * 8))
        return code, relocs


def parse_menu(data):
    """Win16 MENU resource -> nested list of (text, id or submenu, flags)."""
    pos = 4

    def items():
        nonlocal pos
        out = []
        while pos < len(data):
            flags = struct.unpack_from('<H', data, pos)[0]
            pos += 2
            if flags & 0x10:  # MF_POPUP
                end = data.index(b'\0', pos)
                text = data[pos:end].decode('latin1')
                pos = end + 1
                out.append((text, items(), flags))
            else:
                mid = struct.unpack_from('<H', data, pos)[0]
                pos += 2
                end = data.index(b'\0', pos)
                text = data[pos:end].decode('latin1')
                pos = end + 1
                out.append((text, mid, flags))
            if flags & 0x80:  # MF_END
                break
        return out
    return items()


def _sz_or_ord(data, pos):
    if data[pos] == 0xFF:
        return struct.unpack_from('<H', data, pos + 1)[0], pos + 3
    end = data.index(b'\0', pos)
    return data[pos:end].decode('latin1'), end + 1


CLASSES = {0x80: 'BUTTON', 0x81: 'EDIT', 0x82: 'STATIC', 0x83: 'LISTBOX', 0x84: 'SCROLLBAR', 0x85: 'COMBOBOX'}


def parse_dialog(data):
    style, n, x, y, cx, cy = struct.unpack_from('<IBhhhh', data, 0)
    pos = 13
    menu, pos = _sz_or_ord(data, pos)
    if data[pos - 1:pos] == b'' and False:
        pass
    end = data.index(b'\0', pos)
    cls = data[pos:end].decode('latin1')
    pos = end + 1
    end = data.index(b'\0', pos)
    caption = data[pos:end].decode('latin1')
    pos = end + 1
    font = None
    if style & 0x40:  # DS_SETFONT
        size = struct.unpack_from('<H', data, pos)[0]
        end = data.index(b'\0', pos + 2)
        font = (data[pos + 2:end].decode('latin1'), size)
        pos = end + 1
    items = []
    for _ in range(n):
        ix, iy, icx, icy, iid, istyle = struct.unpack_from('<hhhhHI', data, pos)
        pos += 14
        c = data[pos]
        if c & 0x80:
            icls = CLASSES.get(c, c)
            pos += 1
        else:
            end = data.index(b'\0', pos)
            icls = data[pos:end].decode('latin1')
            pos = end + 1
        if data[pos] == 0xFF:
            text = struct.unpack_from('<H', data, pos + 1)[0]
            pos += 3
        else:
            end = data.index(b'\0', pos)
            text = data[pos:end].decode('latin1')
            pos = end + 1
        extra = data[pos]
        pos += 1 + extra
        items.append({'x': ix, 'y': iy, 'cx': icx, 'cy': icy, 'id': iid, 'style': istyle,
                      'class': icls, 'text': text})
    return {'style': style, 'x': x, 'y': y, 'cx': cx, 'cy': cy, 'menu': menu, 'class': cls,
            'caption': caption, 'font': font, 'items': items}


def parse_strings(rid, data):
    """STRINGTABLE block rid -> {string id: text}."""
    out = {}
    pos = 0
    for i in range(16):
        if pos >= len(data):
            break
        n = data[pos]
        if n:
            out[(rid - 1) * 16 + i] = data[pos + 1:pos + 1 + n].decode('latin1')
        pos += 1 + n
    return out


def parse_accel(data):
    out = []
    for pos in range(0, len(data) - 4, 5):
        fl, key, cmd = struct.unpack_from('<BHH', data, pos)
        out.append((fl, key, cmd))
        if fl & 0x80:
            break
    return out
