"""Event window (MDIEVENTWNDPROC): the event list."""
import tkinter as tk

from .. import ui, resources
from ..ui import s
from ..widgets import Toolbar
from ..song import Event
from ..procedures import QUANT_VALUES, note_ticks
from .common import EditorWindow, TYPE_COLOURS, controller_label, note_name

ROW = 13
FILTERS = [('Note', 0x90), ('Aftertouch', 0xA0), ('Controller', 0xB0), ('Program', 0xC0),
           ('Pressure', 0xD0), ('Bend', 0xE0), ('Sysex', 0xF0)]
# column x positions (relative to the list) as in the original 1:1 screenshots
COLS = [('', 0, 12), ('Position', 13, 71), ('Ch', 85, 17), ('Event', 103, 131), ('Key', 235, 29),
        ('Vel', 265, 23), ('Length', 289, 44)]
HEADS = {0x90: ('Key', 'Vel', 'Length'), 0xA0: ('Key', 'Val', ''), 0xB0: ('Ctrl', 'Val', ''),
         0xC0: ('Prog', '', ''), 0xD0: ('Val', '', ''), 0xE0: ('LSB', 'MSB', ''), 0xF0: ('', '', '')}


def insert_types():
    t = ['Note', 'Aftertouch'] + ['Controller %d' % i if False else controller_label(i) for i in range(128)]
    t += ['Program', 'Pressure', 'Bend', 'Vanilla Sysex'] + [n for n, _h in resources.tables()['xg_sysex']]
    return t


def sysex_name(data):
    for n, h in resources.tables()['xg_sysex']:
        b = bytes.fromhex(h)
        if len(b) == len(data) and data[:len(b) - 2] == b[:len(b) - 2]:
            return n
    if data[1:2] == b'\x7e':
        return 'Universal NRT'
    if data[1:2] == b'\x7f':
        return 'Universal RT'
    return 'Vanilla Sysex'


