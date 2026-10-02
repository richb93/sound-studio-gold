"""The floating tool windows: Transport, Editors strip, Fast Menu and the Large Time Display."""
import tkinter as tk

from . import ui
from .mdi import Floating
from .ui import s
from .timing import TimeMap, smpte, ts_parts
from .song import COND_TIMESIG


class Transport(Floating):
    """604 x 74 tape-recorder bar (TRANSPORTWNDPROC)."""
    W, H = 602, 72
    GROUPS = [
        (76, [('TB_RTZ', 'rtz'), ('TB_END', 'end')]),
        (145, [('TB_REW', 'rew'), ('TB_FWD', 'fwd'), ('TB_STOP', 'stop'), ('TB_PLAY', 'play'),
               ('TB_REC', 'rec')]),
        (307, [('METRO', 'metronome'), ('CYCLE', 'cycle'), ('FOLLOW', 'follow'), ('CONDUCTOR', 'conductor'),
               ('EDSOLO', 'edit_solo'), ('SYNC', 'sync'), ('PUNCH', 'punch')]),
    ]
    # (label, x0, x1) of the value boxes on the bottom row
    BOXES = [('Time', 4, 82), ('Position', 99, 177), ('Left Locator', 194, 272),
             ('Right Locator', 289, 367), ('Tempo', 384, 437), ('TimeSig', 454, 507), ('Chord', 524, 592)]

    def __init__(self, client, app):
        super().__init__(client, 'Transport', self.W, self.H)
        self.app = app
        self.c = tk.Canvas(self.body, width=s(self.W), height=s(self.H), bg=ui.FACE, highlightthickness=0, bd=0)
        self.c.pack(fill='both', expand=True)
        self.pressed = None
        self.values = {}
        self.c.bind('<ButtonPress-1>', lambda e: self._press(e, 1))
        self.c.bind('<ButtonRelease-1>', lambda e: self._release(e, 1))
        ui.bind_right(self.c, 'ButtonPress', lambda e: self._press(e, 3))
        ui.bind_right(self.c, 'ButtonRelease', lambda e: self._release(e, 3))
        self.rep = ui.Repeater(self.c)
        self.draw()

    # ---- drawing
    def draw(self):
        c = self.c
        c.delete('all')
        ui.raised(c, 0, 0, 598, 67, outer=False)
        ui.text(c, 34, 8, 'Auto Return', 'small', anchor='center')
        ui.text(c, 563, 8, 'Record Mode', 'small', anchor='center')
        for gx, btns in self.GROUPS:
            x = gx
            for bmp, key in btns:
                self._draw_button(x, 3, bmp, key)
                x += 31
        for label, x0, x1 in self.BOXES:
            ui.text(c, (x0 + x1) // 2, 42, label, 'small', anchor='center')
        self.update_values(force=True)

    def _button_image(self, bmp, key):
        a = self.app
        if key in ('rtz', 'end', 'rew', 'fwd', 'stop', 'play', 'rec'):
            down = self.pressed == key or (key == 'play' and a.seq.playing and not a.seq.recording) \
                or (key == 'rec' and a.seq.playing and a.seq.recording) or (key == 'stop' and not a.seq.playing)
            return bmp + ('_PR' if down else '')
        on = getattr(a.seq.opts, key)
        return bmp + ('_ON' if on else '_OFF')

    def _draw_button(self, x, y, bmp, key):
        tag = 'b_' + key
        self.c.delete(tag)
        ui.image(self.c, x, y, self.app.images.get(self._button_image(bmp, key)), tags=tag)

    def redraw_buttons(self):
        for gx, btns in self.GROUPS:
            x = gx
            for bmp, key in btns:
                self._draw_button(x, 3, bmp, key)
                x += 31

    def _box(self, x0, x1, y0, txt, tag):
        c = self.c
        tid = self._box_text.get(tag) if hasattr(self, '_box_text') else None
        if tid is not None and c.type(tid) == 'text':
            c.itemconfigure(tid, text=txt)       # the frame is already there
            return
        c.delete(tag)
        ui.sunken(c, x0, y0, x1 + 1, y0 + 15, fill=ui.FACE, deep=False, tags=tag)
        self.__dict__.setdefault('_box_text', {})[tag] = ui.text(c, (x0 + x1 + 1) // 2, y0 + 7, txt, 'smallbold',
                                                                 anchor='center', tags=tag)

    def update_values(self, force=False):
        a = self.app
        song = a.song
        tm = a.tmap
        pos = a.seq.position
        o = a.seq.opts
        tempo = tm.bpm_at(pos) if o.conductor else o.fixed_tempo
        sig = song.conductor.at(COND_TIMESIG, pos) if o.conductor else song.conductor.of(COND_TIMESIG)[0]
        num, den = ts_parts(sig.value)
        vals = {
            'Time': smpte(tm.to_ms(pos), a.fps(), song.smpte_start),
            'Position': tm.fmt(pos),
            'Left Locator': tm.fmt(song.left),
            'Right Locator': tm.fmt(song.right),
            'Tempo': str(tempo),
            'TimeSig': '%d / %d' % (num, den),
            'Chord': a.chord_name or '',
            'auto': ['Off', 'Zero', 'Last Start'][o.auto_return],
            'mode': ['Replace', 'Overdub'][o.record_mode],
        }
        for k, v in vals.items():
            if not force and self.values.get(k) == v:
                continue
            self.values[k] = v
            if k == 'auto':
                self._box(5, 67, 17, v, 'v_auto')
            elif k == 'mode':
                self._box(535, 592, 17, v, 'v_mode')
            else:
                for label, x0, x1 in self.BOXES:
                    if label == k:
                        self._box(x0 + 1, x1, 50, v, 'v_' + label)

    # ---- mouse
    def _hit(self, ev):
        x, y = ev.x / ui.S, ev.y / ui.S
        for gx, btns in self.GROUPS:
            for i, (_bmp, key) in enumerate(btns):
                bx = gx + i * 31
                if bx <= x < bx + 32 and 3 <= y < 35:
                    return ('btn', key)
        if 5 <= x < 68 and 17 <= y < 32:
            return ('auto', None)
        if 535 <= x < 593 and 17 <= y < 32:
            return ('mode', None)
        for label, x0, x1 in self.BOXES:
            if x0 <= x <= x1 and 50 <= y < 65:
                return ('box', label)
            if x0 <= x <= x1 and 36 <= y < 49:
                return ('label', label)
        return None

    def _press(self, ev, button):
        h = self._hit(ev)
        if not h:
            if button == 3:
                self.app.floating_menu(self, ev)
            return
        kind, key = h
        a = self.app
        if kind == 'btn':
            if key in ('rew', 'fwd'):
                self.pressed = key
                self.redraw_buttons()
                self.rep.start(ev, lambda d, big: a.wind(-1 if key == 'rew' else 1, big), button)
                return
            if key in ('rtz', 'end', 'stop', 'play', 'rec'):
                self.pressed = key
                self.redraw_buttons()
                return
            a.toggle_option(key)
        elif kind == 'auto' and button == 1:
            a.seq.opts.auto_return = (a.seq.opts.auto_return + 1) % 3
            self.update_values()
        elif kind == 'mode' and button == 1:
            a.seq.opts.record_mode ^= 1
            self.update_values()
        elif kind == 'label' and key in ('Left Locator', 'Right Locator'):
            a.locate(a.song.left if key == 'Left Locator' else a.song.right)
        elif kind == 'box':
            self.rep.start(ev, lambda d, big: a.adjust_transport(key, d, big), button)

    def _release(self, ev, button):
        self.rep.stop(button)
        key = self.pressed
        if key is None:
            return
        self.pressed = None
        h = self._hit(ev)
        a = self.app
        if h and h == ('btn', key):
            {'rtz': a.return_to_zero, 'end': a.go_to_end, 'stop': a.stop,
             'play': a.play, 'rec': a.record}.get(key, lambda: None)()
        self.redraw_buttons()


class Editors(Floating):
    """Vertical strip of editor buttons (WB_* bitmaps, WBP_* when pressed)."""
    ITEMS = [('TRACK', 80), ('PROLL', 81), ('EVENT', 82), ('SCORE', 83), ('DRUM', 84), None,
             ('COND', 85), ('NOTE', 86), ('MIXER', 87), ('KEY', 88), ('LYRIC', 89), ('ICT', 90),
             ('AUDIO', 91)]
    W = 36

    def __init__(self, client, app):
        self.layout = []
        y = 1
        for it in self.ITEMS:
            if it is None:
                y += 8
                continue
            self.layout.append((y, it[0], it[1]))
            y += 31
        super().__init__(client, 'Editors', self.W, y + 5)
        self.app = app
        self.c = tk.Canvas(self.body, width=s(self.W), height=s(self.h), bg=ui.FACE, highlightthickness=0, bd=0)
        self.c.pack(fill='both', expand=True)
        self.down = None
        self.c.bind('<ButtonPress-1>', self._press)
        self.c.bind('<ButtonRelease-1>', self._release)
        ui.bind_right(self.c, 'ButtonPress', lambda e: app.floating_menu(self, e))
        self.draw()

    def draw(self):
        c = self.c
        c.delete('all')
        ui.raised(c, 0, 0, self.W, self.h, outer=False)
        for y, name, cid in self.layout:
            img = ('WBP_' if self.down == cid else 'WB_') + name
            ui.image(c, 1, y, self.app.images.get(img))

    def _hit(self, ev):
        y = ev.y / ui.S
        for yy, _n, cid in self.layout:
            if yy <= y < yy + 32:
                return cid
        return None

    def _press(self, ev):
        self.down = self._hit(ev)
        self.draw()

    def _release(self, ev):
        cid = self.down
        self.down = None
        self.draw()
        if cid is not None and self._hit(ev) == cid:
            self.app.command(cid)


class FastMenu(Floating):
    """Up to ten user-chosen commands (Window > Configure Fast Menu)."""
    W = 103
    BH = 20

    def __init__(self, client, app):
        super().__init__(client, 'Fast Menu', self.W, self.BH * 10 - 4)
        self.app = app
        self.c = tk.Canvas(self.body, width=s(self.W), height=s(self.h), bg=ui.FACE, highlightthickness=0, bd=0)
        self.c.pack(fill='both', expand=True)
        self.down = None
        self.c.bind('<ButtonPress-1>', self._press)
        self.c.bind('<ButtonRelease-1>', self._release)
        ui.bind_right(self.c, 'ButtonPress', lambda e: app.floating_menu(self, e))
        self.draw()

    def items(self):
        return self.app.settings['fast_menu']

    def draw(self):
        c = self.c
        c.delete('all')
        items = self.items()
        self.h = max(1, len(items)) * self.BH - 4
        for i, name in enumerate(items):
            y = i * self.BH
            if self.down == i:
                ui.sunken(c, 0, y, self.W, y + self.BH - 3, fill=ui.FACE)
            else:
                ui.raised(c, 0, y, self.W, y + self.BH - 3, outer=False)
                ui.line(c, 0, y + self.BH - 4, self.W, y + self.BH - 4, fill=ui.SHADOW)
            o = 1 if self.down == i else 0
            ui.text(c, self.W // 2 + o, y + 8 + o, name, 'small', anchor='center')

    def resize(self):
        self.h = max(1, len(self.items())) * self.BH - 4
        self.place_at(*self.pos)
        self.draw()

    def _hit(self, ev):
        i = int(ev.y / ui.S) // self.BH
        return i if 0 <= i < len(self.items()) else None

    def _press(self, ev):
        self.down = self._hit(ev)
        self.draw()

    def _release(self, ev):
        i = self.down
        self.down = None
        self.draw()
        if i is not None and self._hit(ev) == i:
            self.app.fast_command(self.items()[i])


class BigTime(Floating):
    """Large Time Display: yellow Arial 30 bold on black."""
    W, H = 212, 30

    def __init__(self, client, app):
        super().__init__(client, 'Time', self.W, self.H)
        self.app = app
        self.c = tk.Canvas(self.body, width=s(self.W), height=s(self.H), bg='black', highlightthickness=0, bd=0)
        self.c.pack(fill='both', expand=True)
        self.txt = self.c.create_text(s(self.W // 2), s(self.H // 2), text='00:00:00:00', fill='#ffc800',
                                      font=ui.f('bigtime'))
        ui.bind_right(self.c, 'ButtonPress', lambda e: app.floating_menu(self, e))

    def set(self, t):
        self.c.itemconfigure(self.txt, text=t)
