"""Accompaniment styles: checked against the notes the original program produced.

ORIGINAL holds, for each style, the number of bars the original's Instant Chord Track made and a
hash of the notes its 'Convert to MIDI Track' wrote (captured from Sound Studio Gold 4.00).
Set SSGOLD_STYLE_SONGS to a folder of songs saved by the original after converting a chord track
(ST00.SNG ... ST15.SNG) to compare them note by note as well.
"""
import glob
import hashlib
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ssgold import styles as st          # noqa: E402
from ssgold.song import Song, Track, CHORD, MIDI   # noqa: E402

ORIGINAL = {
    'Rock': (32, '11cf317cba19fe04'),
    "Rock 'n' Roll": (24, 'bec8d4748f482dbf'),
    "R 'n' B": (24, '10b2e8269784cfbe'),
    'Pop': (16, 'bb3000c180d9bdd4'),
    'Disco': (16, 'f271832ba8d22dd8'),
    'Soul': (16, '2d39969920ff6e7c'),
    'Ballad': (12, 'b6cf8be8fcfea210'),
    'Slow Rock': (16, '9634ef4990aa3e07'),
    'Reggae': (10, 'dce206e36c74f4f3'),
    'Afro': (16, '21cb8a8c5c3c326a'),
    'Swing': (16, '41d04a3c0b2d47c8'),
    'Latin': (16, '788a36df36de3e44'),
    'March': (16, 'cc13fe9d7eeb9aa5'),
    'Big Band': (16, '0c66db70ebcf971a'),
    'Bluegrass': (16, 'd3b219a8d67a3011'),
    'Waltz': (16, 'be63b806c9d92256'),
}


def notes_hash(notes):
    return hashlib.sha256(repr(sorted(tuple(n) for n in notes)).encode()).hexdigest()[:16]


class Styles(unittest.TestCase):
    def test_sixteen_styles(self):
        self.assertEqual(st.STYLE_NAMES[0], 'Rock')
        self.assertEqual(st.STYLE_NAMES[15], 'Waltz')
        self.assertEqual(len(st.styles()), 16)

    def test_rock_progression(self):
        self.assertEqual(st.styles()[0]['progression'],
                         [[0, 1], [5, 1], [10, 0], [3, 0], [8, 0], [11, 8], [7, 0], [7, 2]])

    def test_instant_chord_track_bars(self):
        # changing style keeps whole progression cycles, as the original's dialog does
        bars = 32
        seen = []
        for i in (1, 3, 6, 7, 8, 9, 15):
            bars = st.fit_bars(i, bars)
            seen.append(bars)
        self.assertEqual(seen, [24, 16, 12, 16, 10, 16, 16])
        self.assertEqual(st.max_bars(0), 200)
        self.assertEqual(st.max_bars(1), 192)

    def test_matches_original_output(self):
        song = Song()
        song.timebase = 192
        for i, name in enumerate(st.STYLE_NAMES):
            bars, expected = ORIGINAL[name]
            ct = Track(name='CHORDS', kind=CHORD)
            ct.patterns = st.build_chord_patterns(song, ct, i, bars, 0)
            _start, entries = st.chord_entries(ct)
            with self.subTest(style=name):
                self.assertEqual(notes_hash(st.render(st.styles()[i], entries, 192)), expected)

    def test_convert_pattern(self):
        song = Song()
        st.set_style(song, 15)
        ct = Track(name='CHORDS', kind=CHORD)
        ct.patterns = st.build_chord_patterns(song, ct, 15, 16, 0)
        p = st.convert_pattern(song, ct)
        self.assertEqual(p.name, 'Waltz')
        self.assertEqual(p.end, 16 * 3 * song.timebase)
        programs = sorted((e.channel, e.d1) for e in p.events if e.status & 0xF0 == 0xC0)
        self.assertEqual([c for c, _ in programs], [9, 10, 11, 12, 13, 14])

    def test_live_matches_render(self):
        """Played live, the chord track gives the same notes as Convert to MIDI."""
        song = Song()
        song.timebase = 192
        st.set_style(song, 0)
        ct = Track(name='CHORDS', kind=CHORD)
        ct.patterns = st.build_chord_patterns(song, ct, 0, 32, 0)
        live = st.Live(song, ct)
        got = []
        for t in range(32 * 4 * 192 + 400):
            got += [(t, m) for _p, m in live.tick(t) if m[0] & 0xF0 == 0x90]
        ref = sorted((t, m) for t, _pr, _p, m in st.render_chord_track(song, ct) if m[0] & 0xF0 == 0x90)
        self.assertEqual(sorted(got), ref)

    def test_single_finger_chord(self):
        """A live chord plays every part (even with no chord list); released with Hold off, drums only."""
        song = Song()
        song.timebase = 192
        ct = Track(name='CHORDS', kind=CHORD)
        live = st.Live(song, ct)
        self.assertEqual(live.tick(0), [])              # nothing without a chord list or a live chord
        held, released = set(), set()
        for t in range(4 * 4 * 192):
            for _p, m in live.tick(t, (2, 1, True)):
                if m[0] & 0xF0 == 0x90:
                    held.add(m[0] & 0x0F)
        for t in range(4 * 4 * 192, 8 * 4 * 192):
            for _p, m in live.tick(t, (2, 1, False)):
                if m[0] & 0xF0 == 0x90:
                    released.add(m[0] & 0x0F)
        self.assertTrue({9, 14} <= held)                  # drums and bass
        self.assertEqual(released, {9})                  # drums only

    def test_original_songs(self):
        folder = os.environ.get('SSGOLD_STYLE_SONGS')
        if not folder:
            self.skipTest('SSGOLD_STYLE_SONGS not set')
        for path in sorted(glob.glob(os.path.join(folder, 'ST*.SNG'))):
            s = Song.load(path)
            ct = next(t for t in s.tracks if t.kind == CHORD)
            conv = [t for t in s.tracks if t.kind == MIDI and t.patterns and t.channel == 0][-1]
            i = st.STYLE_NAMES.index(conv.name)
            orig = [(e.tick, e.status, e.d1, e.d2, e.length) for p in conv.patterns for e in p.events
                    if e.status & 0xF0 == 0x90]
            _start, entries = st.chord_entries(ct)
            mine = st.render(st.styles()[i], entries, s.timebase)
            with self.subTest(song=os.path.basename(path)):
                self.assertEqual(sorted(map(tuple, mine)), sorted(orig))


if __name__ == '__main__':
    unittest.main()
