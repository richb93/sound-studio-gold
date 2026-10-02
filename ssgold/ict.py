"""Instant Chord Track (STYLE_DLG, modeless; STYLEDLGPROC): builds a chord track in a chosen style.

The chords come from the style's own progression, one chord per bar; Bars is always a whole
number of progression cycles (the scroll bar's arrows step one cycle, its page area four).
"""
from .bwcc import Dialog
from .song import Track, CHORD
from . import styles as st


class InstantChordTrack:
    dlg = None
    bars = None         # remembered between openings, like the original's global

    @classmethod
    def open(cls, app):
        if cls.dlg is not None and cls.dlg.winfo_exists():
            cls.dlg.lift()
            return cls.dlg
        d = Dialog(app, 'STYLE_DLG', modal=False)
        cls.dlg = d
        song = app.song
        state = {'style': st.style_index(song)}
        if cls.bars is None:
            cls.bars = st.engine()['ict_bars']
        cls.bars = st.fit_bars(state['style'], cls.bars)
        d.combo(2201, st.STYLE_NAMES, st.STYLE_NAMES[state['style']], cmd=lambda name: pick(name))
        sb = d.ctrls[2206]

        def show_time():
            ticks = st.chord_ticks(state['style'], song.timebase) * cls.bars
            secs = int((app.tmap.to_ms(ticks) + 500) // 1000)
            d.set_text(2202, '%d' % (secs // 60))
            d.set_text(2203, '%02d' % (secs % 60))
            d.set_text(2205, '%d' % cls.bars)

        def setup_scroll():
            n = st.cycle_length(state['style'])
            sb.lo, sb.hi = 0, st.max_bars(state['style'])
            sb.step, sb.page = n, 4 * n
            sb.set(cls.bars)

        def scrolled(v):
            i = state['style']
            n = st.cycle_length(i)
            cls.bars = max(n, min(st.max_bars(i), v - v % n))
            sb.set(cls.bars)
            show_time()

        def pick(name):
            state['style'] = st.STYLE_NAMES.index(name) if name in st.STYLE_NAMES else 0
            cls.bars = st.fit_bars(state['style'], cls.bars)
            setup_scroll()
            show_time()

        sb.cmd = scrolled
        setup_scroll()
        show_time()
        d.set_check(2207, app.settings.get('ict_replace', True))
        d.set_check(2208, app.settings.get('ict_loop', False))
        ct = next((t for t in song.tracks if t.kind == CHORD), None)
        d.enable(2211, bool(ct and ct.patterns))

        def create():
            app.settings['ict_replace'] = d.check(2207)
            app.settings['ict_loop'] = d.check(2208)
            i = state['style']
            app.checkpoint()
            st.set_style(song, i)
            ct = next((t for t in song.tracks if t.kind == CHORD), None)
            if ct is None:
                ct = Track(name='CHORDS', kind=CHORD)
                ct.channel = 0
                ct.height = song.tracks[0].height if song.tracks else 13
                song.tracks.insert(0, ct)
            if d.check(2207):
                ct.patterns = []
            start = max((p.end for p in ct.patterns), default=0)
            new = st.build_chord_patterns(song, ct, i, cls.bars, start)
            ct.patterns.extend(new)
            if d.check(2208) and new:
                song.left, song.right = new[0].start, new[-1].end
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
