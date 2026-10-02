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
        self.app.command(49)        # cascade
        self.app.command(50)        # tile
        self.app.update()
        self.app.command(52)        # close all
        self.app.update()

    def test_playback_position(self):
        self.app.locate(self.app.song.timebase * 4)
        self.app.update()
        self.assertEqual(self.app.seq.position, self.app.song.timebase * 4)


if __name__ == '__main__':
    unittest.main()
