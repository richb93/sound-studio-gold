"""Piano Roll window."""
import tkinter as tk

from .. import ui, tools
from ..ui import s
from ..widgets import Toolbar, InfoLine
from ..song import Event
from .common import EditorWindow, TYPE_COLOURS, controller_label, note_name

GRID_VALUES = ['Off', ' 1', ' 2', ' 4', ' 8', '16', '32', '64', ' 4T', ' 8T', '16T', '32T']
DISPLAY_FIXED = ['Velocity', 'Aftertouch', 'Pressure', 'Bend', 'Program']
PR_TOOLS = [('arrow', 'CUR_ARROW_BM', ''), ('pencil', 'CUR_PENCIL_BM', 'CUR_PENCIL'),
            ('eraser', 'CUR_ERASER_BM', 'CUR_ERASER'), ('modify', 'CUR_MODIFY_BM', 'CUR_MODIFY'),
            ('knife', 'CUR_KNIFE_BM', 'CUR_KNIFE'), ('glue', 'CUR_GLUE_BM', 'CUR_GLUE')]
KEYS_W = 40
PRE = 12             # grey margin before the pattern start
VEL_H = 49
TL_H = 13


class PianoRoll(EditorWindow):
    title_prefix = 'Piano Roll'
    icon_name = 'IC_PROLL'
    kind = 'proll'

    def __init__(self, client, app, pattern):
        self.tpp = max(1, app.song.timebase // 32)
        self.row = 9
        self.x0 = 0          # first visible tick (relative to pattern)
        self.top = 0         # vertical scroll (pixels)
        self.drag = None
        self.tool = tools.ToolSelector(app, PR_TOOLS, cols=3)
        super().__init__(client, app, pattern)
        self.tool.on_change = lambda k: tools.set_cursor(self.grid, self.tool.cursor_name())
        self._build()
        self.maximize()
        self.after_idle(self._initial_scroll)

    def _build(self):
        b = self.body
        tb = Toolbar(b, self.app)
        tb.pack(side='top', fill='x')
        tb.add_button('ZOOMIN_BM', lambda: self.hzoom(-1))
        tb.add_button('ZOOMOUT_BM', lambda: self.hzoom(1))
        tb.add_button('KEYVZOOMIN_BM', lambda: self.vzoom(1))
        tb.add_button('KEYVZOOMOUT_BM', lambda: self.vzoom(-1))
        self.add_toggles(tb)
        self.add_close_recall(tb)
        tb.add_label('Grid', 22)
        self.grid_combo = tb.add_combo(GRID_VALUES, 46, '16', cmd=lambda v: self.redraw(), listw=50)
        tb.add_label('Display', 40)
        disp = DISPLAY_FIXED + [controller_label(i) for i in range(128)]
        self.display = tb.add_combo(disp, 140, 'Velocity', cmd=lambda v: self.redraw(), rows=16)
        self.tb = tb
        self.info = InfoLine(b, self.app, self.info_fields())
        self.info.pack(side='top', fill='x')
        body = tk.Frame(b, bg=ui.FACE)
        body.pack(side='top', fill='both', expand=True)
        self.hbar = tk.Scrollbar(body, orient='horizontal', command=self._hscroll)
        self.hbar.pack(side='bottom', fill='x')
        self.vbar = tk.Scrollbar(body, orient='vertical', command=self._vscroll)
        self.vbar.pack(side='right', fill='y')
        left = tk.Frame(body, bg=ui.FACE, width=s(KEYS_W + 2))
        left.pack(side='left', fill='y')
        self.keys_top = tk.Canvas(left, width=s(KEYS_W + 2), height=s(TL_H), bg=ui.FACE, highlightthickness=0, bd=0)
        self.keys_top.pack(side='top')
        self.vel_scale = tk.Canvas(left, width=s(KEYS_W + 2), height=s(VEL_H), bg=ui.FACE, highlightthickness=0, bd=0)
        self.vel_scale.pack(side='bottom')
        self.keys = tk.Canvas(left, width=s(KEYS_W + 2), bg=ui.WINDOW, highlightthickness=0, bd=0)
        self.keys.pack(side='top', fill='y', expand=True)
        right = tk.Frame(body, bg=ui.FACE)
        right.pack(side='left', fill='both', expand=True)
        self.timeline = tk.Canvas(right, height=s(TL_H), bg=ui.FACE, highlightthickness=0, bd=0)
        self.timeline.pack(side='top', fill='x')
        self.vel = tk.Canvas(right, height=s(VEL_H), bg=ui.WINDOW, highlightthickness=0, bd=0)
        self.vel.pack(side='bottom', fill='x')
        self.grid = tk.Canvas(right, bg=ui.WINDOW, highlightthickness=0, bd=0)
        self.grid.pack(side='top', fill='both', expand=True)
        self.grid.bind('<Configure>', lambda e: self.redraw())
        self.grid.bind('<ButtonPress-1>', self._press)
        self.grid.bind('<B1-Motion>', self._drag)
        self.grid.bind('<ButtonRelease-1>', self._release)
        self.vel.bind('<ButtonPress-1>', self._vpress)
        self.vel.bind('<B1-Motion>', self._vdrag)
        self.vel.bind('<ButtonRelease-1>', self._vrelease)
        self.keys.bind('<ButtonPress-1>', self._key_press)
        self.timeline.bind('<Button-1>', self._tl_click)
        self.tool.bind(self.grid)
        self.tool.bind(self.vel)
        for w in (self.grid, self.keys):
            w.bind('<MouseWheel>', lambda e: self._vscroll('scroll', -1 if e.delta > 0 else 1, 'units'))
            w.bind('<Button-4>', lambda e: self._vscroll('scroll', -1, 'units'))
            w.bind('<Button-5>', lambda e: self._vscroll('scroll', 1, 'units'))

    def _initial_scroll(self):
        notes = [e.d1 for e in self.events if e.is_note()]
        H = self.grid.winfo_height() // ui.S
        mid = (sum(notes) // len(notes)) if notes else 60
        self.top = max(0, (127 - mid) * self.row - H // 2)
        self.redraw()

    # ---- coordinates
    def x_of(self, tick):
        return PRE + (tick - self.x0) / self.tpp

    def tick_of(self, x):
        return int((x - PRE) * self.tpp + self.x0)

    def y_of(self, note):
        return (127 - note) * self.row - self.top

    def note_of(self, y):
        return 127 - int((y + self.top) // self.row)

    def grid_ticks(self):
        v = self.grid_combo.value.strip()
        if v == 'Off':
            return 1
        from ..procedures import note_ticks
        return note_ticks(v, self.app.song.timebase)

    def snap(self, tick):
        g = self.grid_ticks()
        return max(0, int(round(tick / g)) * g)

    def step_length(self):
        return self.grid_ticks()

    # ---- zoom / scroll
    def hzoom(self, d):
        self.tpp = max(1, self.tpp // 2) if d < 0 else min(512, self.tpp * 2)
        self.redraw()

    def vzoom(self, d):
        self.row = max(5, min(17, self.row + 2 * d))
        self.redraw()

    def _vscroll(self, *a):
        H = self.grid.winfo_height() // ui.S
        tot = 128 * self.row
        if a[0] == 'moveto':
            self.top = int(float(a[1]) * tot)
        else:
            self.top += int(a[1]) * (self.row * 3 if a[2] == 'units' else H)
        self.top = max(0, min(self.top, max(0, tot - H)))
        self.redraw()

    def _hscroll(self, *a):
        W = self.grid.winfo_width() // ui.S
        end = max(self.pattern.length, (W - PRE) * self.tpp)
        if a[0] == 'moveto':
            self.x0 = int(float(a[1]) * end)
        else:
            self.x0 += int(a[1]) * (self.app.tmap.sig_at(self.pattern.start)[3] if a[2] == 'units' else W * self.tpp)
        self.x0 = max(0, min(self.x0, max(0, end - (W - PRE) * self.tpp)))
        self.redraw()

    # ---- drawing
    def redraw(self):
        if not self.winfo_exists():
            return
        self.draw_keys()
        self.draw_grid()
        self.draw_vel()
        W = self.grid.winfo_width() // ui.S
        self.draw_timeline(self.timeline, lambda t: self.x_of(t), W, TL_H)
        self.update_info()
        H = self.grid.winfo_height() // ui.S
        tot = 128 * self.row
        self.vbar.set(self.top / tot, min(1, (self.top + H) / tot))
        end = max(self.pattern.length, 1)
        vis = (W - PRE) * self.tpp
        self.hbar.set(self.x0 / max(end, vis), min(1, (self.x0 + vis) / max(end, vis)))

    def draw_keys(self):
        c = self.keys
        c.delete('all')
        H = c.winfo_height() // ui.S
        r = self.row
        c.create_rectangle(0, 0, s(KEYS_W), s(H), fill=ui.WINDOW, outline='')
        for n in range(128):
            y = self.y_of(n)
            if y + r < 0 or y > H:
                continue
            pc = n % 12
            if pc in (1, 3, 6, 8, 10):
                c.create_rectangle(0, s(y + 2), s(KEYS_W // 2), s(y + r - 2), fill='#000000', outline='')
                ui.line(c, KEYS_W // 2, y + r // 2, KEYS_W, y + r // 2)
            elif pc in (4, 11):
                ui.line(c, 0, y, KEYS_W, y)
            if pc == 0:
                ui.text(c, KEYS_W - 2, y + r // 2, 'C%d' % (n // 12 - 2), 'small', fill='#a06000', anchor='e')
                if pc == 0:
                    ui.line(c, 0, y + r, KEYS_W, y + r)
        c.create_rectangle(s(KEYS_W), 0, s(KEYS_W + 2), s(H), fill=ui.FACE, outline='')
        tc = self.keys_top
        tc.delete('all')
        vs = self.vel_scale
        vs.delete('all')
        for v, y in ((127, 0), (64, VEL_H // 2), (0, VEL_H - 1)):
            ui.text(vs, KEYS_W - 2, max(5, min(VEL_H - 5, y)), str(v), 'small', anchor='e')

    def draw_grid(self):
        c = self.grid
        c.delete('all')
        W, H = c.winfo_width() // ui.S, c.winfo_height() // ui.S
        p = self.pattern
        tm = self.app.tmap
        r = self.row
        # pre-roll margin and area after the pattern end
        c.create_rectangle(0, 0, s(PRE), s(H), fill=ui.FACE, outline='')
        xe = self.x_of(p.length)
        if xe < W:
            c.create_rectangle(s(xe), 0, s(W), s(H), fill=ui.FACE, outline='')
        # horizontal note lines
        for n in range(128):
            y = self.y_of(n)
            if 0 <= y <= H:
                c.create_line(s(PRE), s(y), s(min(W, xe)), s(y), fill='#c2c2c2', width=ui.S)
        # vertical grid/beat/bar lines
        g = self.grid_ticks()
        t_end = self.tick_of(W)
        if g > 1 and g / self.tpp >= 3:
            t = (self.x0 // g) * g
            while t <= min(t_end, p.length):
                x = self.x_of(t)
                if x >= PRE:
                    c.create_line(s(x), 0, s(x), s(H), fill='#c2c2c2', width=ui.S)
                t += g
        for tick, bar, tpbeat, beats in tm.bar_lines(p.start + self.x0, p.start + min(t_end, p.length)):
            x = self.x_of(tick - p.start)
            if x >= PRE:
                c.create_line(s(x), 0, s(x), s(H), fill='#000000', width=ui.S)
            for bt in range(1, beats):
                bx = self.x_of(tick + bt * tpbeat - p.start)
                if PRE <= bx < W:
                    c.create_line(s(bx), 0, s(bx), s(H), fill='#808080', width=ui.S)
        # notes
        for e in self.events:
            if not e.is_note():
                continue
            x0 = self.x_of(e.tick)
            x1 = self.x_of(e.tick + max(1, e.length))
            if x1 < 0 or x0 > W:
                continue
            y = self.y_of(e.d1)
            if y + r < 0 or y > H:
                continue
            fill = '#000000' if e.selected else '#ffffff'
            c.create_rectangle(s(x0), s(y + (r - 6) // 2 + 1), s(max(x0 + 3, x1)), s(y + (r - 6) // 2 + 6),
                               fill=fill, outline='#000000', width=ui.S)
        # play position
        px = self.x_of(self.app.seq.position - p.start)
        if PRE <= px < W:
            c.create_line(s(px), 0, s(px), s(H), fill='#000000', dash=(1, 1), width=ui.S, tags='cursor')

    def display_kind(self):
        v = self.display.value
        if v == 'Velocity':
            return 0x90, None
        if v == 'Aftertouch':
            return 0xA0, None
        if v == 'Pressure':
            return 0xD0, None
        if v == 'Bend':
            return 0xE0, None
        if v == 'Program':
            return 0xC0, None
        for i in range(128):
            if controller_label(i) == v:
                return 0xB0, i
        return 0x90, None

    def vel_value(self, e):
        hi = e.status & 0xF0
        if hi == 0xE0:
            return ((e.d2 << 7) | e.d1) >> 7
        if hi in (0xC0, 0xD0):
            return e.d1
        return e.d2

    def vel_events(self):
        kind, cc = self.display_kind()
        out = []
        for e in self.events:
            if e.status >= 0xF0 or e.status & 0xF0 != kind:
                continue
            if kind == 0xB0 and e.d1 != cc:
                continue
            out.append(e)
        return out

    def draw_vel(self):
        c = self.vel
        c.delete('all')
        W = c.winfo_width() // ui.S
        p = self.pattern
        ui.line(c, 0, 0, W, 0)
        c.create_rectangle(0, s(1), s(PRE), s(VEL_H), fill=ui.FACE, outline='')
        kind, _cc = self.display_kind()
        for e in self.vel_events():
            x = self.x_of(e.tick)
            if not PRE <= x < W:
                continue
            v = self.vel_value(e)
            h = (VEL_H - 3) * v / 127
            col = '#000000' if e.selected else ('#808080' if kind == 0x90 else TYPE_COLOURS.get(kind, '#000000'))
            c.create_rectangle(s(x), s(VEL_H - 1 - h), s(x + 2), s(VEL_H - 1), fill=col, outline='')

    def set_position(self, tick, follow=False):
        W = self.grid.winfo_width() // ui.S
        rel = tick - self.pattern.start
        x = self.x_of(rel)
        if follow and 0 <= rel <= self.pattern.length and (x < PRE or x > W - 10):
            self.x0 = max(0, rel)
            self.redraw()
            return
        c = self.grid
        c.delete('cursor')
        if PRE <= x < W:
            c.create_line(s(x), 0, s(x), c.winfo_height(), fill='#000000', dash=(1, 1), width=ui.S, tags='cursor')
        self.draw_position_marker(self.timeline, lambda t: self.x_of(t), TL_H)

    # ---- mouse in the note display
    def hit_note(self, ev):
        x, y = ev.x / ui.S, ev.y / ui.S
        n = self.note_of(y)
        for e in reversed(self.events):
            if e.is_note() and e.d1 == n and self.x_of(e.tick) <= x <= self.x_of(e.tick + max(1, e.length)) + 1:
                return e
        return None

    def _press(self, ev):
        e = self.hit_note(ev)
        tool = self.tool.current
        app = self.app
        x = ev.x / ui.S
        tick = self.tick_of(x)
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
                self.play_event(e)
                self.drag = ('move', ev.x, ev.y, e, ui.is_ctrl(ev), 0, 0)
            self.redraw()
        elif tool == 'pencil':
            app.checkpoint()
            if e is None:
                n = self.note_of(ev.y / ui.S)
                st = self.snap(tick) if self.grid_ticks() > 1 else tick
                if st < 0 or st >= self.pattern.length:
                    return
                ch = max(1, self.track.channel or self.pattern.channel or 1) - 1
                vel = app.settings['prefs'].get('kbd_velocity', 100)
                ne = Event(st, 0x90 | ch, n, vel, max(1, self.grid_ticks() - 1))
                self.deselect_all()
                ne.selected = True
                self.events.append(ne)
                self.events.sort(key=lambda q: q.tick)
                self.play_event(ne)
                self.drag = ('size', ne, 'end')
            else:
                mid = e.tick + e.length / 2
                self.drag = ('size', e, 'start' if tick < mid else 'end')
            self.redraw()
        elif tool == 'eraser' and e is not None:
            app.checkpoint()
            victims = self.selected() if e.selected else [e]
            ids = {id(v) for v in victims}
            self.events[:] = [q for q in self.events if id(q) not in ids]
            app.song_changed('events')
        elif tool == 'knife' and e is not None:
            st = self.snap(tick)
            if e.tick < st < e.tick + e.length:
                app.checkpoint()
                n = e.copy()
                n.tick = st
                n.length = e.tick + e.length - st
                e.length = st - e.tick
                self.events.append(n)
                self.events.sort(key=lambda q: q.tick)
                app.song_changed('events')
        elif tool == 'glue' and e is not None:
            nxt = [q for q in self.events if q.is_note() and q.d1 == e.d1 and q.tick >= e.tick + e.length and q is not e]
            if nxt:
                app.checkpoint()
                q = min(nxt, key=lambda q: q.tick)
                e.length = q.tick + q.length - e.tick
                self.events.remove(q)
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
            dn = self.note_of(ev.y / ui.S) - self.note_of(d[2] / ui.S)
            self.drag = d[:5] + (dt, dn)
            c.delete('ghost')
            for e in self.selected():
                if not e.is_note():
                    continue
                x0, x1 = self.x_of(e.tick + dt), self.x_of(e.tick + dt + max(1, e.length))
                y = self.y_of(e.d1 + dn)
                c.create_rectangle(s(x0), s(y + 1), s(x1), s(y + self.row - 1), dash=(1, 1), outline='#000000', tags='ghost')
        elif d[0] == 'size':
            e = d[1]
            tick = self.tick_of(ev.x / ui.S)
            tick = self.snap(tick) if self.grid_ticks() > 1 else tick
            if d[2] == 'end':
                e.length = max(1, tick - e.tick)
            else:
                end = e.tick + e.length
                e.tick = max(0, min(end - 1, tick))
                e.length = end - e.tick
            self.draw_grid()

    def _release(self, ev):
        d = self.drag
        self.drag = None
        if not d:
            return
        app = self.app
        if d[0] == 'lasso':
            self.grid.delete('lasso')
            x0, x1 = sorted((d[1] / ui.S, ev.x / ui.S))
            y0, y1 = sorted((d[2] / ui.S, ev.y / ui.S))
            for e in self.events:
                if e.is_note():
                    ex0, ex1 = self.x_of(e.tick), self.x_of(e.tick + e.length)
                    ey = self.y_of(e.d1) + self.row / 2
                    if ex1 >= x0 and ex0 <= x1 and y0 <= ey <= y1:
                        e.selected = True
            self.redraw()
        elif d[0] == 'move':
            self.grid.delete('ghost')
            dt, dn = d[5], d[6]
            if dt == 0 and dn == 0:
                return
            app.checkpoint()
            sel = self.selected()
            if d[4]:
                new = []
                for e in sel:
                    n = e.copy()
                    e.selected = False
                    n.selected = True
                    new.append(n)
                self.events.extend(new)
                sel = new
            for e in sel:
                e.tick = max(0, e.tick + dt)
                if e.status & 0xF0 in (0x90, 0xA0):
                    e.d1 = max(0, min(127, e.d1 + dn))
            self.events.sort(key=lambda q: q.tick)
            app.song_changed('events')
        elif d[0] == 'size':
            app.song_changed('events')

    # ---- velocity display
    def _vval(self, y):
        return max(0, min(127, int(round((VEL_H - 1 - y) * 127 / (VEL_H - 3)))))

    def _vpress(self, ev):
        tool = self.tool.current
        kind, cc = self.display_kind()
        x, y = ev.x / ui.S, ev.y / ui.S
        if tool in ('modify', 'pencil'):
            self.app.checkpoint()
            if tool == 'pencil' and kind != 0x90:
                self._vdraw(x, y)
            else:
                self._vmodify(x, y)
            self.drag = ('v', tool)
        elif tool == 'eraser':
            evs = [e for e in self.vel_events() if abs(self.x_of(e.tick) - x) <= 2]
            if evs:
                self.app.checkpoint()
                ids = {id(e) for e in evs}
                self.events[:] = [e for e in self.events if id(e) not in ids or e.is_note() and kind != 0x90]
                self.app.song_changed('events')
        elif tool == 'arrow':
            evs = [e for e in self.vel_events() if abs(self.x_of(e.tick) - x) <= 2]
            if not ui.is_shift(ev):
                self.deselect_all()
            for e in evs[:1]:
                e.selected = True
            self.redraw()

    def _vdrag(self, ev):
        if self.drag and self.drag[0] == 'v':
            x, y = ev.x / ui.S, ev.y / ui.S
            kind, _cc = self.display_kind()
            if self.drag[1] == 'pencil' and kind != 0x90:
                self._vdraw(x, y)
            else:
                self._vmodify(x, y)

    def _vrelease(self, ev):
        if self.drag and self.drag[0] == 'v':
            self.drag = None
            self.app.song_changed('events')

    def _set_vel(self, e, v):
        hi = e.status & 0xF0
        if hi == 0xE0:
            val = v << 7
            e.d1, e.d2 = val & 0x7F, (val >> 7) & 0x7F
        elif hi in (0xC0, 0xD0):
            e.d1 = v
        else:
            e.d2 = max(1, v) if hi == 0x90 else v

    def _vmodify(self, x, y):
        v = self._vval(y)
        for e in self.vel_events():
            if abs(self.x_of(e.tick) - x) <= 1.5 * max(1, self.tpp / self.tpp):
                self._set_vel(e, v)
        self.draw_vel()

    def _vdraw(self, x, y):
        kind, cc = self.display_kind()
        tick = self.snap(self.tick_of(x))
        if not 0 <= tick < self.pattern.length:
            return
        v = self._vval(y)
        ch = max(1, self.track.channel or 1) - 1
        old = [e for e in self.vel_events() if e.tick == tick]
        if old:
            self._set_vel(old[0], v)
        else:
            e = Event(tick, kind | ch, cc if kind == 0xB0 else 0, 0)
            self._set_vel(e, v)
            self.events.append(e)
            self.events.sort(key=lambda q: q.tick)
        self.draw_vel()

    # ---- keyboard & timeline
    def _key_press(self, ev):
        n = self.note_of(ev.y / ui.S)
        if not 0 <= n <= 127:
            return
        vel = self.app.settings['prefs'].get('kbd_velocity', 100)
        if self.step_mode:
            self.app.checkpoint()
            self.step_insert(n, vel)
            self.step_advance()
        self.play_note(n, vel)

    def _tl_click(self, ev):
        if ui.is_ctrl(ev):
            self.app.locate(self.pattern.start + max(0, self.tick_of(ev.x / ui.S)))
