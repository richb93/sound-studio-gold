"""Standard MIDI File import (Open / Merge Midi File) and export (Save As .MID)."""
import struct

from .song import (Song, Track, Pattern, Event, CondPoint, COND_TEMPO, COND_TIMESIG, COND_KEY,
                   MIDI, OFF, PAN_OFF, SongError)
from .timing import TimeMap, ts_index
from .sequencer import schedule_pattern, initial_messages

TIMEBASES = (48, 72, 96, 120, 144, 168, 192, 224, 240, 384, 480, 720)


def _varlen(d, p):
    v = 0
    while True:
        b = d[p]
        p += 1
        v = (v << 7) | (b & 0x7F)
        if not b & 0x80:
            return v, p


def _write_varlen(v):
    out = [v & 0x7F]
    v >>= 7
    while v:
        out.append(0x80 | (v & 0x7F))
        v >>= 7
    return bytes(reversed(out))


def parse(path):
    d = open(path, 'rb').read()
    if d[:4] == b'RIFF':
        i = d.find(b'MThd')
        d = d[i:]
    if d[:4] != b'MThd':
        raise SongError('Not a Standard MIDI File')
    hl, fmt, ntrk, div = struct.unpack('>IHHH', d[4:14])
    if div & 0x8000:
        raise SongError('SMPTE-based MIDI files are not supported')
    p = 8 + hl
    tracks = []
    while p + 8 <= len(d) and len(tracks) < ntrk:
        cid, ln = d[p:p + 4], struct.unpack('>I', d[p + 4:p + 8])[0]
        p += 8
        if cid != b'MTrk':
            p += ln
            continue
        end = p + ln
        evs = []
        tick = 0
        running = 0
        q = p
        while q < end:
            dt, q = _varlen(d, q)
            tick += dt
            st = d[q]
            if st < 0x80:
                st = running
            else:
                q += 1
            if st == 0xFF:
                typ = d[q]
                ln2, q = _varlen(d, q + 1)
                evs.append((tick, 'meta', typ, d[q:q + ln2]))
                q += ln2
                if typ == 0x2F:
                    break
            elif st in (0xF0, 0xF7):
                ln2, q = _varlen(d, q)
                body = d[q:q + ln2]
                q += ln2
                evs.append((tick, 'sysex', st, (b'\xF0' + body) if st == 0xF0 else body))
            else:
                running = st
                n = 1 if st & 0xF0 in (0xC0, 0xD0) else 2
                evs.append((tick, 'midi', st, d[q:q + n]))
                q += n
        tracks.append(evs)
        p = end
    return fmt, div, tracks


def read_smf(path, app=None, split_type0=None):
    fmt, div, tracks = parse(path)
    s = Song()
    s.timebase = div
    s.ports = app.port_names() if app else ['A: MIDI Out']
    s.conductor.points = []
    leave = bool(app and app.settings['prefs'].get('leave_midi'))
    if split_type0 is None:
        split_type0 = fmt == 0
        if app is not None and fmt == 0 and app.settings['prefs'].get('ask_type0', False):
            from tkinter import messagebox
            split_type0 = messagebox.askyesno('Sound Studio Gold', app_string(816), parent=app)
    groups = []
    for evs in tracks:
        if split_type0 and fmt == 0:
            by_ch = {}
            meta = []
            for e in evs:
                if e[1] == 'midi':
                    by_ch.setdefault(e[2] & 0x0F, []).append(e)
                else:
                    meta.append(e)
            groups.append(meta)
            for ch in sorted(by_ch):
                groups.append(by_ch[ch])
        else:
            groups.append(evs)
    tmap_song = s
    for evs in groups:
        for tick, kind, st, data in evs:
            if kind == 'meta' and st == 0x51 and len(data) == 3:
                us = (data[0] << 16) | (data[1] << 8) | data[2]
                s.conductor.points.append(CondPoint(tick, COND_TEMPO, max(1, round(60000000 / us))))
            elif kind == 'meta' and st == 0x58 and len(data) >= 2:
                s.conductor.points.append(CondPoint(tick, COND_TIMESIG, ts_index(data[0], 2 ** data[1])))
            elif kind == 'meta' and st == 0x59 and len(data) >= 2:
                sf = struct.unpack('b', data[:1])[0]
                minor = data[1]
                semis = (sf * 7) % 12
                if minor:
                    semis = (semis + 3) % 12
                s.conductor.points.append(CondPoint(tick, COND_KEY, semis))
    for kind in (COND_TEMPO, COND_TIMESIG, COND_KEY):
        pts = [p for p in s.conductor.points if p.kind == kind]
        seen = {}
        for p in pts:
            seen[p.tick] = p
        s.conductor.points = [p for p in s.conductor.points if p.kind != kind] + list(seen.values())
        if 0 not in seen:
            s.conductor.points.append(CondPoint(0, kind, {COND_TEMPO: 120, COND_TIMESIG: 3, COND_KEY: 0}[kind]))
    tm = TimeMap(tmap_song)
    n = 0
    for evs in groups:
        notes = [e for e in evs if e[1] in ('midi', 'sysex')]
        name = ''
        for tick, kind, st, data in evs:
            if kind == 'meta' and st == 0x03:
                name = data.decode('latin1', 'replace')[:20]
                break
        if not notes:
            continue
        n += 1
        t = Track(name=name or 'Track %d' % n)
        chans = {e[2] & 0x0F for e in notes if e[1] == 'midi'}
        t.channel = (min(chans) + 1) if len(chans) == 1 else 0
        t.prog = OFF
        events = []
        on = {}
        for tick, kind, st, data in notes:
            if kind == 'sysex':
                events.append(Event(tick, 0xF0, data=bytes(data) if data.endswith(b'\xF7') else bytes(data) + b'\xF7'))
                continue
            hi = st & 0xF0
            if hi == 0x90 and data[1] > 0:
                e = Event(tick, st, data[0], data[1], 0)
                on.setdefault((st & 0x0F, data[0]), []).append(e)
                events.append(e)
            elif hi == 0x80 or (hi == 0x90 and data[1] == 0):
                lst = on.get((st & 0x0F, data[0]))
                if lst:
                    e = lst.pop(0)
                    e.length = max(1, tick - e.tick)
            elif hi in (0xC0, 0xD0):
                events.append(Event(tick, st, data[0]))
            else:
                events.append(Event(tick, st, data[0], data[1] if len(data) > 1 else 0))
        if not leave:
            _extract_initial(t, events)
        if not events:
            s.tracks.append(t)
            continue
        first = min(e.tick for e in events)
        last = max(e.tick + e.length for e in events)
        start = tm.bar_tick(first)
        end = tm.bar_tick(last) + tm.sig_at(last)[2]
        p = Pattern(name=t.name, start=start, end=end)
        for e in events:
            e.tick -= start
        p.events = events
        p.track = t
        t.patterns.append(p)
        s.tracks.append(t)
    s.right = s.end_tick() or 4 * 4 * s.timebase
    return s


