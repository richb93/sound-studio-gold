"""Chord-track accompaniment: the original's 16 styles and its accompaniment engine.

The style data (rhythms, per-chord-type note tables, drum patterns, part settings and the
Instant Chord Track progressions) is extracted from Gold.exe and Goldlib.dll into
assets/styles.json by tools/extract_assets.py.  The engine below follows Goldlib's player
(segment 32: the per-tick routine at 00EF and its driver at 0666; set-up in segment 22 at 1529),
so 'Convert to MIDI Track' gives the same notes as the original, note for note.

How it plays: five tonal parts (Acc1-Acc4, Bass) each step through their own run of the
style's rhythm table, looping independently of the chords.  A note's pitch is looked up in the
block for the current chord type (all blocks are written for a C root) and moved to the chord's
root; Bass plays an octave lower.  Rhythm entries marked 'tied' extend the previous note.  The
drum part steps through one of eight one-bar drum patterns (cycled bar by bar), each step a
bitmask of eight drum voices; voices alternate between two notes (e.g. closed/pedal hi-hat).
Each chord pattern's six switches turn the parts on and off.
"""
import json

from . import resources
from .song import Pattern, Event, OFF

NO_CHORD = 0x7F
PART_NAMES = ['Acc1', 'Acc2', 'Acc3', 'Acc4', 'Bass', 'Drums']
HEADER_STYLE = 0x233        # song header byte holding the chord track's style

_data = None


def data():
    global _data
    if _data is None:
        with open(resources.path('styles.json')) as f:
            _data = json.load(f)
    return _data


def engine():
    return data()['engine']


def styles():
    return data()['styles']


STYLE_NAMES = [s['name'] for s in styles()]


def style_index(song):
    return song.header[HEADER_STYLE] % 16


def set_style(song, i):
    song.header[HEADER_STYLE] = i % 16


def style_of(song):
    return STYLE_NAMES[style_index(song)]


# ----------------------------------------------------------------------------- chord list
def chord_entries(track):
    """The chord list the engine walks: (root or NO_CHORD, type, six part switches, length).
    Starts at the first chord pattern; gaps and muted patterns play nothing."""
    pats = sorted(track.patterns, key=lambda p: p.start)
    if not pats:
        return 0, []
    start = pats[0].start
    out = []
    pos = start
    for p in pats:
        if p.start > pos:
            out.append((NO_CHORD, 0, [0] * 6, p.start - pos))
            pos = p.start
        if p.end <= pos:
            continue
        root, ctype = p.source.chord()
        flags = [1 if m else 0 for m in p.source.chord_mutes()][:6]
        flags += [0] * (6 - len(flags))
        if p.mute or root < 0:
            root = NO_CHORD
        out.append((root if root == NO_CHORD else root % 12, max(0, ctype) % 12, flags, p.end - pos))
        pos = p.end
    return start, out


# ----------------------------------------------------------------------------- the engine
def render(style, entries, tb=192, transpose=0, vel_ofs=0):
    """Notes for a chord list, in the order the original writes them:
    [tick, status, note, velocity, length] with ticks from the start of the list."""
    eng = engine()
    dur_tab, dnotes, dvel, roff = eng['durations'], eng['drum_notes'], eng['drum_velocity'], eng['root_offset']
    acc_ch, drum_ch = eng['acc_channel'], eng['drum_channel']
    out = []
    if not entries:
        return out
    parts = style['parts']
    rhythm, pitches = style['rhythm'], style['pitches']
    vcode = [v * 8 + 7 for v in style['velocity']]
    idx = [parts[k] for k in range(5)] + [0]
    count = [1] * 6
    last = [0xFF] * 6
    lastptr = [None] * 6
    toggle = [0] * 8
    variant = 0
    pat = style['drums'][0]
    ei, epos, t = 0, 0, 0
    total = sum(e[3] for e in entries)

    def scale(i):
        return dur_tab[i] * tb // 192

    while t < total:
        if t:
            epos += 1
            if epos == entries[ei][3]:
                ei += 1
                if ei == len(entries):
                    break
                epos = 0
        root, ctype, flags, _len = entries[ei]
        rootoff = 0 if root == NO_CHORD else roff[root]
        for k in range(6):
            count[k] -= 1
            if count[k]:
                continue
            if k == 5:                                   # drums
                if idx[5] == 0 and variant == 0:
                    toggle = [0] * 8
                count[5] = scale(pat['step'])
                hits = pat['hits'][idx[5]]
                idx[5] += 1
                if idx[5] == pat['steps']:
                    idx[5] = 0
                    variant = (variant + 1) % 8
                    pat = style['drums'][variant]
                if root == NO_CHORD or not flags[5] or not hits:
                    continue
                for b in range(8):
                    if hits & (1 << b):
                        vel = max(1, min(127, dvel[b] + vel_ofs))
                        out.append([t, 0x90 | drum_ch, dnotes[8 * toggle[b] + b], vel, 4])
                        toggle[b] ^= 1
                continue
            r = rhythm[idx[k]]
            tie = r & 0x40
            length = 0
            skip = 0
            save_idx = None
            while True:
                d = scale(r & 0x3F)
                if length == 0:
                    count[k] = d
                length += d
                p = pitches[ctype][idx[k]]
                if p:
                    p += transpose
                    while p < 1:
                        p += 12
                    while p > 127:
                        p -= 12
                if tie:
                    if p == 0 or rootoff + p == last[k]:
                        skip += 1
                    elif last[k] != 0xFF and lastptr[k] is not None and lastptr[k] < len(out):
                        out[lastptr[k]][4] = t - out[lastptr[k]][0]
                idx[k] += 1
                if idx[k] == parts[k + 1]:
                    idx[k] = parts[k]
                if save_idx is None:
                    save_idx = idx[k]
                r = rhythm[idx[k]]
                if r & 0x40:
                    continue
                idx[k] = save_idx
                break
            lastptr[k] = len(out)
            if p == 0:
                last[k] = 0
            if skip or not p:
                continue
            p += rootoff
            last[k] = p
            if root == NO_CHORD or not flags[k]:
                continue
            vel = max(1, min(127, vcode[k] + vel_ofs))
            out.append([t, 0x90 | (acc_ch + k), p - 12 if k == 4 else p, vel, length - 4])
        t += 1
    return out


