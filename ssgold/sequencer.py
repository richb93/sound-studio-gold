"""Playback and recording engine."""
import collections
import threading
import time

from .song import MIDI, CHORD, OFF, PAN_OFF, Event, Pattern
from .timing import TimeMap

NOTE_ON = 0x90


def _clamp(v, lo, hi):
    return lo if v < lo else hi if v > hi else v


class Options:
    """Transport toggles and MIDI Settings that affect playback."""

    def __init__(self):
        self.metronome = False
        self.cycle = False
        self.follow = True
        self.conductor = True
        self.edit_solo = False
        self.sync = False
        self.punch = False
        self.auto_return = 0          # 0 off, 1 zero, 2 last start
        self.record_mode = 1          # 0 replace, 1 overdub
        self.multitrack = False
        self.fixed_tempo = 120
        # MIDI settings dialog
        self.thru_channel = True
        self.thru_realtime = False
        self.reset_on_stop = True
        self.kill_on_cycle = True
        self.chase = True
        self.send_reset = True
        self.filter_types = set()     # statuses (0x90, 0xA0 ...) blocked on input
        self.filter_channels = set()  # 1..16 blocked on input
        # metronome dialog
        self.metro_midi = True
        self.metro_speaker = False
        self.metro_port = 0
        self.metro_channel = 10
        self.metro_pitch = (37, 37)   # bar, beat
        self.metro_vel = (100, 70)
        self.metro_record_only = True
        self.count_in = 1


def schedule_song(song, opts, solo_patterns=None, chord_player=None):
    """Return a sorted list of (tick, prio, port, bytes) for the whole song."""
    out = []
    tracks = [t for t in song.tracks if t.kind in (MIDI, CHORD)]
    any_solo = any(t.solo for t in tracks)
    for t in tracks:
        if t.mute or (any_solo and not t.solo):
            continue
        if t.kind == CHORD:
            if chord_player:
                out += chord_player.schedule(song, t)
            continue
        port = max(0, t.port)
        for p in t.patterns:
            if p.mute:
                continue
            if solo_patterns is not None and p not in solo_patterns and p.source not in solo_patterns:
                continue
            out += schedule_pattern(t, p, port)
    out.sort(key=lambda e: (e[0], e[1]))
    return out


def initial_messages(t, ch_default=1):
    """Program/bank/volume/pan/reverb/chorus messages for a track or pattern (OFF = not sent)."""
    ch = (t.channel if t.channel and t.channel > 0 else ch_default) - 1
    msgs = []
    bank = t.bank
    if bank is not None and bank >= 0:
        msb, lsb = (bank >> 7) & 0x7F, bank & 0x7F
        if bank > 127:
            msgs.append(bytes([0xB0 | ch, 0, msb]))
            msgs.append(bytes([0xB0 | ch, 32, lsb]))
        else:
            msgs.append(bytes([0xB0 | ch, 0, bank]))
    if t.prog is not None and t.prog >= 0:
        msgs.append(bytes([0xC0 | ch, t.prog & 0x7F]))
    if t.volume is not None and t.volume >= 0:
        msgs.append(bytes([0xB0 | ch, 7, t.volume & 0x7F]))
    if t.pan is not None and t.pan != PAN_OFF:
        msgs.append(bytes([0xB0 | ch, 10, _clamp(t.pan + 64, 0, 127)]))
    if t.reverb is not None and t.reverb >= 0 and t.kind == MIDI:
        msgs.append(bytes([0xB0 | ch, 91, t.reverb & 0x7F]))
    if t.chorus is not None and t.chorus >= 0 and t.kind == MIDI:
        msgs.append(bytes([0xB0 | ch, 93, t.chorus & 0x7F]))
    return msgs


