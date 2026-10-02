"""Shared behaviour of the pattern editors (Piano Roll, Event, Score, Drum)."""
import tkinter as tk
from tkinter import messagebox

from .. import ui, resources
from ..mdi import MDIChild
from ..ui import s
from ..widgets import Toolbar, InfoLine
from ..song import Event

NOTE_NAMES = ['C ', 'C#', 'D ', 'Eb', 'E ', 'F ', 'F#', 'G ', 'G#', 'A ', 'Bb', 'B ']

GM_CONTROLLERS = {
    0: 'Bank Select', 1: 'Modulation', 2: 'Breath Control', 4: 'Foot Control', 5: 'Porta Time',
    6: 'Data Entry', 7: 'Channel Volume', 8: 'Balance', 10: 'Pan', 11: 'Expression', 16: 'Gen Purpose 1',
    17: 'Gen Purpose 2', 18: 'Gen Purpose 3', 19: 'Gen Purpose 4', 32: 'Bank Select LSB',
    33: 'Modulation LSB', 34: 'Breath Control LSB', 36: 'Foot Control LSB', 37: 'Porta Time LSB',
    38: 'Data Entry LSB', 39: 'Channel Volume LSB', 40: 'Balance LSB', 42: 'Pan LSB', 43: 'Expression LSB',
    48: 'Gen Purpose 1 LSB', 49: 'Gen Purpose 2 LSB', 50: 'Gen Purpose 3 LSB', 51: 'Gen Purpose 4 LSB',
    64: 'Sustain Pedal', 65: 'Portamento', 66: 'Sostenuto', 67: 'Soft Pedal', 69: 'Hold 2', 71: 'Resonance',
    72: 'Release Time', 73: 'Attack Time', 74: 'Cutoff Frequency', 80: 'Gen Purpose 5', 81: 'Gen Purpose 6',
    82: 'Gen Purpose 7', 83: 'Gen Purpose 8', 84: 'Portamento Control', 91: 'Reverb Depth',
    92: 'Tremelo Depth', 93: 'Chorus Depth', 94: 'Variation Depth', 95: 'Phaser Depth',
    96: 'Data Increment', 97: 'Data Decrement', 98: 'Non-Reg Param LSB', 99: 'Non-Reg Param MSB',
    100: 'Reg Param LSB', 101: 'Reg Param MSB', 121: 'Reset Controllers', 122: 'Local Control',
    123: 'All Notes Off', 124: 'Omni Off', 125: 'Omni On', 126: 'Mono On (Poly Off)', 127: 'Poly On (Mono Off)'}

# Event / velocity display colours (same in Event list and Piano Roll velocity display)
TYPE_COLOURS = {0x90: '#000000', 0xA0: '#800080', 0xB0: '#008000', 0xC0: '#0000ff', 0xD0: '#808000',
                0xE0: '#ff0000', 0xF0: '#008080'}


def controller_label(n):
    return GM_CONTROLLERS.get(n, 'Controller %d' % n)


