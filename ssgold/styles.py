"""Accompaniment for chord tracks.

Each chord pattern holds a root (0-11), a chord type (0-11, see chords.CHORD_TYPES) and six part
switches (Acc1-Acc4, Bass, Drums).  Chord tracks play on channels 10-15 of their port (the
'Chord Track Conflict Warning' dialog says so): drums on 10, bass on 11, accompaniment on 12-15.
The 16 styles are generated from per-style rhythm templates.
"""
from .chords import CHORD_TYPES
from .song import COND_TIMESIG
from .timing import TimeMap

DRUM_CH, BASS_CH, ACC_CH = 9, 10, (11, 12, 13, 14)

# style -> (tempo feel, drum hits per beat subdivision, bass rhythm, comping rhythm, programs)
# Rhythms are lists of (beat fraction, velocity) within one bar of 4 beats.
STYLES = {
    'Rock': dict(sub=2, kick=[0, 2.5], snare=[1, 3], hat=[x / 2 for x in range(8)],
                 bass=[(0, 0), (1.5, 0), (2, 7), (3.5, 0)], comp=[0, 1, 2, 3], progs=(30, 29, 48, 0)),
    "Rock 'n' Roll": dict(sub=3, kick=[0, 2], snare=[1, 3], hat=[x / 3 * 1.0 for x in range(0, 12, 2)],
                          bass=[(0, 0), (1, 4), (2, 7), (3, 9)], comp=[0, 0.67, 1, 1.67, 2, 2.67, 3, 3.67],
                          progs=(0, 26, 66, 16)),
    "R 'n' B": dict(sub=2, kick=[0, 1.5, 2.5], snare=[1, 3], hat=[x / 2 for x in range(8)],
                    bass=[(0, 0), (0.75, 0), (1.5, 7), (2.5, 0), (3, 10)], comp=[0.5, 1.5, 2.5, 3.5],
                    progs=(4, 61, 16, 48)),
    'Pop': dict(sub=2, kick=[0, 2], snare=[1, 3], hat=[x / 2 for x in range(8)],
                bass=[(0, 0), (2, 0), (2.5, 7)], comp=[0, 1, 2, 3], progs=(0, 48, 24, 89)),
    'Disco': dict(sub=2, kick=[0, 1, 2, 3], snare=[1, 3], hat=[0.5, 1.5, 2.5, 3.5],
                  bass=[(0, 0), (0.5, 12), (1, 0), (1.5, 12), (2, 0), (2.5, 12), (3, 0), (3.5, 12)],
                  comp=[0.5, 1.5, 2.5, 3.5], progs=(48, 27, 61, 4)),
    'Soul': dict(sub=2, kick=[0, 2.5], snare=[1, 3], hat=[x / 2 for x in range(8)],
                 bass=[(0, 0), (1.5, 7), (2, 0), (3, 10)], comp=[1, 3], progs=(16, 61, 4, 48)),
    'Ballad': dict(sub=2, kick=[0, 2], snare=[1, 3], hat=[0, 1, 2, 3],
                   bass=[(0, 0), (2, 7)], comp=[0, 2], progs=(0, 48, 4, 89)),
    'Slow Rock': dict(sub=3, kick=[0, 2], snare=[1, 3], hat=[x / 3 for x in range(12)],
                      bass=[(0, 0), (2, 7)], comp=[x / 3 for x in range(12)], progs=(0, 16, 48, 29)),
    'Reggae': dict(sub=2, kick=[2], snare=[2], hat=[x / 2 for x in range(8)],
                   bass=[(0, 0), (1.5, 0), (2.5, 7)], comp=[0.5, 1.5, 2.5, 3.5], progs=(16, 27, 0, 48)),
    'Afro': dict(sub=2, kick=[0, 1.5, 3], snare=[1, 2.5], hat=[x / 2 for x in range(8)],
                 bass=[(0, 0), (1.5, 7), (3, 0)], comp=[0.5, 1, 2.5, 3], progs=(12, 24, 0, 48)),
    'Swing': dict(sub=3, kick=[0, 2], snare=[1, 3], hat=[0, 1, 1.67, 2, 3, 3.67],
                  bass=[(0, 0), (1, 4), (2, 7), (3, 9)], comp=[0, 1.67, 3], progs=(0, 32, 65, 26)),
    'Latin': dict(sub=2, kick=[0, 1.5, 2, 3.5], snare=[0.5, 2.5], hat=[x / 2 for x in range(8)],
                  bass=[(0, 0), (1.5, 7), (2, 0), (3.5, 7)], comp=[0, 0.5, 1.5, 2, 3], progs=(0, 32, 24, 56)),
    'March': dict(sub=2, kick=[0, 2], snare=[0.5, 1, 2.5, 3, 3.5], hat=[0, 1, 2, 3],
                  bass=[(0, 0), (1, 7), (2, 0), (3, 7)], comp=[1, 3], progs=(56, 58, 71, 60)),
    'Big Band': dict(sub=3, kick=[0, 2], snare=[1, 3], hat=[0, 1, 1.67, 2, 3, 3.67],
                     bass=[(0, 0), (1, 4), (2, 7), (3, 9)], comp=[0, 1.67, 2.67], progs=(61, 56, 65, 0)),
    'Bluegrass': dict(sub=2, kick=[0, 2], snare=[1, 3], hat=[x / 2 for x in range(8)],
                      bass=[(0, 0), (1, 7), (2, 0), (3, 7)], comp=[0.5, 1.5, 2.5, 3.5], progs=(105, 25, 110, 21)),
    'Waltz': dict(sub=2, kick=[0], snare=[1, 2], hat=[0, 1, 2], bass=[(0, 0)], comp=[1, 2],
                  progs=(0, 48, 21, 73), beats=3),
}
STYLE_NAMES = list(STYLES)


