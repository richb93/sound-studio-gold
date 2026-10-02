"""Keyboard window (MDIKEYBOARDWNDPROC): a 49-note on-screen keyboard.

Plays notes (or chords, drums, 'Playright' notes) to the recording track, shows notes
arriving at MIDI In, turns the PC's QWERTY keys into a keyboard and provides Single
Finger Chord input for the chord track.

Single Finger Chord (Goldlib segment 22 at 848E/8540): with Active on, the lowest 17 keys
choose the chord the accompaniment plays live.  On screen (mouse or PC keys) the key is the
root and the chord buttons give the type; from a MIDI keyboard the highest key held there is
the root and the next one down makes it minor (black key) or 7th (white key), with a third key
of the other colour making it m7.  Synchro starts the song from the beginning on the first
chord; with Hold off the accompaniment drops to drums alone while no chord key is held.
"""
import tkinter as tk

from .. import ui
from ..mdi import MDIChild
from ..ui import s
from ..widgets import Toolbar
from ..song import MIDI, CHORD, Pattern
from ..chords import CHORD_TYPES, ROOTS

BM_X, BM_Y = 2, 3            # KEYBOARD bitmap position in the canvas
KEY_X0, KEY_W = 8, 21        # first white key boundary and white key pitch (bitmap coords)
KEY_TOP, BLACK_BOT, WHITE_BOT = 48, 106, 144
BLACK_W = 12
WHITE_PCS = [0, 2, 4, 5, 7, 9, 11]
BLACK_OFF = {1: 16, 3: 37, 6: 79, 8: 100, 10: 121}   # left edge of a black key within its octave
LOW = 36                     # lowest key (C1 in Gold's note names)
NKEYS = 49
LEDS = {'active': (14, 'Active'), 'synchro': (69, 'Synchro'), 'hold': (131, 'Hold'),
        'free': (183, 'Free'), 'drum': (229, 'Drum'), 'playright': (281, 'Playright'), 'chord': (344, 'Chord'),
        'sus': (578, 'Sus')}
LED_Y = 24
CHORD_GRID = (398, 6, 29, 14)      # x, y, cell width, cell height
CHORD_LABELS = ['Maj', 'm', '7', 'm7', 'Maj7', '6', 'm6', 'aug', 'm7-5', 'dim', 'Sus4', '11']
OCT_BOX = (578, 6, 593, 20)
# PC keyboard: A-' and # are the white keys, W-] the black keys
PC_KEYS = {'a': 0, 'w': 1, 's': 2, 'e': 3, 'd': 4, 'f': 5, 't': 6, 'g': 7, 'y': 8, 'h': 9, 'u': 10, 'j': 11,
           'k': 12, 'o': 13, 'l': 14, 'p': 15, 'semicolon': 16, 'apostrophe': 17, 'bracketright': 18,
           'numbersign': 19, 'quoteright': 17}
DRUM_CHANNEL = 10
SFC_KEYS = 17                # Single Finger Chord zone: the lowest 17 keys
WHITE = [1, 0, 1, 0, 1, 1, 0, 1, 0, 1, 0, 1]      # DS:2B9E
# Playright (DS:2BF2): for each chord type, the chord note each of the 12 keys plays (above the root)
PLAYRIGHT = [[0, 0, 4, 4, 7, 0, 0, 4, 4, 7, 7, 0], [0, 0, 3, 3, 7, 0, 0, 3, 3, 7, 7, 0],
             [0, 0, 4, 4, 7, 10, 10, 0, 0, 4, 4, 7], [0, 0, 3, 3, 7, 10, 10, 0, 0, 3, 3, 7],
             [0, 0, 4, 4, 7, 11, 11, 0, 0, 4, 4, 7], [0, 0, 4, 4, 7, 9, 9, 0, 0, 4, 4, 7],
             [0, 0, 3, 3, 7, 9, 9, 0, 0, 3, 3, 7], [0, 0, 4, 4, 8, 0, 0, 4, 4, 8, 8, 0],
             [0, 0, 3, 3, 6, 10, 10, 0, 0, 3, 3, 6], [0, 0, 3, 3, 6, 0, 0, 3, 3, 6, 6, 0],
             [0, 0, 5, 5, 7, 0, 0, 5, 5, 7, 7, 0], [0, 0, 4, 4, 7, 10, 10, 12, 12, 16, 16, 17]]


def is_black(n):
    return n % 12 in BLACK_OFF


