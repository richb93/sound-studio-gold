"""Drum window (MDIDRUMWNDPROC): drum kit list and the hit grid."""
import tkinter as tk
from tkinter import messagebox

from .. import ui, tools, resources
from ..ui import s
from ..widgets import Toolbar, InfoLine, PopupMenu
from ..song import Event
from ..patches import Drum
from .common import EditorWindow, note_name

ROW = 13
TL_H = 13
GRID_VALUES = [' 1', ' 2', ' 4', ' 8', '16', '32', '64', ' 4T', ' 8T', '16T', '32T']
DRUM_COLUMNS = {651: ('Name', 96, 'name'), 652: ('Ch', 17, 'channel'), 653: ('Key', 28, 'key'),
                654: ('Vel', 21, 'velocity'), 655: ('Len', 23, 'length'), 656: ('Mute', 29, 'mute'),
                657: ('Solo', 29, 'solo'), 658: ('Info', 40, 'info')}
# hit colours: at/above the drum velocity, then each 10 lower (help: Drum Window)
HIT_COLOURS = ['#ff0000', '#ff00ff', '#0000ff', '#00ff00', '#008080', '#404040', '#808080', '#c0c0c0']
DRUM_TOOLS = [('arrow', 'CUR_ARROW_BM', ''), ('stick1', 'CUR_DRUM1_BM', 'CUR_DRUM1'),
              ('eraser', 'CUR_ERASER_BM', 'CUR_ERASER'), ('stick2', 'CUR_DRUM2_BM', 'CUR_DRUM2'),
              ('plus', 'CUR_DRUMPLUS_BM', 'CUR_DRUMPLUS'), ('minus', 'CUR_DRUMMINUS_BM', 'CUR_DRUMMINUS')]
PC_KEYS = ['grave', '1', '2', '3', '4', '5', '6', '7', '8', '9', '0', 'minus', 'equal', 'BackSpace', 'Tab']


