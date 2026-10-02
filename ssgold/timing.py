"""Conversions between ticks, bar:beat:tick, clock time and SMPTE using the conductor maps."""
from .song import COND_TEMPO, COND_TIMESIG
from . import resources


def ts_parts(index):
    t = resources.tables()
    index = max(0, min(index, len(t['timesig_num']) - 1))
    return t['timesig_num'][index], t['timesig_den'][index]


def ts_index(num, den):
    t = resources.tables()
    for i, (n, d) in enumerate(zip(t['timesig_num'], t['timesig_den'])):
        if n == num and d == den:
            return i
    return 3


class TimeMap:
    """Built from a song; rebuild whenever the conductor or timebase changes."""

    def __init__(self, song):
        self.tb = song.timebase or 192
        self.sigs = []          # (tick, bar_index_at_tick, ticks_per_bar, ticks_per_beat, num, den)
        bar = 0
        last_tick = 0
        last_tpb = None
        for p in song.conductor.of(COND_TIMESIG):
            num, den = ts_parts(p.value)
            beat = self.tb * 4 // den
            if last_tpb is not None:
                bar += (p.tick - last_tick) // last_tpb
            self.sigs.append((p.tick, bar, num * beat, beat, num, den))
            last_tick, last_tpb = p.tick, num * beat
        if not self.sigs:
            self.sigs = [(0, 0, 4 * self.tb, self.tb, 4, 4)]
        self.tempos = []        # (tick, ms_at_tick, us_per_tick)
        ms = 0.0
        prev = None
        for p in song.conductor.of(COND_TEMPO):
            if prev is not None:
                ms += (p.tick - prev[0]) * prev[2] / 1000.0
            bpm = max(1, p.value)
            upt = 60000000.0 / bpm / self.tb
            prev = (p.tick, ms, upt)
            self.tempos.append(prev)
        if not self.tempos:
            self.tempos = [(0, 0.0, 60000000.0 / 120 / self.tb)]

    # ---- bars
    def sig_at(self, tick):
        cur = self.sigs[0]
        for s in self.sigs:
            if s[0] <= tick:
                cur = s
            else:
                break
        return cur

    def to_bbt(self, tick):
        tick = max(0, int(tick))
        st, bar0, tpbar, tpbeat, _n, _d = self.sig_at(tick)
        rel = tick - st
        bar = bar0 + rel // tpbar
        r = rel % tpbar
        return bar + 1, r // tpbeat + 1, r % tpbeat

    def from_bbt(self, bar, beat=1, t=0):
        bar = max(1, bar) - 1
        cur = self.sigs[0]
        for s in self.sigs:
            if s[1] <= bar:
                cur = s
            else:
                break
        st, bar0, tpbar, tpbeat, _n, _d = cur
        return st + (bar - bar0) * tpbar + (max(1, beat) - 1) * tpbeat + t

    def fmt(self, tick, width=1):
        b, bt, t = self.to_bbt(tick)
        return '%*d:%02d:%03d' % (width, b, bt, t)

    def parse(self, text):
        parts = [p for p in text.replace('.', ':').split(':') if p.strip()]
        try:
            vals = [int(p) for p in parts]
        except ValueError:
            return None
        while len(vals) < 3:
            vals.append(1 if len(vals) < 2 else 0)
        return self.from_bbt(*vals[:3])

    def bar_tick(self, tick):
        """Start tick of the bar containing tick."""
        b, _bt, _t = self.to_bbt(tick)
        return self.from_bbt(b)

    def bar_lines(self, t0, t1):
        """Yield (tick, bar_number, ticks_per_beat, beats_per_bar) for bars intersecting t0..t1."""
        b = self.to_bbt(max(0, t0))[0]
        while True:
            t = self.from_bbt(b)
            if t > t1:
                break
            st, _b0, tpbar, tpbeat, num, _d = self.sig_at(t)
            yield t, b, tpbeat, tpbar // tpbeat
            b += 1

    # ---- time
    def tempo_at(self, tick):
        cur = self.tempos[0]
        for p in self.tempos:
            if p[0] <= tick:
                cur = p
            else:
                break
        return cur

    def to_ms(self, tick):
        t0, ms0, upt = self.tempo_at(tick)
        return ms0 + (tick - t0) * upt / 1000.0

    def from_ms(self, ms):
        cur = self.tempos[0]
        for p in self.tempos:
            if p[1] <= ms:
                cur = p
            else:
                break
        t0, ms0, upt = cur
        return int(t0 + (ms - ms0) * 1000.0 / upt)

    def bpm_at(self, tick):
        return round(60000000.0 / self.tempo_at(tick)[2] / self.tb)


def smpte(ms, fps=25, offset='00:00:00:00'):
    """hh:mm:ss:ff of ms after the song start offset."""
    try:
        h, m, s, f = [int(x) for x in offset.split(':')]
        ms += ((h * 60 + m) * 60 + s) * 1000 + f * 1000.0 / fps
    except ValueError:
        pass
    total_frames = int(ms * fps / 1000.0)
    f = total_frames % fps
    s = total_frames // fps
    return '%02d:%02d:%02d:%02d' % (s // 3600 % 100, s // 60 % 60, s % 60, f)


FPS = {24: 24, 25: 25, 29: 30, 30: 30}
