"""Conductor window (MDICONDUCTORWNDPROC): tempo, time-signature and key-signature points."""
import tkinter as tk

from .. import ui, resources, tools
from ..mdi import MDIChild
from ..ui import s
from ..widgets import Toolbar, InfoLine
from ..song import CondPoint, COND_TEMPO, COND_TIMESIG, COND_KEY
from ..timing import ts_parts
from ..bwcc import message_box

SNAP_VALUES = ['Bar', ' 1', ' 2', ' 4', ' 8', '16', '32', '64', 'Off']
COND_TOOLS = [('arrow', 'CUR_ARROW_BM', ''), ('pencil', 'CUR_PENCIL_BM', 'CUR_PENCIL'),
              ('eraser', 'CUR_ERASER_BM', 'CUR_ERASER')]
TL_H = 13           # time line
ROW = 13            # time signature / key signature displays
LW = 24             # tempo label column (black line at x = LW)
X0 = 36             # x of the window's left-most tick
T_MAX = 250         # tempo at the top of the Tempo Display
T_MIN = 8           # tempo at the bottom
GRID = (40, 80, 120, 160, 200)


def key_label(v):
    return resources.tables()['key_names'][v % 12].split(' / ')[0]


def ts_label(v):
    n, d = ts_parts(v)
    return '%d/%d' % (n, d)


class CondClip:
    def __init__(self, points):
        self.points = points

    def describe(self):
        return '%d Conductor Points' % len(self.points)


