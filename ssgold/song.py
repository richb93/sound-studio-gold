"""Song model and the Evolution .SNG file format.

Layout (reverse-engineered from Goldlib.dll's loader, see docs/FORMATS.md):

    0x000  'song' | 'sng2' | 'sng3'
    0x004  be16 version, be16 tracks, be16 patterns, be16 conductor entries
    0x00C  16 x 32-byte MIDI port names
    0x20C  be16 timebase, header fields ..., be32 left / right locators,
           be16 notepad length (0x22E), be16 lyric data length (0x235) ...
    0x400  notepad text, lyric data, conductor entries (be32 tick, be16 value),
           track order table (le16 x tracks), pattern order table (le16 x patterns),
           track records (0x235 bytes each, little-endian struct),
           pattern records (0x4D bytes each),
           event data for every parent MIDI / audio / chord pattern.

Header integers are big-endian; the track and pattern records are raw little-endian structs,
so unknown bytes are kept and written back unchanged.
"""
import struct

TRACK_SIZE = 0x235
PATTERN_SIZE = 0x4D
HEADER_SIZE = 0x400
MAX_TRACKS = 256
MAX_PATTERNS = 700
PATTERNS_PER_TRACK = 250

MIDI, AUDIO, CHORD = 0, 1, 2
OFF = -1
PAN_OFF = -65

COND_TEMPO, COND_TIMESIG, COND_KEY = 0, 1, 2


class SongError(Exception):
    pass


# ----------------------------------------------------------------------------- events
class Event:
    """One MIDI event inside a pattern. tick is relative to the pattern start."""
    __slots__ = ('tick', 'status', 'd1', 'd2', 'length', 'data', 'selected')

    def __init__(self, tick, status, d1=0, d2=0, length=0, data=b''):
        self.tick = tick
        self.status = status
        self.d1 = d1
        self.d2 = d2
        self.length = length      # notes only
        self.data = data          # sysex body (F0 ... F7) or raw bytes of unknown events
        self.selected = False

    @property
    def kind(self):
        return self.status & 0xF0 if self.status < 0xF0 else self.status

    @property
    def channel(self):
        return self.status & 0x0F

    def is_note(self):
        return self.status & 0xF0 == 0x90

    def copy(self):
        e = Event(self.tick, self.status, self.d1, self.d2, self.length, self.data)
        return e

    def __repr__(self):
        return 'Event(%d, %02X, %d, %d, %d)' % (self.tick, self.status, self.d1, self.d2, self.length)


DATA_LEN = {0x80: 2, 0x90: 2, 0xA0: 2, 0xB0: 2, 0xC0: 1, 0xD0: 1, 0xE0: 2}


def decode_events(buf):
    """Event stream: be24 tick, status, data bytes; notes add be16 length; ends with tick + 0xFC."""
    out = []
    p = 0
    n = len(buf)
    while p + 4 <= n:
        tick = (buf[p] << 16) | (buf[p + 1] << 8) | buf[p + 2]
        st = buf[p + 3]
        p += 4
        if st == 0xFC:
            break
        if st == 0xF0:
            try:
                e = buf.index(0xF7, p)
            except ValueError:
                break
            out.append(Event(tick, 0xF0, data=bytes(buf[p - 1:e + 1])))
            p = e + 1
            continue
        hi = st & 0xF0
        if hi in DATA_LEN:
            if DATA_LEN[hi] == 2:
                d1, d2 = buf[p], buf[p + 1]
            else:
                d1, d2 = buf[p], 0
            p += DATA_LEN[hi]
            ln = 0
            if hi == 0x90:
                ln = (buf[p] << 8) | buf[p + 1]
                p += 2
            out.append(Event(tick, st, d1, d2, ln))
        else:
            # Damaged data (EVENT.SNG has one): keep the bytes verbatim up to the next
            # plausible event so a save reproduces them, and carry on from there.
            q = p
            while q + 4 <= n:
                t2 = (buf[q] << 16) | (buf[q + 1] << 8) | buf[q + 2]
                s2 = buf[q + 3]
                if tick <= t2 < tick + 0x10000 and (s2 & 0xF0 in DATA_LEN or s2 in (0xF0, 0xFC)):
                    break
                q += 1
            out.append(Event(tick, st, data=bytes(buf[p:q])))
            p = q
    return out


