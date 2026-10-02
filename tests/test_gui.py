"""GUI smoke test: opens the main window, every editor and single window, then closes them.

Needs a display (on Linux CI use Xvfb).  Skipped when Tk cannot start.
"""
import os
import sys
import tkinter as tk
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class Windows(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            r = tk.Tk()
            r.destroy()
        except tk.TclError:
            raise unittest.SkipTest('no display')
        from ssgold.app import App
        cls.app = App(scale=1)
        cls.app.update()

    @classmethod
    def tearDownClass(cls):
        cls.app.destroy()

    def setUp(self):
        from ssgold.song import Pattern, Event
        app = self.app
        t = next(t for t in app.song.tracks if t.kind == 0)
        if not t.patterns:
            p = Pattern(name='Test', start=0, end=app.song.timebase * 16)
            p.track = t
            p.events = [Event(i * 96, 0x90, 60 + i, 100, 90) for i in range(8)]
            t.patterns.append(p)
        for p in app.song.all_patterns():
            p.selected = False
        t.patterns[0].selected = True
        app.song_changed()

    def test_editors(self):
        # 80 Track, 81 Piano Roll, 82 Event, 83 Score, 84 Drum, 85 Conductor, 86 Notepad,
        # 87 Mixer, 88 Keyboard, 89 Lyrics, 90 Instant Chord Track
        for cid in range(80, 91):
            with self.subTest(command=cid):
                self.app.command(cid)
                self.app.update()
        for w in self.app.client.children_:      # no instance attribute may hide a method
            for klass in type(w).__mro__:
                if not klass.__module__.startswith('ssgold'):
                    continue
                for name, val in vars(klass).items():
                    if callable(val) and not name.startswith('__') and name in vars(w):
                        self.fail('%s.%s is hidden by an attribute' % (type(w).__name__, name))
        self.app.command(49)        # cascade
        self.app.command(50)        # tile
        self.app.update()
        self.app.command(52)        # close all
        self.app.update()

    def test_single_finger_chord(self):
        """A chord key on the Keyboard window starts the song (Synchro) with the band playing."""
        import time
        from ssgold.editors import open_single
        from ssgold.song import Track, CHORD
        app = self.app
        app.seq.stop()
        ct = Track(name='CHORDS', kind=CHORD)
        app.song.tracks.insert(0, ct)
        try:
            kb = open_single(app, 'keyboard')
            kb.st.update(active=True, synchro=True, hold=False, ctype=1)
            app.seq.out_log.clear()
            kb.note_on(36 + 2, 100, 'mouse')               # D minor
            self.assertTrue(app.seq.playing)
            self.assertEqual(app.seq.sfc, (2, 1, True))
            deadline = time.time() + 5
            while time.time() < deadline and not any(d[0] & 0xF0 == 0x90 and 10 <= d[0] & 0x0F <= 14
                                                     for _p, d in list(app.seq.out_log)):
                time.sleep(0.05)
            self.assertTrue(any(d[0] & 0xF0 == 0x90 and 10 <= d[0] & 0x0F <= 14
                                for _p, d in list(app.seq.out_log)))
            kb.note_off(36 + 2)
            self.assertEqual(app.seq.sfc, (2, 1, False))  # Hold off: drums only
            app.stop()
            self.assertIsNone(app.seq.sfc)
            kb.close()
        finally:
            app.seq.stop()
            app.song.tracks.remove(ct)
            app.update()

    def test_playback_position(self):
        self.app.locate(self.app.song.timebase * 4)
        self.app.update()
        self.assertEqual(self.app.seq.position, self.app.song.timebase * 4)


if __name__ == '__main__':
    unittest.main()