def schedule_pattern(t, p, port):
    out = []
    events = p.get_events()
    plen = p.end - p.start
    tch = t.channel if t.channel and t.channel > 0 else 0
    pch = p.channel if p.channel and p.channel > 0 else 0
    force = pch or tch
    trans = (t.transpose or 0) + (p.transpose or 0)
    vel = (t.velocity or 0) + (p.velocity or 0)
    shift = (t.time or 0) + (p.time or 0)
    base = p.start + shift
    if force or any(getattr(p, f) not in (OFF, None) for f in ('prog', 'bank', 'volume', 'reverb', 'chorus')) \
            or p.pan != PAN_OFF:
        class _P:
            pass
        q = _P()
        q.channel = force or 1
        for f in ('prog', 'bank', 'volume', 'pan', 'reverb', 'chorus'):
            setattr(q, f, getattr(p, f))
        q.kind = MIDI
        for m in initial_messages(q):
            out.append((max(0, p.start), 0, port, m))
    for e in events:
        if e.tick >= plen or e.tick < 0:
            continue
        tick = base + e.tick
        if tick < 0:
            continue
        st = e.status
        if st == 0xF0:
            out.append((tick, 0, port, e.data))
            continue
        if st < 0x80:
            continue
        hi = st & 0xF0
        ch = (force - 1) if force else (st & 0x0F)
        if hi == NOTE_ON:
            note = _clamp(e.d1 + trans, 0, 127)
            v = _clamp(e.d2 + vel, 1, 127)
            end = min(tick + max(1, e.length), base + plen) if e.length else tick + 1
            out.append((tick, 6, port, bytes([0x90 | ch, note, v])))
            out.append((end, 1, port, bytes([0x80 | ch, note, 0])))
        elif hi in (0xC0, 0xD0):
            out.append((tick, 2, port, bytes([hi | ch, e.d1 & 0x7F])))
        elif hi == 0xA0:
            out.append((tick, 5, port, bytes([hi | ch, _clamp(e.d1 + trans, 0, 127), e.d2 & 0x7F])))
        else:
            out.append((tick, 3, port, bytes([hi | ch, e.d1 & 0x7F, e.d2 & 0x7F])))
    return out