class EventWindow(EditorWindow):
    title_prefix = 'Event'
    icon_name = 'IC_EVENT'
    kind = 'event'

    def __init__(self, client, app, pattern):
        self.top_row = 0
        self.filters = {k: k in (0x90, 0xC0, 0xE0) for _n, k in FILTERS}
        self.anchor = None
        self.drag_sel = None
        super().__init__(client, app, pattern)
        self._build()
        self.move_to(0, 0, 346, self.client.winfo_height() // ui.S)

    def _build(self):
        b = self.body
        tb = Toolbar(b, self.app)
        tb.pack(side='top', fill='x')
        self.add_toggles(tb)
        self.add_close_recall(tb)
        tb.add_button('BUT_INSERT', self.insert_event, pressed='BUT_INSERT_PR')
        tb.add_button('BUT_DELETE', self.edit_clear, pressed='BUT_DELETE_PR')
        tb.add_button('BUT_CLONE', self.clone, pressed='BUT_CLONE_PR')
        tb2 = Toolbar(b, self.app)
        tb2.pack(side='top', fill='x')
        tb2.add_label('Note Length', 64)
        self.notelen = tb2.add_combo(QUANT_VALUES[1:], 46, '16', listw=50)
        tb2.add_label('Insert Type', 58)
        self.instype = tb2.add_combo(insert_types(), 158, 'Note', rows=16, cmd=lambda *_a: self.redraw())
        self.fbar = tk.Canvas(b, height=s(14), bg=ui.FACE, highlightthickness=0, bd=0)
        self.fbar.pack(side='top', fill='x')
        self.fbar.bind('<Button-1>', self._filter_click)
        self.head = tk.Canvas(b, height=s(ROW + 1), bg=ui.FACE, highlightthickness=0, bd=0)
        self.head.pack(side='top', fill='x')
        fr = tk.Frame(b, bg=ui.FACE)
        fr.pack(side='top', fill='both', expand=True)
        self.vbar = tk.Scrollbar(fr, orient='vertical', command=self._vscroll)
        self.list = tk.Canvas(fr, bg=ui.FACE, highlightthickness=0, bd=0)
        self.list.pack(side='left', fill='both', expand=True)
        self.list.bind('<Configure>', lambda e: self.redraw())
        self.list.bind('<ButtonPress-1>', lambda e: self._press(e, 1))
        self.list.bind('<ButtonRelease-1>', lambda e: self._release(e, 1))
        self.list.bind('<B1-Motion>', self._drag)
        self.list.bind('<Double-Button-1>', self._double)
        ui.bind_right(self.list, 'ButtonPress', lambda e: self._press(e, 3))
        ui.bind_right(self.list, 'ButtonRelease', lambda e: self._release(e, 3))
        self.list.bind('<MouseWheel>', lambda e: self._vscroll('scroll', -1 if e.delta > 0 else 1, 'units'))
        self.list.bind('<Button-4>', lambda e: self._vscroll('scroll', -1, 'units'))
        self.list.bind('<Button-5>', lambda e: self._vscroll('scroll', 1, 'units'))
        self.rep = ui.Repeater(self.list)

    def step_length(self):
        return note_ticks(self.notelen.value, self.app.song.timebase)

    # ---- data
    def shown(self):
        out = []
        for e in self.events:
            k = e.status if e.status >= 0xF0 else e.status & 0xF0
            if k < 0x80:
                k = 0xF0
            if self.filters.get(k, True):
                out.append(e)
        return out

    def insert_kind(self):
        v = self.instype.value
        if v == 'Note':
            return 0x90
        if v == 'Aftertouch':
            return 0xA0
        if v == 'Program':
            return 0xC0
        if v == 'Pressure':
            return 0xD0
        if v == 'Bend':
            return 0xE0
        types = insert_types()
        if v in types and 2 <= types.index(v) < 130:
            return 0xB0
        return 0xF0

    def _update_vbar(self, n, H):
        need = n > H
        if need != getattr(self, '_vbar_shown', False):
            self._vbar_shown = need
            if need:
                self.vbar.pack(side='right', fill='y', before=self.list)
            else:
                self.vbar.pack_forget()

    def _vscroll(self, *a):
        n = len(self.shown())
        H = self.list.winfo_height() // ui.S // ROW
        if a[0] == 'moveto':
            self.top_row = int(float(a[1]) * n)
        else:
            self.top_row += int(a[1]) * (1 if a[2] == 'units' else H)
        self.top_row = max(0, min(self.top_row, max(0, n - H)))
        self.redraw()

    # ---- drawing
    def redraw(self):
        if not self.winfo_exists():
            return
        self._draw_filters()
        self._draw_head()
        self._draw_list()
        self.update_info()

    def update_info(self):
        pass

    def _draw_filters(self):
        c = self.fbar
        c.delete('all')
        x = 0
        for name, k in FILTERS:
            w = int(ui.text_width(name, 'smallbold')) + 5
            ui.raised(c, x, 0, x + w, 14, outer=False)
            ui.text(c, x + 2, 7, name, 'smallbold', fill=ui.TEXT if self.filters[k] else ui.GREYTEXT, anchor='w')
            x += w
        self.filter_x = []
        x = 0
        for name, k in FILTERS:
            w = int(ui.text_width(name, 'smallbold')) + 5
            self.filter_x.append((x, x + w, k))
            x += w

    def _filter_click(self, ev):
        x = ev.x / ui.S
        for x0, x1, k in getattr(self, 'filter_x', []):
            if x0 <= x < x1:
                self.filters[k] = not self.filters[k]
                self.top_row = 0
                self.redraw()

    def _draw_head(self):
        c = self.head
        c.delete('all')
        W = c.winfo_width() // ui.S
        kind = self.insert_kind()
        heads = HEADS.get(kind, ('', '', ''))
        for i, (name, x, w) in enumerate(COLS):
            if i >= 4:
                name = heads[i - 4]
            ui.text(c, x + w // 2, ROW // 2 + 1, name, 'small', anchor='center')
            if i:
                ui.line(c, x - 1, 0, x - 1, ROW + 1)
        ui.line(c, 0, ROW, W, ROW)

    def _row_values(self, e):
        tm = self.app.tmap
        pos = tm.fmt(self.pattern.start + e.tick)
        st = e.status
        hi = st & 0xF0 if st < 0xF0 else st
        ch = str(e.channel + 1) if st < 0xF0 else ''
        if st < 0x80:
            return pos, '', 'Unknown', '', '', ''
        if hi == 0x90:
            return pos, ch, 'Note', note_name(e.d1), str(e.d2), str(e.length)
        if hi == 0xA0:
            return pos, ch, 'Aftertouch', note_name(e.d1), str(e.d2), ''
        if hi == 0xB0:
            return pos, ch, controller_label(e.d1), str(e.d1), str(e.d2), ''
        if hi == 0xC0:
            nm = self.app.patches.name(max(0, self.track.port), e.channel + 1, e.d1, -1)
            return pos, ch, 'Program %s' % (nm.split(' ', 1)[1] if ' ' in nm else nm), str(
                e.d1 + (1 if self.app.settings['prefs'].get('number_from_1') else 0)), '', ''
        if hi == 0xD0:
            return pos, ch, 'Pressure', str(e.d1), '', ''
        if hi == 0xE0:
            return pos, ch, 'Bend', str(e.d1), str(e.d2), ''
        if st == 0xF0:
            return pos, '', 'SysEx ' + sysex_name(e.data), '', '', ''
        return pos, '', '', '', '', ''

    def _draw_list(self):
        c = self.list
        c.delete('all')
        W, H = c.winfo_width() // ui.S, c.winfo_height() // ui.S
        for i, (_n, x, w) in enumerate(COLS):
            if i:
                ui.line(c, x - 1, 0, x - 1, H)
        rows = self.shown()
        tm = self.app.tmap
        nvis = H // ROW + 1
        y = 0
        prev_bar = None
        pos = self.app.seq.position - self.pattern.start
        marker_done = False
        for idx in range(self.top_row, min(len(rows), self.top_row + nvis)):
            e = rows[idx]
            vals = self._row_values(e)
            col = TYPE_COLOURS.get(e.status & 0xF0 if e.status < 0xF0 else 0xF0, '#000000')
            if e.is_note() and e.length == 0:
                c.create_rectangle(s(COLS[1][1]), s(y), s(W), s(y + ROW), fill='#ffff00', outline='')
            fg = col
            if e.selected:
                c.create_rectangle(s(COLS[3][1]), s(y), s(COLS[3][1] + COLS[3][2]), s(y + ROW),
                                   fill='#000000', outline='')
            for i, v in enumerate(vals):
                _n, x, w = COLS[i + 1]
                if not v:
                    continue
                f = '#ffffff' if (e.selected and i == 2) else fg
                if i == 2:
                    ui.text(c, x + 1, y + ROW // 2, ui.clip_text(v, w - 2), 'system', fill=f, anchor='w')
                else:
                    ui.text(c, x + w - 1, y + ROW // 2, v, 'system', fill=f, anchor='e')
            bar = tm.to_bbt(self.pattern.start + e.tick)[0]
            nxt = rows[idx + 1] if idx + 1 < len(rows) else None
            if nxt is not None and tm.to_bbt(self.pattern.start + nxt.tick)[0] != bar:
                ui.line(c, COLS[1][1], y + ROW - 1, W, y + ROW - 1)
            if not marker_done and e.tick >= pos and self.app.seq.playing:
                c.create_polygon(s(2), s(y + 2), s(8), s(y + ROW // 2), s(2), s(y + ROW - 2), fill='#000000')
                marker_done = True
            y += ROW
        if not self.app.seq.playing and rows and self.top_row == 0:
            c.create_polygon(s(2), s(2), s(8), s(ROW // 2), s(2), s(ROW - 2), fill='#000000')
        self._update_vbar(len(rows), nvis)
        n = max(1, len(rows))
        self.vbar.set(self.top_row / n, min(1, (self.top_row + nvis) / n))

    def set_position(self, tick, follow=False):
        rows = self.shown()
        rel = tick - self.pattern.start
        idx = next((i for i, e in enumerate(rows) if e.tick >= rel), None)
        if follow:
            H = self.list.winfo_height() // ui.S // ROW
            if idx is not None and not self.top_row <= idx < self.top_row + H - 1:
                self.top_row = max(0, idx - 1)
        state = (idx, self.top_row, self.app.seq.playing)
        if self.app.seq.playing and state != getattr(self, '_pos_state', None):
            self._draw_list()                  # only when the marked row moves
        self._pos_state = state

    # ---- mouse
    def _hit(self, ev):
        x, y = ev.x / ui.S, ev.y / ui.S
        idx = self.top_row + int(y // ROW)
        rows = self.shown()
        if not 0 <= idx < len(rows):
            return None, None
        for i, (_n, cx, w) in enumerate(COLS):
            if cx <= x < cx + w:
                return rows[idx], i
        return rows[idx], None

    def _press(self, ev, button):
        e, col = self._hit(ev)
        if col == 0 or e is None:
            if ui.is_ctrl(ev) and e is not None:
                self.app.locate(self.pattern.start + e.tick)
            elif col == 0:
                self.deselect_all()
                self.redraw()
            return
        if col == 3:
            if button == 1:
                if ui.is_shift(ev):
                    e.selected = not e.selected
                else:
                    self.deselect_all()
                    e.selected = True
                    self.anchor = e
                    self.drag_sel = e
                self.play_event(e)
                self.redraw()
            return
        self.app.checkpoint()
        self.rep.start(ev, lambda d, big: self._adjust(e, col, d, big), button)

    def _release(self, ev, button):
        self.rep.stop(button)
        self.drag_sel = None

    def _drag(self, ev):
        if self.drag_sel is None:
            return
        e, _c = self._hit(ev)
        if e is None:
            return
        rows = self.shown()
        a, b = rows.index(self.drag_sel), rows.index(e)
        for i, r in enumerate(rows):
            r.selected = min(a, b) <= i <= max(a, b)
        self.redraw()

    def _double(self, ev):
        e, col = self._hit(ev)
        if e is not None and e.status == 0xF0 and col == 3:
            from .. import dialogs
            dialogs.run(self.app, 'SYSEX_DLG', event=e)

    def _adjust(self, e, col, d, big):
        tm = self.app.tmap
        hi = e.status & 0xF0 if e.status < 0xF0 else e.status
        if col == 1:
            if big:
                e.tick = max(0, e.tick + (1 if d > 0 else -1) * tm.sig_at(self.pattern.start + e.tick)[3])
            else:
                e.tick = max(0, e.tick + d)
            self.events.sort(key=lambda x: x.tick)
        elif col == 2 and e.status < 0xF0:
            e.status = (e.status & 0xF0) | max(0, min(15, e.channel + (1 if d > 0 else -1)))
        elif col == 4:
            if hi in (0x90, 0xA0):
                e.d1 = max(0, min(127, e.d1 + (12 if big else 1) * (1 if d > 0 else -1)))
                self.play_event(e)
            elif hi in (0xB0, 0xC0, 0xD0, 0xE0):
                e.d1 = max(0, min(127, e.d1 + d))
        elif col == 5 and hi in (0x90, 0xA0, 0xB0, 0xE0):
            e.d2 = max(1 if hi == 0x90 else 0, min(127, e.d2 + d))
        elif col == 6 and hi == 0x90:
            e.length = max(0, e.length + d)
        self.app.song.modified = True
        self.redraw()

    # ---- buttons
    def insert_event(self):
        t = self.instype.value
        pos = max(0, self.app.seq.position - self.pattern.start)
        if pos >= self.pattern.length:
            pos = 0
        ch = max(1, self.track.channel or 1) - 1
        types = insert_types()
        if t == 'Note':
            e = Event(pos, 0x90 | ch, 60, self.app.settings['prefs'].get('kbd_velocity', 100),
                      max(1, self.step_length()))
        elif t == 'Aftertouch':
            e = Event(pos, 0xA0 | ch, 60, 64)
        elif t == 'Program':
            e = Event(pos, 0xC0 | ch, 0)
        elif t == 'Pressure':
            e = Event(pos, 0xD0 | ch, 64)
        elif t == 'Bend':
            e = Event(pos, 0xE0 | ch, 0, 64)
        elif t == 'Vanilla Sysex':
            e = Event(pos, 0xF0, data=b'\xF0\xF7')
        elif t.startswith('XG '):
            h = dict(resources.tables()['xg_sysex'])[t]
            e = Event(pos, 0xF0, data=bytes.fromhex(h))
        else:
            cc = next((i for i in range(128) if controller_label(i) == t), 7)
            e = Event(pos, 0xB0 | ch, cc, 64)
        self.app.checkpoint()
        self.deselect_all()
        e.selected = True
        self.events.append(e)
        self.events.sort(key=lambda x: x.tick)
        self.app.song_changed('events')

    def clone(self):
        sel = self.selected()
        if not sel:
            return
        self.app.checkpoint()
        for e in sel:
            n = e.copy()
            e.selected = False
            n.selected = True
            self.events.insert(self.events.index(e) + 1, n)
        self.app.song_changed('events')