def encode_events(events, end_tick=0):
    out = bytearray()
    for e in sorted(events, key=lambda ev: ev.tick):   # stable: keeps same-tick order
        out += e.tick.to_bytes(3, 'big')
        if e.status == 0xF0:
            out += e.data
            continue
        out.append(e.status)
        hi = e.status & 0xF0
        if e.status < 0x80:
            out += e.data
        elif hi in DATA_LEN:
            out.append(e.d1 & 0x7F)
            if DATA_LEN[hi] == 2:
                out.append(e.d2 & 0x7F)
            if hi == 0x90:
                out += max(0, min(0xFFFF, e.length)).to_bytes(2, 'big')
    out += (0).to_bytes(3, 'big') + b'\xFC'
    return bytes(out)


# Order in which simultaneous events are sent ("sysex before notes" - see help, New Gold Features)
_ORDER = {0xF0: 0, 0xB0: 1, 0xC0: 2, 0xE0: 3, 0xD0: 4, 0xA0: 5, 0x90: 6, 0x80: 7}


def event_sort_key(e):
    return (e.tick, _ORDER.get(e.status & 0xF0 if e.status < 0xF0 else e.status, 8))


def sorted_events(events):
    return sorted(events, key=event_sort_key)


# ----------------------------------------------------------------------------- tracks / patterns
class _Struct:
    """Base for records kept as raw bytes with named little-endian 16-bit fields."""
    FIELDS = {}

    def _get(self, off, signed=True):
        return struct.unpack_from('<h' if signed else '<H', self.raw, off)[0]

    def _set(self, off, v, signed=True):
        struct.pack_into('<h' if signed else '<H', self.raw, off, int(v))

    def __getattr__(self, name):
        f = type(self).FIELDS.get(name)
        if f is None:
            raise AttributeError(name)
        return self._get(f)

    def __setattr__(self, name, value):
        f = type(self).FIELDS.get(name)
        if f is not None and name != 'raw':
            self._set(f, value)
        else:
            object.__setattr__(self, name, value)

    def _name(self):
        return self.raw[:0x15].split(b'\0')[0].decode('latin1')

    def _setname(self, s):
        b = s.encode('latin1', 'replace')[:20]
        self.raw[:0x15] = b + b'\0' * (0x15 - len(b))


class Track(_Struct):
    FIELDS = {'prog': 0x15, 'bank': 0x17, 'channel': 0x19, 'port': 0x1B, 'volume': 0x1D,
              'pan': 0x1F, 'reverb': 0x21, 'chorus': 0x23, 'velocity': 0x25, 'transpose': 0x27,
              'time': 0x29, 'mute': 0x2B, 'solo': 0x2D, 'rec': 0x2F, 'fx_type': 0x31,
              'monitor': 0x33, 'y': 0x22D, 'divider': 0x22F, 'height': 0x231}

    def __init__(self, raw=None, name='Track', kind=MIDI):
        object.__setattr__(self, 'raw', bytearray(raw) if raw else bytearray(TRACK_SIZE))
        object.__setattr__(self, 'patterns', [])
        if raw is None:
            self.raw[0x37:0x22B] = b"\xff" * (0x22B - 0x37)
            self.name = name
            self.prog = OFF
            self.bank = OFF
            self.channel = 1
            self.port = 0
            self.volume = OFF
            self.pan = PAN_OFF
            self.reverb = OFF
            self.chorus = OFF
            self.height = 13
            self.raw[0x35] = 1
            self.kind = kind

    name = property(_Struct._name, _Struct._setname)

    @property
    def kind(self):
        return self.raw[0x234]

    @kind.setter
    def kind(self, v):
        self.raw[0x234] = v

    @property
    def selected(self):
        return bool(self.raw[0x233])

    @selected.setter
    def selected(self, v):
        self.raw[0x233] = 1 if v else 0

    def copy(self):
        t = Track(bytes(self.raw))
        return t


