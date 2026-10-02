"""Chord detection (Transport 'Chord' box) and the chord track (Instant Chord Track styles)."""
from . import resources

ROOTS = ['C', 'Db', 'D', 'Eb', 'E', 'F', 'F#', 'G', 'Ab', 'A', 'Bb', 'B']

# interval sets for Gold's chord suffix table (DS:0x12fb), in the same order
TEMPLATES = [
    ('', (0, 4, 7)), (' m', (0, 3, 7)), (' dim', (0, 3, 6)), (' aug', (0, 4, 8)), (' sus4', (0, 5, 7)),
    (' 7', (0, 4, 7, 10)), (' m7', (0, 3, 7, 10)), (' m7-5', (0, 3, 6, 10)), (' 6', (0, 4, 7, 9)),
    (' m6', (0, 3, 7, 9)), (' Maj7', (0, 4, 7, 11)), (' 9', (0, 2, 4, 7, 10)), (' m9', (0, 2, 3, 7, 10)),
    (' 11', (0, 4, 5, 7, 10)), (' m11', (0, 3, 5, 7, 10)), (' 7sus4', (0, 5, 7, 10)),
    (' +9', (0, 3, 4, 7, 10)), (' m+9', (0, 2, 3, 7)), (' +4', (0, 4, 6, 7)), (' m+4', (0, 3, 6, 7)),
    (' 6/9', (0, 2, 4, 7, 9)), (' m6/9', (0, 2, 3, 7, 9)), (' mMaj7', (0, 3, 7, 11)), (' 13', (0, 4, 7, 9, 10)),
]

# Instant Chord Track / chord pattern 'Type' menu (DS:0x5f65): Maj m 7 m7 Maj7 6 m6 aug m7-5 dim Sus4 11
CHORD_TYPES = [(0, 4, 7), (0, 3, 7), (0, 4, 7, 10), (0, 3, 7, 10), (0, 4, 7, 11), (0, 4, 7, 9),
               (0, 3, 7, 9), (0, 4, 8), (0, 3, 6, 10), (0, 3, 6, 9), (0, 5, 7), (0, 4, 7, 10, 17)]


def chord_name(notes):
    """Name the chord formed by MIDI note numbers, or '' if none matches."""
    pcs = sorted({n % 12 for n in notes})
    if len(pcs) < 3:
        return ''
    bass = min(notes) % 12
    best = None
    for root in sorted(pcs, key=lambda r: (r != bass, r)):
        rel = tuple(sorted((p - root) % 12 for p in pcs))
        for suf, iv in TEMPLATES:
            if rel == tuple(sorted(iv)):
                return ROOTS[root] + suf
            if set(iv) <= set(rel) and (best is None or len(iv) > best[0]):
                best = (len(iv), ROOTS[root] + suf)
    return best[1] if best and best[0] >= 3 else ''


_held = set()


def detect_input(app, data):
    """Update the held-notes set from MIDI input; returns the new chord name (or None if unchanged)."""
    st = data[0]
    hi = st & 0xF0
    if st >= 0xF0 or (st & 0x0F) == 9 or len(data) < 3:
        return None
    if hi == 0x90 and data[2]:
        _held.add(data[1])
    elif hi in (0x80, 0x90):
        _held.discard(data[1])
    else:
        return None
    return chord_name(_held)


def type_names():
    return [t.strip() for t in resources.tables()['chord_types']]


class ChordPlayer:
    """Plays chord-track patterns in the song's accompaniment style."""

    def __init__(self):
        self.styles = None

    def schedule(self, song, track):
        from .styles import render_chord_track
        try:
            return render_chord_track(song, track)
        except Exception:
            return []

    def live(self, song, track, pos=0, muted=False):
        """The chord track played tick by tick (see styles.Live)."""
        from .styles import Live
        return Live(song, track, pos, muted)