class Sequencer:
    """Runs in its own thread; the GUI polls .position (ticks) and .playing."""

    def __init__(self, midi, app=None):
        self.midi = midi
        self.app = app
        self.opts = Options()
        self.song = None
        self.position = 0
        self.playing = False
        self.recording = False
        self.thread = None
        self.stop_flag = threading.Event()
        self.last_start = 0
        self.left = 0
        self.right = 0
        self.solo_patterns = None
        self.chord_player = None
        self.recorded = []            # (tick, bytes) captured while recording
        self.counting_in = False
        self.held = {}                # (port, ch, note) -> True, notes currently on
        self.on_tick = None           # optional callback(tick) from the thread
        self.input_monitor = None     # callback(bytes) for MIDI-in activity
        self.out_log = collections.deque(maxlen=4096)   # (port, bytes) sent, read by the Mixer
        self.mixer_mute = set()       # (port, channel) muted in the Mixer
        self.mixer_solo = set()       # (port, channel) soloed in the Mixer

    # ---- control
    def set_song(self, song):
        self.stop()
        self.song = song
        self.position = 0

    def play(self, record=False):
        if self.playing or not self.song:
            return
        self.recording = record
        self.recorded = []
        self.last_start = self.position
        self.stop_flag.clear()
        self.playing = True
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()

    def stop(self):
        if not self.playing:
            return
        self.stop_flag.set()
        if self.thread and self.thread is not threading.current_thread():
            self.thread.join(1.0)
        self.playing = False
        self._release_all()
        if self.opts.reset_on_stop:
            for port in range(len(self.midi.outs)):
                for ch in range(16):
                    self.midi.send(port, bytes([0xB0 | ch, 121, 0]))
        if self.opts.auto_return == 1:
            self.position = 0
        elif self.opts.auto_return == 2:
            self.position = self.last_start

    def locate(self, tick):
        was = self.playing
        if was:
            self.stop()
        self.position = max(0, int(tick))
        if was:
            self.play(self.recording)

    # ---- internals
    def _release_all(self):
        for (port, ch, note) in list(self.held):
            self.midi.send(port, bytes([0x80 | ch, note, 0]))
        self.held.clear()

    def _send(self, port, data):
        st = data[0]
        if st & 0xF0 == 0x90 and len(data) > 2 and data[2]:
            key = (port, st & 0x0F)
            if key in self.mixer_mute or (self.mixer_solo and key not in self.mixer_solo):
                return
        if st & 0xF0 == 0x90 and len(data) > 2 and data[2]:
            self.held[(port, st & 0x0F, data[1])] = True
        elif st & 0xF0 == 0x80 or (st & 0xF0 == 0x90 and len(data) > 2 and not data[2]):
            self.held.pop((port, st & 0x0F, data[1]), None)
        self.midi.send(port, data)
        self.out_log.append((port, data))

    def record_event(self, data):
        """Record a message generated inside the program (Mixer moves) while recording."""
        if self.playing and self.recording and not self.counting_in and self.song:
            now_ms = self.rec_origin[1] + (time.perf_counter() - self.rec_origin[0]) * 1000.0
            tick = TimeMap(self.song).from_ms(now_ms)
            if not self.opts.punch or (self.song.left <= tick < self.song.right):
                self.recorded.append((tick, bytes(data)))

    def _chase(self, sched, start):
        """Send the last controller/program/bend values before the start position."""
        state = {}
        for tick, _pr, port, data in sched:
            if tick >= start:
                break
            hi = data[0] & 0xF0
            if hi in (0xB0,):
                state[(port, data[0], data[1])] = data
            elif hi in (0xC0, 0xD0, 0xE0):
                state[(port, data[0])] = data
        for k, data in state.items():
            self.midi.send(k[0], data)

    def _metro_events(self, tmap, t0, t1):
        o = self.opts
        if not o.metronome or (o.metro_record_only and not self.recording) or not o.metro_midi:
            return []
        out = []
        for bar_tick, _b, tpbeat, beats in tmap.bar_lines(t0, t1):
            for i in range(beats):
                t = bar_tick + i * tpbeat
                if t0 <= t <= t1:
                    pitch = o.metro_pitch[0 if i == 0 else 1]
                    vel = o.metro_vel[0 if i == 0 else 1]
                    ch = max(1, o.metro_channel) - 1
                    out.append((t, 7, o.metro_port, bytes([0x90 | ch, pitch, vel])))
                    out.append((t + tpbeat // 4, 1, o.metro_port, bytes([0x80 | ch, pitch, 0])))
        return out

    def _run(self):
        song = self.song
        tmap = TimeMap(song)
        o = self.opts
        if not o.conductor:
            class _Fixed(TimeMap):
                pass
            tmap.tempos = [(0, 0.0, 60000000.0 / max(1, o.fixed_tempo) / tmap.tb)]
        sched = schedule_song(song, o, self.solo_patterns, self.chord_player)
        end_tick = max(song.end_tick(), self.position)
        loop = o.cycle and song.right > song.left
        pos = self.position
        if loop and not (song.left <= pos < song.right):
            pos = song.left
        if o.chase:
            self._chase(sched, pos)
        # count in
        if self.recording and o.count_in > 0:
            self.counting_in = True
            _st, _b0, tpbar, tpbeat, num, _d = tmap.sig_at(pos)
            beat_s = tmap.tempo_at(pos)[2] * tpbeat / 1e6
            for b in range(o.count_in * num):
                if self.stop_flag.is_set():
                    break
                ch = max(1, o.metro_channel) - 1
                pitch = o.metro_pitch[0 if b % num == 0 else 1]
                self.midi.send(o.metro_port, bytes([0x90 | ch, pitch, o.metro_vel[0 if b % num == 0 else 1]]))
                self.stop_flag.wait(beat_s)
                self.midi.send(o.metro_port, bytes([0x80 | ch, pitch, 0]))
            self.counting_in = False
        idx = 0
        while idx < len(sched) and sched[idx][0] < pos:
            idx += 1
        metro = self._metro_events(tmap, pos, max(end_tick, pos) + 100000)
        midx = 0
        while midx < len(metro) and metro[midx][0] < pos:
            midx += 1
        base_ms = tmap.to_ms(pos)
        t_start = time.perf_counter()
        self.rec_origin = (t_start, base_ms)
        while not self.stop_flag.is_set():
            now_ms = base_ms + (time.perf_counter() - t_start) * 1000.0
            cur = tmap.from_ms(now_ms)
            if loop and cur >= song.right:
                # finish events before right locator, wrap around
                while idx < len(sched) and sched[idx][0] < song.right:
                    self._send(*sched[idx][2:])
                    idx += 1
                if o.kill_on_cycle:
                    self._release_all()
                pos = song.left
                idx = 0
                while idx < len(sched) and sched[idx][0] < pos:
                    idx += 1
                midx = 0
                while midx < len(metro) and metro[midx][0] < pos:
                    midx += 1
                base_ms = tmap.to_ms(pos)
                t_start = time.perf_counter()
                self.position = pos
                continue
            while idx < len(sched) and sched[idx][0] <= cur:
                self._send(*sched[idx][2:])
                idx += 1
            while midx < len(metro) and metro[midx][0] <= cur:
                self._send(*metro[midx][2:])
                midx += 1
            self.position = cur
            if not self.recording and not loop and idx >= len(sched) and cur > end_tick + tmap.tb:
                break
            time.sleep(0.001)
        self._release_all()
        self.playing = False
        if self.app:
            try:
                self.app.after_idle(self.app.on_sequencer_stopped)
            except Exception:
                pass

    # ---- recording input
    def midi_in(self, data):
        """Called (from the MIDI input thread) with each incoming message."""
        o = self.opts
        if not data:
            return
        st = data[0]
        if st < 0xF0:
            if (st & 0xF0) in o.filter_types or ((st & 0x0F) + 1) in o.filter_channels:
                return
        if self.playing and self.recording and not self.counting_in:
            now_ms = self.rec_origin[1] + (time.perf_counter() - self.rec_origin[0]) * 1000.0
            tick = TimeMap(self.song).from_ms(now_ms) if self.song else 0
            if not o.punch or (self.song.left <= tick < self.song.right):
                self.recorded.append((tick, bytes(data)))
        if self.input_monitor:
            self.input_monitor(data)


def build_recorded_pattern(song, track, recorded, start_tick=None):
    """Turn (tick, bytes) messages into a new Pattern with note lengths resolved."""
    if not recorded:
        return None
    events = []
    on = {}
    t0 = start_tick if start_tick is not None else min(t for t, _ in recorded)
    tmap = TimeMap(song)
    t0 = tmap.bar_tick(t0)
    for tick, d in recorded:
        st = d[0]
        hi = st & 0xF0
        rel = max(0, tick - t0)
        if hi == 0x90 and len(d) > 2 and d[2] > 0:
            e = Event(rel, st, d[1], d[2], 0)
            on[(st & 0x0F, d[1])] = e
            events.append(e)
        elif hi == 0x80 or (hi == 0x90 and len(d) > 2 and d[2] == 0):
            e = on.pop((st & 0x0F, d[1]), None)
            if e:
                e.length = max(1, rel - e.tick)
        elif st == 0xF0:
            events.append(Event(rel, 0xF0, data=bytes(d)))
        elif hi in (0xA0, 0xB0, 0xE0):
            events.append(Event(rel, st, d[1], d[2] if len(d) > 2 else 0))
        elif hi in (0xC0, 0xD0):
            events.append(Event(rel, st, d[1]))
    last = max(e.tick + e.length for e in events) if events else 0
    end_bar = tmap.bar_tick(t0 + last) + tmap.sig_at(t0 + last)[2]
    p = Pattern(name=track.name, start=t0, end=max(end_bar, t0 + tmap.sig_at(t0)[2]))
    p.events = events
    return p
