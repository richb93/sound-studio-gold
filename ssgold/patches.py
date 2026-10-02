"""Patch lists (.PLS), drum kits (.DRM) and the port/channel -> patch list routing."""
import os
import struct

from . import resources


class PatchList:
    """Text file: 'patc', instrument name, prefix, then program names.

    A line starting with '*' opens the next bank section; the bank number is the section's
    position (so XG's '*Tutti 1' is bank 40).  Programs absent from a bank fall back to bank 0,
    as in the original (sub_7_063a).
    """

    def __init__(self, path):
        self.path = path
        with open(path, 'rb') as f:
            lines = f.read().decode('latin1').replace('\r', '').split('\n')
        if not lines or lines[0].strip() != 'patc':
            raise ValueError('%s is not an Evolution Patch List File' % os.path.basename(path))
        self.instrument = lines[1] if len(lines) > 1 else ''
        self.prefix = lines[2] if len(lines) > 2 else ''
        self.banks = [('', [])]
        for ln in lines[3:]:
            if ln.startswith('*'):
                self.banks.append((ln[1:], []))
            elif ln or self.banks[-1][1]:
                self.banks[-1][1].append(ln)
        while self.banks[-1][1] and self.banks[-1][1][-1] == '':
            self.banks[-1][1].pop()

    @property
    def filename(self):
        return os.path.basename(self.path).upper()

    def raw_name(self, prog, bank=0):
        if bank is None or bank < 0:
            bank = 0
        if prog is None or prog < 0:
            return ''
        if bank >= len(self.banks):
            bank = 0                       # unknown bank: the original falls back to bank 0
        names = self.banks[bank][1]
        name = names[prog] if prog < len(names) else '-'
        if name in ('-', '') and bank > 0:
            return self.raw_name(prog, 0)
        return name or '-'

    def name(self, prog, bank=0):
        if prog is None or prog < 0:
            return ''
        return ('%s %s' % (self.prefix, self.raw_name(prog, bank))).strip()

    def bank_name(self, bank):
        if 0 <= bank < len(self.banks):
            return self.banks[bank][0]
        return ''


class Drum:
    __slots__ = ('raw', 'name', 'channel', 'key', 'velocity', 'length', 'mute', 'solo')

    def __init__(self, raw=None):
        self.raw = bytearray(raw or bytes(47))
        if raw:
            self.name = self.raw[:21].split(b'\0')[0].decode('latin1')
            (self.channel, self.key, self.velocity, self.length, self.mute,
             self.solo) = struct.unpack_from('<6h', self.raw, 21)
        else:
            self.name, self.channel, self.key, self.velocity, self.length = '', 10, 36, 127, 48
            self.mute = self.solo = 0

    def to_bytes(self):
        b = bytearray(self.raw)
        nm = self.name.encode('latin1', 'replace')[:20]
        b[:21] = nm + b'\0' * (21 - len(nm))
        struct.pack_into('<6h', b, 21, self.channel, self.key, self.velocity, self.length,
                         self.mute, self.solo)
        return bytes(b)


class DrumKit:
    """'drum' + version + count, kit name at 0x20, then 128 x 47-byte drum records at 0x37."""
    HEADER = 0x37
    RECORD = 47

    def __init__(self, path=None):
        self.path = path
        self.header = bytearray(self.HEADER)
        self.name = 'General MIDI'
        self.drums = []
        if path:
            self.load(path)

    def load(self, path):
        with open(path, 'rb') as f:
            d = f.read()
        if d[:4] != b'drum':
            raise ValueError('%s is not an Evolution Drum File' % os.path.basename(path))
        self.header = bytearray(d[:self.HEADER])
        count = struct.unpack_from('<H', d, 6)[0] + 1
        self.name = d[0x20:0x35].split(b'\0')[0].decode('latin1')
        self.drums = []
        for i in range(min(count, 128)):
            o = self.HEADER + i * self.RECORD
            self.drums.append(Drum(d[o:o + self.RECORD]))
        self.path = path

    def save(self, path):
        h = bytearray(self.header)
        h[:4] = b'drum'
        struct.pack_into('>H', h, 4, 0x0200)
        struct.pack_into('<H', h, 6, max(0, len(self.drums) - 1))
        nm = self.name.encode('latin1', 'replace')[:20]
        h[0x20:0x35] = nm + b'\0' * (21 - len(nm))
        out = bytes(h)
        for i in range(128):
            out += self.drums[i].to_bytes() if i < len(self.drums) else bytes(self.RECORD)
        open(path, 'wb').write(out)
        self.path = path

    def find(self, channel, key):
        for d in self.drums:
            if d.key == key and (d.channel == channel or channel == 0):
                return d
        return None


class PatchManager:
    """Installed patch lists and the routing of (port, channel) to a list (Patch Lists dialog)."""

    DEFAULTS = ['GM.PLS', 'GMDRUMS.PLS', 'GSNORM.PLS', 'GSDRUMS.PLS', 'XGNORM.PLS', 'XGUSER.PLS',
                'XGSFXVC.PLS', 'XGSFXKT.PLS', 'XGDRUMKT.PLS', 'PROTEUS1.PLS', 'M1.PLS', 'M3R.PLS',
                'T123.PLS', 'X3.PLS', '05R_W.PLS', 'EVS1.PLS']
    MODE_LISTS = {'GM': ('GM.PLS', 'GMDRUMS.PLS'), 'GS': ('GSNORM.PLS', 'GSDRUMS.PLS'),
                  'XG': ('XGNORM.PLS', 'XGDRUMKT.PLS')}

    def __init__(self, extra_dirs=()):
        self.lists = []
        self.dirs = [resources.path('patches')] + list(extra_dirs)
        for nm in self.DEFAULTS:
            self.add(nm)
        self.routing = {}            # (port, ch) -> (list filename, is_drum)

    def find_file(self, name):
        for d in self.dirs:
            p = os.path.join(d, name)
            if os.path.exists(p):
                return p
            for f in os.listdir(d) if os.path.isdir(d) else ():
                if f.upper() == name.upper():
                    return os.path.join(d, f)
        return None

    def add(self, name_or_path):
        p = name_or_path if os.path.isabs(name_or_path) else self.find_file(name_or_path)
        if not p:
            return None
        pl = PatchList(p)
        for i, q in enumerate(self.lists):
            if q.filename == pl.filename:
                self.lists[i] = pl
                return pl
        self.lists.append(pl)
        return pl

    def get(self, filename):
        for q in self.lists:
            if q.filename == filename.upper():
                return q
        return None

    def set_mode(self, port, mode):
        norm, drums = self.MODE_LISTS.get(mode, self.MODE_LISTS['GM'])
        for ch in range(1, 17):
            self.routing[(port, ch)] = (drums if ch == 10 else norm, ch == 10)

    def list_for(self, port, ch):
        fn, _drum = self.routing.get((port, ch), ('GMDRUMS.PLS' if ch == 10 else 'GM.PLS', ch == 10))
        if fn == 'OFF':
            return None
        return self.get(fn)

    def name(self, port, ch, prog, bank):
        if ch is None or ch < 1:
            ch = 1
        pl = self.list_for(port, ch)
        if pl is None or prog is None or prog < 0:
            return ''
        b = bank if bank is not None and bank >= 0 else 0
        if b > 127:
            b = b >> 7 if (b & 0x7F) == 0 else b & 0x7F
        return pl.name(prog, b)
