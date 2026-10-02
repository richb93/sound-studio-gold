"""Mixer window (MDIMIXERWNDPROC): 16 channels per MIDI output, plus the Audio channels.

All mixers form one long window; the buttons across the top jump to a port and the
vertical scroll bar scrolls through them.  Each MIDI channel has, from the top: Record,
Flat, two user-definable knobs (Reverb and Chorus by default), Pan, Solo, Mute and a
Volume fader with a velocity meter; the Audio channels have Record, Depth, Delay, Pan,
Solo, Mute and a fader.
"""
import math
import tkinter as tk

from .. import ui
from ..mdi import MDIChild, BORDER, CAPTION_H
from ..ui import s
from ..song import MIDI, AUDIO, OFF, PAN_OFF
from .common import controller_label

STRIP = 36
HEAD = 13
LABEL = '#000080'
GROUP_COLOURS = ['#ff0000', '#00ff00', '#ffff00', '#0000ff', '#ff00ff', '#00ffff', '#ffffff', '#000000']
SHORT = {91: 'Reverb', 93: 'Chorus', 1: 'Mod', 7: 'Volume', 10: 'Pan', 11: 'Express', 64: 'Sustain',
         71: 'Reso', 72: 'Release', 73: 'Attack', 74: 'Cutoff', 94: 'Variation', 5: 'Porta'}

# control layouts: (kind, key, y) relative to the top of a page (the channel-number row)
MIDI_LAYOUT = [('button', 'rec', 16, 'Record'), ('flat', 'flat', 43, 'Flat'),
               ('knob', 'user0', 70, None), ('knob', 'user1', 110, None), ('knob', 'pan', 150, 'Pan'),
               ('button', 'solo', 190, 'Solo'), ('button', 'mute', 217, 'Mute'), ('fader', 'vol', 244, None)]
AUDIO_LAYOUT = [('button', 'rec', 16, 'Record'), ('knob', 'depth', 43, 'Depth'), ('knob', 'delay', 83, 'Delay'),
                ('knob', 'pan', 123, 'Pan'), ('button', 'solo', 163, 'Solo'), ('button', 'mute', 190, 'Mute'),
                ('fader', 'vol', 217, None)]
VOL_LAYOUT = [('fader', 'vol', 16, None)]
FADER_H = 96
CAP_H = 22
KNOB_COLOURS = {'user0': 'KNOB_RED', 'user1': 'KNOB_BLUE', 'pan': 'KNOB_PUR', 'depth': 'KNOB_RED',
                'delay': 'KNOB_BLUE'}


def short_name(ctrl):
    return SHORT.get(ctrl, controller_label(ctrl).split(' ')[0][:7])


class Channel:
    def __init__(self):
        self.vol = 100
        self.pan = 64
        self.user = [0, 0]
        self.solo = False
        self.mute = False
        self.group = 0
        self.meter = 0.0