class KeyboardWindow(MDIChild):
    icon_name = 'IC_KEY'

    def __init__(self, client, app):
        self.app = app
        self.held = {}             # displayed note -> source ('mouse', 'pc', 'in')
        self.sounding = {}         # displayed note -> list of (port, status, note) sent
        self.mouse_note = None
        self.pc_on = False
        self.pc_down = 0
        self.sfc_down = False      # a chord key is held
        st = app.__dict__.setdefault('keyboard_state', {'active': False, 'synchro': True, 'hold': True,
                                                         'mode': 'free', 'ctype': 0, 'oct': 0, 'sus': False})
        self.st = st
        H = max(200, client.winfo_height() // ui.S)
        super().__init__(client, 'Keyboard', app.small_icon(self.icon_name), 0, max(0, H - 200), 632, 200)
        b = self.body
        tb = Toolbar(b, app)
        tb.pack(side='top', fill='x')
        tb.add_button('BUT_CLOSE', self.close, pressed='BUT_CLOSE_PR')
        tb.add_label('PC Keyboard', 68)
        self.pc_toggle = tb.add_widget(self._make_check(tb), 14)
        self.c = tk.Canvas(b, bg=ui.FACE, highlightthickness=0, bd=0)
        self.c.pack(side='top', fill='both', expand=True)
        self.c.bind('<Configure>', lambda e: self.redraw())
        self.c.bind('<ButtonPress-1>', lambda e: self._press(e, 1))
        self.c.bind('<B1-Motion>', self._motion)
        self.c.bind('<ButtonRelease-1>', self._release)
        ui.bind_right(self.c, 'ButtonPress', lambda e: self._press(e, 3))
        self._kb = (app.bind_all('<KeyPress>', self._any_key, add='+'),
                    app.bind_all('<KeyRelease>', self._key_up, add='+'))

    def _make_check(self, master):
        c = tk.Canvas(master, width=s(13), height=s(13), bg=ui.FACE, highlightthickness=0, bd=0)
        c.bind('<Button-1>', lambda e: self.set_pc(not self.pc_on))
        c.bind('<Configure>', lambda e: self._draw_check())
        self._check = c
        self._draw_check()
        return c

    def _draw_check(self):
        c = self._check
        c.delete('all')
        y = max(0, (c.winfo_height() // ui.S - 13) // 2)       # centred on the label beside it
        ui.sunken(c, 0, y, 13, y + 13, fill=ui.FACE)
        if self.pc_on:
            ui.text(c, 6, y + 6, '✓', 'smallbold', anchor='center')

    def set_pc(self, on):
        self.pc_on = on
        self._draw_check()
        if not on:
            for n, src in list(self.held.items()):
                if src == 'pc':
                    self.note_off(n)

    def on_close(self):
        for n in list(self.held):
            self.note_off(n)
        try:
            self.app.unbind_all('<KeyPress>')
            self.app.unbind_all('<KeyRelease>')
        except tk.TclError:
            pass

    # ------------------------------------------------------------------ geometry
    def key_rect(self, n):
        """(x0, y0, x1, y1) of key n in canvas coordinates."""
        i = n - LOW
        octv, pc = divmod(i, 12)
        ox = BM_X + KEY_X0 + octv * 7 * KEY_W
        if pc in BLACK_OFF:
            x = ox + BLACK_OFF[pc]
            return x, BM_Y + KEY_TOP, x + BLACK_W, BM_Y + BLACK_BOT
        w = WHITE_PCS.index(pc)
        x = ox + w * KEY_W
        return x + 1, BM_Y + KEY_TOP, x + KEY_W, BM_Y + WHITE_BOT

    def key_at(self, x, y):
        if not (BM_Y + KEY_TOP <= y < BM_Y + WHITE_BOT):
            return None
        for n in range(LOW, LOW + NKEYS):
            if is_black(n):
                x0, y0, x1, y1 = self.key_rect(n)
                if x0 <= x <= x1 and y <= y1:
                    return n
        for n in range(LOW, LOW + NKEYS):
            if not is_black(n):
                x0, y0, x1, y1 = self.key_rect(n)
                if x0 - 1 <= x < x1:
                    return n
        return None

    # ------------------------------------------------------------------ drawing
    def redraw(self):
        if not self.winfo_exists():
            return
        c = self.c
        c.delete('all')
        img = self.app.images.get
        ui.image(c, BM_X, BM_Y, img('KEYBOARD'))
        st = self.st
        on = {'active': st['active'], 'synchro': st['synchro'], 'hold': st['hold'], 'sus': st['sus'],
              'free': st['mode'] == 'free', 'drum': st['mode'] == 'drum',
              'playright': st['mode'] == 'playright', 'chord': st['mode'] == 'chord'}
        for key, (x, label) in LEDS.items():
            if on[key]:
                led = 'LED_RED' if key in ('free', 'drum', 'playright', 'chord') else 'LED_BLUE'
            else:
                led = 'LED_GREY'
            ui.image(c, BM_X + x, BM_Y + LED_Y, img(led))
            ui.text(c, BM_X + x + 14, BM_Y + LED_Y + 5, label, 'small', anchor='w')
        # chord type buttons
        gx, gy, cw, chh = CHORD_GRID
        gx += BM_X
        gy += BM_Y
        ui.rect(c, gx - 1, gy - 1, gx + 6 * cw, gy + 2 * chh, outline='#000000')
        for i, lab in enumerate(CHORD_LABELS):
            r, col = divmod(i, 6)
            x0, y0 = gx + col * cw, gy + r * chh
            sel = i == st['ctype']
            if sel:
                c.create_rectangle(s(x0), s(y0), s(x0 + cw - 1), s(y0 + chh - 1), fill=ui.SHADOW, outline='')
                ui.line(c, x0, y0, x0 + cw - 1, y0, fill='#000000')
                ui.line(c, x0, y0, x0, y0 + chh - 1, fill='#000000')
            else:
                ui.raised(c, x0, y0, x0 + cw, y0 + chh, outer=False)
            ui.text(c, x0 + cw // 2, y0 + chh // 2, lab, 'small', fill='#ffffff' if sel else '#000000',
                    anchor='center')
        x0, y0, x1, y1 = OCT_BOX
        ui.sunken(c, BM_X + x0, BM_Y + y0, BM_X + x1, BM_Y + y1, fill='#ffffff')
        ui.text(c, BM_X + (x0 + x1) // 2, BM_Y + (y0 + y1) // 2, str(st['oct']), 'smallbold', anchor='center')
        ui.text(c, BM_X + x1 + 4, BM_Y + (y0 + y1) // 2 + 1, 'Oct', 'small', anchor='w')
        self.draw_held()

    def draw_held(self):
        """The dots on held keys (all a note changes: cheaper than redrawing the keyboard)."""
        c = self.c
        c.delete('held')
        for n, src in self.held.items():
            if not LOW <= n < LOW + NKEYS:
                continue
            x0, y0, x1, y1 = self.key_rect(n)
            col = '#0000ff' if src == 'in' else '#ff0000'
            cx = (x0 + x1) / 2.0
            cy = y1 - 8
            c.create_oval(s(cx - 3), s(cy - 3), s(cx + 3), s(cy + 3), fill=col, outline='', tags='held')

    # ------------------------------------------------------------------ mouse
    def _hit_controls(self, x, y):
        for key, (lx, label) in LEDS.items():
            tw = ui.text_width(label, 'small')
            if BM_X + lx <= x <= BM_X + lx + 14 + tw and BM_Y + LED_Y - 2 <= y <= BM_Y + LED_Y + 12:
                return ('led', key)
        gx, gy, cw, chh = CHORD_GRID
        if BM_X + gx <= x < BM_X + gx + 6 * cw and BM_Y + gy <= y < BM_Y + gy + 2 * chh:
            col = int((x - BM_X - gx) // cw)
            r = int((y - BM_Y - gy) // chh)
            return ('ctype', r * 6 + col)
        x0, y0, x1, y1 = OCT_BOX
        if BM_X + x0 <= x <= BM_X + x1 + 20 and BM_Y + y0 <= y <= BM_Y + y1:
            return ('oct', None)
        return None

    def _press(self, ev, button):
        x, y = ev.x / ui.S, ev.y / ui.S
        h = self._hit_controls(x, y)
        st = self.st
        if h is not None:
            kind, v = h
            if kind == 'led':
                if v in ('free', 'drum', 'playright', 'chord'):
                    st['mode'] = v
                elif v == 'sus':
                    st['sus'] = not st['sus']
                    self._send_all(lambda port, ch: bytes([0xB0 | ch, 64, 127 if st['sus'] else 0]))
                else:
                    st[v] = not st[v]
                    if v == 'hold':
                        self._update_sfc()
            elif kind == 'ctype':
                st['ctype'] = v
                sfc = self.app.seq.sfc
                if sfc is not None:            # changes the live chord at once
                    self.set_sfc(sfc[0], v, self.sfc_down)
            elif kind == 'oct':
                st['oct'] = max(-4, min(4, st['oct'] + (1 if button == 3 else -1)))
            self.redraw()
            return
        if button != 1:
            return
        n = self.key_at(x, y)
        if n is not None:
            self.mouse_note = n
            vel = self._velocity(y, n)
            self.note_on(n, vel, 'mouse')

    def _velocity(self, y, n):
        return max(1, min(127, self.app.settings['prefs'].get('kbd_velocity', 100)))

    def _motion(self, ev):
        if self.mouse_note is None:
            return
        n = self.key_at(ev.x / ui.S, ev.y / ui.S)
        if n is not None and n != self.mouse_note:
            self.note_off(self.mouse_note)
            self.mouse_note = n
            self.note_on(n, self._velocity(ev.y / ui.S, n), 'mouse')

    def _release(self, _ev):
        if self.mouse_note is not None:
            self.note_off(self.mouse_note)
            self.mouse_note = None

    # ------------------------------------------------------------------ PC keyboard
    def _pc_note(self, ev):
        k = ev.keysym.lower() if len(ev.keysym) == 1 else ev.keysym
        if k not in PC_KEYS:
            return None
        n = 48 + PC_KEYS[k] + (12 if ev.state & 0x1 else 0) + self.pc_down
        return n

    def key(self, ev):
        """Called by the main window for keys it would otherwise use as shortcuts."""
        if not self.pc_on:
            return False
        if ev.keysym == 'Scroll_Lock':
            self.pc_down = 0 if self.pc_down else -12
            return True
        n = self._pc_note(ev)
        if n is None:
            return False
        if self.held.get(n) != 'pc':
            self.note_on(n, self._velocity(0, n), 'pc')
        return True

    def _any_key(self, ev):
        if not self.pc_on or self.app.client.active is not self:
            return
        if self.app._typing(ev) or ev.state & 0x4:
            return
        self.key(ev)

    def _key_up(self, ev):
        if not self.pc_on:
            return
        n = self._pc_note(ev)
        for m in (n, None if n is None else n + 12, None if n is None else n - 12):
            if m is not None and self.held.get(m) == 'pc':
                self.note_off(m)

    # ------------------------------------------------------------------ notes out
    def target(self):
        """(port, channel 0-15) of the recording MIDI track."""
        t = next((t for t in self.app.song.tracks if t.rec and t.kind == MIDI), None)
        if t is None:
            return 0, 0
        return max(0, t.port), max(1, t.channel or 1) - 1

    def _send_all(self, make):
        port, ch = self.target()
        self._out(port, make(port, ch))

    def _out(self, port, data):
        self.app.midi.send(port, data)
        self.app.seq.midi_in(data)
        try:
            self.app._midi_in_gui(data)
        except tk.TclError:
            pass

    def current_chord(self):
        """(root, type) for Playright: the Single Finger Chord, else the chord track at the play position."""
        sfc = self.app.seq.sfc
        if sfc:
            return sfc[0], sfc[1]
        pos = self.app.seq.position
        for t in self.app.song.tracks:
            if t.kind == CHORD:
                for p in t.patterns:
                    if p.start <= pos < p.end:
                        return p.source.chord()
        return None

    def note_on(self, n, vel, src):
        st = self.st
        self.held[n] = src
        port, ch = self.target()
        base = n + 12 * st['oct']
        if st['active'] and 0 <= n - LOW < SFC_KEYS and src != 'in':
            self._single_finger(n)
            self.draw_held()
            return
        notes = [base]
        if st['mode'] == 'chord':
            notes = [base + i for i in CHORD_TYPES[st['ctype']]]
        elif st['mode'] == 'drum':
            ch = DRUM_CHANNEL - 1
        elif st['mode'] == 'playright':
            notes = [self._playright(base)]
        sent = []
        for m in notes:
            if 0 <= m <= 127:
                self._out(port, bytes([0x90 | ch, m, vel]))
                sent.append((port, ch, m))
        self.sounding[n] = sent
        self.draw_held()

    def _playright(self, base):
        """The chord note a key plays in Playright mode (the key itself if there is no chord)."""
        chord = self.current_chord()
        if not chord or chord[0] is None or chord[0] < 0:
            return base
        root, ctype = chord[0] % 12, chord[1] % 12
        pc = base % 12
        m = base - pc + PLAYRIGHT[ctype][pc] + root
        if self.app.seq.sfc is not None and m - LOW - 12 * self.st['oct'] < SFC_KEYS:
            m += 12                     # keep clear of the chord keys
        return m

    def note_off(self, n):
        src = self.held.pop(n, None)
        for port, ch, m in self.sounding.pop(n, []):
            self._out(port, bytes([0x80 | ch, m, 0]))
        if self.st['active'] and 0 <= n - LOW < SFC_KEYS and src in ('mouse', 'pc'):
            sfc = self.app.seq.sfc
            if sfc is not None:
                self.set_sfc(sfc[0], sfc[1], False)
        self.draw_held()

    # ------------------------------------------------------------------ Single Finger Chord
    def _single_finger(self, n):
        """Mouse/PC: the key is the root and the chord buttons give the type."""
        self.set_sfc((n - LOW) % 12, self.st['ctype'], True)

    def _update_sfc(self):
        sfc = self.app.seq.sfc
        if sfc is not None:
            self.set_sfc(sfc[0], sfc[1], self.sfc_down)

    def set_sfc(self, root, ctype, held):
        """A chord from the chord keys; held is False once the keys are released."""
        app = self.app
        seq = app.seq
        prev = seq.sfc
        self.sfc_down = held
        sounding = held or self.st['hold']
        seq.sfc = (root, ctype, sounding)
        if held:
            app.chord_name = ROOTS[root] + ('' if ctype == 0 else ' ' + CHORD_LABELS[ctype])
            app.transport.update_values()
            from ..sequencer import chord_track
            if self.st['synchro'] and not seq.playing and chord_track(app.song) is not None:
                seq.position = 0
                app.play()
                seq.sfc = (root, ctype, sounding)
        if seq.playing and seq.recording:
            was = prev[:2] if prev and prev[2] else None
            now = (root, ctype) if sounding else None
            if now != was:
                app.__dict__.setdefault('sfc_record', []).append((seq.position,) + (now or (None, None)))
        if held and self.st['mode'] == 'playright':
            self._retrigger()

    def _retrigger(self):
        """Held Playright keys follow a new chord."""
        for n, sent in list(self.sounding.items()):
            if not sent or self.held.get(n) not in ('mouse', 'pc'):
                continue
            port, ch, m = sent[0]
            new = self._playright(n + 12 * self.st['oct'])
            if new != m and 0 <= new <= 127:
                self._out(port, bytes([0x80 | ch, m, 0]))
                self._out(port, bytes([0x90 | ch, new, self._velocity(0, n)]))
                self.sounding[n] = [(port, ch, new)]

    def midi_in(self, data):
        if len(data) < 2:
            return
        hi = data[0] & 0xF0
        n = data[1]
        if hi == 0x90 and len(data) > 2 and data[2]:
            if n in self.held or any(m == n for v in self.sounding.values() for _p, _c, m in v):
                return      # our own note echoed back
            self.held[n] = 'in'
            if self.st['active'] and 0 <= n - LOW < SFC_KEYS:
                self._external_sfc()
        elif hi == 0x80 or (hi == 0x90 and len(data) > 2 and not data[2]):
            if self.held.get(n) == 'in':
                del self.held[n]
                if self.st['active'] and 0 <= n - LOW < SFC_KEYS:
                    self._external_sfc()
        else:
            return
        self.draw_held()

    def _external_sfc(self):
        """Chord from the keys held in the chord zone of a MIDI keyboard (sub 848E)."""
        keys = sorted(k - LOW for k, src in self.held.items() if src == 'in' and 0 <= k - LOW < SFC_KEYS)
        if not keys:
            sfc = self.app.seq.sfc
            if sfc is not None:
                self.set_sfc(sfc[0], sfc[1], False)
            return
        top = keys[::-1][:3]
        ctype = 0
        if len(top) > 1:
            if WHITE[top[1] % 12]:
                ctype = 2
                if len(top) > 2 and not WHITE[top[2] % 12]:
                    ctype = 3
            else:
                ctype = 1
                if len(top) > 2 and WHITE[top[2] % 12]:
                    ctype = 3
        self.set_sfc(top[0] % 12, ctype, True)


def finish_sfc_recording(app, end_tick):
    """Turn Single Finger Chord changes made while recording into chord-track patterns."""
    evs = app.__dict__.pop('sfc_record', [])
    if not evs:
        return False
    track = next((t for t in app.song.tracks if t.kind == CHORD), None)
    if track is None:
        return False
    evs.sort()
    for i, (tick, root, ctype) in enumerate(evs):
        end = evs[i + 1][0] if i + 1 < len(evs) else max(end_tick, tick + app.song.timebase)
        if end <= tick or root is None:         # keys released with Hold off: no chord here
            continue
        for q in list(track.patterns):
            if q.start < end and q.end > tick:
                track.patterns.remove(q)
        p = Pattern(name=track.name, start=tick, end=end)
        p.set_chord(root, ctype)
        for k in range(6):
            p.set_chord_mute(k, 1)
        p.track = track
        track.patterns.append(p)
    track.patterns.sort(key=lambda q: q.start)
    return True