class ConductorWindow(MDIChild):
    icon_name = 'IC_CONDUCTOR'

    def __init__(self, client, app):
        self.app = app
        self.tpp = app.song.timebase * 4 / 12.0      # 12 pixels per 4/4 bar
        self.x0 = 0
        self.drag = None
        self.tool = tools.ToolSelector(app, COND_TOOLS, cols=3)
        cw = max(300, client.winfo_width() // ui.S - client.reserved_right - 2)
        ch = max(200, client.winfo_height() // ui.S)
        super().__init__(client, self._title(), app.small_icon(self.icon_name), 0, 0, cw, ch)
        self.tool.on_change = lambda k: tools.set_cursor(self.c, self.tool.cursor_name())
        self._build()
        # opening the Conductor switches the Conductor on
        if not app.seq.opts.conductor:
            app.toggle_option('conductor')
        self.maximize()

    def _title(self):
        return 'Conductor - %s' % self.app.song_name()

    @property
    def cond(self):
        return self.app.song.conductor

    # ------------------------------------------------------------------ layout
    def _build(self):
        b = self.body
        tb = Toolbar(b, self.app)
        tb.pack(side='top', fill='x')
        tb.add_button('ZOOMIN_BM', lambda: self.hzoom(-1))
        tb.add_button('ZOOMOUT_BM', lambda: self.hzoom(1))
        tb.add_button('BUT_CLOSE', self.close, pressed='BUT_CLOSE_PR')
        tb.add_label('Snap', 30)
        self.snap = tb.add_combo(SNAP_VALUES, 46, 'Bar', listw=46)
        self.info = InfoLine(b, self.app, [('Position', 120), ('Tempo', 80), ('TimeSig', 100), ('Key', 55)])
        self.info.pack(side='top', fill='x')
        self.hbar = tk.Scrollbar(b, orient='horizontal', command=self._hscroll)
        self.hbar.pack(side='bottom', fill='x')
        self.c = tk.Canvas(b, bg=ui.FACE, highlightthickness=0, bd=0)
        self.c.pack(side='top', fill='both', expand=True)
        self.c.bind('<Configure>', lambda e: self.redraw())
        self.c.bind('<ButtonPress-1>', self._press)
        self.c.bind('<B1-Motion>', self._motion)
        self.c.bind('<ButtonRelease-1>', self._release)
        self.tool.bind(self.c)

    # ------------------------------------------------------------------ geometry
    def x_of(self, tick):
        return X0 + (tick - self.x0) / self.tpp

    def tick_of(self, x):
        return max(0, int(round((x - X0) * self.tpp + self.x0)))

    def area(self):
        H = self.c.winfo_height() // ui.S
        top = TL_H + 2 * ROW
        return top, max(top + 20, H - 1)

    def y_of_tempo(self, v):
        top, bot = self.area()
        return top + (T_MAX - v) * (bot - top) / float(T_MAX - T_MIN)

    def tempo_of_y(self, y):
        top, bot = self.area()
        v = T_MAX - (y - top) * float(T_MAX - T_MIN) / (bot - top)
        return max(20, min(T_MAX, int(round(v))))

    def snap_tick(self, tick):
        tick = max(0, tick)
        v = self.snap.value.strip()
        tm = self.app.tmap
        if v == 'Off':
            return tick
        if v == 'Bar':
            b = tm.bar_tick(tick)
            nb = b + tm.sig_at(b)[2]
            return b if tick - b < nb - tick else nb
        st = self.app.song.timebase * 4 // int(v)
        return int(round(tick / st)) * st

    def snap_step(self, at):
        v = self.snap.value.strip()
        if v == 'Bar':
            return self.app.tmap.sig_at(at)[2]
        if v == 'Off':
            return 1
        return self.app.song.timebase * 4 // int(v)

    def region(self, y):
        if y < TL_H:
            return 'time'
        if y < TL_H + ROW:
            return COND_TIMESIG
        if y < TL_H + 2 * ROW:
            return COND_KEY
        return COND_TEMPO

    # ------------------------------------------------------------------ scrolling / zoom
    def hzoom(self, d):
        tb = self.app.song.timebase
        lo, hi = tb / 96.0, tb * 4 / 1.5
        self.tpp = max(lo, self.tpp / 2) if d < 0 else min(hi, self.tpp * 2)
        self.redraw()

    def _extent(self):
        W = self.c.winfo_width() // ui.S
        last = max((p.tick for p in self.cond.points), default=0)
        return max(self.app.song.end_tick(), last) + int((W - X0) * self.tpp)

    def _hscroll(self, *a):
        W = self.c.winfo_width() // ui.S
        page = int((W - X0) * self.tpp)
        end = self._extent()
        if a[0] == 'moveto':
            self.x0 = int(float(a[1]) * end)
        else:
            step = self.app.tmap.sig_at(self.x0)[2]
            self.x0 += int(a[1]) * (step if a[2] == 'units' else page)
        self.x0 = max(0, min(self.x0, max(0, end - page)))
        self.redraw()

    def set_position(self, tick, follow=False):
        if follow:
            W = self.c.winfo_width() // ui.S
            x = self.x_of(tick)
            if x < X0 or x > W - 4:
                self.x0 = max(0, int(tick))
                self.redraw()
                return
        self._draw_position()

    # ------------------------------------------------------------------ drawing
    def refresh(self, what=None):
        self.set_title(self._title())
        self.redraw()

    def redraw(self):
        if not self.winfo_exists():
            return
        c = self.c
        c.delete('all')
        W, H = c.winfo_width() // ui.S, c.winfo_height() // ui.S
        if W < 10:
            return
        self._draw_timeline(W)
        top, bot = self.area()
        # time / key signature displays
        for i in range(2):
            y = TL_H + i * ROW
            ui.line(c, LW, y, W, y, fill='#ffffff')
            ui.line(c, LW, y + ROW - 1, W, y + ROW - 1, fill='#000000')
        ui.line(c, LW, top, W, top, fill='#ffffff')
        ui.line(c, LW, TL_H, LW, H, fill='#000000')
        # tempo grid and labels
        for v in GRID:
            y = int(self.y_of_tempo(v))
            ui.line(c, LW + 1, y, W, y, fill=ui.SHADOW)
            ui.line(c, LW + 1, y + 1, W, y + 1, fill='#ffffff')
            ui.text(c, LW - 1, y, str(v), 'small', anchor='e')
        ui.text(c, LW - 1, top + 5, str(T_MAX), 'small', anchor='e')
        # signatures
        for kind, row in ((COND_TIMESIG, TL_H), (COND_KEY, TL_H + ROW)):
            for p in self.cond.of(kind):
                x = self.x_of(p.tick)
                if x < LW or x > W:
                    continue
                txt = ts_label(p.value) if kind == COND_TIMESIG else key_label(p.value)
                tw = ui.text_width(txt, 'small')
                if p.selected:
                    c.create_rectangle(s(x + 1), s(row + 1), s(x + tw + 3), s(row + ROW - 1),
                                       fill='#000000', outline='')
                ui.text(c, x + 2, row + ROW // 2, txt, 'small',
                        fill='#ffffff' if p.selected else '#000000', anchor='w')
        # tempo curve
        pts = self.cond.of(COND_TEMPO)
        for i, p in enumerate(pts):
            x = self.x_of(p.tick)
            y = int(self.y_of_tempo(p.value))
            nx = self.x_of(pts[i + 1].tick) if i + 1 < len(pts) else W
            if nx >= LW and x <= W:
                c.create_rectangle(s(max(LW + 1, x)), s(y), s(min(W, nx)), s(y + 2),
                                   fill='#000000', outline='')
            if i + 1 < len(pts) and LW < nx <= W:
                ny = int(self.y_of_tempo(pts[i + 1].value))
                ui.line(c, nx, min(y, ny), nx, max(y, ny) + 2, fill='#000000')
        img_n = self.app.images.get('CONDPOINT')
        img_s = self.app.images.get('CONDPOINT_SEL')
        for p in pts:
            x = self.x_of(p.tick)
            if LW <= x <= W + 6:
                ui.image(c, x - 5, int(self.y_of_tempo(p.value)) - 4, img_s if p.selected else img_n)
        self._draw_position()
        self._update_scroll()
        self.update_info()

    def _draw_timeline(self, W):
        c = self.c
        tm = self.app.tmap
        ui.line(c, 0, TL_H - 1, W, TL_H - 1, fill='#000000')
        bar_px = tm.sig_at(self.x0)[2] / self.tpp
        every = 1
        while every * bar_px < 40:
            every *= 2
        for tick, bar, _tpb, _beats in tm.bar_lines(self.x0, self.tick_of(W)):
            x = self.x_of(tick)
            if x < X0 - 1 or x > W:
                continue
            if (bar - 1) % every == 0:
                ui.line(c, x, 0, x, TL_H - 1, fill='#000000')
                ui.text(c, x + 1, TL_H // 2, str(bar), 'small', anchor='w')
            else:
                ui.line(c, x, TL_H - 3, x, TL_H - 1, fill='#000000')

    def _draw_position(self):
        c = self.c
        c.delete('pos')
        H = c.winfo_height() // ui.S
        x = self.x_of(self.app.seq.position)
        if x < LW or x > c.winfo_width() // ui.S:
            return
        c.create_polygon(s(x - 4), 0, s(x + 4), 0, s(x), s(5), fill='#808080', outline='#000000', tags='pos')
        c.create_line(s(x), s(TL_H), s(x), s(H), fill='#3f3f3f', dash=(1, 1), tags='pos')

    def _update_scroll(self):
        W = self.c.winfo_width() // ui.S
        end = max(1, self._extent())
        page = (W - X0) * self.tpp
        self.hbar.set(self.x0 / end, min(1.0, (self.x0 + page) / end))

    # ------------------------------------------------------------------ info line
    def selected(self):
        return [p for p in self.cond.points if p.selected]

    def deselect_all(self):
        for p in self.cond.points:
            p.selected = False

    def update_info(self):
        il = self.info
        sel = self.selected()
        il.clear()
        if not sel:
            return
        p = min(sel, key=lambda q: q.tick)
        first = self.cond.of(p.kind)[0] is p
        tm = self.app.tmap

        def adj_pos(d, big):
            if first:
                return
            step = self.snap_step(p.tick)
            delta = (1 if d > 0 else -1) * step * (10 if big else 1)
            for q in self.selected():
                if self.cond.of(q.kind)[0] is not q:
                    q.tick = max(1, q.tick + delta)
            self._changed()

        def adj_val(d, big):
            for q in self.selected():
                if q.kind != p.kind:
                    continue
                if q.kind == COND_TEMPO:
                    q.value = max(20, min(T_MAX, q.value + d * (10 if big else 1)))
                elif q.kind == COND_TIMESIG:
                    n = len(resources.tables()['timesig_num'])
                    q.value = max(0, min(n - 1, q.value + (1 if d > 0 else -1)))
                else:
                    q.value = (q.value + (1 if d > 0 else -1)) % 12
            self._changed()

        il.set(0, tm.fmt(p.tick), adj_pos)
        if p.kind == COND_TEMPO:
            il.set(1, str(p.value), adj_val)
        elif p.kind == COND_TIMESIG:
            il.set(2, ts_label(p.value), adj_val)
        else:
            il.set(3, key_label(p.value), adj_val)

    def _changed(self):
        self.app.song.modified = True
        self.app.song_changed('conductor')

    # ------------------------------------------------------------------ mouse
    def hit(self, x, y):
        reg = self.region(y)
        if reg == 'time':
            return None
        if reg == COND_TEMPO:
            for p in reversed(self.cond.of(COND_TEMPO)):
                px, py = self.x_of(p.tick), self.y_of_tempo(p.value)
                if abs(px - x) <= 5 and abs(py - y) <= 5:
                    return p
            return None
        for p in reversed(self.cond.of(reg)):
            px = self.x_of(p.tick)
            txt = ts_label(p.value) if reg == COND_TIMESIG else key_label(p.value)
            if px - 1 <= x <= px + ui.text_width(txt, 'small') + 3:
                return p
        return None

    def _press(self, ev):
        self.c.focus_set()
        x, y = ev.x / ui.S, ev.y / ui.S
        reg = self.region(y)
        if reg == 'time':
            if ev.state & 0x4:
                self.app.locate(self.snap_tick(self.tick_of(x)))
            return
        tool = self.tool.current
        p = self.hit(x, y)
        if tool == 'pencil':
            self.insert_point(reg, x, y)
            return
        if tool == 'eraser':
            if p is not None:
                self.erase(p)
            return
        if p is None:
            if not ui.is_shift(ev):
                self.deselect_all()
            self.drag = {'mode': 'lasso', 'x': x, 'y': y}
            self.redraw()
            return
        if ui.is_shift(ev):
            p.selected = not p.selected
            self.redraw()
            return
        if not p.selected:
            self.deselect_all()
            p.selected = True
        self.drag = {'mode': 'move', 'x': x, 'y': y, 'p': p, 'copy': bool(ev.state & 0x4),
                     'orig': [(q, q.tick, q.value) for q in self.selected()], 'moved': False}
        self.redraw()

    def _motion(self, ev):
        d = self.drag
        if not d:
            return
        x, y = ev.x / ui.S, ev.y / ui.S
        c = self.c
        if d['mode'] == 'lasso':
            c.delete('lasso')
            c.create_rectangle(s(d['x']), s(d['y']), s(x), s(y), outline='#000000', dash=(2, 2), tags='lasso')
            return
        if not d['moved'] and abs(x - d['x']) + abs(y - d['y']) < 3:
            return
        if not d['moved']:
            self.app.checkpoint()
            if d['copy']:
                new = []
                for q, t, v in d['orig']:
                    n = CondPoint(t, q.kind, v)
                    q.selected = False
                    n.selected = True
                    self.cond.points.append(n)
                    new.append((n, t, v))
                d['orig'] = new
            d['moved'] = True
        p = d['p']
        dt = self.snap_tick(self.tick_of(x)) - self.snap_tick(self.tick_of(d['x']))
        dv = self.tempo_of_y(y) - self.tempo_of_y(d['y'])
        for q, t, v in d['orig']:
            is_first = self.cond.of(q.kind)[0] is q and t == 0
            if not is_first:
                q.tick = max(0, t + dt)
            if q.kind == COND_TEMPO:
                q.value = max(20, min(T_MAX, v + dv))
        self.app.tmap.__init__(self.app.song)
        self.redraw()

    def _release(self, ev):
        d = self.drag
        self.drag = None
        if not d:
            return
        if d['mode'] == 'lasso':
            self.c.delete('lasso')
            x, y = ev.x / ui.S, ev.y / ui.S
            x0, x1 = sorted((d['x'], x))
            y0, y1 = sorted((d['y'], y))
            for p in self.cond.points:
                px = self.x_of(p.tick)
                if p.kind == COND_TEMPO:
                    py = self.y_of_tempo(p.value)
                elif p.kind == COND_TIMESIG:
                    py = TL_H + ROW / 2
                else:
                    py = TL_H + ROW * 1.5
                if x0 <= px <= x1 and y0 <= py <= y1:
                    p.selected = True
            self.redraw()
            return
        if d['moved']:
            self._resolve_duplicates()
            self._changed()

    def _resolve_duplicates(self):
        """Two points of the same kind at one position: the moved (selected) one wins."""
        seen = {}
        for p in sorted(self.cond.points, key=lambda q: (q.kind, q.tick, q.selected)):
            seen[(p.kind, p.tick)] = p
        self.cond.points[:] = list(seen.values())
        for kind in (COND_TEMPO, COND_TIMESIG, COND_KEY):
            if not any(p.kind == kind and p.tick == 0 for p in self.cond.points):
                pts = self.cond.of(kind)
                if pts:
                    pts[0].tick = 0

    # ------------------------------------------------------------------ editing
    def insert_point(self, kind, x, y):
        tick = self.snap_tick(self.tick_of(x))
        if kind == COND_TIMESIG:
            tick = self.app.tmap.bar_tick(tick)
        if any(p.kind == kind and p.tick == tick for p in self.cond.points):
            message_box(self.app, resources.string(75), kind='info')
            return
        self.app.checkpoint()
        value = {COND_TEMPO: self.tempo_of_y(y), COND_TIMESIG: 3, COND_KEY: 0}[kind]
        self.deselect_all()
        p = CondPoint(tick, kind, value)
        p.selected = True
        self.cond.points.append(p)
        self._changed()

    def erase(self, p):
        victims = self.selected() if p.selected else [p]
        firsts = {id(self.cond.of(k)[0]) for k in (COND_TEMPO, COND_TIMESIG, COND_KEY)}
        victims = [q for q in victims if id(q) not in firsts]
        if not victims:
            return
        self.app.checkpoint()
        self.cond.points[:] = [q for q in self.cond.points if q not in victims]
        self._changed()

    def edit_copy(self, cut=False):
        sel = self.selected()
        if not sel:
            message_box(self.app, resources.string(16), kind='info')
            return
        t0 = min(p.tick for p in sel)
        self.app.clipboard = CondClip([CondPoint(p.tick - t0, p.kind, p.value) for p in sel])
        if cut:
            self.edit_clear()

    def edit_cut(self):
        self.edit_copy(cut=True)

    def edit_paste(self):
        cb = self.app.clipboard
        if not isinstance(cb, CondClip):
            message_box(self.app, resources.string(66), kind='info')
            return
        self.app.checkpoint()
        self.deselect_all()
        pos = self.app.seq.position
        for p in cb.points:
            n = CondPoint(p.tick + pos, p.kind, p.value)
            n.selected = True
            self.cond.points.append(n)
        self._resolve_duplicates()
        self._changed()

    def edit_clear(self):
        sel = self.selected()
        if sel:
            self.erase(sel[0])

    def edit_select_all(self):
        for p in self.cond.points:
            p.selected = True
        self.redraw()

    def key(self, ev):
        if ev.keysym not in ('Up', 'Down'):
            return False
        sel = self.selected()
        if not sel:
            return True
        p = sel[0]
        pts = self.cond.of(p.kind)
        i = pts.index(p) + (1 if ev.keysym == 'Down' else -1)
        if 0 <= i < len(pts):
            self.deselect_all()
            pts[i].selected = True
            self.redraw()
        return True