class DrumWindow(EditorWindow):
    title_prefix = 'Drum'
    icon_name = 'IC_DRUM'
    kind = 'drum'

    def __init__(self, client, app, pattern):
        self.tpp = max(1, app.song.timebase // 32)
        self.x0 = 0
        self.top_row = 0
        self.cur_drum = 0
        self.drag = None
        self.divider = 0
        self.tool = tools.ToolSelector(app, DRUM_TOOLS, cols=3)
        super().__init__(client, app, pattern)
        self.tool.on_change = lambda k: tools.set_cursor(self.grid, self.tool.cursor_name())
        self._build()
        self.maximize()

    @property
    def kit(self):
        return self.app.drumkit

    def _build(self):
        b = self.body
        tb = Toolbar(b, self.app)
        tb.pack(side='top', fill='x')
        tb.add_button('MENU_BM', self.functions_menu, pressed='MENU_BM_PR')
        tb.add_button('ZOOMIN_BM', lambda: self.hzoom(-1))
        tb.add_button('ZOOMOUT_BM', lambda: self.hzoom(1))
        self.add_toggles(tb)
        self.add_close_recall(tb)
        tb.add_label('Grid', 22)
        self.grid_combo = tb.add_combo(GRID_VALUES, 46, '16', cmd=lambda v: self.redraw(), listw=50)
        self.tb = tb
        self.info = InfoLine(b, self.app, [('Position', 120), ('Chan', 60), ('Pitch', 70), ('Vel', 55),
                                           ('Length', 85), ('Kit', 220)])
        self.info.fields[5]['align'] = 'w'
        self.info.pack(side='top', fill='x')
        body = tk.Frame(b, bg=ui.FACE)
        body.pack(side='top', fill='both', expand=True)
        self.hbar = tk.Scrollbar(body, orient='horizontal', command=self._hscroll)
        self.hbar.pack(side='bottom', fill='x')
        self.vbar = tk.Scrollbar(body, orient='vertical', command=self._vscroll)
        self.vbar.pack(side='right', fill='y')
        self.cols = tk.Canvas(body, bg=ui.FACE, highlightthickness=0, bd=0)
        self.cols.pack(side='left', fill='y')
        div = tk.Canvas(body, width=s(3), bg=ui.SHADOW, highlightthickness=0, bd=0, cursor='sb_h_double_arrow')
        div.pack(side='left', fill='y')
        div.bind('<Button-1>', lambda e: setattr(self, '_dx', (e.x_root, self.divider)))
        div.bind('<B1-Motion>', self._div_drag)
        right = tk.Frame(body, bg=ui.FACE)
        right.pack(side='left', fill='both', expand=True)
        self.timeline = tk.Canvas(right, height=s(TL_H), bg=ui.FACE, highlightthickness=0, bd=0)
        self.timeline.pack(side='top', fill='x')
        self.grid = tk.Canvas(right, bg=ui.WINDOW, highlightthickness=0, bd=0)
        self.grid.pack(side='top', fill='both', expand=True)
        self.grid.bind('<Configure>', lambda e: self.redraw())
        self.grid.bind('<ButtonPress-1>', self._press)
        self.grid.bind('<B1-Motion>', self._drag)
        self.grid.bind('<ButtonRelease-1>', self._release)
        self.tool.bind(self.grid)
        self.cols.bind('<ButtonPress-1>', lambda e: self._col_press(e, 1))
        self.cols.bind('<ButtonRelease-1>', lambda e: self.rep.stop(1))
        self.cols.bind('<B1-Motion>', self._col_drag)
        self.cols.bind('<Double-Button-1>', self._col_double)
        ui.bind_right(self.cols, 'ButtonPress', lambda e: self._col_press(e, 3))
        ui.bind_right(self.cols, 'ButtonRelease', lambda e: self.rep.stop(3))
        self.timeline.bind('<Button-1>', self._tl_click)
        self.rep = ui.Repeater(self.cols)
        for w in (self.grid, self.cols):
            w.bind('<MouseWheel>', lambda e: self._vscroll('scroll', -1 if e.delta > 0 else 1, 'units'))
            w.bind('<Button-4>', lambda e: self._vscroll('scroll', -1, 'units'))
            w.bind('<Button-5>', lambda e: self._vscroll('scroll', 1, 'units'))

    # ---- helpers
    def grid_ticks(self):
        from ..procedures import note_ticks
        return note_ticks(self.grid_combo.value.strip(), self.app.song.timebase)

    def step_length(self):
        return self.grid_ticks()

    def x_of(self, tick):
        return (tick - self.x0) / self.tpp + 4

    def tick_of(self, x):
        return int((x - 4) * self.tpp + self.x0)

    def snap(self, tick):
        g = self.grid_ticks()
        return max(0, int(tick // g) * g)

    def eff_channel(self, e):
        return self.pattern.channel or self.track.channel or (e.channel + 1)

    def drum_of(self, e):
        if not e.is_note():
            return None
        ch = self.eff_channel(e)
        for i, d in enumerate(self.kit.drums):
            if d.key == e.d1 and (d.channel == ch or d.channel == 0 or self.track.channel == 0 and d.channel == e.channel + 1):
                return i
        for i, d in enumerate(self.kit.drums):
            if d.key == e.d1:
                return i
        return None

    def hzoom(self, d):
        self.tpp = max(1, self.tpp // 2) if d < 0 else min(256, self.tpp * 2)
        self.redraw()

    def _vscroll(self, *a):
        n = len(self.kit.drums)
        H = self.grid.winfo_height() // ui.S // ROW
        if a[0] == 'moveto':
            self.top_row = int(float(a[1]) * n)
        else:
            self.top_row += int(a[1]) * (1 if a[2] == 'units' else H)
        self.top_row = max(0, min(self.top_row, max(0, n - H)))
        self.redraw()

    def _hscroll(self, *a):
        W = self.grid.winfo_width() // ui.S
        end = max(self.pattern.length, W * self.tpp)
        if a[0] == 'moveto':
            self.x0 = int(float(a[1]) * end)
        else:
            self.x0 += int(a[1]) * (self.app.tmap.sig_at(self.pattern.start)[3] if a[2] == 'units' else W * self.tpp)
        self.x0 = max(0, min(self.x0, max(0, end - W * self.tpp)))
        self.redraw()

    def _div_drag(self, ev):
        x0, d0 = self._dx
        self.divider = d0 + (ev.x_root - x0) // ui.S
        self.redraw()

    # ---- drawing
    def visible_columns(self):
        return [c for c in self.app.settings['drum_columns'] if c in DRUM_COLUMNS]

    def redraw(self):
        if not self.winfo_exists():
            return
        self.draw_cols()
        self.draw_grid()
        W = self.grid.winfo_width() // ui.S
        self.draw_timeline(self.timeline, self.x_of, W, TL_H)
        self.update_info()
        self.info.set(5, self.kit.name)
        n = max(1, len(self.kit.drums))
        H = self.grid.winfo_height() // ui.S // ROW
        self.vbar.set(self.top_row / n, min(1, (self.top_row + H) / n))

    def draw_cols(self):
        c = self.cols
        c.delete('all')
        H = c.winfo_height() // ui.S
        widths = [(cid, DRUM_COLUMNS[cid][1]) for cid in self.visible_columns()]
        total = max(20, sum(w + 1 for _c, w in widths) + self.divider)
        c.configure(width=s(total))
        x = 0
        self.col_x = []
        for cid, w in widths:
            ui.text(c, x + w // 2, TL_H // 2 + 1, DRUM_COLUMNS[cid][0], 'small', anchor='center')
            self.col_x.append((cid, x, w))
            x += w
            ui.line(c, x, 0, x, H)
            x += 1
        ui.line(c, 0, TL_H - 1, total, TL_H - 1)
        y = TL_H
        for i in range(self.top_row, len(self.kit.drums)):
            if y > H:
                break
            d = self.kit.drums[i]
            sel = i == self.cur_drum
            for cid, x0, w in self.col_x:
                key = DRUM_COLUMNS[cid][2]
                if key in ('mute', 'solo'):
                    img = self.app.images.get('MUTE_PRESSED' if getattr(d, key) else 'MUTE_BUT')
                    ui.image(c, x0 + 1, y, img)
                    continue
                if sel:
                    c.create_rectangle(s(x0), s(y), s(x0 + w), s(y + ROW), fill='#404040', outline='')
                fg = '#ffffff' if sel else '#000000'
                if key == 'name':
                    ui.text(c, x0 + 2, y + ROW // 2, ui.clip_text(d.name, w - 2), 'system', fill=fg, anchor='w')
                elif key == 'key':
                    ui.text(c, x0 + w - 1, y + ROW // 2, note_name(d.key), 'system', fill=fg, anchor='e')
                elif key == 'info':
                    pass
                else:
                    ui.text(c, x0 + w - 1, y + ROW // 2, str(getattr(d, key)), 'system', fill=fg, anchor='e')
            y += ROW

    def draw_grid(self):
        c = self.grid
        c.delete('all')
        W, H = c.winfo_width() // ui.S, c.winfo_height() // ui.S
        p = self.pattern
        tm = self.app.tmap
        for r in range(H // ROW + 1):
            y = r * ROW
            c.create_line(0, s(y), s(W), s(y), fill='#c2c2c2', width=ui.S)
        g = self.grid_ticks()
        t = (self.x0 // g) * g
        tend = self.tick_of(W)
        while t <= tend:
            x = self.x_of(t)
            if x >= 0:
                c.create_line(s(x), 0, s(x), s(H), fill='#c2c2c2', width=ui.S)
            t += g
        for tick, bar, tpbeat, beats in tm.bar_lines(p.start + self.x0, p.start + tend):
            x = self.x_of(tick - p.start)
            if 0 <= x <= W:
                c.create_line(s(x), 0, s(x), s(H), fill='#000000', width=ui.S)
        # hits
        for e in self.events:
            i = self.drum_of(e)
            if i is None or i < self.top_row:
                continue
            y = (i - self.top_row) * ROW
            if y > H:
                continue
            x = self.x_of(e.tick)
            if not -6 < x < W:
                continue
            d = self.kit.drums[i]
            if e.selected:
                col = '#000000'
            else:
                lvl = max(0, min(7, (d.velocity - e.d2 + 9) // 10))
                col = HIT_COLOURS[lvl]
            c.create_oval(s(x - 5), s(y + 1), s(x + 5), s(y + ROW - 1), fill=col, outline='#000000', width=ui.S)
        px = self.x_of(self.app.seq.position - p.start)
        if 0 <= px < W:
            c.create_line(s(px), 0, s(px), s(H), dash=(1, 1), width=ui.S, tags='cursor')

    def set_position(self, tick, follow=False):
        W = self.grid.winfo_width() // ui.S
        rel = tick - self.pattern.start
        x = self.x_of(rel)
        if follow and 0 <= rel <= self.pattern.length and (x < 0 or x > W - 10):
            self.x0 = max(0, rel)
            self.redraw()
            return
        self.grid.delete('cursor')
        if 0 <= x < W:
            self.grid.create_line(s(x), 0, s(x), self.grid.winfo_height(), dash=(1, 1), width=ui.S, tags='cursor')
        self.draw_timeline(self.timeline, self.x_of, W, TL_H)

    # ---- columns mouse
    def _col_hit(self, ev):
        x, y = ev.x / ui.S, ev.y / ui.S
        if y < TL_H:
            return 'header', None, None
        i = self.top_row + int((y - TL_H) // ROW)
        if not 0 <= i < len(self.kit.drums):
            return None, None, None
        for cid, x0, w in getattr(self, 'col_x', []):
            if x0 <= x < x0 + w:
                return 'cell', i, DRUM_COLUMNS[cid][2]
        return 'cell', i, None

    def _col_press(self, ev, button):
        kind, i, key = self._col_hit(ev)
        if kind == 'header':
            from .. import dialogs
            dialogs.run(self.app, 'DRUM_COLUMN_DLG')
            return
        if i is None:
            return
        d = self.kit.drums[i]
        if key in ('mute', 'solo') and button == 1:
            if key == 'mute':
                d.mute = 0 if d.mute else 1
            else:
                self._solo(i)
            self.redraw()
            return
        self.cur_drum = i
        if key == 'name':
            self._drag_drum = i
            self.play_drum(d)
            self.redraw()
            return
        if key in ('channel', 'key', 'velocity', 'length'):
            lim = {'channel': (0, 16), 'key': (0, 127), 'velocity': (1, 127), 'length': (1, 9999)}[key]

            def adj(dlt, big, d=d, key=key, lim=lim):
                step = dlt
                if key == 'key' and big:
                    step = 12 if dlt > 0 else -12
                setattr(d, key, max(lim[0], min(lim[1], getattr(d, key) + step)))
                self.redraw()
            self.rep.start(ev, adj, button)

    def _col_drag(self, ev):
        i0 = getattr(self, '_drag_drum', None)
        if i0 is None:
            return
        _k, i, _key = self._col_hit(ev)
        if i is not None and i != i0:
            drums = self.kit.drums
            d = drums.pop(i0)
            drums.insert(i, d)
            self._drag_drum = i
            self.cur_drum = i
            self.redraw()

    def _col_double(self, ev):
        _k, i, key = self._col_hit(ev)
        if i is not None and key == 'name':
            from .. import dialogs
            dialogs.run(self.app, 'DRUM_INFO_DLG', drum=self.kit.drums[i])

    def _solo(self, i):
        drums = self.kit.drums
        d = drums[i]
        if d.solo:
            d.solo = 0
            saved = getattr(self, '_solo_saved', None)
            if saved:
                for x, m in saved.items():
                    x.mute = m
            return
        for x in drums:
            x.solo = 0
        if getattr(self, '_solo_last', None) is not d:
            self._solo_saved = {x: x.mute for x in drums}
        else:
            for x, m in getattr(self, '_solo_saved', {}).items():
                x.mute = m
        self._solo_last = d
        d.solo = 1

    def play_drum(self, d, vel=None):
        if not self.speaker:
            return
        ch = max(1, d.channel or self.track.channel or 10) - 1
        port = max(0, self.track.port)
        self.app.midi.send(port, bytes([0x90 | ch, d.key, vel or d.velocity]))
        self.after(200, lambda: self.app.midi.send(port, bytes([0x80 | ch, d.key, 0])))

    # ---- grid mouse
    def _hit(self, ev):
        x, y = ev.x / ui.S, ev.y / ui.S
        i = self.top_row + int(y // ROW)
        if not 0 <= i < len(self.kit.drums):
            return None, None
        for e in reversed(self.events):
            if self.drum_of(e) == i and abs(self.x_of(e.tick) - x) <= 5:
                return i, e
        return i, None

    def _press(self, ev):
        i, e = self._hit(ev)
        if i is None:
            return
        tool = self.tool.current
        app = self.app
        self.cur_drum = i
        d = self.kit.drums[i]
        if tool == 'arrow':
            if e is None:
                if not ui.is_shift(ev):
                    self.deselect_all()
                self.drag = ('lasso', ev.x, ev.y)
            else:
                if ui.is_shift(ev):
                    e.selected = not e.selected
                elif not e.selected:
                    self.deselect_all()
                    e.selected = True
                self.play_drum(d, e.d2)
                self.drag = ('move', ev.x, ev.y, ui.is_ctrl(ev), 0, 0)
            self.redraw()
        elif tool in ('stick1', 'stick2'):
            vel = d.velocity if tool == 'stick1' else max(1, d.velocity - 10)
            app.checkpoint()
            if e is not None:
                e.d2 = vel
            else:
                tick = self.snap(self.tick_of(ev.x / ui.S))
                if not 0 <= tick < self.pattern.length:
                    return
                ch = max(1, d.channel or self.track.channel or 10) - 1
                self.events.append(Event(tick, 0x90 | ch, d.key, vel, d.length))
                self.events.sort(key=lambda q: q.tick)
            self.play_drum(d, vel)
            app.song_changed('events')
        elif tool == 'eraser' and e is not None:
            app.checkpoint()
            victims = self.selected() if e.selected else [e]
            ids = {id(v) for v in victims}
            self.events[:] = [q for q in self.events if id(q) not in ids]
            app.song_changed('events')
        elif tool in ('plus', 'minus') and e is not None:
            app.checkpoint()
            e.d2 = max(1, min(127, e.d2 + (10 if tool == 'plus' else -10)))
            app.song_changed('events')

    def _drag(self, ev):
        d = self.drag
        if not d:
            return
        c = self.grid
        if d[0] == 'lasso':
            c.delete('lasso')
            c.create_rectangle(d[1], d[2], ev.x, ev.y, dash=(2, 2), tags='lasso')
        elif d[0] == 'move':
            dt = self.snap(self.tick_of(ev.x / ui.S)) - self.snap(self.tick_of(d[1] / ui.S))
            dr = int((ev.y - d[2]) / ui.S // ROW)
            self.drag = d[:4] + (dt, dr)

    def _release(self, ev):
        d = self.drag
        self.drag = None
        if not d:
            return
        if d[0] == 'lasso':
            self.grid.delete('lasso')
            x0, x1 = sorted((d[1] / ui.S, ev.x / ui.S))
            y0, y1 = sorted((d[2] / ui.S, ev.y / ui.S))
            for e in self.events:
                i = self.drum_of(e)
                if i is None:
                    continue
                x = self.x_of(e.tick)
                y = (i - self.top_row) * ROW + ROW / 2
                if x0 <= x <= x1 and y0 <= y <= y1:
                    e.selected = True
            self.redraw()
        elif d[0] == 'move':
            dt, dr = d[4], d[5]
            if not dt and not dr:
                return
            self.app.checkpoint()
            sel = self.selected()
            if d[3]:
                new = [e.copy() for e in sel]
                for e in sel:
                    e.selected = False
                for n in new:
                    n.selected = True
                self.events.extend(new)
                sel = new
            for e in sel:
                e.tick = max(0, e.tick + dt)
                i = self.drum_of(e)
                if dr and i is not None:
                    j = max(0, min(len(self.kit.drums) - 1, i + dr))
                    nd = self.kit.drums[j]
                    e.d1 = nd.key
            self.events.sort(key=lambda q: q.tick)
            self.app.song_changed('events')

    def _tl_click(self, ev):
        if ui.is_ctrl(ev):
            self.app.locate(self.pattern.start + max(0, self.tick_of(ev.x / ui.S)))

    # ---- functions menu
    def functions_menu(self):
        st = resources.string
        items = [(st(782), self.add_drum), (st(783), self.delete_drum), (st(784), self.delete_all)]
        PopupMenu.show(self, items, self.winfo_rootx() + ui.s(8), self.body.winfo_rooty() + ui.s(18))

    def add_drum(self):
        if len(self.kit.drums) >= 128:
            messagebox.showinfo('Sound Studio Gold', resources.string(67), parent=self.app)
            return
        d = Drum()
        d.name = 'New Drum'
        self.kit.drums.append(d)
        self.redraw()

    def delete_drum(self):
        if not self.kit.drums:
            messagebox.showinfo('Sound Studio Gold', resources.string(68), parent=self.app)
            return
        self.kit.drums.pop(min(self.cur_drum, len(self.kit.drums) - 1))
        self.cur_drum = max(0, self.cur_drum - 1)
        self.redraw()

    def delete_all(self):
        self.kit.drums.clear()
        self.redraw()

    # ---- PC keyboard plays drums (speaker on)
    def key(self, ev):
        if self.speaker and ev.keysym in PC_KEYS:
            i = self.cur_drum + PC_KEYS.index(ev.keysym)
            if i < len(self.kit.drums):
                d = self.kit.drums[i]
                self.play_drum(d)
                if self.step_mode:
                    self.app.checkpoint()
                    self.step_insert(d.key, d.velocity)
                    self.step_advance()
            return True
        return super().key(ev)