def note_name(n):
    return '%s%d' % (NOTE_NAMES[n % 12], n // 12 - 2)


class EventClip:
    def __init__(self, events, name):
        self.events = events
        self.name = name

    def describe(self):
        n = len(self.events)
        return ('%d Events from ' % n if n != 1 else '1 Event from ') + self.name


class EditorWindow(MDIChild):
    """Base: toolbar row, info line, Close/Recall, speaker/MIDI/step toggles, editing helpers."""
    is_editor = True
    title_prefix = 'Editor'
    icon_name = 'IC_PROLL'

    def __init__(self, client, app, pattern, w=600, h=400):
        self.app = app
        self.pattern = pattern
        self.recall_copy = [e.copy() for e in pattern.source.events]
        self.speaker = False
        self.midi_edit = False
        self.step_mode = False
        self.step_pos = None
        self.held_step = set()
        cw = max(300, client.winfo_width() // ui.S - client.reserved_right - 2)
        ch = max(200, client.winfo_height() // ui.S)
        super().__init__(client, self._title(), app.small_icon(self.icon_name), 0, 0, cw, ch)
        if app.settings.get('maximize_editors', True):
            pass

    def _title(self):
        return '%s - %s' % (self.title_prefix, self.pattern.name if self.pattern else '')

    @property
    def events(self):
        return self.pattern.source.events

    @property
    def song(self):
        return self.app.song

    @property
    def track(self):
        return self.pattern.track

    # ---- toolbar helpers
    def add_toggles(self, tb):
        self.t_speaker = tb.add_toggle('EVMIDI_OFF', 'EVMIDI_ON', self._set_speaker, self.speaker)
        self.t_midi = tb.add_toggle('MIDIEDIT_OFF', 'MIDIEDIT_ON', self._set_midi, self.midi_edit)
        self.t_step = tb.add_toggle('STEP_OFF', 'STEP_ON', self._set_step, self.step_mode)

    def add_close_recall(self, tb):
        tb.add_button('BUT_CLOSE', self.close, pressed='BUT_CLOSE_PR')
        tb.add_button('BUT_RECALL', self.recall, pressed='BUT_RECALL_PR')

    def _set_speaker(self, v):
        self.speaker = v

    def _set_midi(self, v):
        self.midi_edit = v

    def _set_step(self, v):
        self.step_mode = v
        self.step_pos = None

    def recall(self):
        """Restore the pattern's original contents (as when the window was opened)."""
        self.app.checkpoint()
        self.pattern.source.events[:] = [e.copy() for e in self.recall_copy]
        self.app.song_changed('events')

    def rebind(self, pattern):
        if pattern is None:
            self.after_idle(self.close)
            return
        self.pattern = pattern
        self.set_title(self._title())

    def refresh(self, what=None):
        if what in ('patterns', None) and self.pattern is not None:
            self.set_title(self._title())
        self.redraw()

    def redraw(self):
        pass

    # ---- selection
    def selected(self):
        return [e for e in self.events if e.selected]

    def deselect_all(self):
        for e in self.events:
            e.selected = False

    def first_selected(self):
        sel = self.selected()
        return sel[0] if sel else None

    def play_event(self, e):
        if not self.speaker or not e.is_note():
            return
        t = self.track
        ch = (self.pattern.channel or t.channel or (e.channel + 1)) - 1
        port = max(0, t.port)
        n = max(0, min(127, e.d1 + (t.transpose or 0)))
        self.app.midi.send(port, bytes([0x90 | ch, n, e.d2]))
        self.after(250, lambda: self.app.midi.send(port, bytes([0x80 | ch, n, 0])))

    def play_note(self, note, vel=100, dur=250):
        t = self.track
        ch = max(1, self.pattern.channel or t.channel or 1) - 1
        port = max(0, t.port)
        self.app.midi.send(port, bytes([0x90 | ch, note, vel]))
        self.after(dur, lambda: self.app.midi.send(port, bytes([0x80 | ch, note, 0])))

    # ---- edit menu
    def edit_copy(self, cut=False):
        sel = self.selected()
        if not sel:
            messagebox.showinfo('Sound Studio Gold', resources.string(16), parent=self.app)
            return
        t0 = min(e.tick for e in sel)
        items = []
        for e in sel:
            n = e.copy()
            n.tick -= t0
            items.append(n)
        self.app.clipboard = EventClip(items, self.pattern.name)
        if cut:
            self.app.checkpoint()
            self.events[:] = [e for e in self.events if not e.selected]
            self.app.song_changed('events')

    def edit_cut(self):
        self.edit_copy(cut=True)

    def edit_paste(self):
        cb = self.app.clipboard
        if not isinstance(cb, EventClip):
            messagebox.showinfo('Sound Studio Gold', resources.string(3), parent=self.app)
            return
        self.app.checkpoint()
        self.deselect_all()
        pos = max(0, self.app.seq.position - self.pattern.start)
        for e in cb.events:
            n = e.copy()
            n.tick += pos
            n.selected = True
            self.events.append(n)
        self.events.sort(key=lambda e: e.tick)
        self.app.song_changed('events')

    def edit_clear(self):
        if not self.selected():
            return
        self.app.checkpoint()
        self.events[:] = [e for e in self.events if not e.selected]
        self.app.song_changed('events')

    def edit_select_all(self):
        for e in self.events:
            e.selected = True
        self.redraw()

    def procedure_target(self):
        from ..procedures import Target
        sel = self.selected()
        return Target.from_events(self.app, self.pattern, sel or None)

    # ---- step time / MIDI edit
    def midi_in(self, data):
        if len(data) < 2:
            return
        st = data[0] & 0xF0
        on = st == 0x90 and len(data) > 2 and data[2] > 0
        off = st == 0x80 or (st == 0x90 and len(data) > 2 and data[2] == 0)
        if self.step_mode and (on or off):
            if on:
                if not self.held_step:
                    self.app.checkpoint()
                self.held_step.add(data[1])
                self.step_insert(data[1], data[2])
            else:
                self.held_step.discard(data[1])
                if not self.held_step:
                    self.step_advance()
            return
        if self.midi_edit and on:
            e = self.first_selected()
            if e is not None and e.is_note():
                self.app.checkpoint()
                e.d1 = data[1]
                e.d2 = data[2]
                self.app.song_changed('events')

    def step_length(self):
        return self.app.song.timebase // 4

    def step_insert(self, note, vel):
        pos = self.app.seq.position - self.pattern.start
        if pos < 0:
            pos = 0
        ch = max(1, self.track.channel or 1) - 1
        e = Event(pos, 0x90 | ch, note, vel, max(1, self.step_length() - 1))
        self.events.append(e)
        self.events.sort(key=lambda x: x.tick)
        self.app.song_changed('events')

    def step_advance(self):
        self.app.locate(self.app.seq.position + self.step_length())

    def step_rest(self):
        self.step_advance()

    # ---- standard info line (Position, Chan, Pitch, Vel, Length)
    def info_fields(self):
        return [('Position', 120), ('Chan', 60), ('Pitch', 70), ('Vel', 60), ('Length', 260)]

    def update_info(self):
        il = getattr(self, 'info', None)
        if il is None:
            return
        e = self.first_selected()
        if e is None:
            il.clear()
            return
        tm = self.app.tmap
        abs_tick = self.pattern.start + e.tick
        def adj(field):
            def f(d, big):
                self.app.song.modified = True
                if field == 'pos':
                    step = tm.sig_at(abs_tick)[3] if big else 1
                    for x in self.selected():
                        x.tick = max(0, x.tick + d // (10 if big else 1) * step) if big else max(0, x.tick + d)
                    self.events.sort(key=lambda x: x.tick)
                elif field == 'ch':
                    for x in self.selected():
                        if x.status < 0xF0:
                            x.status = (x.status & 0xF0) | max(0, min(15, (x.status & 0x0F) + d // abs(d)))
                elif field == 'pitch':
                    for x in self.selected():
                        if x.is_note() or x.status & 0xF0 in (0xA0, 0xB0):
                            x.d1 = max(0, min(127, x.d1 + (12 if big and x.is_note() else (10 if big else 1)) * (1 if d > 0 else -1)))
                    self.play_event(e)
                elif field == 'vel':
                    for x in self.selected():
                        if x.status & 0xF0 in (0x90, 0xA0, 0xB0, 0xE0):
                            x.d2 = max(1 if x.is_note() else 0, min(127, x.d2 + d))
                elif field == 'len':
                    for x in self.selected():
                        if x.is_note():
                            x.length = max(1, x.length + d)
                self.app.song_changed('events')
            return f
        il.set(0, tm.fmt(abs_tick), adj('pos'))
        il.set(1, str(e.channel + 1) if e.status < 0xF0 else '', adj('ch'))
        hi = e.status & 0xF0
        if hi in (0x90, 0xA0):
            il.set(2, note_name(e.d1), adj('pitch'))
        elif hi == 0xB0:
            il.set(2, str(e.d1), adj('pitch'))
        else:
            il.set(2, '', None)
        il.set(3, str(e.d2) if hi in (0x90, 0xA0, 0xB0) else (str(e.d1) if hi in (0xC0, 0xD0) else ''), adj('vel'))
        il.set(4, str(e.length) if e.is_note() else '', adj('len'))

    # ---- timeline (pattern-relative, inverted bar numbers like the original)
    def draw_timeline(self, c, x_of_tick, width, height=13, show_beats=True):
        c.delete('all')
        tm = self.app.tmap
        p = self.pattern
        t0 = p.start
        t1 = p.end
        x, t = x_of_tick(t1 - t0), t1
        while x < width:
            t += tm.sig_at(t)[2]
            x = x_of_tick(t - t0)
        t1 = t
        ui.line(c, 0, height - 1, width, height - 1)
        first = True
        for tick, bar, tpbeat, beats in tm.bar_lines(t0, t1 + tm.sig_at(t1)[2]):
            x = x_of_tick(tick - p.start)
            if x > width:
                break
            rel_bar = tm.to_bbt(tick)[0] - tm.to_bbt(p.start)[0] + 1
            ui.line(c, x, 0, x, height)
            w = ui.text_width(str(rel_bar), 'small') + 3
            c.create_rectangle(s(x), s(1), s(x + w), s(height - 1), fill='#000000', outline='')
            ui.text(c, x + 1, height // 2, str(rel_bar), 'smallbold' if False else 'small', fill='#ffffff', anchor='w')
            if show_beats:
                for b in range(1, beats):
                    bx = x_of_tick(tick + b * tpbeat - p.start)
                    if bx - x > 14:
                        ui.text(c, bx, height // 2, str(b + 1), 'small', anchor='center')
        pos = self.app.seq.position - p.start
        x = x_of_tick(pos)
        c.create_polygon(s(x - 4), s(height - 6), s(x + 4), s(height - 6), s(x), s(height - 1), fill='#ffffff',
                         outline='#000000', tags='pos')

    def can_close(self):
        return True

    def on_close(self):
        pass

    def key(self, ev):
        if ev.keysym in ('Up', 'Down'):
            evs = self.events
            sel = self.selected()
            if not evs:
                return True
            if sel:
                i = evs.index(sel[0]) + (1 if ev.keysym == 'Down' else -1)
            else:
                i = 0
            i = max(0, min(len(evs) - 1, i))
            self.deselect_all()
            evs[i].selected = True
            self.play_event(evs[i])
            self.redraw()
            return True
        if ev.keysym == 'Insert' and hasattr(self, 'insert_event'):
            self.insert_event()
            return True
        return False
