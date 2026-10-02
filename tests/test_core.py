"""Non-GUI tests: song file round trips, MIDI files, timing and the Procedures.

Run with:  python -m unittest discover tests
Set SSGOLD_SONGS to a folder of original .SNG files to also round-trip those (load, save, load).
"""
import glob
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ssgold import procedures                              # noqa: E402
from ssgold.song import (Song, Pattern, Event, new_song, CondPoint, COND_TEMPO,  # noqa: E402
                         COND_TIMESIG, MIDI)
from ssgold.timing import TimeMap, ts_index, ts_parts      # noqa: E402
from ssgold import smf                                     # noqa: E402


def song_with_notes():
    s = new_song()
    t = s.tracks[4]                     # Track 1
    p = Pattern(name='Riff', start=0, end=4 * s.timebase * 4)
    p.track = t
    for i, n in enumerate((60, 64, 67, 72)):
        p.events.append(Event(i * s.timebase, 0x90, n, 100, s.timebase // 2))
    p.events.append(Event(10, 0xB0, 7, 90))
    p.events.sort(key=lambda e: e.tick)
    t.patterns.append(p)
    return s, t, p


def summary(s):
    """Everything a song means, independent of table order."""
    out = [s.timebase, s.notepad, s.lyrics, sorted((c.tick, c.kind, c.value) for c in s.conductor.points)]
    for t in s.tracks:
        out.append((t.name, t.kind, bytes(t.raw[0x15:0x37])))
        for p in t.patterns:
            out.append((p.name, p.start, p.end, p.parent is not None,
                        [(e.tick, e.status, e.d1, e.d2, e.length, e.data) for e in p.events],
                        p.blob if t.kind != MIDI else None))
    return out


class FakeApp:
    def __init__(self, song):
        self.song = song


class SongFiles(unittest.TestCase):
    def test_new_song_round_trip(self):
        s = new_song()
        data = s.to_bytes()
        self.assertEqual(Song.from_bytes(data).to_bytes(), data)

    def test_patterns_and_conductor_survive(self):
        s, _t, _p = song_with_notes()
        s.conductor.points.append(CondPoint(s.timebase * 8, COND_TEMPO, 90))
        s.conductor.points.append(CondPoint(s.timebase * 8, COND_TIMESIG, ts_index(3, 4)))
        s.notepad = 'hello\nworld'
        s.set_lyrics([[0, 'la '], [192, 'la\n']])
        s2 = Song.from_bytes(s.to_bytes())
        p2 = s2.tracks[4].patterns[0]
        self.assertEqual(p2.name, 'Riff')
        self.assertEqual([(e.tick, e.d1, e.length) for e in p2.events if e.is_note()],
                         [(i * s.timebase, n, s.timebase // 2) for i, n in enumerate((60, 64, 67, 72))])
        self.assertEqual(s2.conductor.at(COND_TEMPO, s.timebase * 9).value, 90)
        self.assertEqual(s2.notepad.replace('\r\n', '\n'), 'hello\nworld')
        self.assertEqual(s2.lyric_list(), [[0, 'la '], [192, 'la\n']])

    def test_original_songs_round_trip(self):
        folder = os.environ.get('SSGOLD_SONGS')
        if not folder:
            self.skipTest('SSGOLD_SONGS not set')
        files = glob.glob(os.path.join(folder, '**', '*.[sS][nN][gG]'), recursive=True)
        self.assertTrue(files)
        for f in files:
            data = open(f, 'rb').read()
            with self.subTest(song=os.path.basename(f)):
                s1 = Song.from_bytes(data)
                b1 = s1.to_bytes()
                s2 = Song.from_bytes(b1)
                self.assertEqual(s2.to_bytes(), b1)                 # saving is stable
                self.assertEqual(summary(s1), summary(s2))           # nothing lost

    def test_original_header_kept(self):
        folder = os.environ.get('SSGOLD_SONGS')
        if not folder:
            self.skipTest('SSGOLD_SONGS not set')
        for f in glob.glob(os.path.join(folder, '**', '*.[sS][nN][gG]'), recursive=True):
            data = open(f, 'rb').read()
            out = Song.from_bytes(data).to_bytes()
            with self.subTest(song=os.path.basename(f)):
                # pattern count may shrink: unreferenced patterns are not written back
                self.assertEqual(out[:8] + out[10:0x400], data[:8] + data[10:0x400])


class PatternFiles(unittest.TestCase):
    def test_pat_round_trip(self):
        from ssgold.song import save_pattern, load_pattern
        _s, _t, p = song_with_notes()
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, 'riff.pat')
            save_pattern(p, path)
            q = load_pattern(path)
        self.assertEqual(q.name, 'Riff')
        self.assertEqual((q.start, q.end), (0, p.end - p.start))
        self.assertEqual([(e.tick, e.status, e.d1, e.d2, e.length) for e in q.events],
                         [(e.tick, e.status, e.d1, e.d2, e.length) for e in p.events])

    def test_original_pat(self):
        path = os.environ.get('SSGOLD_PAT')
        if not path:
            self.skipTest('SSGOLD_PAT not set')
        from ssgold.song import load_pattern
        q = load_pattern(path)
        self.assertTrue(q.events)


class MidiFiles(unittest.TestCase):
    def test_smf_write_read(self):
        s, _t, _p = song_with_notes()
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, 'x.mid')
            smf.write_smf(s, path)
            s2 = smf.read_smf(path, split_type0=False)
        notes = sorted((p.start + e.tick, e.d1, e.length) for t in s2.tracks if t.kind == MIDI
                       for p in t.patterns for e in p.events if e.is_note())
        self.assertEqual(notes, [(i * s.timebase, n, s.timebase // 2) for i, n in enumerate((60, 64, 67, 72))])


class Timing(unittest.TestCase):
    def test_bars_beats(self):
        s = new_song()
        tb = s.timebase
        s.conductor.points.append(CondPoint(tb * 4 * 2, COND_TIMESIG, ts_index(3, 4)))
        tm = TimeMap(s)
        self.assertEqual(tm.to_bbt(0), (1, 1, 0))
        self.assertEqual(tm.to_bbt(tb * 4 * 2), (3, 1, 0))
        self.assertEqual(tm.to_bbt(tb * 4 * 2 + tb * 3), (4, 1, 0))
        self.assertEqual(tm.from_bbt(4), tb * 11)
        self.assertEqual(tm.fmt(tb * 5 + 7), '2:02:007')
        self.assertEqual(ts_parts(ts_index(6, 8)), (6, 8))

    def test_tempo_to_ms(self):
        s = new_song()
        tm = TimeMap(s)
        self.assertAlmostEqual(tm.to_ms(s.timebase), 500.0, places=3)     # one beat at 120 bpm


class Procedures(unittest.TestCase):
    def setUp(self):
        self.s, self.t, self.p = song_with_notes()
        self.target = procedures.Target(FakeApp(self.s), [(self.p, list(self.p.events))])

    def notes(self):
        return [e for e in self.p.events if e.is_note()]

    def test_transpose(self):
        procedures.transpose(self.target, 12)
        self.assertEqual([e.d1 for e in self.notes()], [72, 76, 79, 84])

    def test_quantize(self):
        for e in self.notes():
            e.tick += 7
        procedures.quantize(self.target, self.s.timebase)
        self.assertEqual([e.tick for e in self.notes()], [i * self.s.timebase for i in range(4)])

    def test_legato(self):
        procedures.lengths(self.target, 'legato')
        self.assertEqual([e.length for e in self.notes()][:3], [self.s.timebase] * 3)

    def test_velocity_limits(self):
        procedures.velocity(self.target, 50, 'up', 1, 120)
        self.assertTrue(all(e.d2 == 120 for e in self.notes()))

    def test_reverse(self):
        procedures.reverse(self.target)
        self.assertEqual([e.d1 for e in sorted(self.notes(), key=lambda e: e.tick)], [72, 67, 64, 60])


if __name__ == '__main__':
    unittest.main()