class Pattern(_Struct):
    FIELDS = {'prog': 0x17, 'bank': 0x19, 'channel': 0x1B, 'volume': 0x1D, 'pan': 0x1F,
              'reverb': 0x21, 'chorus': 0x23, 'velocity': 0x25, 'transpose': 0x27, 'time': 0x29,
              'mute': 0x2B}
    # chord patterns reuse the same slots
    CHORD = {'root': 0x17, 'ctype': 0x19, 'bass': 0x1B}
    CHORD_MUTES = (0x1D, 0x1F, 0x21, 0x23, 0x25, 0x27)

    def __init__(self, raw=None, name='', start=0, end=0):
        object.__setattr__(self, 'raw', bytearray(raw) if raw else bytearray(PATTERN_SIZE))
        object.__setattr__(self, 'events', [])
        object.__setattr__(self, 'parent', None)    # Pattern object for a child
        object.__setattr__(self, 'track', None)     # Track object
        object.__setattr__(self, 'blob', b'')       # raw data of audio / chord patterns
        object.__setattr__(self, 'selected', False)
        if raw is None:
            self.name = name
            for f, v in (('prog', OFF), ('bank', OFF), ('channel', 0), ('volume', OFF),
                         ('pan', PAN_OFF), ('reverb', OFF), ('chorus', OFF)):
                setattr(self, f, v)
            self._set(0x15, -1)
            self._set(0x2D, 1)
            self._set(0x2F, -1)
            self.start = start
            self.end = end

    name = property(_Struct._name, _Struct._setname)

    @property
    def start(self):
        return struct.unpack_from('<i', self.raw, 0x35)[0]

    @start.setter
    def start(self, v):
        struct.pack_into('<i', self.raw, 0x35, int(v))

    @property
    def end(self):
        return struct.unpack_from('<i', self.raw, 0x39)[0]

    @end.setter
    def end(self, v):
        struct.pack_into('<i', self.raw, 0x39, int(v))

    @property
    def length(self):
        return self.end - self.start

    @property
    def is_child(self):
        return self.parent is not None

    @property
    def source(self):
        """The pattern whose events this one plays."""
        return self.parent if self.parent is not None else self

    def get_events(self):
        return self.source.events

    # chord helpers
    def chord(self):
        return self._get(0x17), self._get(0x19)

    def set_chord(self, root, ctype):
        self._set(0x17, root)
        self._set(0x19, ctype)

    def chord_mutes(self):
        return [self._get(o) for o in Pattern.CHORD_MUTES]

    def set_chord_mute(self, i, v):
        self._set(Pattern.CHORD_MUTES[i], v)


# ----------------------------------------------------------------------------- conductor
class CondPoint:
    __slots__ = ('tick', 'kind', 'value', 'selected')

    def __init__(self, tick, kind, value):
        self.tick = tick
        self.kind = kind
        self.value = value
        self.selected = False

    def encode(self):
        if self.kind == COND_TIMESIG:
            return 0x8000 | self.value
        if self.kind == COND_KEY:
            return 0x4000 | self.value
        return self.value & 0x3FFF


class Conductor:
    """Tempo, time-signature and key-signature maps."""

    def __init__(self):
        self.points = [CondPoint(0, COND_TEMPO, 120), CondPoint(0, COND_TIMESIG, 3),
                       CondPoint(0, COND_KEY, 0)]

    def of(self, kind):
        return sorted((p for p in self.points if p.kind == kind), key=lambda p: p.tick)

    def at(self, kind, tick):
        cur = None
        for p in self.of(kind):
            if p.tick <= tick:
                cur = p
            else:
                break
        return cur or self.of(kind)[0]