def app_string(i):
    from . import resources
    return resources.string(i)


def _extract_initial(t, events):
    """Move tick-0 program / bank / volume / pan / reverb / chorus into the track settings."""
    if t.channel == 0:
        return
    keep = []
    for e in events:
        if e.tick == 0 and e.status & 0xF0 == 0xC0 and t.prog == OFF:
            t.prog = e.d1
            continue
        if e.tick == 0 and e.status & 0xF0 == 0xB0:
            cc = e.d1
            if cc == 0 and t.bank == OFF:
                t.bank = e.d2
                continue
            if cc == 7 and t.volume == OFF:
                t.volume = e.d2
                continue
            if cc == 10 and t.pan == PAN_OFF:
                t.pan = e.d2 - 64
                continue
            if cc == 91 and t.reverb == OFF:
                t.reverb = e.d2
                continue
            if cc == 93 and t.chorus == OFF:
                t.chorus = e.d2
                continue
        keep.append(e)
    events[:] = keep


def write_smf(song, path, app=None):
    tb = song.timebase
    chunks = []
    # conductor track
    ev = []
    for p in song.conductor.points:
        if p.kind == COND_TEMPO:
            us = int(60000000 / max(1, p.value))
            ev.append((p.tick, b'\xFF\x51\x03' + us.to_bytes(3, 'big')))
        elif p.kind == COND_TIMESIG:
            from .timing import ts_parts
            num, den = ts_parts(p.value)
            ev.append((p.tick, b'\xFF\x58\x04' + bytes([num, den.bit_length() - 1, 24, 8])))
        elif p.kind == COND_KEY:
            sf = {0: 0, 1: -5, 2: 2, 3: -3, 4: 4, 5: -1, 6: 6, 7: 1, 8: -4, 9: 3, 10: -2, 11: 5}[p.value % 12]
            ev.append((p.tick, b'\xFF\x59\x02' + struct.pack('b', sf) + b'\x00'))
    chunks.append(_chunk(ev))
    any_solo = any(t.solo for t in song.tracks)
    for t in song.tracks:
        if t.kind != MIDI or not t.patterns:
            continue
        if t.mute or (any_solo and not t.solo):
            continue
        ev = [(0, b'\xFF\x03' + _write_varlen(len(t.name)) + t.name.encode('latin1', 'replace'))]
        for m in initial_messages(t):
            ev.append((0, m))
        for p in t.patterns:
            if p.mute:
                continue
            for tick, _pr, _port, data in schedule_pattern(t, p, 0):
                if data[0] == 0xF0:
                    data = b'\xF0' + _write_varlen(len(data) - 1) + data[1:]
                ev.append((tick, data))
        chunks.append(_chunk(ev))
    out = b'MThd' + struct.pack('>IHHH', 6, 1, len(chunks), tb)
    for c in chunks:
        out += b'MTrk' + struct.pack('>I', len(c)) + c
    with open(path, 'wb') as f:
        f.write(out)


def _chunk(ev):
    ev = sorted(ev, key=lambda e: e[0])
    out = bytearray()
    last = 0
    for tick, data in ev:
        out += _write_varlen(max(0, tick - last))
        out += data
        last = tick
    out += b'\x00\xFF\x2F\x00'
    return bytes(out)
