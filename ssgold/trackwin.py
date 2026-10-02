"""Track window (MDITRACKWNDPROC): track columns, timeline and the pattern display."""
import tkinter as tk
from tkinter import messagebox

from . import ui, resources, tools
from .mdi import MDIChild
from .ui import s
from .widgets import Toolbar, PopupMenu
from .song import Track, Pattern, MIDI, AUDIO, CHORD, OFF, PAN_OFF, Event
from .timing import TimeMap

# column id -> (heading, base width, key)
COLUMNS = {
    551: ('Name', 60, 'name'), 552: ('Prog', 29, 'prog'), 553: ('Patch', 131, 'patch'),
    554: ('Bank', 29, 'bank'), 555: ('Ch', 17, 'channel'), 556: ('P', 13, 'port'),
    557: ('Vol', 29, 'volume'), 558: ('Pan', 29, 'pan'), 559: ('FX Type', 41, 'fx_type'),
    560: ('Rev', 29, 'reverb'), 561: ('Chor', 29, 'chorus'), 562: ('Vel', 29, 'velocity'),
    563: ('Tran', 29, 'transpose'), 564: ('Time', 29, 'time'), 565: ('Mute', 29, 'mute'),
    566: ('Solo', 29, 'solo'), 567: ('Rec', 29, 'rec'), 568: ('Mon', 23, 'monitor'),
}
FX_NAMES = ['OFF', 'Delay', 'Echo', 'Reverb']
ROW_COLOURS = {MIDI: '#000000', AUDIO: '#800000', CHORD: '#000080'}
SNAP_VALUES = ['Bar', ' 1', ' 2', ' 4', ' 8', '16', '32', '64', 'Off']
CHORD_SNAP = ['1', '2', '4', '8', '16']
TOOLBAR_H = 18
HEADER_H = 13
CHORD_ROW_H = 16

TRACK_TOOLS = [('arrow', 'CUR_ARROW_BM', ''), ('pencil', 'CUR_PENCIL_BM', 'CUR_PENCIL'),
               ('eraser', 'CUR_ERASER_BM', 'CUR_ERASER'), ('mute', 'CUR_MUTE_BM', 'CUR_MUTE'),
               ('knife', 'CUR_KNIFE_BM', 'CUR_KNIFE'), ('glue', 'CUR_GLUE_BM', 'CUR_GLUE')]


class PatternClip:
    """Clipboard contents for patterns."""

    def __init__(self, items, origin):
        self.items = items        # list of (track index offset, Pattern copy, source)
        self.origin = origin

    def describe(self):
        n = len(self.items)
        return resources.tables() and ('%d Patterns' % n if n != 1 else '1 Pattern')


