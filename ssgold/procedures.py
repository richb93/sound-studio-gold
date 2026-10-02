"""The Procedures menu: Transpose, Change Velocity, Change Lengths, Quantize, Move Events,
Change Timing, Delete Events, Thin Out, Delete Identical Events, Reverse Notes.

Scope rules (help file): in an editor, only selected events are treated, or all events if none
are selected.  In the Track window, the selected patterns, or all patterns on the selected track.
"""
from .song import event_sort_key

QUANT_VALUES = ['OFF', '64T', '64', '64.', '32T', '32', '32.', '16T', '16', '16.', '8T', '8', '8.',
                '4T', '4', '4.', '2T', '2', '2.', '1T', '1', '1.']


def note_ticks(value, tb):
    """'16' -> semiquaver in ticks, '8T' triplet, '4.' dotted."""
    if not value or value == 'OFF':
        return 0
    v = value.strip()
    mod = 1.0
    if v.endswith('T'):
        mod, v = 2 / 3, v[:-1]
    elif v.endswith('.'):
        mod, v = 1.5, v[:-1]
    try:
        n = int(v)
    except ValueError:
        return 0
    return max(1, int(round(tb * 4 / n * mod)))


class Target:
    """A set of (pattern source, [events]) the procedure applies to."""

    def __init__(self, app, groups):
        self.app = app
        self.groups = groups          # list of (pattern, events-list-to-treat)

    @classmethod
    def from_window(cls, app, w):
        if w is not None and hasattr(w, 'procedure_target'):
            return w.procedure_target()
        tw = app.windows.get('track')
        if tw is None:
            return None
        return tw.procedure_target()

    @classmethod
    def from_patterns(cls, app, patterns):
        groups = []
        seen = set()
        for p in patterns:
            src = p.source
            if id(src) in seen or p.track.kind != 0:
                continue
            seen.add(id(src))
            groups.append((src, list(src.events)))
        return cls(app, groups) if groups else None

    @classmethod
    def from_events(cls, app, pattern, events):
        src = pattern.source
        sel = [e for e in src.events if e.selected] if events is None else events
        return cls(app, [(src, sel or list(src.events))])

    def all_events(self):
        for p, evs in self.groups:
            for e in evs:
                yield p, e

    @property
    def tb(self):
        return self.app.song.timebase


def _in_scope(e, scope):
    if scope is None:
        return True
    lo, hi = scope
    return lo <= e.d1 <= hi


def _resort(target):
    for p, _evs in target.groups:
        p.events.sort(key=lambda e: e.tick)


def transpose(target, semis, scope=None):
    for _p, e in target.all_events():
        if e.status & 0xF0 in (0x90, 0xA0) and _in_scope(e, scope):
            e.d1 = max(0, min(127, e.d1 + semis))


def velocity(target, amount, mode, vmin=1, vmax=127, scope=None):
    """mode: 'up', 'down' or 'fixed'."""
    for _p, e in target.all_events():
        if e.status & 0xF0 == 0x90 and _in_scope(e, scope):
            if mode == 'fixed':
                v = amount
            else:
                v = e.d2 + (amount if mode == 'up' else -amount)
            e.d2 = max(max(1, vmin), min(vmax, v))


def lengths(target, mode, amount=0, fixed=0, scope=None):
    """mode: 'longer', 'shorter', 'legato', 'overlaps', 'fixed'."""
    for p, evs in target.groups:
        notes = sorted((e for e in evs if e.status & 0xF0 == 0x90 and _in_scope(e, scope)),
                       key=lambda e: e.tick)
        if mode in ('longer', 'shorter'):
            for e in notes:
                e.length = max(1, min(0xFFFF, e.length + (amount if mode == 'longer' else -amount)))
        elif mode == 'fixed':
            for e in notes:
                e.length = max(1, fixed)
        elif mode == 'legato':
            ticks = sorted({e.tick for e in notes})
            for e in notes:
                nxt = [t for t in ticks if t > e.tick]
                if nxt:
                    e.length = nxt[0] - e.tick
        elif mode == 'overlaps':
            by_note = {}
            for e in notes:
                by_note.setdefault(e.d1, []).append(e)
            for lst in by_note.values():
                for a, b in zip(lst, lst[1:]):
                    if a.tick + a.length > b.tick:
                        a.length = max(1, b.tick - a.tick)


def quantize(target, grid, percent=100, scope=None):
    if grid <= 0:
        return
    for p, evs in target.groups:
        for e in evs:
            if e.status & 0xF0 == 0x90 and not _in_scope(e, scope):
                continue
            q = int(round(e.tick / grid)) * grid
            e.tick = max(0, e.tick + int(round((q - e.tick) * percent / 100.0)))
    _resort(target)


def move(target, amount):
    for p, evs in target.groups:
        lo = min((e.tick for e in evs), default=0)
        if amount < 0 and lo + amount < 0:
            raise ValueError(52)
        for e in evs:
            e.tick += amount
    _resort(target)


def timing(target, percent):
    for p, evs in target.groups:
        if not evs:
            continue
        t0 = min(e.tick for e in evs)
        for e in evs:
            e.tick = t0 + int(round((e.tick - t0) * percent / 100.0))
            if e.status & 0xF0 == 0x90:
                e.length = max(1, int(round(e.length * percent / 100.0)))
    _resort(target)


EVENT_TYPES = {1101: 0x90, 1102: 0xA0, 1103: 0xB0, 1104: 0xC0, 1105: 0xD0, 1106: 0xE0, 1107: 0xF0}


def delete(target, kinds, controller=None, scope=None):
    for p, evs in target.groups:
        kill = set()
        for e in evs:
            k = e.status if e.status >= 0xF0 else e.status & 0xF0
            if k not in kinds:
                continue
            if k == 0xB0 and controller is not None and e.d1 != controller:
                continue
            if k in (0x90, 0xA0) and not _in_scope(e, scope):
                continue
            kill.add(id(e))
        p.events[:] = [e for e in p.events if id(e) not in kill]


def thinout(target, kinds, every, controller=None):
    every = max(2, every)
    for p, evs in target.groups:
        kill = set()
        counters = {}
        for e in sorted(evs, key=lambda e: e.tick):
            k = e.status & 0xF0
            if k not in kinds or (k == 0xB0 and controller is not None and e.d1 != controller):
                continue
            key = (e.status, e.d1 if k in (0xA0, 0xB0) else None)
            counters[key] = counters.get(key, 0) + 1
            if counters[key] % every == 0:
                kill.add(id(e))
        p.events[:] = [e for e in p.events if id(e) not in kill]


def identical(target):
    for p, evs in target.groups:
        seen = set()
        kill = set()
        for e in evs:
            key = (e.tick, e.status, e.d1, e.d2, e.length, e.data)
            if key in seen:
                kill.add(id(e))
            seen.add(key)
        p.events[:] = [e for e in p.events if id(e) not in kill]


def reverse(target):
    """Reverse the order of the notes in time, keeping the overall span."""
    for p, evs in target.groups:
        notes = [e for e in evs if e.status & 0xF0 == 0x90]
        if not notes:
            continue
        t0 = min(e.tick for e in notes)
        t1 = max(e.tick + e.length for e in notes)
        for e in notes:
            e.tick = t0 + (t1 - (e.tick + e.length))
    _resort(target)