def setup_messages(style):
    """Program and controller settings sent for each part (Acc1..Bass, then Drums)."""
    eng = engine()
    chans = [eng['acc_channel'] + k for k in range(5)] + [eng['drum_channel']]
    out = []
    for k, ch in enumerate(chans):
        out.append(bytes([0xC0 | ch, style['program'][k]]))
        for cc, key in ((7, 'volume'), (10, 'pan'), (91, 'reverb'), (93, 'chorus')):
            out.append(bytes([0xB0 | ch, cc, style[key][k]]))
    return out


def _track_offsets(track):
    tr = track.transpose or 0
    vel = track.velocity if track.velocity not in (None, OFF) else 0
    return tr, vel


def render_chord_track(song, track):
    """Sequencer schedule for a chord track: (tick, priority, port, message)."""
    style = styles()[style_index(song)]
    start, entries = chord_entries(track)
    if not entries:
        return []
    port = max(0, track.port)
    tr, vel = _track_offsets(track)
    out = [(start, 0, port, m) for m in setup_messages(style)]
    for t, st, n, v, ln in render(style, entries, song.timebase, tr, vel):
        out.append((start + t, 6, port, bytes([st, n, v])))
        out.append((start + t + max(1, ln), 1, port, bytes([0x80 | (st & 0x0F), n, 0])))
    return out


def convert_pattern(song, track):
    """'Convert to MIDI Track': one pattern holding the accompaniment, named after the style."""
    style = styles()[style_index(song)]
    start, entries = chord_entries(track)
    end = max((p.end for p in track.patterns), default=start)
    p = Pattern(name=style['name'], start=start, end=end)
    for m in setup_messages(style):
        p.events.append(Event(0, m[0], m[1], m[2] if len(m) > 2 else 0))
    tr, vel = _track_offsets(track)
    for t, st, n, v, ln in render(style, entries, song.timebase, tr, vel):
        p.events.append(Event(t, st, n, v, max(1, ln)))
    p.events.sort(key=lambda e: e.tick)
    return p


# ----------------------------------------------------------------------------- Instant Chord Track
def cycle_length(i):
    return len(styles()[i]['progression'])


def max_bars(i):
    """Largest whole number of progression cycles that fits in 200 bars."""
    n = cycle_length(i)
    return max(n, engine()['ict_max_bars'] // n * n)


def fit_bars(i, bars):
    """Bars after choosing style i: whole cycles, at least one, at most max_bars."""
    n = cycle_length(i)
    bars -= bars % n
    return max(n, min(bars, max_bars(i)))


def chord_ticks(i, tb):
    """Each Instant Chord Track chord lasts one bar of the style (3 beats for Waltz)."""
    return styles()[i]['beats'] * tb


def build_chord_patterns(song, track, i, bars, start):
    """Patterns for the Instant Chord Track: the style's progression, one chord per bar."""
    prog = styles()[i]['progression']
    n = len(prog)
    step = chord_ticks(i, song.timebase)
    out = []
    pos = start
    for b in range(max(n, bars - bars % n)):
        root, ctype = prog[b % n]
        p = Pattern(name='', start=pos, end=pos + step)
        p.set_chord(root, ctype)
        for k in range(6):
            p.set_chord_mute(k, 1)
        p.track = track
        out.append(p)
        pos += step
    return out