class TrackWindow(MDIChild):
    closable = True

    def __init__(self, client, app):
        client.update_idletasks()
        cw = max(400, client.winfo_width() // ui.S - 38)
        ch = max(300, client.winfo_height() // ui.S)
        super().__init__(client, 'Track - (Untitled)', app.small_icon('IC_TRACK'), 0, 0, cw, ch)
        self.app = app
        self.x0_tick = 0          # leftmost tick in pattern display
        self.top_row = 0          # vertical scroll in pixels
        self.tpp = 64             # ticks per pixel (horizontal zoom)
        self.divider = 0          # extra width added to column area (dragged)
        self.cur_track = None
        self.drag = None
        self.monitor = {}
        self.tool = tools.ToolSelector(app, TRACK_TOOLS, cols=3)
        self.tool.on_change = self._tool_changed
        self._build()
        self.new_song()

    # ------------------------------------------------------------------ layout
    def _build(self):
        b = self.body
        self.tb = Toolbar(b, self.app)
        self.tb.pack(side='top', fill='x')
        tb = self.tb
        tb.add_button('MENU_BM', self.functions_menu, pressed='MENU_BM_PR')
        tb.add_button('ZOOMIN_BM', lambda ev=None: self.zoom(-1))
        tb.add_button('ZOOMOUT_BM', lambda ev=None: self.zoom(1))
        tb.add_button('ZOOMIN_TRK', lambda: self.vzoom(1))
        tb.add_button('ZOOMOUT_TRK', lambda: self.vzoom(-1))
        tb.add_button('IB_MIDI', lambda: self.add_track(MIDI))
        tb.add_button('IB_CHORD', lambda: self.add_track(CHORD))
        tb.add_button('IB_AUDIO', lambda: self.add_track(AUDIO))
        tb.add_label('Snap', 30)
        self.snap = tb.add_combo(SNAP_VALUES, 46, 'Bar', listw=46)
        tb.add_label('Chord Snap', 60)
        self.chord_snap = tb.add_combo(CHORD_SNAP, 46, '4', listw=46)
        tb.add_label('Multitrack Recording', 102)
        self.multi_box = tk.Canvas(tb, width=s(12), height=s(12), bg=ui.WINDOW, highlightthickness=0, bd=0)
        tb.create_window(s(tb.x + 2), s(3), window=self.multi_box, anchor='nw')
        self.multi_box.bind('<Button-1>', lambda e: self.toggle_multitrack())
        self._draw_multi()
        # chord style row
        self.chordrow = tk.Canvas(b, height=s(CHORD_ROW_H), bg=ui.FACE, highlightthickness=0, bd=0)
        self.chordrow.bind('<Button-1>', self._chordrow_click)
        # main area: columns | divider | timeline + patterns, with scrollbars
        self.main = tk.Frame(b, bg=ui.FACE)
        self.main.pack(side='top', fill='both', expand=True)
        self.hbar = tk.Scrollbar(self.main, orient='horizontal', command=self._hscroll)
        self.hbar.pack(side='bottom', fill='x')
        self.vbar = tk.Scrollbar(self.main, orient='vertical', command=self._vscroll)
        self.vbar.pack(side='right', fill='y')
        self.cols = tk.Canvas(self.main, bg=ui.FACE, highlightthickness=0, bd=0)
        self.cols.pack(side='left', fill='y')
        self.div = tk.Canvas(self.main, width=s(3), bg=ui.SHADOW, highlightthickness=0, bd=0, cursor='sb_h_double_arrow')
        self.div.pack(side='left', fill='y')
        self.div.bind('<B1-Motion>', self._div_drag)
        self.div.bind('<Button-1>', self._div_press)
        self.right = tk.Frame(self.main, bg=ui.FACE)
        self.right.pack(side='left', fill='both', expand=True)
        self.timeline = tk.Canvas(self.right, height=s(HEADER_H + 1), bg=ui.FACE, highlightthickness=0, bd=0)
        self.timeline.pack(side='top', fill='x')
        self.pat = tk.Canvas(self.right, bg=ui.WINDOW, highlightthickness=0, bd=0)
        self.pat.pack(side='top', fill='both', expand=True)
        # events
        self.cols.bind('<Configure>', lambda e: self.draw_columns())
        self.pat.bind('<Configure>', lambda e: self.redraw())
        self.cols.bind('<ButtonPress-1>', lambda e: self._col_press(e, 1))
        self.cols.bind('<ButtonRelease-1>', lambda e: self._col_release(e, 1))
        self.cols.bind('<B1-Motion>', self._col_drag)
        self.cols.bind('<Double-Button-1>', self._col_double)
        ui.bind_right(self.cols, 'ButtonPress', lambda e: self._col_press(e, 3))
        ui.bind_right(self.cols, 'ButtonRelease', lambda e: self._col_release(e, 3))
        self.timeline.bind('<Button-1>', lambda e: self._tl_click(e, 1))
        ui.bind_right(self.timeline, 'ButtonPress', lambda e: self._tl_click(e, 3))
        self.pat.bind('<ButtonPress-1>', self._pat_press)
        self.pat.bind('<B1-Motion>', self._pat_drag)
        self.pat.bind('<ButtonRelease-1>', self._pat_release)
        self.pat.bind('<Double-Button-1>', self._pat_double)
        self.tool.bind(self.pat)
        for w in (self.pat, self.cols):
            w.bind('<MouseWheel>', self._wheel)
            w.bind('<Button-4>', lambda e: self._vscroll('scroll', -1, 'units'))
            w.bind('<Button-5>', lambda e: self._vscroll('scroll', 1, 'units'))
        self.rep = ui.Repeater(self.cols)
        self.set_background()

    def set_background(self):
        bg = self.app.settings['prefs'].get('bg_track', 'Vellum')
        name = self.app.BACKGROUNDS.get(bg)
        self.bg_img = self.app.images.get(name) if name else None
        self.redraw()

    # ------------------------------------------------------------------ song binding
    def new_song(self):
        song = self.app.song
        tr = [t for t in song.tracks]
        self.cur_track = next((t for t in tr if t.selected), tr[0] if tr else None)
        for t in tr:
            t.selected = t is self.cur_track
        self.tpp = max(1, song.timebase // 3)
        h0 = tr[0].height if tr else 13
        self.x0_tick = 0
        self.top_row = 0
        dv = tr[0].divider if tr else 0
        self.set_title('Track - %s' % self.app.song_name())
        self.refresh()

    def refresh(self, what=None):
        if not self.winfo_exists():
            return
        if self.cur_track not in self.app.song.tracks:
            self.cur_track = self.app.song.tracks[0] if self.app.song.tracks else None
        self._layout_chord_row()
        self.draw_columns()
        self.redraw()

    def rebind(self, _p):
        self.cur_track = next((t for t in self.app.song.tracks if t.selected), None)

    def current_track(self):
        return self.cur_track

    # ------------------------------------------------------------------ geometry helpers
    def visible_columns(self):
        return [c for c in self.app.settings['track_columns'] if c in COLUMNS]

    def column_widths(self):
        song = self.app.song
        out = []
        for cid in self.visible_columns():
            head, w, key = COLUMNS[cid]
            if key == 'name':
                w = max([w] + [int(ui.text_width(t.name, 'system')) + 4 for t in song.tracks])
            elif key == 'patch':
                w = max([w] + [int(ui.text_width(self.patch_name(t), 'system')) + 4 for t in song.tracks[:300]])
            elif key in ('reverb', 'chorus') and any(t.kind == AUDIO for t in song.tracks):
                w = max(w, 31)
            out.append((cid, w))
        return out

    def heading(self, cid):
        head = COLUMNS[cid][0]
        has_audio = any(t.kind == AUDIO for t in self.app.song.tracks)
        cur = self.cur_track
        if cid == 560 and cur is not None and cur.kind == AUDIO:
            return 'Delay'
        if cid == 561 and cur is not None and cur.kind == AUDIO:
            return 'Depth'
        return head

    def row_y(self, i):
        y = 0
        for t in self.app.song.tracks[:i]:
            y += t.height
        return y

    def track_at_y(self, y):
        """y in pattern-canvas pixels (scrolled)."""
        yy = 0
        for i, t in enumerate(self.app.song.tracks):
            if yy <= y < yy + t.height:
                return i, t
            yy += t.height
        return None, None

    def tick_to_x(self, tick):
        return (tick - self.x0_tick) / self.tpp

    def x_to_tick(self, x):
        return int(x * self.tpp + self.x0_tick)

    def patch_name(self, t):
        if t.kind != MIDI:
            return ''
        return self.app.patches.name(max(0, t.port), t.channel or 1, t.prog, t.bank)

    # ------------------------------------------------------------------ chord row
    def _layout_chord_row(self):
        has_chord = any(t.kind == CHORD for t in self.app.song.tracks)
        if has_chord and not self.chordrow.winfo_ismapped():
            self.chordrow.pack(side='top', fill='x', after=self.tb)
        elif not has_chord and self.chordrow.winfo_ismapped():
            self.chordrow.pack_forget()
        if has_chord:
            self._draw_chord_row()

    def _sel_chord(self):
        sel = [p for p in self.app.song.all_patterns() if p.selected and p.track.kind == CHORD]
        return sel[0] if len(sel) == 1 else None

    def _draw_chord_row(self):
        from .styles import style_of
        from .chords import ROOTS, type_names
        c = self.chordrow
        c.delete('all')
        ui.raised(c, 0, 0, 35, CHORD_ROW_H, outer=False)
        ui.text(c, 3, CHORD_ROW_H // 2, 'Style', 'small', anchor='w')
        ui.raised(c, 35, 0, 115, CHORD_ROW_H)
        ui.text(c, 38, CHORD_ROW_H // 2, style_of(self.app.song), 'system', anchor='w')
        self.chord_hot = [('style', 35, 115)]
        p = self._sel_chord()
        if p is not None:
            root, ctype = p.source.chord()
            x = 118
            ui.raised(c, x, 0, x + 34, CHORD_ROW_H, outer=False)
            ui.text(c, x + 3, CHORD_ROW_H // 2, 'Chord', 'small', anchor='w')
            ui.raised(c, x + 34, 0, x + 60, CHORD_ROW_H)
            ui.text(c, x + 47, CHORD_ROW_H // 2, ROOTS[root % 12], 'system', anchor='center')
            self.chord_hot.append(('root', x + 34, x + 60))
            x += 62
            ui.raised(c, x, 0, x + 30, CHORD_ROW_H, outer=False)
            ui.text(c, x + 3, CHORD_ROW_H // 2, 'Type', 'small', anchor='w')
            ui.raised(c, x + 30, 0, x + 66, CHORD_ROW_H)
            ui.text(c, x + 48, CHORD_ROW_H // 2, type_names()[ctype % 12], 'system', anchor='center')
            self.chord_hot.append(('type', x + 30, x + 66))
            x += 70
            names = ['Acc1', 'Acc2', 'Acc3', 'Acc4', 'Bass', 'Drums']
            mutes = p.source.chord_mutes()
            for i, nm in enumerate(names):
                w = int(ui.text_width(nm, 'small')) + 20
                ui.raised(c, x, 0, x + w, CHORD_ROW_H, outer=False)
                ui.image(c, x + 2, 1, self.app.images.get('BUT_ON' if mutes[i] else 'BUT_OFF'))
                ui.text(c, x + 17, CHORD_ROW_H // 2, nm, 'small', anchor='w')
                self.chord_hot.append(('mute%d' % i, x, x + w))
                x += w

    def _chordrow_click(self, ev):
        from .styles import STYLE_NAMES
        from .chords import ROOTS, type_names
        x = ev.x / ui.S
        for key, x0, x1 in getattr(self, 'chord_hot', []):
            if not x0 <= x < x1:
                continue
            app = self.app
            p = self._sel_chord()
            if key == 'style':
                def set_style(i):
                    app.checkpoint()
                    app.song.header[0x2D3] = i
                    app.song_changed()
                PopupMenu.show(self, [(n, lambda i=i: set_style(i)) for i, n in enumerate(STYLE_NAMES)],
                               ev.x_root, ev.y_root)
            elif key == 'root' and p:
                PopupMenu.show(self, [(n, lambda i=i: self._set_chord(p, root=i)) for i, n in enumerate(ROOTS)],
                               ev.x_root, ev.y_root)
            elif key == 'type' and p:
                PopupMenu.show(self, [(n, lambda i=i: self._set_chord(p, ctype=i)) for i, n in enumerate(type_names())],
                               ev.x_root, ev.y_root)
            elif key.startswith('mute') and p:
                i = int(key[4:])
                self.app.checkpoint()
                p.source.set_chord_mute(i, 0 if p.source.chord_mutes()[i] else 1)
                self.app.song_changed('patterns')
            return

    def _set_chord(self, p, root=None, ctype=None):
        self.app.checkpoint()
        r, t = p.source.chord()
        p.source.set_chord(r if root is None else root, t if ctype is None else ctype)
        self.app.song_changed('patterns')

    # ------------------------------------------------------------------ toolbar actions
    def _draw_multi(self):
        c = self.multi_box
        c.delete('all')
        ui.sunken(c, 0, 0, 12, 12, fill=ui.WINDOW)
        if self.app.seq.opts.multitrack:
            ui.line(c, 3, 3, 9, 9)
            ui.line(c, 9, 3, 3, 9)

    def toggle_multitrack(self):
        o = self.app.seq.opts
        o.multitrack = not o.multitrack
        if not o.multitrack:
            recs = [t for t in self.app.song.tracks if t.rec]
            for t in recs[1:]:
                t.rec = 0
        self._draw_multi()
        self.draw_columns()

    def zoom(self, d, ev=None):
        if d < 0:
            self.tpp = max(1, self.tpp // 2)
        else:
            self.tpp = min(4096, self.tpp * 2)
        self.redraw()

    def vzoom(self, d):
        for t in self.app.song.tracks:
            t.height = max(13, min(64, t.height + (4 if d > 0 else -4)))
        self.refresh()

    def add_track(self, kind):
        song = self.app.song
        if len(song.tracks) >= 256:
            messagebox.showinfo('Sound Studio Gold', resources.string(19), parent=self.app)
            return
        if kind == CHORD and any(t.kind == CHORD for t in song.tracks):
            return
        self.app.checkpoint()
        if kind == MIDI:
            n = len([t for t in song.tracks if t.kind == MIDI]) + 1
            t = Track(name='Track %d' % n)
            t.channel = (n - 1) % 16 + 1
        elif kind == CHORD:
            t = Track(name='CHORDS', kind=CHORD)
            t.channel = 0
        else:
            n = len([t for t in song.tracks if t.kind == AUDIO]) + 1
            t = Track(name='Audio %d' % n, kind=AUDIO)
        h = song.tracks[0].height if song.tracks else 13
        t.height = h
        idx = song.tracks.index(self.cur_track) + 1 if self.cur_track in song.tracks else len(song.tracks)
        if kind == CHORD:
            idx = 0
        song.tracks.insert(idx, t)
        self.select_track(t)
        self.app.song_changed('tracks')

    def functions_menu(self, ev=None):
        st = resources.string
        items = [(st(768), self.copy_track), (st(769), self.delete_track), (st(770), self.delete_all_tracks),
                 (st(771), self.delete_unused), None, (st(772), self.pattern_dimensions), None,
                 (st(773), self.insert_between), (st(774), self.delete_between), (st(775), self.slice_at),
                 None, (st(776), self.chords_to_midi, any(t.kind == CHORD for t in self.app.song.tracks)),
                 (st(777), self.merge_patterns), (st(778), self.extract_pattern), None,
                 (st(779), lambda: self.add_track(MIDI)), (st(780), lambda: self.add_track(CHORD)),
                 (st(781), lambda: self.add_track(AUDIO))]
        x = self.tb.winfo_rootx()
        y = self.tb.winfo_rooty() + self.tb.winfo_height()
        PopupMenu.show(self, items, x, y)

    # ------------------------------------------------------------------ functions
    def selected_patterns(self):
        return [p for p in self.app.song.all_patterns() if p.selected]

    def scope_patterns(self):
        sel = self.selected_patterns()
        if sel:
            return sel
        return list(self.cur_track.patterns) if self.cur_track else []

    def _editing(self, patterns):
        for w in self.app.client.children_:
            p = getattr(w, 'pattern', None)
            if p is not None and any(p.source is q.source for q in patterns):
                return True
        return False

    def copy_track(self):
        t = self.cur_track
        if t is None:
            return
        app = self.app
        app.checkpoint()
        nt = t.copy()
        nt.patterns = []
        as_parent = app.settings['prefs'].get('copy_as_parents')
        for p in t.patterns:
            q = self._copy_pattern(p, as_parent)
            q.track = nt
            nt.patterns.append(q)
        song = app.song
        song.tracks.insert(song.tracks.index(t) + 1, nt)
        app.song_changed('tracks')

    def _copy_pattern(self, p, as_parent):
        q = Pattern(bytes(p.raw))
        q.selected = False
        if as_parent or p.track.kind == CHORD and as_parent:
            src = p.source
            q.parent = None
            q.events = [e.copy() for e in src.events]
            q.blob = src.blob
            if p.parent is not None:
                for f in ('root',):
                    pass
        else:
            q.parent = p.source
        return q

    def delete_track(self):
        t = self.cur_track
        if t is None:
            return
        if self._editing(t.patterns):
            messagebox.showinfo('Sound Studio Gold', resources.string(53), parent=self.app)
            return
        self.app.checkpoint()
        self._remove_patterns(list(t.patterns))
        song = self.app.song
        i = song.tracks.index(t)
        song.tracks.remove(t)
        self.cur_track = song.tracks[min(i, len(song.tracks) - 1)] if song.tracks else None
        if self.cur_track:
            self.cur_track.selected = True
        self.app.song_changed('tracks')

    def delete_all_tracks(self):
        if messagebox.askyesno('Sound Studio Gold', resources.string(817) % 'all tracks', parent=self.app):
            self.app.checkpoint()
            self.app.song.tracks.clear()
            self.cur_track = None
            self.app.song_changed('tracks')

    def delete_unused(self):
        self.app.checkpoint()
        song = self.app.song
        song.tracks = [t for t in song.tracks if t.patterns]
        self.app.song_changed('tracks')

    def _remove_patterns(self, pats):
        """Delete patterns; a child of a deleted parent becomes the parent (help: Track Window)."""
        song = self.app.song
        dead = {id(p) for p in pats}
        for p in pats:
            if p.parent is None:
                kids = [c for c in song.children_of(p) if id(c) not in dead]
                if kids:
                    heir = kids[0]
                    heir.parent = None
                    heir.events = p.events
                    heir.blob = p.blob
                    for k in kids[1:]:
                        k.parent = heir
        for t in song.tracks:
            t.patterns = [q for q in t.patterns if id(q) not in dead]

    def pattern_dimensions(self):
        from . import commands
        p = commands.selected_pattern(self.app)
        if p is None:
            return
        if self._editing([p]):
            messagebox.showinfo('Sound Studio Gold', resources.string(36), parent=self.app)
            return
        from . import dialogs
        dialogs.run(self.app, 'DIM_PAT_DLG', pattern=p)

    def insert_between(self):
        song = self.app.song
        l, r = song.left, song.right
        if r <= l:
            return
        self.app.checkpoint()
        d = r - l
        self._slice_all(l)
        for p in song.all_patterns():
            if p.start >= l:
                p.start += d
                p.end += d
        for c in song.conductor.points:
            if c.tick >= l and c.tick > 0:
                c.tick += d
        self.app.song_changed('patterns')

    def delete_between(self):
        song = self.app.song
        l, r = song.left, song.right
        if r <= l:
            return
        self.app.checkpoint()
        self._slice_all(l)
        self._slice_all(r)
        d = r - l
        gone = [p for p in song.all_patterns() if l <= p.start and p.end <= r]
        self._remove_patterns(gone)
        for p in song.all_patterns():
            if p.start >= r:
                p.start -= d
                p.end -= d
        self.app.song_changed('patterns')

    def slice_at(self):
        self.app.checkpoint()
        self._slice_all(self.app.song.left)
        self._slice_all(self.app.song.right)
        self.app.song_changed('patterns')

    def _slice_all(self, tick):
        for t in self.app.song.tracks:
            for p in list(t.patterns):
                if p.start < tick < p.end:
                    self.slice_pattern(p, tick)

    def slice_pattern(self, p, tick):
        """Knife: split p at tick into two patterns (MIDI patterns become parents)."""
        t = p.track
        rel = tick - p.start
        a = p
        b = Pattern(bytes(p.raw))
        b.track = t
        b.start = tick
        b.end = p.end
        if t.kind == MIDI:
            src = p.source.events
            ev_a = [e.copy() for e in src if e.tick < rel]
            ev_b = []
            for e in src:
                if e.tick >= rel:
                    n = e.copy()
                    n.tick -= rel
                    ev_b.append(n)
            for e in ev_a:
                if e.is_note() and e.tick + e.length > rel:
                    e.length = rel - e.tick
            if a.parent is not None:
                a.parent = None
            a.events = ev_a
            b.parent = None
            b.events = ev_b
        else:
            b.parent = p.source
        a.end = tick
        t.patterns.insert(t.patterns.index(a) + 1, b)
        return b

    def glue(self, p):
        t = p.track
        after = [q for q in t.patterns if q.start >= p.end and q is not p]
        if not after:
            return
        q = min(after, key=lambda x: x.start)
        if t.kind == MIDI:
            ev = [e.copy() for e in p.source.events if e.tick < p.length]
            off = q.start - p.start
            for e in q.source.events:
                if e.tick < q.length:
                    n = e.copy()
                    n.tick += off
                    ev.append(n)
            p.parent = None
            p.events = sorted(ev, key=lambda e: e.tick)
        p.end = q.end
        self._remove_patterns([q])

    def chords_to_midi(self):
        from .styles import render_chord_track
        song = self.app.song
        ct = next((t for t in song.tracks if t.kind == CHORD), None)
        if ct is None:
            return
        self.app.checkpoint()
        data = render_chord_track(song, ct)
        t = Track(name='Chords')
        t.channel = 0
        t.height = ct.height
        start = min((p.start for p in ct.patterns), default=0)
        end = max((p.end for p in ct.patterns), default=0)
        p = Pattern(name='Chords', start=start, end=end)
        on = {}
        for tick, _pr, _port, d in sorted(data, key=lambda x: (x[0], x[1])):
            hi = d[0] & 0xF0
            if hi == 0x90:
                e = Event(tick - start, d[0], d[1], d[2], 1)
                on[(d[0] & 0x0F, d[1])] = e
                p.events.append(e)
            elif hi == 0x80:
                e = on.pop((d[0] & 0x0F, d[1]), None)
                if e:
                    e.length = max(1, tick - start - e.tick)
            elif hi == 0xC0:
                p.events.append(Event(tick - start, d[0], d[1]))
        p.track = t
        t.patterns.append(p)
        song.tracks.insert(song.tracks.index(ct) + 1, t)
        self.app.song_changed('tracks')

    def merge_patterns(self):
        sel = [p for p in self.selected_patterns() if p.track.kind == MIDI]
        if not sel:
            messagebox.showinfo('Sound Studio Gold', resources.string(15), parent=self.app)
            return
        self.app.checkpoint()
        start = min(p.start for p in sel)
        end = max(p.end for p in sel)
        np = Pattern(name='Merged', start=start, end=end)
        for p in sel:
            ch = p.channel or p.track.channel
            for e in p.get_events():
                if e.tick >= p.length:
                    continue
                n = e.copy()
                n.tick += p.start - start
                if ch and n.status < 0xF0:
                    n.status = (n.status & 0xF0) | (ch - 1)
                np.events.append(n)
        np.events.sort(key=lambda e: e.tick)
        t = Track(name='Merged')
        t.channel = 0
        t.height = sel[0].track.height
        np.track = t
        t.patterns.append(np)
        self.app.song.tracks.append(t)
        self.app.song_changed('tracks')

    def extract_pattern(self):
        from . import commands
        p = commands.selected_pattern(self.app)
        if p is None or p.track.kind != MIDI:
            return
        chans = sorted({e.channel for e in p.get_events() if e.status < 0xF0})
        if len(chans) < 2:
            return
        self.app.checkpoint()
        song = self.app.song
        at = song.tracks.index(p.track) + 1
        for ch in chans:
            t = Track(name='%s %d' % (p.name[:16], ch + 1))
            t.channel = ch + 1
            t.height = p.track.height
            q = Pattern(name=t.name, start=p.start, end=p.end)
            q.events = [e.copy() for e in p.get_events() if e.status < 0xF0 and e.channel == ch]
            q.track = t
            t.patterns.append(q)
            song.tracks.insert(at, t)
            at += 1
        self.app.song_changed('tracks')

    # ------------------------------------------------------------------ edit menu
    def edit_copy(self, cut=False):
        sel = self.selected_patterns()
        if not sel:
            messagebox.showinfo('Sound Studio Gold', resources.string(15), parent=self.app)
            return
        song = self.app.song
        base = min(song.tracks.index(p.track) for p in sel)
        t0 = min(p.start for p in sel)
        items = []
        for p in sel:
            q = Pattern(bytes(p.raw))
            q.events = [e.copy() for e in p.source.events]
            q.blob = p.source.blob
            q.start -= t0
            q.end -= t0
            items.append((song.tracks.index(p.track) - base, q, p.source))
        self.app.clipboard = PatternClip(items, t0)
        if cut:
            self.app.checkpoint()
            self._remove_patterns(sel)
            self.app.song_changed('patterns')

    def edit_cut(self):
        self.edit_copy(cut=True)

    def edit_paste(self):
        cb = self.app.clipboard
        if not isinstance(cb, PatternClip):
            messagebox.showinfo('Sound Studio Gold', resources.string(2), parent=self.app)
            return
        song = self.app.song
        if self.cur_track is None:
            messagebox.showinfo('Sound Studio Gold', resources.string(4), parent=self.app)
            return
        self.app.checkpoint()
        base = song.tracks.index(self.cur_track)
        pos = self.app.seq.position
        for p in song.all_patterns():
            p.selected = False
        as_parent = self.app.settings['prefs'].get('copy_as_parents')
        for off, q, src in cb.items:
            ti = base + off
            if ti >= len(song.tracks):
                continue
            t = song.tracks[ti]
            n = Pattern(bytes(q.raw))
            n.start = pos + q.start
            n.end = pos + q.end
            alive = any(src is p.source for p in song.all_patterns())
            if as_parent or not alive:
                n.events = [e.copy() for e in q.events]
                n.blob = q.blob
            else:
                n.parent = src
            n.track = t
            n.selected = True
            t.patterns.append(n)
            t.patterns.sort(key=lambda x: x.start)
        self.app.song_changed('patterns')

    def edit_clear(self):
        sel = self.selected_patterns()
        if not sel:
            return
        if self._editing(sel):
            messagebox.showinfo('Sound Studio Gold', resources.string(36), parent=self.app)
            return
        self.app.checkpoint()
        self._remove_patterns(sel)
        self.app.song_changed('patterns')

    def edit_select_all(self):
        for p in self.app.song.all_patterns():
            p.selected = True
        self.redraw()

    def procedure_target(self):
        from .procedures import Target
        return Target.from_patterns(self.app, self.scope_patterns())

    # ------------------------------------------------------------------ track list drawing
    def draw_columns(self):
        c = self.cols
        c.delete('all')
        song = self.app.song
        widths = self.column_widths()
        total = sum(w + 1 for _c, w in widths) + self.divider
        c.configure(width=s(total))
        H = c.winfo_height() // ui.S
        # header
        x = 0
        self.col_x = []
        for cid, w in widths:
            ui.text(c, x + w // 2, HEADER_H // 2 + 1, self.heading(cid), 'small', anchor='center')
            self.col_x.append((cid, x, w))
            x += w
            ui.line(c, x, 0, x, H)
            x += 1
        ui.line(c, 0, HEADER_H, total, HEADER_H)
        # rows
        y = HEADER_H + 1 - self.top_row
        any_rec_multi = self.app.seq.opts.multitrack
        for i, t in enumerate(song.tracks):
            h = t.height
            if y + h < HEADER_H:
                y += h
                continue
            if y > H:
                break
            sel = t is self.cur_track
            fg = '#ffffff' if sel else ROW_COLOURS.get(t.kind, '#000000')
            for cid, x0, w in self.col_x:
                key = COLUMNS[cid][2]
                if key in ('rec', 'mute', 'solo'):
                    self._draw_button_cell(c, t, key, x0, y, w, h)
                    continue
                if key == 'monitor':
                    lvl = self.monitor.get(i, 0)
                    if lvl:
                        c.create_rectangle(s(x0 + 2), s(y + 2), s(x0 + 2 + (w - 4) * lvl / 127), s(y + h - 2),
                                           fill='#ff0000', outline='')
                    continue
                if sel:
                    c.create_rectangle(s(x0), s(y), s(x0 + w), s(y + h), fill='#404040', outline='')
                txt, anchor = self._cell_text(t, key)
                if txt == '':
                    continue
                tx = x0 + 2 if anchor == 'w' else x0 + w - 1
                ui.text(c, tx, y + h // 2, ui.clip_text(txt, w - 2), 'system', fill=fg, anchor=anchor)
            y += h
        self._update_vbar()

    def _draw_button_cell(self, c, t, key, x0, y, w, h):
        if t.kind == CHORD and key == 'rec':
            return
        on = bool(getattr(t, key))
        name = {'rec': ('REC_BUT', 'REC_PRESSED'), 'mute': ('MUTE_BUT', 'MUTE_PRESSED'),
                'solo': ('MUTE_BUT', 'MUTE_PRESSED')}[key][1 if on else 0]
        img = self.app.images.get(name)
        ui.image(c, x0 + 1, y + max(0, (h - 12) // 2) if h > 13 else y, img)

    def _cell_text(self, t, key):
        if key == 'name':
            return t.name, 'w'
        if t.kind == CHORD and key not in ('channel', 'velocity', 'transpose', 'time', 'port'):
            return '', 'e'
        if key == 'patch':
            return self.patch_name(t), 'w'
        if key == 'prog':
            if t.kind != MIDI:
                return '', 'e'
            if t.prog < 0:
                return 'OFF', 'w'
            return str(t.prog + (1 if self.app.settings['prefs'].get('number_from_1') else 0)), 'e'
        if key == 'bank':
            if t.kind != MIDI:
                return '', 'e'
            return ('OFF', 'w') if t.bank < 0 else (str(t.bank), 'e')
        if key == 'channel':
            return str(t.channel), 'e'
        if key == 'port':
            return chr(65 + max(0, t.port)), 'e'
        if key == 'fx_type':
            return (FX_NAMES[t.fx_type % 4] if t.kind == AUDIO else ''), 'w'
        if key == 'pan':
            return ('OFF', 'e') if t.pan == PAN_OFF else (str(t.pan), 'e')
        if key in ('volume', 'reverb', 'chorus'):
            v = getattr(t, key)
            return ('OFF', 'e') if v < 0 else (str(v), 'e')
        if key in ('velocity', 'transpose', 'time'):
            return str(getattr(t, key)), 'e'
        return '', 'e'

    # ------------------------------------------------------------------ track list mouse
    def _col_hit(self, ev):
        x, y = ev.x / ui.S, ev.y / ui.S
        if y < HEADER_H:
            return 'header', None, None
        _i, t = self.track_at_y(y - HEADER_H - 1 + self.top_row)
        for cid, x0, w in getattr(self, 'col_x', []):
            if x0 <= x < x0 + w:
                return 'cell', t, COLUMNS[cid][2]
        return None, t, None

    def select_track(self, t):
        for x in self.app.song.tracks:
            x.selected = x is t
        self.cur_track = t
        self.draw_columns()
        self.app.song_changed('select') if False else None
        for w in self.app.client.children_:
            if hasattr(w, 'track_selected'):
                w.track_selected(t)

    def _col_press(self, ev, button):
        kind, t, key = self._col_hit(ev)
        if kind == 'header':
            from . import dialogs
            dialogs.run(self.app, 'TRACK_COLUMN_DLG')
            return
        if t is None:
            return
        if key in ('rec', 'mute', 'solo'):
            if button == 1:
                self._toggle_button(t, key)
            return
        if key == 'name':
            if button == 1:
                self.select_track(t)
                self.drag = ('track', t, ev.y)
            return
        if key == 'port' and button == 1 and ui.is_ctrl(ev):
            for x in self.app.song.tracks:
                x.port = t.port
            self.draw_columns()
            return
        if key == 'port' and button == 1:
            names = self.app.port_names()
            PopupMenu.show(self, [(n, lambda i=i: self._set_port(t, i)) for i, n in enumerate(names)],
                           ev.x_root, ev.y_root)
            return
        if key == 'patch':
            self.select_track(t)
            return
        if key in ('prog', 'bank', 'channel', 'volume', 'pan', 'reverb', 'chorus', 'velocity', 'transpose',
                   'time', 'fx_type'):
            self.select_track(t)
            self.app.checkpoint()
            self.rep.start(ev, lambda d, big: self._adjust(t, key, d, big), button)

    def _set_port(self, t, i):
        t.port = i
        self.draw_columns()

    def _col_release(self, ev, button):
        self.rep.stop(button)
        if self.drag and self.drag[0] == 'track':
            self.drag = None

    def _col_drag(self, ev):
        if not self.drag or self.drag[0] != 'track':
            return
        _k, t, _y0 = self.drag
        _i, over = self.track_at_y(ev.y / ui.S - HEADER_H - 1 + self.top_row)
        tracks = self.app.song.tracks
        if over is not None and over is not t:
            tracks.remove(t)
            tracks.insert(tracks.index(over) + (1 if self.track_at_y(ev.y / ui.S - HEADER_H - 1 + self.top_row)[0] > tracks.index(over) else 0), t)
            self.app.song.modified = True
            self.draw_columns()
            self.redraw()

    def _col_double(self, ev):
        kind, t, key = self._col_hit(ev)
        if t is not None and key in ('name', 'patch'):
            from . import commands
            self.select_track(t)
            if key == 'patch' and t.kind == MIDI:
                from . import dialogs
                r = dialogs.run(self.app, 'PATCH_DLG', select=True, port=t.port, channel=t.channel or 1,
                                prog=max(0, t.prog), bank=max(0, t.bank))
                if r:
                    self.app.checkpoint()
                    t.prog, t.bank = r
                    self.app.send_track_settings(t)
                    self.app.song_changed('tracks')
            else:
                commands.track_settings(self.app)

    def _toggle_button(self, t, key):
        song = self.app.song
        if key == 'rec':
            if t.kind == CHORD:
                return
            new = 0 if t.rec else 1
            if new and not self.app.seq.opts.multitrack:
                for x in song.tracks:
                    x.rec = 0
            t.rec = new
        elif key == 'mute':
            t.mute = 0 if t.mute else 1
        elif key == 'solo':
            self._solo(t)
        song.modified = True
        self.draw_columns()
        self.app.song_changed('mixer')

    def _solo(self, t):
        """Solo with the mute-memory behaviour described in the help (Track Buttons)."""
        song = self.app.song
        if t.solo:
            t.solo = 0
            saved = getattr(self, '_solo_saved', None)
            if saved:
                for x, m in saved.items():
                    if x in song.tracks:
                        x.mute = m
            return
        for x in song.tracks:
            x.solo = 0
        prev = getattr(self, '_solo_last', None)
        if prev is not t:
            self._solo_saved = {x: x.mute for x in song.tracks}
        self._solo_last = t
        t.solo = 1

    def _adjust(self, t, key, d, big):
        lim = {'prog': (-1, 127), 'bank': (-1, 16383), 'channel': (0, 16), 'volume': (-1, 127),
               'pan': (PAN_OFF, 63), 'reverb': (-1, 127), 'chorus': (-1, 127), 'velocity': (-127, 127),
               'transpose': (-127, 127), 'time': (-9999, 9999), 'fx_type': (0, 3)}[key]
        v = getattr(t, key) + d
        v = max(lim[0], min(lim[1], v))
        setattr(t, key, v)
        self.app.send_track_settings(t, key)
        self.draw_columns()
        if key in ('volume', 'pan', 'reverb', 'chorus'):
            for w in self.app.client.children_:
                if hasattr(w, 'refresh') and w is not self and getattr(w, 'kind', '') == 'mixer':
                    w.refresh('mixer')

    def _div_press(self, ev):
        self._div_x0 = ev.x_root
        self._div_start = self.divider

    def _div_drag(self, ev):
        total = sum(w + 1 for _c, w in self.column_widths())
        self.divider = max(-total + 20, self._div_start + (ev.x_root - self._div_x0) // ui.S)
        self.draw_columns()

    # ------------------------------------------------------------------ pattern display
    def redraw(self):
        if not self.winfo_exists():
            return
        self.draw_timeline()
        self.draw_patterns()
        self._update_hbar()

    def draw_timeline(self):
        c = self.timeline
        c.delete('all')
        W = c.winfo_width() // ui.S
        tm = self.app.tmap
        t0 = self.x0_tick
        t1 = self.x_to_tick(W)
        last_x = -100
        for tick, bar, tpbeat, beats in tm.bar_lines(t0, t1):
            x = self.tick_to_x(tick)
            ui.line(c, x, HEADER_H - 4 if (bar - 1) % 4 else 0, x, HEADER_H)
            if x - last_x >= 18 or (bar - 1) % 4 == 0 and x - last_x >= 12:
                if x - last_x >= 18 or True:
                    ui.text(c, x + 2, 1, str(bar), 'small')
                    last_x = x
            if tpbeat / self.tpp >= 4:
                for b in range(1, beats):
                    bx = self.tick_to_x(tick + b * tpbeat)
                    ui.line(c, bx, HEADER_H - 2, bx, HEADER_H)
        ui.line(c, 0, HEADER_H, W, HEADER_H)
        song = self.app.song
        for tick, img in ((song.left, 'LOC_L'), (song.right, 'LOC_R')):
            x = self.tick_to_x(tick)
            if -10 < x < W:
                ui.image(c, x, 0, self.app.images.get(img))
        x = self.tick_to_x(self.app.seq.position)
        if 0 <= x < W:
            c.create_polygon(s(x - 4), s(HEADER_H - 5), s(x + 4), s(HEADER_H - 5), s(x), s(HEADER_H),
                             fill=ui.SHADOW, outline=ui.DARK)

    def draw_patterns(self):
        c = self.pat
        c.delete('all')
        W, H = c.winfo_width() // ui.S, c.winfo_height() // ui.S
        if self.bg_img is not None:
            iw, ih = self.bg_img.width(), self.bg_img.height()
            for y in range(0, s(H), ih):
                for x in range(0, s(W), iw):
                    c.create_image(x, y, image=self.bg_img, anchor='nw')
        tm = self.app.tmap
        song = self.app.song
        # left/right locator lines
        for tick in (song.left, song.right):
            x = self.tick_to_x(tick)
            if 0 <= x < W:
                ui.line(c, x, 0, x, H, fill=ui.SHADOW)
        y = -self.top_row
        for t in song.tracks:
            h = t.height
            if y > H:
                break
            if y + h >= 0:
                for p in t.patterns:
                    self._draw_pattern(c, t, p, y, h, W)
            y += h
        self.draw_cursor()

    def _draw_pattern(self, c, t, p, y, h, W):
        x0 = self.tick_to_x(p.start)
        x1 = self.tick_to_x(p.end)
        if x1 < 0 or x0 > W:
            return
        sel = p.selected
        if p.mute:
            fill = ui.FACE
        elif sel:
            fill = '#000000'
        else:
            fill = '#ffffff'
        fg = '#ffffff' if sel and not p.mute else {MIDI: '#000000', CHORD: '#0000ff', AUDIO: '#800000'}[t.kind]
        x0i, x1i = int(round(x0)), max(int(round(x0)) + 2, int(round(x1)))
        c.create_rectangle(s(x0i), s(y), s(x1i), s(y + h - 1), fill=fill, outline='')
        dash = (2, 2) if p.parent is not None else None
        c.create_rectangle(s(x0i), s(y), s(x1i), s(y + h - 1), outline='#000000', width=ui.S, dash=dash)
        if not p.mute:
            # shadow on the right/bottom like the original
            ui.line(c, x0i + 1, y + h - 1, x1i + 1, y + h - 1, x1i + 1, y + 1)
        name = p.name
        if t.kind == CHORD:
            from .chords import ROOTS, type_names
            root, ct = p.source.chord()
            name = ROOTS[root % 12] + ('' if ct == 0 else type_names()[ct % 12].strip())
        elif t.kind == AUDIO:
            if h > 12:
                ui.image(c, max(x0i + 1, 0), y + 1, self.app.images.get('IB_AUDIO'))
        if x1i - x0i > 6:
            ui.text(c, x0i + 1, y, ui.clip_text(name, x1i - x0i - 2, 'small'), 'small', fill=fg)

    def draw_cursor(self):
        c = self.pat
        c.delete('cursor')
        x = self.tick_to_x(self.app.seq.position)
        W, H = c.winfo_width() // ui.S, c.winfo_height() // ui.S
        if 0 <= x < W:
            c.create_line(s(x), 0, s(x), s(H), fill='#000000', width=ui.S, dash=(1, 1), tags='cursor')

    def set_position(self, tick, follow=False):
        W = self.pat.winfo_width() // ui.S
        x = self.tick_to_x(tick)
        if follow and (x < 0 or x > W - 10):
            self.x0_tick = max(0, self.app.tmap.bar_tick(tick))
            self.redraw()
            return
        self.draw_cursor()
        self.timeline.delete('pos')
        self.draw_timeline()

    # ------------------------------------------------------------------ scrolling
    def total_height(self):
        return sum(t.height for t in self.app.song.tracks)

    def _update_vbar(self):
        H = max(1, self.pat.winfo_height() // ui.S)
        tot = max(1, self.total_height())
        a = self.top_row / tot
        self.vbar.set(a, min(1.0, a + H / tot))

    def _update_hbar(self):
        W = max(1, self.pat.winfo_width() // ui.S)
        end = max(self.app.song.end_tick(), self.x0_tick + W * self.tpp) + 16 * self.app.song.timebase * 4
        a = self.x0_tick / end
        self.hbar.set(a, min(1.0, a + W * self.tpp / end))

    def _vscroll(self, *args):
        H = self.pat.winfo_height() // ui.S
        tot = self.total_height()
        if args[0] == 'moveto':
            self.top_row = int(float(args[1]) * tot)
        elif args[0] == 'scroll':
            n = int(args[1])
            step = 13 if args[2] == 'units' else H
            self.top_row += n * step
        self.top_row = max(0, min(self.top_row, max(0, tot - H)))
        self.draw_columns()
        self.draw_patterns()

    def _hscroll(self, *args):
        W = self.pat.winfo_width() // ui.S
        end = max(self.app.song.end_tick(), self.x0_tick + W * self.tpp) + 16 * self.app.song.timebase * 4
        if args[0] == 'moveto':
            self.x0_tick = int(float(args[1]) * end)
        elif args[0] == 'scroll':
            n = int(args[1])
            step = self.app.tmap.sig_at(self.x0_tick)[2] if args[2] == 'units' else W * self.tpp
            self.x0_tick += n * step
        self.x0_tick = max(0, self.x0_tick)
        self.redraw()

    def _wheel(self, ev):
        self._vscroll('scroll', -1 if ev.delta > 0 else 1, 'units')

    # ------------------------------------------------------------------ timeline mouse
    def _tl_click(self, ev, button):
        tick = self.x_to_tick(ev.x / ui.S)
        tick = self.snap_tick(tick)
        song = self.app.song
        if ui.is_ctrl(ev):
            self.app.locate(tick)
            return
        if button == 1:
            song.left = tick
        else:
            song.right = tick
        song.modified = True
        self.app.song_changed('locators')

    # ------------------------------------------------------------------ snapping
    def snap_ticks(self, kind=MIDI, at=0):
        tm = self.app.tmap
        tb = self.app.song.timebase
        if kind == CHORD:
            v = int(self.chord_snap.value)
            return tb * 4 // v
        v = self.snap.value.strip()
        if v == 'Bar':
            return None
        if v == 'Off':
            return 1
        return tb * 4 // int(v)

    def snap_tick(self, tick, kind=MIDI):
        tick = max(0, tick)
        st = self.snap_ticks(kind)
        if st is None:
            tm = self.app.tmap
            b = tm.bar_tick(tick)
            nb = b + tm.sig_at(b)[2]
            return b if tick - b < nb - tick else nb
        return int(round(tick / st)) * st

    # ------------------------------------------------------------------ pattern mouse
    def _hit_pattern(self, ev):
        x, y = ev.x / ui.S, ev.y / ui.S
        _i, t = self.track_at_y(y + self.top_row)
        if t is None:
            return None, None
        for p in reversed(t.patterns):
            if self.tick_to_x(p.start) <= x < self.tick_to_x(p.end) + 1:
                return t, p
        return t, None

    def _tool_changed(self, key):
        tools.set_cursor(self.pat, self.tool.cursor_name())

    def _pat_press(self, ev):
        t, p = self._hit_pattern(ev)
        if t is not None and t is not self.cur_track:
            self.select_track(t)
        tool = self.tool.current
        app = self.app
        tick = self.x_to_tick(ev.x / ui.S)
        if tool == 'arrow':
            if p is None:
                if not ui.is_shift(ev):
                    for q in app.song.all_patterns():
                        q.selected = False
                self.drag = ('lasso', ev.x, ev.y)
                self.draw_patterns()
                self._layout_chord_row()
                return
            if ui.is_shift(ev):
                p.selected = not p.selected
            elif not p.selected:
                for q in app.song.all_patterns():
                    q.selected = False
                p.selected = True
            self.drag = ('move', ev.x, ev.y, p, ui.is_ctrl(ev), None)
            self.draw_patterns()
            self._layout_chord_row()
            for w in app.client.children_:
                if hasattr(w, 'pattern_selected'):
                    w.pattern_selected(p)
        elif tool == 'pencil':
            if t is None:
                return
            app.checkpoint()
            if p is None:
                st = self.snap_tick(tick, t.kind)
                tm = app.tmap
                np = Pattern(name=t.name, start=st, end=st + (tm.sig_at(st)[2] if t.kind != CHORD
                                                              else self.snap_ticks(CHORD) * 4))
                if t.kind == CHORD:
                    np.set_chord(0, 0)
                    for i in range(6):
                        np.set_chord_mute(i, 1)
                np.track = t
                t.patterns.append(np)
                t.patterns.sort(key=lambda q: q.start)
                self.drag = ('size', np, 'end', np.start)
            else:
                mid = (p.start + p.end) / 2
                self.drag = ('size', p, 'start' if tick < mid else 'end', None)
            self.draw_patterns()
        elif tool == 'eraser' and p is not None:
            if self._editing([p]):
                messagebox.showinfo('Sound Studio Gold', resources.string(36), parent=app)
                return
            app.checkpoint()
            victims = [q for q in app.song.all_patterns() if q.selected] if p.selected else [p]
            self._remove_patterns(victims)
            app.song_changed('patterns')
        elif tool == 'mute' and p is not None:
            app.checkpoint()
            p.mute = 0 if p.mute else 1
            self.draw_patterns()
        elif tool == 'knife' and p is not None:
            st = self.snap_tick(tick, t.kind)
            if p.start < st < p.end:
                app.checkpoint()
                self.slice_pattern(p, st)
                app.song_changed('patterns')
        elif tool == 'glue' and p is not None:
            app.checkpoint()
            self.glue(p)
            app.song_changed('patterns')

    def _pat_drag(self, ev):
        d = self.drag
        if not d:
            return
        if d[0] == 'lasso':
            c = self.pat
            c.delete('lasso')
            c.create_rectangle(d[1], d[2], ev.x, ev.y, dash=(2, 2), outline='black', tags='lasso')
        elif d[0] == 'move':
            dx = (ev.x - d[1]) / ui.S
            p = d[3]
            dt = self.snap_tick(p.start + int(dx * self.tpp), p.track.kind) - p.start
            _i, t_over = self.track_at_y(ev.y / ui.S + self.top_row)
            self.drag = d[:5] + ((dt, t_over),)
            self._preview_move(dt, p, t_over)
        elif d[0] == 'size':
            p, edge = d[1], d[2]
            tick = self.snap_tick(self.x_to_tick(ev.x / ui.S), p.track.kind)
            if edge == 'end':
                p.end = max(p.start + 1, tick)
            else:
                p.start = min(p.end - 1, tick)
            self.draw_patterns()

    def _preview_move(self, dt, p, t_over):
        c = self.pat
        c.delete('ghost')
        song = self.app.song
        sel = [q for q in song.all_patterns() if q.selected]
        dtrack = (song.tracks.index(t_over) - song.tracks.index(p.track)) if t_over in song.tracks else 0
        for q in sel:
            ti = song.tracks.index(q.track) + dtrack
            if not 0 <= ti < len(song.tracks):
                continue
            y = self.row_y(ti) - self.top_row
            h = song.tracks[ti].height
            x0 = self.tick_to_x(q.start + dt)
            x1 = self.tick_to_x(q.end + dt)
            c.create_rectangle(s(x0), s(y), s(x1), s(y + h - 1), outline='#000000', dash=(1, 1), width=ui.S,
                               tags='ghost')

    def _pat_release(self, ev):
        d = self.drag
        self.drag = None
        if not d:
            return
        app = self.app
        song = app.song
        if d[0] == 'lasso':
            self.pat.delete('lasso')
            x0, x1 = sorted((d[1] / ui.S, ev.x / ui.S))
            y0, y1 = sorted((d[2] / ui.S + self.top_row, ev.y / ui.S + self.top_row))
            y = 0
            for t in song.tracks:
                if y + t.height > y0 and y < y1:
                    for p in t.patterns:
                        if self.tick_to_x(p.end) > x0 and self.tick_to_x(p.start) < x1:
                            p.selected = True
                y += t.height
            self.draw_patterns()
            self._layout_chord_row()
        elif d[0] == 'move':
            self.pat.delete('ghost')
            if d[5] is None:
                return
            dt, t_over = d[5]
            p, copy = d[3], d[4]
            sel = [q for q in song.all_patterns() if q.selected]
            dtrack = (song.tracks.index(t_over) - song.tracks.index(p.track)) if t_over in song.tracks else 0
            if dt == 0 and dtrack == 0:
                return
            app.checkpoint()
            moved = []
            for q in sel:
                ti = song.tracks.index(q.track) + dtrack
                if not 0 <= ti < len(song.tracks):
                    continue
                nt = song.tracks[ti]
                if (nt.kind == AUDIO) != (q.track.kind == AUDIO) or (nt.kind == CHORD) != (q.track.kind == CHORD):
                    continue
                if copy:
                    n = self._copy_pattern(q, app.settings['prefs'].get('copy_as_parents'))
                    q.selected = False
                else:
                    n = q
                    q.track.patterns.remove(q)
                n.start += dt
                n.end += dt
                if n.start < 0:
                    n.end -= n.start
                    n.start = 0
                n.track = nt
                n.selected = True
                nt.patterns.append(n)
                nt.patterns.sort(key=lambda x: x.start)
                moved.append(n)
            app.song_changed('patterns')
        elif d[0] == 'size':
            p = d[1]
            if p.end <= p.start:
                p.end = p.start + 1
            app.song_changed('patterns')

    def _pat_double(self, ev):
        t, p = self._hit_pattern(ev)
        if p is None:
            return
        from . import commands
        for q in self.app.song.all_patterns():
            q.selected = q is p
        if t.kind == CHORD:
            from .chords import ROOTS, type_names
            menu = [(n, lambda i=i: self._set_chord(p, root=i)) for i, n in enumerate(ROOTS)]
            PopupMenu.show(self, menu, ev.x_root, ev.y_root)
            self.after(10, lambda: PopupMenu.show(self, [(n, lambda i=i: self._set_chord(p, ctype=i))
                                                        for i, n in enumerate(type_names())],
                                                  ev.x_root, ev.y_root))
            return
        if t.kind == AUDIO:
            return
        pref = self.app.settings['prefs'].get('dbl_midi', 'Piano Roll')
        kind = {'Piano Roll': 'proll', 'Event': 'event', 'Score': 'score', 'Drum': 'drum'}.get(pref)
        if kind:
            commands.open_editor(self.app, kind)

    # ------------------------------------------------------------------ misc
    def midi_in(self, data):
        if data[0] >= 0xF0 or (data[0] & 0xF0) != 0x90 or len(data) < 3:
            return
        ch = (data[0] & 0x0F) + 1
        for i, t in enumerate(self.app.song.tracks):
            if t.rec or (self.app.seq.opts.multitrack and t.channel == ch):
                self.monitor[i] = data[2]
        self.draw_columns()
        self.after(150, self._decay)

    def _decay(self):
        if self.monitor:
            self.monitor.clear()
            self.draw_columns()

    def key(self, ev):
        if ev.keysym in ('Up', 'Down'):
            tr = self.app.song.tracks
            if self.cur_track in tr:
                i = tr.index(self.cur_track) + (1 if ev.keysym == 'Down' else -1)
                if 0 <= i < len(tr):
                    self.select_track(tr[i])
            return True
        return False

    def can_close(self):
        return True
