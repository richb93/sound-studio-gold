"""Score window (MDISCOREWNDPROC): notation drawn with Gold's own glyph bitmaps."""
import tkinter as tk
from tkinter import simpledialog, filedialog

from .. import ui, tools, resources
from ..ui import s
from ..widgets import Toolbar, InfoLine, PopupMenu
from ..song import Event, COND_KEY, COND_TIMESIG
from ..procedures import note_ticks
from .common import EditorWindow, note_name

RESOLUTIONS = [' 4', ' 8', '16', '32', '64', ' 4T', ' 8T', '16T', '32T']
NOTE_LENS = ['1', '2', '4', '8', '16', '32', '64', '2.', '4.', '8.', '16.', '4T', '8T', '16T']
LINE = 6           # staff line spacing (px)
STAVE_GAP = 70     # distance between staves
LEFT = 5           # stave left margin
KEY_SHARPS = {0: 0, 1: 7, 2: 2, 3: -3, 4: 4, 5: -1, 6: 6, 7: 1, 8: -4, 9: 3, 10: -2, 11: 5}
SHARP_ORDER = [3, 0, 4, 1, 5, 2, 6]       # F C G D A E B (letter index C=0)
FLAT_ORDER = [6, 2, 5, 1, 4, 0, 3]        # B E A D G C F
LETTER_PC = [0, 2, 4, 5, 7, 9, 11]
SHARP_SPELL = [(0, 0), (0, 1), (1, 0), (1, 1), (2, 0), (3, 0), (3, 1), (4, 0), (4, 1), (5, 0), (5, 1), (6, 0)]
FLAT_SPELL = [(0, 0), (1, -1), (1, 0), (2, -1), (2, 0), (3, 0), (4, -1), (4, 0), (5, -1), (5, 0), (6, -1), (6, 0)]
VALUES = [(1, 4.0), (2, 2.0), (4, 1.0), (8, 0.5), (16, 0.25), (32, 0.125), (64, 0.0625)]
SCORE_TOOLS = [('arrow', 'CUR_ARROW_BM', ''), ('note', 'CUR_NOTE_BM', 'CUR_NOTE'),
               ('eraser', 'CUR_ERASER_BM', 'CUR_ERASER'), ('glue', 'CUR_GLUE_BM', 'CUR_GLUE'),
               ('sharp', 'CUR_SHARP_BM', 'CUR_SHARP'), ('flat', 'CUR_FLAT_BM', 'CUR_FLAT'),
               ('pen', 'CUR_PEN_BM', 'CUR_PEN'), ('pennote', 'CUR_PENNOTE_BM', 'CUR_PENNOTE')]
CLEF_TOP = {'treble': 77, 'bass': 57}      # MIDI note on the top line (F5 / A3)


def diatonic(note, flats):
    """MIDI note -> (absolute diatonic step, accidental -1/0/1)."""
    letter, acc = (FLAT_SPELL if flats else SHARP_SPELL)[note % 12]
    octave = note // 12
    return octave * 7 + letter, acc


def split_value(ticks, tb):
    """Break a duration into (value, dotted) pieces, largest first."""
    out = []
    left = ticks
    while left > 0:
        for v, beats in VALUES:
            t = int(tb * beats)
            if t * 1.5 <= left and v < 64:
                out.append((v, True, int(t * 1.5)))
                left -= int(t * 1.5)
                break
            if t <= left:
                out.append((v, False, t))
                left -= t
                break
        else:
            break
    return out