def style_of(song):
    i = song.header[0x2D3] if len(song.header) > 0x2D3 else 0
    return STYLE_NAMES[i % len(STYLE_NAMES)]


def render_chord_track(song, track):
    tm = TimeMap(song)
    st = STYLES.get(style_of(song), STYLES['Rock'])
    port = max(0, track.port)
    out = []
    for i, ch in enumerate(ACC_CH):
        out.append((0, 0, port, bytes([0xC0 | ch, st['progs'][i % 4]])))
    out.append((0, 0, port, bytes([0xC0 | BASS_CH, 33])))
    vel_adj = track.velocity or 0
    for p in track.patterns:
        if p.mute:
            continue
        src = p.source
        root, ctype = src.chord()
        root %= 12
        iv = CHORD_TYPES[ctype % len(CHORD_TYPES)]
        mutes = src.chord_mutes()
        for bar_tick, _b, tpbeat, beats in tm.bar_lines(p.start, p.end - 1):
            if bar_tick < p.start:
                continue
            def at(frac):
                return bar_tick + int(frac * tpbeat)
            # drums
            if len(mutes) > 5 and mutes[5]:
                for f, note, v in ([(x, 36, 110) for x in st['kick']] + [(x, 38, 100) for x in st['snare']] +
                                   [(x, 42, 80) for x in st['hat']]):
                    if f < beats:
                        out.append((at(f), 6, port, bytes([0x90 | DRUM_CH, note, _v(v + vel_adj)])))
                        out.append((at(f) + tpbeat // 4, 1, port, bytes([0x80 | DRUM_CH, note, 0])))
            # bass
            if len(mutes) > 4 and mutes[4]:
                for f, off in st['bass']:
                    if f < beats:
                        n = 36 + root + off
                        out.append((at(f), 6, port, bytes([0x90 | BASS_CH, n, _v(100 + vel_adj)])))
                        out.append((at(f) + tpbeat * 3 // 4, 1, port, bytes([0x80 | BASS_CH, n, 0])))
            # comping parts
            for k, ch in enumerate(ACC_CH):
                if k < len(mutes) and mutes[k]:
                    base = 48 + (12 if k == 1 else 0) + root
                    if base > 60:
                        base -= 12
                    for f in st['comp'] if k in (0, 2) else st['comp'][::2] or [0]:
                        if f >= beats:
                            continue
                        dur = tpbeat // 2 if k == 0 else tpbeat
                        for i in iv:
                            n = base + i
                            out.append((at(f), 6, port, bytes([0x90 | ch, n, _v(85 + vel_adj)])))
                            out.append((at(f) + dur, 1, port, bytes([0x80 | ch, n, 0])))
    return out


def _v(v):
    return max(1, min(127, v))
