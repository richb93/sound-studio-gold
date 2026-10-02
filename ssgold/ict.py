"""Instant Chord Track (STYLE_DLG, modeless): builds a chord track in a chosen style."""
from . import resources
from .bwcc import Dialog
from .song import Track, Pattern, CHORD
from .styles import STYLE_NAMES


class InstantChordTrack:
    dlg = None

    @classmethod
    def open(cls, app):
        if cls.dlg is not None and cls.dlg.winfo_exists():
            cls.dlg.lift()
            return cls.dlg
        d = Dialog(app, 'STYLE_DLG', modal=False)
        cls.dlg = d
        song = app.song
        d.combo(2201, STYLE_NAMES, STYLE_NAMES[song.header[0x2D3] % len(STYLE_NAMES)])
        sb = d.ctrls[2206]
        sb.lo, sb.hi = 1, 256

        def upd(v):
            d.set_text(2205, '%3d' % v)
            from .timing import TimeMap
            tm = TimeMap(song)
            ms = tm.to_ms(tm.from_bbt(v + 1))
            secs = int(ms / 1000)
            d.set_text(2202, '%d' % (secs // 60))
            d.set_text(2203, '%02d' % (secs % 60))
        sb.cmd = upd
        sb.set(32, notify=True)
        d.set_check(2207, True)
        d.set_check(2208, False)
        has = any(t.kind == CHORD for t in song.tracks)
        d.enable(2211, has)

        def create():
            style = STYLE_NAMES.index(d.combo(2201)) if d.combo(2201) in STYLE_NAMES else 0
            bars = sb.value
            app.checkpoint()
            song.header[0x2D3] = style
            ct = next((t for t in song.tracks if t.kind == CHORD), None)
            if ct is None:
                ct = Track(name='CHORDS', kind=CHORD)
                ct.channel = 0
                ct.height = song.tracks[0].height if song.tracks else 13
                song.tracks.insert(0, ct)
            if d.check(2207):
                ct.patterns = []
            from .timing import TimeMap
            tm = TimeMap(song)
            start = max((p.end for p in ct.patterns), default=0)
            first = start
            for b in range(0, bars, 4):
                st = tm.from_bbt(tm.to_bbt(start)[0] + b) if b else start
                en = tm.from_bbt(tm.to_bbt(st)[0] + min(4, bars - b))
                p = Pattern(name='', start=st, end=en)
                p.set_chord(0, 0)
                for i in range(6):
                    p.set_chord_mute(i, 1)
                if b and ct.patterns:
                    p.parent = ct.patterns[-1].source if False else None
                p.track = ct
                ct.patterns.append(p)
            if d.check(2208):
                song.left, song.right = first, max(p.end for p in ct.patterns)
                app.seq.opts.cycle = True
                app.transport.redraw_buttons()
            d.enable(2211, True)
            app.song_changed('tracks')

        def convert():
            tw = app.windows.get('track')
            if tw:
                tw.chords_to_midi()
        d.on_command[2210] = create
        d.on_command[2211] = convert
        d.on_command[2212] = d.close
        d.show()
        return d