class ScoreWindow(EditorWindow):
    title_prefix = 'Score'
    icon_name = 'IC_SCORE'
    kind = 'score'

    def __init__(self, client, app, pattern):
        self.top = 0
        self.preview = False
        self.page = 0
        self.hits = []          # (x0, y0, x1, y1, event) for clicking noteheads
        self.layout_rows = []
        self.drag = None
        self.tool = tools.ToolSelector(app, SCORE_TOOLS, cols=4)
        super().__init__(client, app, pattern)
        self.tool.on_change = lambda k: tools.set_cursor(self.c, self.tool.cursor_name())
        self._heads()
        self._build()
        self.maximize()

    def _heads(self):
        """Notehead-only images cut from the quarter and half note glyphs."""
        im = self.app.images
        self.head_filled = tk.PhotoImage(master=self.app)
        self.head_filled.tk.call(self.head_filled, 'copy', im.get('N4U'), '-from', 0, s(18), s(8), s(25))
        self.head_open = tk.PhotoImage(master=self.app)
        self.head_open.tk.call(self.head_open, 'copy', im.get('N2U'), '-from', 0, s(18), s(8), s(25))

    def _build(self):
        b = self.body
        tb = Toolbar(b, self.app)
        tb.pack(side='top', fill='x')
        tb.add_button('MENU_BM', self.functions_menu, pressed='MENU_BM_PR')
        self.add_toggles(tb)
        self.add_close_recall(tb)
        tb.add_button('BUT_PAGE', self.toggle_preview, pressed='BUT_PAGE_PR')
        tb.add_label('Resolution', 56)
        self.res = tb.add_combo(RESOLUTIONS, 46, '16', cmd=lambda v: self.redraw(), listw=50)
        tb.add_label('Note Len', 46)
        self.notelen = tb.add_combo(NOTE_LENS, 46, '8', listw=50)
        self.info = InfoLine(b, self.app, self.info_fields() + [('Mouse', 200)])
        self.info.pack(side='top', fill='x')
        fr = tk.Frame(b, bg=ui.FACE)
        fr.pack(side='top', fill='both', expand=True)
        self.vbar = tk.Scrollbar(fr, orient='vertical', command=self._vscroll)
        self.vbar.pack(side='right', fill='y')
        self.c = tk.Canvas(fr, bg=ui.WINDOW, highlightthickness=0, bd=0)
        self.c.pack(side='left', fill='both', expand=True)
        self.c.bind('<Configure>', lambda e: self.redraw())
        self.c.bind('<ButtonPress-1>', self._press)
        self.c.bind('<B1-Motion>', self._drag)
        self.c.bind('<ButtonRelease-1>', self._release)
        self.c.bind('<Motion>', self._motion)
        self.tool.bind(self.c)
        self.c.bind('<MouseWheel>', lambda e: self._vscroll('scroll', -1 if e.delta > 0 else 1, 'units'))
        self.c.bind('<Button-4>', lambda e: self._vscroll('scroll', -1, 'units'))
        self.c.bind('<Button-5>', lambda e: self._vscroll('scroll', 1, 'units'))

    def step_length(self):
        return note_ticks(self.notelen.value, self.app.song.timebase)

    @property
    def cfg(self):
        return self.app.settings['score']

    @property
    def stave_gap(self):
        """Inter-stave distance: the Score Settings value is in points."""
        return max(40, int(round(self.cfg.get('interstave', 53) * 4 / 3.0)))

    # ---- clef choice
    def staves(self):
        """List of (clef, lo, hi) note ranges shown on each system."""
        clef = self.cfg.get('clef', 0)
        notes = [e.d1 for e in self.events if e.is_note()]
        if self.cfg.get('auto', True) and notes:
            lo, hi = min(notes), max(notes)
            split = self.cfg.get('split', 60)
            if lo < split - 5 and hi > split + 4:
                clef = 3
            elif sum(notes) / len(notes) < 57:
                clef = 4
            else:
                clef = 0
        split = self.cfg.get('split', 60)
        oct_ = {1: 12, 2: -12, 5: 12, 6: -12}.get(clef, 0)
        if clef == 3:
            return [('treble', split, 127, 0), ('bass', 0, split - 1, 0)]
        if clef in (4, 5, 6):
            return [('bass', 0, 127, oct_)]
        return [('treble', 0, 127, oct_)]

    # ---- quantize into bars of chords/rests
    def quantum(self):
        return note_ticks(self.res.value.strip(), self.app.song.timebase)

    def bars(self):
        """[(bar_tick, bar_len, num, den, [(start, dur, [events])...])] relative to the pattern."""
        tm = self.app.tmap
        p = self.pattern
        q = self.quantum()
        out = []
        evs = [e for e in self.events if e.is_note() and e.tick < p.length]
        for tick, bar, tpbeat, beats in tm.bar_lines(p.start, p.start + p.length - 1):
            rel = tick - p.start
            blen = tpbeat * beats
            from ..timing import ts_parts
            num, den = ts_parts(self.song.conductor.at(COND_TIMESIG, tick).value)
            onsets = {}
            for e in evs:
                st = int(round(e.tick / q)) * q
                if rel <= st < rel + blen:
                    onsets.setdefault(st, []).append(e)
            out.append([rel, blen, num, den, sorted(onsets.items())])
        return out

    # ---- drawing
    def redraw(self):
        if not self.winfo_exists():
            return
        c = self.c
        c.delete('all')
        self.hits = []
        W = c.winfo_width() // ui.S
        flats = KEY_SHARPS.get(self.song.conductor.at(COND_KEY, self.pattern.start).value % 12, 0) < 0
        staves = self.staves()
        bars = self.bars()
        tb = self.song.timebase
        internote = max(8, int(self.cfg.get('internote', 11) * 4 / 3) + 4)   # points -> pixels
        # lay out bars into systems
        systems = []
        cur = []
        x = 0
        header_w = 64
        avail = W - LEFT - 6
        for b in bars:
            n = sum(len(split_value(min(d, b[1]), tb)) for d in [b[1]]) + len(b[4]) * 2
            bw = max(80, (len(b[4]) + 1) * internote + 8)
            if cur and x + bw > avail - header_w:
                systems.append(cur)
                cur, x = [], 0
            cur.append([b, bw])
            x += bw
        if cur:
            systems.append(cur)
        # stretch bars to fill each system
        for sysbars in systems:
            tot = sum(bw for _b, bw in sysbars)
            k = (avail - header_w) / max(1, tot)
            if sysbars is not systems[-1] or len(sysbars) > 1 or k < 3:
                for item in sysbars:
                    item[1] = item[1] * k
        sys_h = self.stave_gap * len(staves)
        nshow = max(len(systems), (c.winfo_height() // ui.S) // sys_h + 1)
        y0 = 36 - self.top
        self.layout_rows = []
        key_val = self.song.conductor.at(COND_KEY, self.pattern.start).value % 12
        bar_no = 1
        for si in range(nshow):
            ys = [y0 + si * sys_h + k * self.stave_gap for k in range(len(staves))]
            for k, (clef, lo, hi, oct_) in enumerate(staves):
                y = ys[k]
                if y > c.winfo_height() // ui.S + 40 or y + 30 < 0:
                    continue
                for ln in range(5):
                    ui.line(c, LEFT + 8, y + ln * LINE, W - 6, y + ln * LINE)
                ui.line(c, LEFT + 8, y, LEFT + 8, y + 4 * LINE)
                ui.line(c, W - 6, y, W - 6, y + 4 * LINE)
                if clef == 'treble':
                    ui.image(c, LEFT + 10, y - 11, self.app.images.get('TRCLEF'))
                else:
                    ui.image(c, LEFT + 10, y - 1, self.app.images.get('BASSCLEF'))
                kx = self._draw_keysig(c, LEFT + 32, y, clef, key_val)
                if si == 0:
                    num, den = (bars[0][2], bars[0][3]) if bars else (4, 4)
                    self._draw_digits(c, kx + 2, y, num)
                    self._draw_digits(c, kx + 2, y + 2 * LINE, den)
            if len(staves) == 2:
                ui.line(c, LEFT + 8, ys[0], LEFT + 8, ys[1] + 4 * LINE)
            if si >= len(systems):
                continue
            x = LEFT + 8 + header_w
            for b, bw in systems[si]:
                rel, blen, num, den, onsets = b
                ui.text(c, x + 2, ys[0] - 14, str(bar_no), 'score', fill='#800000')
                self.layout_rows.append((rel, blen, x, bw, ys, staves))
                for k, st in enumerate(staves):
                    self._draw_bar(c, b, x, bw, ys[k], st, flats, key_val)
                x += bw
                for k in range(len(staves)):
                    ui.line(c, x, ys[k], x, ys[k] + 4 * LINE)
                bar_no += 1
        self._draw_lyrics()
        self._draw_cursor()
        self.update_info()
        tot = max(1, len(systems) * sys_h + 60)
        H = c.winfo_height() // ui.S
        self.vbar.set(self.top / tot, min(1, (self.top + H) / tot))

    def _draw_keysig(self, c, x, y, clef, key):
        n = KEY_SHARPS.get(key, 0)
        if n == 0:
            return x
        glyph = self.app.images.get('SHARP' if n > 0 else 'FLAT')
        order = SHARP_ORDER if n > 0 else FLAT_ORDER
        top_step = diatonic(CLEF_TOP[clef], False)[0]
        for i in range(abs(n)):
            letter = order[i]
            # place in the octave that sits on/inside the staff
            for octv in range(2, 8):
                step = octv * 7 + letter
                pos = top_step - step
                if 0 <= pos <= 8 if n > 0 else -1 <= pos <= 8:
                    break
            yy = y + pos * LINE / 2
            ui.image(c, x, yy - (10 if n > 0 else 13), glyph)
            x += 7
        return x + 2

    def _draw_digits(self, c, x, y, n):
        for ch in str(n):
            ui.image(c, x, y - 1, self.app.images.get('TS' + ch))
            x += 9

    def _note_y(self, y, clef, note, oct_, flats):
        step, acc = diatonic(note - oct_, flats)
        top = diatonic(CLEF_TOP[clef], False)[0]
        return y + (top - step) * LINE / 2, acc, step

    def _draw_bar(self, c, b, x, bw, y, staff, flats, key):
        rel, blen, num, den, onsets = b
        clef, lo, hi, oct_ = staff
        tb = self.song.timebase
        img = self.app.images
        key_acc = {}
        n = KEY_SHARPS.get(key, 0)
        for i in range(abs(n)):
            key_acc[(SHARP_ORDER if n > 0 else FLAT_ORDER)[i]] = 1 if n > 0 else -1
        bar_acc = {}

        def xpos(t):
            return x + 10 + (t - rel) / blen * (bw - 16)

        chords = []
        for st, evs in onsets:
            mine = [e for e in evs if lo <= e.d1 <= hi]
            if mine:
                chords.append((st, mine))
        # durations: until next chord on this staff, bar end, or the note length
        items = []
        t = rel
        for i, (st, evs) in enumerate(chords):
            if st > t:
                items.append(('rest', t, st - t, None))
            nxt = chords[i + 1][0] if i + 1 < len(chords) else rel + blen
            q = self.quantum()
            ln = max(q, int(round(max(e.length for e in evs) / q)) * q)
            gap = min(nxt, rel + blen) - st
            # a note sounds until the next one unless it is much shorter (then a rest follows)
            dur = gap if ln * 2 >= gap else min(gap, ln)
            items.append(('chord', st, dur, evs))
            t = st + dur
        if t < rel + blen:
            items.append(('rest', t, rel + blen - t, None))
        if not chords:
            items = [('rest', rel, blen, None)]
        beam_group = []
        for kind, st, dur, evs in items:
            pieces = split_value(dur, tb) if dur > 0 else []
            if kind == 'rest':
                if not pieces:
                    continue
                if dur == blen:
                    ui.image(c, (x + x + bw) / 2 - 3, y + LINE, img.get('REST1'))
                    continue
                tt = st
                for v, dotted, t_len in pieces:
                    name = {1: 'REST1', 2: 'REST1', 4: 'REST4', 8: 'REST8', 16: 'REST16', 32: 'REST32',
                            64: 'REST64'}[v]
                    ry = {1: y + LINE, 2: y + 2 * LINE - 3, 4: y + 3, 8: y + LINE, 16: y + LINE,
                          32: y + 3, 64: y}[v]
                    ui.image(c, xpos(tt), ry, img.get(name))
                    if dotted:
                        c.create_oval(s(xpos(tt) + 10), s(y + 2 * LINE - 1), s(xpos(tt) + 12), s(y + 2 * LINE + 1),
                                      fill='black')
                    tt += t_len
                self._flush_beams(c, beam_group, y)
                beam_group = []
                continue
            v, dotted, t_len = pieces[0]
            ys = []
            for e in evs:
                ny, acc, step = self._note_y(y, clef, e.d1, oct_, flats)
                ys.append((ny, acc, step, e))
            ys.sort()
            mid = y + 2 * LINE
            up = sum(yy for yy, *_ in ys) / len(ys) > mid
            nx = xpos(st)
            # ledger lines and accidentals
            for ny, acc, step, e in ys:
                letter = step % 7
                want = acc
                cur = bar_acc.get(step, key_acc.get(letter, 0))
                if want != cur:
                    gl = {1: 'SHARP', -1: 'FLAT', 0: 'NATURAL'}[want]
                    ui.image(c, nx - 8, ny - 10 if want != -1 else ny - 13, img.get(gl))
                    bar_acc[step] = want
                ly = y - LINE
                while ly >= ny - 1:
                    ui.line(c, nx - 2, ly, nx + 10, ly)
                    ly -= LINE
                ly = y + 5 * LINE
                while ly <= ny + 1:
                    ui.line(c, nx - 2, ly, nx + 10, ly)
                    ly += LINE
            # heads
            for ny, acc, step, e in ys:
                head = self.head_open if v <= 2 else self.head_filled
                if v == 1:
                    ui.image(c, nx, ny - 3, img.get('N1'))
                else:
                    ui.image(c, nx, ny - 3, head)
                if e.selected:
                    c.create_rectangle(s(nx - 1), s(ny - 4), s(nx + 9), s(ny + 4), outline='#0000ff', width=ui.S)
                self.hits.append((nx - 1, ny - 4, nx + 9, ny + 4, e))
                if dotted:
                    c.create_oval(s(nx + 10), s(ny - 1), s(nx + 12), s(ny + 1), fill='black')
            if v == 1:
                beam_group = self._flush_beams(c, beam_group, y)
                continue
            top_y = min(yy for yy, *_ in ys)
            bot_y = max(yy for yy, *_ in ys)
            if up:
                sx, sy0, sy1 = nx + 7, bot_y, top_y - 3 * LINE + 1
            else:
                sx, sy0, sy1 = nx, top_y, bot_y + 3 * LINE - 1
            beat = tb * 4 // den
            if v >= 8 and len(pieces) == 1:
                if beam_group and (st - rel) // beat != beam_group[-1][5]:
                    beam_group = self._flush_beams(c, beam_group, y)
                beam_group.append((sx, sy0, sy1, v, up, (st - rel) // beat))
            else:
                beam_group = self._flush_beams(c, beam_group, y)
                ui.line(c, sx, sy0, sx, sy1)
                if v >= 8:
                    flag = img.get('N%dU' % v if up else 'N%dD' % v)
                    if up:
                        ui.image(c, nx, sy1, flag)
                    else:
                        ui.image(c, nx, sy1 - 25, flag)
            # tie into the remaining pieces of a long note
            tt = st + t_len
            for v2, d2, l2 in pieces[1:]:
                nx2 = xpos(tt)
                for ny, acc, step, e in ys:
                    c.create_arc(s(nx + 6), s(ny + 2), s(nx2 + 2), s(ny + 8), start=180, extent=180, style='arc',
                                 width=ui.S)
                    ui.image(c, nx2, ny - 3, self.head_open if v2 <= 2 else self.head_filled)
                tt += l2
            if (st - rel + dur) % (tb * 4 // den) == 0:
                beam_group = self._flush_beams(c, beam_group, y)
        self._flush_beams(c, beam_group, y)

    def _same_beat(self, st, tb):
        return True

    def _flush_beams(self, c, group, y):
        if not group:
            return []
        if len(group) == 1:
            sx, sy0, sy1, v, up, _b = group[0]
            ui.line(c, sx, sy0, sx, sy1)
            img = self.app.images.get('N%dU' % v if up else 'N%dD' % v)
            if up:
                ui.image(c, sx - 7, sy1, img)
            else:
                ui.image(c, sx, sy1 - 25, img)
            return []
        up = sum(1 for g in group if g[4]) >= len(group) / 2
        if up:
            beam_y = min(g[2] for g in group)
        else:
            beam_y = max(g[2] for g in group)
        x0, x1 = group[0][0], group[-1][0]
        sloped = self.cfg.get('beam_screen', True)
        y_first = group[0][2] if sloped else beam_y
        y_last = group[-1][2] if sloped else beam_y
        if sloped:
            # keep the slope gentle and clear of every stem
            slope = max(-0.25, min(0.25, (y_last - y_first) / max(1, x1 - x0)))
            base = beam_y
            def by(x):
                return base + (x - x0) * slope - (min(0, (x1 - x0) * slope) if up else max(0, (x1 - x0) * slope))
        else:
            def by(x):
                return beam_y
        for sx, sy0, sy1, v, gup, _b in group:
            ui.line(c, sx, sy0, sx, by(sx))
        levels = max(1, {8: 1, 16: 2, 32: 3, 64: 4}.get(max(g[3] for g in group), 1))
        for lvl in range(levels):
            off = lvl * 4 * (1 if up else -1)
            members = [g for g in group if {8: 1, 16: 2, 32: 3, 64: 4}[g[3]] > lvl]
            if len(members) >= 2 or lvl == 0:
                xa, xb = (members[0][0], members[-1][0]) if len(members) >= 2 else (x0, x1)
                for t in range(3):
                    c.create_line(s(xa), s(by(xa) + off + (t if up else -t)), s(xb), s(by(xb) + off + (t if up else -t)),
                                  fill=ui.TEXT, width=ui.S)
            elif members:
                g = members[0]
                xa = g[0]
                for t in range(3):
                    c.create_line(s(xa), s(by(xa) + off + t), s(xa + 6), s(by(xa) + off + t), fill=ui.TEXT, width=ui.S)
        return []

    def _draw_lyrics(self):
        lyr = self.song.lyric_list()
        if not lyr:
            return
        c = self.c
        p = self.pattern
        for tick, text in lyr:
            rel = tick - p.start
            for brel, blen, x, bw, ys, staves in self.layout_rows:
                if brel <= rel < brel + blen:
                    lx = x + 10 + (rel - brel) / blen * (bw - 16)
                    ly = ys[-1] + 5 * LINE + 14
                    ui.text(c, lx, ly, text.replace('\n', ''), 'score')
                    break

    def _draw_cursor(self):
        c = self.c
        c.delete('cursor')
        rel = self.app.seq.position - self.pattern.start
        for brel, blen, x, bw, ys, staves in self.layout_rows:
            if brel <= rel < brel + blen:
                cx = x + 10 + (rel - brel) / blen * (bw - 16)
                c.create_line(s(cx), s(ys[0] - 10), s(cx), s(ys[-1] + 5 * LINE + 6), fill='#0000ff', width=ui.S,
                              tags='cursor')
                return

    def set_position(self, tick, follow=False):
        self._draw_cursor()

    def _vscroll(self, *a):
        H = self.c.winfo_height() // ui.S
        if a[0] == 'moveto':
            tot = max(1, len(self.layout_rows) * self.stave_gap)
            self.top = int(float(a[1]) * tot)
        else:
            self.top += int(a[1]) * (self.stave_gap if a[2] == 'units' else H)
        self.top = max(0, self.top)
        self.redraw()

    # ---- mouse
    def _locate(self, x, y):
        """Screen point -> (relative tick, staff tuple, staff y) or None."""
        for brel, blen, bx, bw, ys, staves in self.layout_rows:
            if bx <= x < bx + bw:
                for k, yy in enumerate(ys):
                    if yy - 30 <= y <= yy + 4 * LINE + 30:
                        frac = (x - bx - 10) / max(1, bw - 16)
                        tick = brel + int(max(0, min(0.999, frac)) * blen)
                        return tick, staves[k], yy
        return None

    def _pitch_at(self, y, staff, yy):
        clef, lo, hi, oct_ = staff
        top = diatonic(CLEF_TOP[clef], False)[0]
        step = top - int(round((y - yy) / (LINE / 2)))
        octv, letter = divmod(step, 7)
        return max(0, min(127, octv * 12 + LETTER_PC[letter] + oct_))

    def _hit(self, ev):
        x, y = ev.x / ui.S, ev.y / ui.S
        for x0, y0, x1, y1, e in self.hits:
            if x0 <= x <= x1 and y0 <= y <= y1:
                return e
        return None

    def _motion(self, ev):
        loc = self._locate(ev.x / ui.S, ev.y / ui.S)
        if loc:
            tick, staff, yy = loc
            n = self._pitch_at(ev.y / ui.S, staff, yy)
            self.info.fields[5]['value'] = '%s  %s' % (note_name(n), self.app.tmap.fmt(self.pattern.start + tick))
            self.info.draw()

    def _press(self, ev):
        e = self._hit(ev)
        tool = self.tool.current
        app = self.app
        if tool == 'arrow':
            if e is None:
                self.deselect_all()
            elif ui.is_shift(ev):
                e.selected = not e.selected
            else:
                if not e.selected:
                    self.deselect_all()
                e.selected = True
                self.play_event(e)
                self.drag = (ev.y, e.d1, ev.x, e.tick)
            self.redraw()
        elif tool == 'note':
            loc = self._locate(ev.x / ui.S, ev.y / ui.S)
            if not loc:
                return
            tick, staff, yy = loc
            q = self.quantum()
            tick = int(round(tick / q)) * q
            n = self._pitch_at(ev.y / ui.S, staff, yy)
            app.checkpoint()
            ch = max(1, self.track.channel or 1) - 1
            ne = Event(tick, 0x90 | ch, n, app.settings['prefs'].get('kbd_velocity', 100), self.step_length())
            self.events.append(ne)
            self.events.sort(key=lambda q: q.tick)
            self.play_event(ne)
            app.song_changed('events')
        elif tool == 'eraser':
            if e is not None:
                app.checkpoint()
                self.events.remove(e)
                app.song_changed('events')
            else:
                self._erase_lyric(ev)
        elif tool in ('sharp', 'flat') and e is not None:
            app.checkpoint()
            d = (12 if ui.is_shift(ev) else 1) * (1 if tool == 'sharp' else -1)
            e.d1 = max(0, min(127, e.d1 + d))
            app.song_changed('events')
        elif tool == 'glue' and e is not None:
            nxt = [q for q in self.events if q.is_note() and q.d1 == e.d1 and q.tick >= e.tick + e.length and q is not e]
            if nxt:
                app.checkpoint()
                q = min(nxt, key=lambda q: q.tick)
                e.length = q.tick + q.length - e.tick
                self.events.remove(q)
                app.song_changed('events')
        elif tool in ('pen', 'pennote'):
            loc = self._locate(ev.x / ui.S, ev.y / ui.S)
            if not loc:
                return
            tick = loc[0]
            if e is not None:
                tick = e.tick
            txt = simpledialog.askstring('Lyrics', 'Lyric:', parent=self.app)
            if txt:
                app.checkpoint()
                lyr = self.song.lyric_list()
                lyr = [l for l in lyr if l[0] != self.pattern.start + tick]
                lyr.append([self.pattern.start + tick, txt + ' '])
                self.song.set_lyrics(lyr)
                app.song_changed('lyrics')

    def _erase_lyric(self, ev):
        loc = self._locate(ev.x / ui.S, ev.y / ui.S)
        if not loc:
            return
        tick = self.pattern.start + loc[0]
        lyr = self.song.lyric_list()
        if not lyr:
            return
        best = min(lyr, key=lambda l: abs(l[0] - tick))
        if abs(best[0] - tick) <= self.quantum() * 2:
            self.app.checkpoint()
            lyr.remove(best)
            self.song.set_lyrics(lyr)
            self.app.song_changed('lyrics')

    def _drag(self, ev):
        if not self.drag or self.tool.current != 'arrow':
            return
        y0, n0, x0, t0 = self.drag
        steps = int(round((y0 - ev.y) / ui.S / (LINE / 2)))
        e = self.first_selected()
        if e is None:
            return
        flats = KEY_SHARPS.get(self.song.conductor.at(COND_KEY, self.pattern.start).value % 12, 0) < 0
        st, _acc = diatonic(n0, flats)
        target = st + steps
        octv, letter = divmod(target, 7)
        new = max(0, min(127, octv * 12 + LETTER_PC[letter]))
        if new != e.d1:
            if not getattr(self, '_dragged', False):
                self.app.checkpoint()
                self._dragged = True
            e.d1 = new
            self.play_event(e)
            self.redraw()

    def _release(self, ev):
        if getattr(self, '_dragged', False):
            self._dragged = False
            self.app.song_changed('events')
        self.drag = None

    # ---- functions / printing
    def functions_menu(self):
        st = resources.string
        items = [(st(785), lambda: __import__('ssgold.dialogs', fromlist=['run']).run(self.app, 'SCORE_DLG')),
                 (st(786), self.print_score), (st(787), self.print_score), (st(788), self.delete_lyrics)]
        PopupMenu.show(self, items, self.winfo_rootx() + ui.s(8), self.body.winfo_rooty() + ui.s(18))

    def delete_lyrics(self):
        self.app.checkpoint()
        p = self.pattern
        lyr = [l for l in self.song.lyric_list() if not p.start <= l[0] < p.end]
        self.song.set_lyrics(lyr)
        self.app.song_changed('lyrics')

    def toggle_preview(self):
        self.preview = not self.preview
        self.print_score(preview=True)

    def print_score(self, preview=False):
        """Printing is done to a PostScript file (portable replacement for the Windows printer)."""
        path = filedialog.asksaveasfilename(parent=self.app, defaultextension='.ps',
                                            filetypes=[('PostScript', '*.ps')], title='Print Score to File')
        if path:
            self.c.postscript(file=path, colormode='mono', pagewidth='19c')