class MixerWindow(MDIChild):
    icon_name = 'IC_MIXER'

    def __init__(self, client, app):
        self.app = app
        self.top = 0
        self.drag = None
        st = app.__dict__.setdefault('mixer_state', {})
        self.state_ = st
        super().__init__(client, 'Mixer', app.small_icon(self.icon_name), 0, 0, 100, 100)
        self._build()
        self.auto_size(place=True)
        if not app.seq.playing:
            self.seed_from_song()
        self._tick()

    # ------------------------------------------------------------------ model
    @property
    def cfg(self):
        m = self.app.settings['mixer']
        m.setdefault('users', [[93, 0, 0, 127], [91, 0, 0, 127]])
        return m

    def ports(self):
        return self.app.midi.port_labels()

    def pages(self):
        return [('midi', i, nm) for i, nm in enumerate(self.ports())] + [('audio', 0, 'Audio')]

    def chan(self, port, ch):
        key = (port, ch)
        c = self.state_.get(key)
        if c is None:
            c = Channel()
            c.user = [u[1] for u in self.cfg['users']]
            self.state_[key] = c
        return c

    def port_enabled(self, port):
        outs = self.app.midi.outs
        return port < len(outs) and outs[port][1] is not None

    def audio_tracks(self):
        return [t for t in self.app.song.tracks if t.kind == AUDIO][:16]

    def layout(self, kind):
        if self.cfg.get('volumes_only'):
            return VOL_LAYOUT
        return AUDIO_LAYOUT if kind == 'audio' else MIDI_LAYOUT

    def page_height(self, kind):
        lay = self.layout(kind)
        return lay[-1][2] + FADER_H + 16

    def page_tops(self):
        y = 0
        out = []
        for pg in self.pages():
            out.append(y)
            y += self.page_height(pg[0])
        return out, y

    # ------------------------------------------------------------------ layout
    def _build(self):
        b = self.body
        self.vbar = tk.Scrollbar(b, orient='vertical', command=self._vscroll)
        self.vbar.pack(side='right', fill='y')
        self.tb = tk.Canvas(b, height=s(18), bg=ui.FACE, highlightthickness=0, bd=0)
        self.tb.pack(side='top', fill='x')
        self.tb.bind('<Configure>', lambda e: self.draw_toolbar())
        self.tb.bind('<ButtonPress-1>', self._tb_press)
        self.tb.bind('<ButtonRelease-1>', self._tb_release)
        self.c = tk.Canvas(b, bg=ui.FACE, highlightthickness=0, bd=0)
        self.c.pack(side='top', fill='both', expand=True)
        self.c.bind('<Configure>', lambda e: self.redraw())
        self.c.bind('<ButtonPress-1>', self._press)
        self.c.bind('<B1-Motion>', self._motion)
        self.c.bind('<ButtonRelease-1>', self._release)
        ui.bind_right(self.c, 'ButtonPress', self._right)
        for w in (self.c,):
            w.bind('<MouseWheel>', lambda e: self._vscroll('scroll', -1 if e.delta > 0 else 1, 'units'))
            w.bind('<Button-4>', lambda e: self._vscroll('scroll', -1, 'units'))
            w.bind('<Button-5>', lambda e: self._vscroll('scroll', 1, 'units'))
        self._tb_down = None

    def auto_size(self, place=False):
        """Resize the window to exactly one set of 16 channels."""
        tops, _total = self.page_tops()
        idx = self.current_page()
        kind = self.pages()[idx][0]
        w = 16 * STRIP + 16 + 2 * BORDER
        h = CAPTION_H + 18 + self.page_height(kind) + 2 * BORDER + 1
        x, y = (0, 0) if place else self.geometry()[:2]
        if self.state != 'normal':
            self.restore()
        self.move_to(x, y, w, h)
        self.top = tops[idx]
        self.redraw()

    def current_page(self):
        tops, _ = self.page_tops()
        idx = 0
        for i, t in enumerate(tops):
            if self.top >= t - 2:
                idx = i
        return idx

    def _vscroll(self, *a):
        _tops, total = self.page_tops()
        H = self.c.winfo_height() // ui.S
        if a[0] == 'moveto':
            self.top = int(float(a[1]) * total)
        else:
            self.top += int(a[1]) * (STRIP if a[2] == 'units' else max(20, H - 20))
        self.top = max(0, min(self.top, max(0, total - H)))
        self.redraw()

    # ------------------------------------------------------------------ drawing
    def refresh(self, what=None):
        if what in ('mixer', 'patterns', 'tracks', 'events'):
            self.update_strips()              # names, record buttons: only the strips that changed
        else:
            self.redraw()

    def draw_toolbar(self):
        c = self.tb
        c.delete('all')
        W = c.winfo_width() // ui.S
        img = self.app.images.get
        x = 0
        self.tb_items = []
        for key, bmp in (('snap', 'MIX_CAMERA'), ('auto', 'MIX_AUTO'), ('close', 'BUT_CLOSE'),
                         ('flat', 'BUT_ALLFLAT')):
            im = img(bmp + ('_PR' if self._tb_down == key else ''))
            ui.image(c, x, 0, im)
            w = im.width() // ui.S
            self.tb_items.append((x, x + w, key))
            x += w - 1
        # port buttons fill the rest of the row
        pages = self.pages()
        cur = self.current_page()
        x0 = x + 1
        bw = (W - x0) / max(1, len(pages))
        for i, (_k, _p, name) in enumerate(pages):
            bx0, bx1 = int(x0 + i * bw), int(x0 + (i + 1) * bw)
            ui.raised(c, bx0, 0, bx1, 18, outer=False)
            ui.text(c, (bx0 + bx1) // 2, 9, ui.clip_text(name, bx1 - bx0 - 4, 'small'), 'small',
                    fill='#0000ff' if i == cur else '#000000', anchor='center')
            self.tb_items.append((bx0, bx1, ('page', i)))

    def redraw(self):
        if not self.winfo_exists():
            return
        c = self.c
        c.delete('all')
        W, H = c.winfo_width() // ui.S, c.winfo_height() // ui.S
        tops, total = self.page_tops()
        self.hits = []
        self.strips = {}
        for (kind, port, _name), top in zip(self.pages(), tops):
            y0 = top - self.top
            ph = self.page_height(kind)
            if y0 > H or y0 + ph < 0:
                continue
            self._draw_page(kind, port, y0)
        self.draw_toolbar()
        if total:
            self.vbar.set(self.top / total, min(1.0, (self.top + H) / total))

    def _draw_page(self, kind, port, y0):
        for i in range(16):
            self._draw_strip(kind, port, i, y0)

    def _strip_state(self, kind, port, i):
        """What a channel strip shows (except its meter)."""
        if kind == 'audio':
            tracks = self.audio_tracks()
            t = tracks[i] if i < len(tracks) else None
            vals = self._audio_vals(t)
            on = True
        else:
            vals = self._midi_vals(port, i)
            on = self.port_enabled(port)
        meter = vals.pop('meter', 0)
        under = self._under_text(kind, port, i, self.audio_tracks() if kind == 'audio' else None)
        sig = (tuple(sorted(vals.items())), on, self._flat_down == (port, i), under)
        return vals, on, under, meter, sig

    def _draw_strip(self, kind, port, i, y0):
        """Draw one channel strip; its items share a tag so it can be redrawn on its own."""
        c = self.c
        key = (kind, port, i)
        tag = 'strip_%s_%s_%d' % (kind, port, i)
        c.delete(tag)
        self.hits = [h for h in self.hits if (h[4], h[5], h[6]) != key]
        vals, on, under, meter, sig = self._strip_state(kind, port, i)
        lay = self.layout(kind)
        ph = self.page_height(kind)
        first = c.create_line(0, 0, 0, 0, fill='', tags=tag)        # marks where the strip starts
        x0 = i * STRIP
        ui.line(c, x0, y0, x0, y0 + ph - 1, fill='#ffffff')
        ui.line(c, x0 + STRIP - 1, y0, x0 + STRIP - 1, y0 + ph - 1, fill=ui.SHADOW)
        ui.line(c, x0, y0, x0 + STRIP - 1, y0, fill='#ffffff')
        ui.line(c, x0, y0 + HEAD - 1, x0 + STRIP - 1, y0 + HEAD - 1, fill=ui.SHADOW)
        ui.text(c, x0 + STRIP // 2, y0 + HEAD // 2, str(i + 1), 'small', anchor='center')
        info = {'y0': y0, 'sig': sig, 'meter': None, 'meter_val': -1}
        for ctl, ckey, y, label in lay:
            yy = y0 + y
            if ctl == 'button':
                pressed = vals.get(ckey, False)
                ui.image(c, x0 + 5, yy, self._button_img(ckey, pressed and on))
                self.hits.append((x0 + 5, yy, x0 + 32, yy + 12, kind, port, i, ckey))
            elif ctl == 'flat':
                ui.image(c, x0 + 3, yy, self.app.images.get('FLAT_PRESSED' if self._flat_down == (port, i)
                                                            else 'FLAT_BUT'))
                self.hits.append((x0 + 3, yy, x0 + 33, yy + 12, kind, port, i, ckey))
            elif ctl == 'knob':
                lo, hi = self._range(ckey)
                self._knob(x0 + 6, yy, vals.get(ckey, lo), lo, hi, KNOB_COLOURS[ckey] if on else 'KNOB_GREY')
                self.hits.append((x0 + 6, yy, x0 + 31, yy + 25, kind, port, i, ckey))
                if label is None:
                    label = short_name(self.cfg['users'][int(ckey[-1])][0])
            elif ctl == 'fader':
                info['meter'] = self._fader(x0, yy, vals.get('vol', 0), vals.get('group', 0), on)
                info['meter_y'] = yy
                self.hits.append((x0 + 3, yy, x0 + 25, yy + FADER_H, kind, port, i, 'vol'))
                ui.text(c, x0 + 1, yy + FADER_H + 6, ui.clip_text(under, STRIP - 1, 'mixer'), 'mixer',
                        fill=LABEL if on else ui.SHADOW, anchor='w')
            if label:
                ly = yy + (17 if ctl in ('button', 'flat') else 30)
                ui.text(c, x0 + STRIP // 2, ly, ui.clip_text(label, STRIP - 2, 'mixer'), 'mixer',
                        fill=LABEL if on else ui.SHADOW, anchor='center')
                label = None
        for item in c.find_all():
            if item > first:
                c.addtag_withtag(tag, item)
        info['on'] = on
        self.strips[key] = info
        self._set_meter(key, meter)

    def _set_meter(self, key, meter):
        info = self.strips.get(key)
        if not info or info['meter'] is None:
            return
        h = int(meter / 127.0 * (FADER_H - 2)) if info['on'] else 0
        if h == info['meter_val']:
            return
        info['meter_val'] = h
        x0, y = key[2] * STRIP, info['meter_y']
        self.c.coords(info['meter'], s(x0 + 27), s(y + FADER_H - 1 - h), s(x0 + 32), s(y + FADER_H - 1))

    def update_strips(self):
        """Bring the strips up to date, redrawing only those whose settings changed (meters move
        on their own): far cheaper than redraw() while the song plays or a control is dragged."""
        if not self.winfo_exists() or not hasattr(self, 'strips'):
            return self.redraw()
        for key, info in list(self.strips.items()):
            kind, port, i = key
            if kind != 'audio':
                meter = self.chan(port, i).meter
            else:
                tracks = self.audio_tracks()
                meter = self.chan('audio', id(tracks[i])).meter if i < len(tracks) else 0
            if self._strip_state(kind, port, i)[4] != info['sig']:
                self._draw_strip(kind, port, i, info['y0'])
            else:
                self._set_meter(key, meter)

    _flat_down = None

    def _button_img(self, key, pressed):
        if key == 'rec':
            return self.app.images.get('REC_PRESSED' if pressed else 'REC_BUT')
        if key == 'solo' and pressed:
            return self._solo_img()
        return self.app.images.get('MUTE_PRESSED' if pressed else 'MUTE_BUT')

    def _solo_img(self):
        """The Solo button lights green: the Mute bitmap with its blue LED recoloured."""
        cache = self.app.images.cache
        img = cache.get('SOLO_PRESSED')
        if img is None:
            src = self.app.images.get('MUTE_PRESSED')
            img = src.copy()
            for y in range(img.height()):
                for x in range(img.width()):
                    r, g, b = img.get(x, y)
                    if b > 100 and r < 100 and g < 100:
                        img.put('#%02x%02x%02x' % (r, b, g), (x, y))
            cache['SOLO_PRESSED'] = img
        return img

    def _knob(self, x, y, v, lo, hi, bmp):
        c = self.c
        ui.image(c, x, y, self.app.images.get(bmp))
        frac = 0.5 if hi == lo else (v - lo) / float(hi - lo)
        a = math.radians(-135 + 270 * max(0.0, min(1.0, frac)))
        cx, cy = x + 12.5, y + 12.5
        ex, ey = cx + 9 * math.sin(a), cy - 9 * math.cos(a)
        c.create_line(s(cx + 1), s(cy), s(ex + 1), s(ey), fill='#ffffff', width=ui.S)
        c.create_line(s(cx), s(cy), s(ex), s(ey), fill='#000000', width=ui.S)

    def _fader(self, x0, y, vol, group, on):
        """Fader and velocity meter; returns the meter bar (sized by _set_meter)."""
        c = self.c
        img = self.app.images.get
        ui.image(c, x0 + 3, y, img('SLIDER_BM'))
        cy = y + int(round((127 - max(0, min(127, vol))) * (FADER_H - CAP_H) / 127.0))
        cap = self._cap_img()
        ui.image(c, x0 + 3, cy, cap)
        band = GROUP_COLOURS[group - 1] if group else ui.SHADOW
        c.create_rectangle(s(x0 + 6), s(cy + 10), s(x0 + 19), s(cy + 11), fill=band, outline='')
        # velocity meter
        ui.line(c, x0 + 26, y, x0 + 26, y + FADER_H - 1, fill=ui.SHADOW)
        ui.line(c, x0 + 26, y + FADER_H - 1, x0 + 34, y + FADER_H - 1, fill='#ffffff')
        ui.line(c, x0 + 33, y, x0 + 33, y + FADER_H - 1, fill='#ffffff')
        c.create_rectangle(s(x0 + 27), s(y), s(x0 + 32), s(y + FADER_H - 1), fill='#000000', outline='')
        return c.create_rectangle(s(x0 + 27), s(y + FADER_H - 1), s(x0 + 32), s(y + FADER_H - 1),
                                  fill='#00ff00', outline='', tags='meter')

    def _cap_img(self):
        cache = self.app.images.cache
        img = cache.get('FADER_CAP')
        if img is None:
            src = self.app.images.get('FADER_GREY')
            img = tk.PhotoImage(master=self.app, width=src.width(), height=s(CAP_H))
            img.tk.call(img, 'copy', src, '-from', 0, 0, src.width(), s(CAP_H), '-to', 0, 0)
            cache['FADER_CAP'] = img
        return img

    def _under_text(self, kind, port, ch, tracks):
        if kind == 'audio':
            t = tracks[ch] if ch < len(tracks) else None
            return t.name if t is not None else ''
        mode = self.cfg.get('under', 0)
        if mode == 0:
            return 'Volume'
        t = self._track_for(port, ch)
        if t is None:
            return ''
        if mode == 1:
            return t.name
        return self.app.patches.name(port, ch + 1, t.prog, t.bank) if t.prog >= 0 else ''

    def _track_for(self, port, ch):
        for t in self.app.song.tracks:
            if t.kind == MIDI and self.app.midi.real_port(max(0, t.port)) == port and t.channel == ch + 1:
                return t
        return None

    def _range(self, key):
        if key.startswith('user'):
            u = self.cfg['users'][int(key[-1])]
            return u[2], u[3]
        return 0, 127

    def _midi_vals(self, port, ch):
        c = self.chan(port, ch)
        t = self._track_for(port, ch)
        return {'rec': bool(t is not None and t.rec), 'user0': c.user[0], 'user1': c.user[1], 'pan': c.pan,
                'solo': c.solo, 'mute': c.mute, 'vol': c.vol, 'group': c.group, 'meter': c.meter}

    def _audio_vals(self, t):
        if t is None:
            return {'vol': 127, 'pan': 64, 'depth': 0, 'delay': 0}
        c = self.chan('audio', id(t))
        return {'rec': bool(t.rec), 'depth': max(0, t.reverb), 'delay': max(0, t.chorus),
                'pan': 64 if t.pan == PAN_OFF else t.pan + 64, 'solo': c.solo, 'mute': bool(t.mute),
                'vol': 100 if t.volume == OFF else t.volume, 'group': c.group, 'meter': c.meter}

    # ------------------------------------------------------------------ toolbar
    def _tb_hit(self, ev):
        x = ev.x / ui.S
        for x0, x1, key in self.tb_items:
            if x0 <= x < x1:
                return key
        return None

    def _tb_press(self, ev):
        k = self._tb_hit(ev)
        if isinstance(k, tuple):
            tops, _ = self.page_tops()
            self.top = tops[k[1]]
            self._vscroll('scroll', 0, 'units')
            return
        self._tb_down = k
        self.draw_toolbar()

    def _tb_release(self, ev):
        k = self._tb_down
        self._tb_down = None
        self.draw_toolbar()
        if k is None or self._tb_hit(ev) != k:
            return
        if k == 'close':
            self.close()
        elif k == 'auto':
            self.auto_size()
        elif k == 'flat':
            self.all_flat()
        elif k == 'snap':
            self.snapshot()

    # ------------------------------------------------------------------ sending
    def send(self, port, data):
        self.app.midi.send(port, data)
        if self.cfg.get('record'):
            self.app.seq.record_event(data)

    def send_control(self, port, ch, key):
        c = self.chan(port, ch)
        if key == 'vol':
            self.send(port, bytes([0xB0 | ch, 7, c.vol]))
        elif key == 'pan':
            self.send(port, bytes([0xB0 | ch, 10, c.pan]))
        elif key.startswith('user'):
            i = int(key[-1])
            self.send(port, bytes([0xB0 | ch, self.cfg['users'][i][0] & 0x7F, c.user[i]]))

    def flat_channel(self, port, ch, send=True):
        c = self.chan(port, ch)
        c.vol = 127
        c.pan = 64
        c.user = [u[1] for u in self.cfg['users']]
        if send:
            for k in ('vol', 'pan', 'user0', 'user1'):
                self.send_control(port, ch, k)

    def all_flat(self):
        for port in range(len(self.ports())):
            for ch in range(16):
                self.flat_channel(port, ch, self.port_enabled(port))
        for t in self.audio_tracks():
            t.volume, t.pan, t.reverb, t.chorus = 127, 0, 0, 0
        self.update_strips()

    def snapshot(self):
        for port in range(len(self.ports())):
            if not self.port_enabled(port):
                continue
            for ch in range(16):
                for k in ('vol', 'pan', 'user0', 'user1'):
                    self.send_control(port, ch, k)

    def _sync_mutes(self):
        seq = self.app.seq
        seq.mixer_mute = {k for k, c in self.state_.items() if isinstance(k[0], int) and c.mute}
        seq.mixer_solo = {k for k, c in self.state_.items() if isinstance(k[0], int) and c.solo}

    # ------------------------------------------------------------------ mouse
    def _hit(self, ev):
        x, y = ev.x / ui.S, ev.y / ui.S
        for x0, y0, x1, y1, kind, port, ch, key in self.hits:
            if x0 <= x < x1 and y0 <= y < y1:
                return kind, port, ch, key
        return None

    def _press(self, ev):
        h = self._hit(ev)
        if h is None:
            return
        kind, port, ch, key = h
        if kind == 'midi' and not self.port_enabled(port):
            return
        if kind == 'audio':
            self._audio_press(ev, ch, key)
            return
        c = self.chan(port, ch)
        if key in ('rec', 'solo', 'mute'):
            if key == 'rec':
                t = self._track_for(port, ch)
                if t is not None:
                    tw = self.app.windows.get('track')
                    if tw is not None:
                        tw._toggle_button(t, 'rec')
                    else:
                        t.rec = 0 if t.rec else 1
                        self.app.song_changed('mixer')
            else:
                setattr(c, key, not getattr(c, key))
                self._sync_mutes()
            self.update_strips()
            return
        if key == 'flat':
            self._flat_down = (port, ch)
            self.flat_channel(port, ch)
            self.update_strips()
            self.after(150, self._flat_up)
            return
        if ev.state & 0x4:          # Ctrl-click flattens one control
            if key == 'vol':
                c.vol = 127
            elif key == 'pan':
                c.pan = 64
            else:
                i = int(key[-1])
                c.user[i] = self.cfg['users'][i][1]
            self.send_control(port, ch, key)
            self.update_strips()
            return
        self.drag = (port, ch, key, ev.y, self._get(port, ch, key))

    def _flat_up(self):
        self._flat_down = None
        self.update_strips()

    def _get(self, port, ch, key):
        c = self.chan(port, ch)
        if key == 'vol':
            return c.vol
        if key == 'pan':
            return c.pan
        return c.user[int(key[-1])]

    def _set(self, port, ch, key, v):
        c = self.chan(port, ch)
        lo, hi = (0, 127) if key in ('vol', 'pan') else self._range(key)
        v = max(min(lo, hi), min(max(lo, hi), int(round(v))))
        if v == self._get(port, ch, key):
            return False
        if key == 'vol':
            c.vol = v
        elif key == 'pan':
            c.pan = v
        else:
            c.user[int(key[-1])] = v
        self.send_control(port, ch, key)
        return True

    def _motion(self, ev):
        if not self.drag:
            return
        port, ch, key, y0, v0 = self.drag
        dy = (y0 - ev.y) / ui.S
        if port == 'audio':
            self._audio_motion(ch, key, v0 + dy)
            return
        scale = 127.0 / (FADER_H - CAP_H) if key == 'vol' else 1.0
        new = v0 + dy * scale
        if key == 'vol':
            delta = int(round(new)) - self._get(port, ch, key)
            g = self.chan(port, ch).group
            self._set(port, ch, key, new)
            if g and delta:
                for och in range(16):
                    if och != ch and self.chan(port, och).group == g:
                        self._set(port, och, 'vol', self._get(port, och, 'vol') + delta)
        else:
            self._set(port, ch, key, new)
        self.update_strips()

    def _release(self, _ev):
        self.drag = None

    def _right(self, ev):
        h = self._hit(ev)
        if h is None or h[3] != 'vol':
            return
        kind, port, ch, _k = h
        c = self.chan(port if kind == 'midi' else 'audio', ch if kind == 'midi' else id(self.audio_tracks()[ch]))
        c.group = (c.group + 1) % 9
        self.update_strips()

    # ---- audio channels edit the Audio tracks' settings
    def _audio_press(self, ev, i, key):
        tracks = self.audio_tracks()
        if i >= len(tracks):
            return
        t = tracks[i]
        if key == 'rec':
            t.rec = not t.rec
        elif key == 'mute':
            t.mute = 0 if t.mute else 1
        elif key == 'solo':
            c = self.chan('audio', id(t))
            c.solo = not c.solo
        else:
            v = self._audio_vals(t)[key]
            self.drag = ('audio', i, key, ev.y, v)
            return
        self.app.song.modified = True
        self.app.song_changed('tracks')

    def _audio_motion(self, i, key, v):
        t = self.audio_tracks()[i]
        if key == 'vol':
            v = self.drag[4] + (v - self.drag[4]) * 127.0 / (FADER_H - CAP_H)
        v = max(0, min(127, int(round(v))))
        if key == 'vol':
            t.volume = v
        elif key == 'pan':
            t.pan = v - 64
        elif key == 'depth':
            t.reverb = v
        elif key == 'delay':
            t.chorus = v
        self.app.song.modified = True
        self.redraw()

    # ------------------------------------------------------------------ song / MIDI in to mixer
    def _apply(self, port, data, meter=True):
        st = data[0]
        hi, ch = st & 0xF0, st & 0x0F
        if hi == 0x90 and len(data) > 2 and data[2] and meter:
            c = self.chan(port, ch)
            if not c.mute:
                c.meter = max(c.meter, data[2])
            return True
        if hi == 0xB0 and len(data) > 2:
            c = self.chan(port, ch)
            n, v = data[1], data[2]
            if n == 7:
                c.vol = v
            elif n == 10:
                c.pan = v
            else:
                for i, u in enumerate(self.cfg['users']):
                    if u[0] == n:
                        c.user[i] = v
            return True
        return False

    def seed_from_song(self):
        """Show the song's settings at the play position: each track's volume / pan / effect
        settings, then the controllers its patterns send up to there (as playback chases them)."""
        from ..sequencer import schedule_song
        app = self.app
        for c in self.state_.values():
            c.vol, c.pan = 100, 64
            c.user = [u[1] for u in self.cfg['users']]
        pos = app.seq.position
        try:
            sched = schedule_song(app.song, app.seq.opts)
        except Exception:
            sched = []
        for tick, _pr, port, data, _src in sched:
            if tick > pos:
                break
            if data[0] & 0xF0 == 0xB0:
                self._apply(app.midi.real_port(port), data, meter=False)
        app.seq.out_log.clear()
        self.redraw()

    def midi_in(self, data):
        if not self.cfg.get('midi_in') or not data:
            return
        rec = next((t for t in self.app.song.tracks if t.rec and t.kind == MIDI), None)
        port = self.app.midi.real_port(max(0, rec.port) if rec is not None else 0)
        if self._apply(port, data):
            self.update_strips()

    def _tick(self):
        if not self.winfo_exists():
            return
        changed = False
        log = self.app.seq.out_log
        song_data = self.cfg.get('song_data', True)
        while log:
            port, data = log.popleft()
            if data[0] & 0xF0 == 0x90 or song_data:
                changed = self._apply(port, data) or changed
        for c in self.state_.values():
            if c.meter > 0:
                c.meter = max(0.0, c.meter - 8)
                changed = True
        if changed:
            self.app._timed('MixerWindow: meters and faders', self.update_strips)
        self.after(max(50, self.app.update_ms()), self._tick)