# ----------------------------------------------------------------------------- song
class Song:
    def __init__(self):
        self.header = bytearray(HEADER_SIZE)
        self.signature = b'sng3'
        self.version = 0x0200
        self.tracks = []
        self.conductor = Conductor()
        self.notepad = ''
        self.lyrics = b''
        self.path = None
        self.modified = False
        self.timebase = 192
        self.left = 0
        self.right = 4 * 4 * 192
        self.ports = ['A: MIDI Out']
        self.smpte_start = '00:00:00:00'
        self.header[0x220] = 25

    # ---- header fields kept in the raw block
    def _h8(self, off, v=None):
        if v is None:
            return self.header[off]
        self.header[off] = v & 0xFF

    @property
    def lyric_channel(self):
        return self.header[0x22D]

    @lyric_channel.setter
    def lyric_channel(self, v):
        self.header[0x22D] = v

    @property
    def frame_format(self):
        return self.header[0x220]

    @frame_format.setter
    def frame_format(self, v):
        self.header[0x220] = v

    @property
    def sample_rate(self):
        return struct.unpack_from('>H', self.header, 0x2B9)[0] or 44100

    # ---- convenience
    def all_patterns(self):
        for t in self.tracks:
            yield from t.patterns

    def track_of(self, pattern):
        return pattern.track

    def end_tick(self):
        return max((p.end for p in self.all_patterns()), default=0)

    def children_of(self, pattern):
        return [p for p in self.all_patterns() if p.parent is pattern]

    # ---- timing (bar/beat/tick)
    def beat_ticks(self, ts_index, tables):
        den = tables['timesig_den'][ts_index]
        return self.timebase * 4 // den

    # ---- load / save
    @classmethod
    def load(cls, path):
        with open(path, 'rb') as f:
            data = f.read()
        s = cls.from_bytes(data)
        s.path = path
        return s

    @classmethod
    def from_bytes(cls, d):
        sig = d[:4]
        if sig not in (b'song', b'sng2', b'sng3'):
            raise SongError('not an Evolution Song File')
        s = cls()
        s.signature = sig
        s.header = bytearray(d[:HEADER_SIZE].ljust(HEADER_SIZE, b'\0'))
        s.version, nt, npat, ncond = struct.unpack_from('>HHHH', d, 4)
        s.ports = []
        for i in range(16):
            nm = d[0x0C + 32 * i:0x0C + 32 * (i + 1)].split(b'\0')[0].decode('latin1')
            if nm:
                s.ports.append(nm)
        s.timebase = struct.unpack_from('>H', d, 0x20C)[0]
        s.smpte_start = d[0x214:0x220].split(b'\0')[0].decode('latin1') or '00:00:00:00'
        s.left, s.right = struct.unpack_from('>ii', d, 0x225)
        nlen = struct.unpack_from('>H', d, 0x22E)[0]
        llen = struct.unpack_from('>H', d, 0x235)[0]
        p = HEADER_SIZE
        s.notepad = d[p:p + nlen].decode('latin1')
        p += nlen
        s.lyrics = d[p:p + llen]
        p += llen
        s.conductor.points = []
        for _ in range(ncond):
            tick, v = struct.unpack_from('>IH', d, p)
            p += 6
            if v & 0x8000:
                s.conductor.points.append(CondPoint(tick, COND_TIMESIG, v & 0xFF))
            elif v & 0x4000:
                s.conductor.points.append(CondPoint(tick, COND_KEY, v & 0xFF))
            else:
                s.conductor.points.append(CondPoint(tick, COND_TEMPO, v))
        if not s.conductor.of(COND_TEMPO):
            s.conductor.points.append(CondPoint(0, COND_TEMPO, 120))
        if not s.conductor.of(COND_TIMESIG):
            s.conductor.points.append(CondPoint(0, COND_TIMESIG, 3))
        if not s.conductor.of(COND_KEY):
            s.conductor.points.append(CondPoint(0, COND_KEY, 0))
        ttab = struct.unpack_from('<%dH' % nt, d, p)
        p += 2 * nt
        p += 2 * npat                      # pattern order table (rebuilt on save)
        raw_tracks = []
        for _ in range(nt):
            raw_tracks.append(Track(d[p:p + TRACK_SIZE]))
            p += TRACK_SIZE
        raw_pats = []
        for _ in range(npat):
            raw_pats.append(Pattern(d[p:p + PATTERN_SIZE]))
            p += PATTERN_SIZE
        for pt in raw_pats:
            parent = pt._get(0x15)
            handle = pt._get(0x2F)
            ln = struct.unpack_from('<I', pt.raw, 0x3D)[0]
            if parent == -1 and handle != -1:
                pt.blob = bytes(d[p:p + ln])
                p += ln
        # resolve parent links and the tracks' pattern lists
        for pt in raw_pats:
            parent = pt._get(0x15)
            if 0 <= parent < len(raw_pats) and raw_pats[parent] is not pt:
                pt.parent = raw_pats[parent]
            pt.selected = bool(pt.raw[0x4B])
        order = [raw_tracks[i] for i in ttab if i < len(raw_tracks)]
        for t in raw_tracks:
            if t not in order:
                order.append(t)
        for t in raw_tracks:
            lst = []
            for o in range(0x37, 0x22B, 2):
                v = struct.unpack_from('<h', t.raw, o)[0]
                if v == -1:
                    break
                if 0 <= v < len(raw_pats):
                    pt = raw_pats[v]
                    pt.track = t
                    lst.append(pt)
            t.patterns = sorted(lst, key=lambda q: q.start)
        for t in raw_tracks:
            for pt in t.patterns:
                if t.kind == MIDI and pt.parent is None:
                    pt.events = decode_events(pt.blob)
        s.tracks = order
        return s

    def to_bytes(self):
        hdr = bytearray(self.header)
        hdr[:4] = self.signature
        tracks = self.tracks
        pats = [p for t in tracks for p in t.patterns]
        index = {id(p): i for i, p in enumerate(pats)}
        conds = sorted(self.conductor.points, key=lambda c: (c.tick, -c.encode() & 0xC000))
        struct.pack_into('>HHHH', hdr, 4, self.version, len(tracks), len(pats), len(conds))
        names = bytearray(512)
        for i, nm in enumerate(self.ports[:16]):
            b = nm.encode('latin1', 'replace')[:31]
            names[32 * i:32 * i + len(b)] = b
        hdr[0x0C:0x20C] = names
        struct.pack_into('>H', hdr, 0x20C, self.timebase)
        tempo0 = self.conductor.of(COND_TEMPO)[0].value
        hdr[0x20E] = min(255, tempo0)
        smp = self.smpte_start.encode('latin1')[:11]
        hdr[0x214:0x220] = smp + b'\0' * (12 - len(smp))
        struct.pack_into('>ii', hdr, 0x225, self.left, self.right)
        notepad = self.notepad.replace('\r\n', '\n').replace('\n', '\r\n').encode('latin1', 'replace')
        struct.pack_into('>H', hdr, 0x22E, len(notepad))
        struct.pack_into('>H', hdr, 0x235, len(self.lyrics))
        out = bytearray(hdr)
        out += notepad
        out += self.lyrics
        for c in conds:
            out += struct.pack('>IH', c.tick, c.encode())
        out += struct.pack('<%dH' % len(tracks), *range(len(tracks)))
        out += struct.pack('<%dH' % len(pats), *range(len(pats)))
        for t in tracks:
            raw = bytearray(t.raw)
            lst = [index[id(p)] for p in t.patterns][:PATTERNS_PER_TRACK]
            raw[0x37:0x22B] = b"\xff" * (0x22B - 0x37)
            for i, v in enumerate(lst):
                struct.pack_into('<h', raw, 0x37 + 2 * i, v)
            raw[0x35] = 1
            out += raw
        blobs = []
        for p in pats:
            raw = bytearray(p.raw)
            t = p.track
            struct.pack_into('<h', raw, 0x15, index[id(p.parent)] if p.parent is not None else -1)
            struct.pack_into('<H', raw, 0x41, tracks.index(t))
            raw[0x4B] = 1 if p.selected else 0
            blob = b''
            if p.parent is None:
                if t.kind == MIDI:
                    blob = encode_events(p.events)
                else:
                    blob = p.blob or (b'\0\0\0\xfc')
            # 0x2F holds the event data's memory handle at run time; Gold links a child to
            # its parent through it, so parents get a unique value and children share it.
            struct.pack_into('<h', raw, 0x2F, 0x100 + index[id(p.source)] * 8)
            struct.pack_into('<I', raw, 0x3D, len(blob) if p.parent is None else
                             (len(encode_events(p.parent.events)) if t.kind == MIDI else len(p.parent.blob or b'')))
            out += raw
            blobs.append(blob)
        for b in blobs:
            out += b
        return bytes(out)

    def save(self, path=None):
        path = path or self.path
        data = self.to_bytes()
        with open(path, 'wb') as f:
            f.write(data)
        self.path = path
        self.modified = False


def new_song(ports=None):
    """The song created by File > New: 4 audio tracks, 9 piano tracks, a drum track, then empties."""
    s = Song()
    s.ports = list(ports or ['A: MIDI Out'])
    for i in range(4):
        t = Track(name='Audio %d' % (i + 1), kind=AUDIO)
        t.channel = i + 1
        s.tracks.append(t)
    for i in range(1, 61):
        t = Track(name='Track %d' % i)
        t.channel = (i - 1) % 16 + 1
        if i <= 10:
            t.prog = 0
        if i == 1:
            t.rec = 1
            t.selected = True
        s.tracks.append(t)
    return s
