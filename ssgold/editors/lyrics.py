"""Lyrics window (MDILYRICWNDPROC): the song's lyric sheet, highlighted karaoke-style during play."""
import tkinter as tk
from tkinter import font as tkfont

from .. import ui
from ..mdi import MDIChild
from ..ui import s
from ..widgets import Toolbar

DEFAULT_FONT = ['Arial', 14, False, False]      # family, points, bold, italic
HILITE = '#ff0000'
MARGIN = 4


def lyric_font(app):
    cur = list(app.settings.get('lyric_font') or DEFAULT_FONT)
    fam, pts, bold, italic = (cur + DEFAULT_FONT[len(cur):])[:4]
    fams = {f.lower(): f for f in tkfont.families(app)}
    if fam.lower() not in fams:
        for alt in ('Arial', 'Liberation Sans', 'Helvetica', 'DejaVu Sans'):
            if alt.lower() in fams:
                fam = fams[alt.lower()]
                break
    px = -int(round(pts * 96 / 72.0)) * ui.S
    return tkfont.Font(root=app, family=fam, size=px, weight='bold' if bold else 'normal',
                       slant='italic' if italic else 'roman')


class LyricsWindow(MDIChild):
    icon_name = 'IC_LYRIC'

    def __init__(self, client, app):
        self.app = app
        self.current = -1
        cw = max(300, client.winfo_width() // ui.S - client.reserved_right - 2)
        ch = max(200, client.winfo_height() // ui.S)
        super().__init__(client, self._title(), app.small_icon(self.icon_name), 0, 0, cw, ch)
        b = self.body
        tb = Toolbar(b, app)
        tb.pack(side='top', fill='x')
        tb.add_button('BUT_CLOSE', self.close, pressed='BUT_CLOSE_PR')
        self.c = tk.Canvas(b, bg=ui.FACE, highlightthickness=0, bd=0)
        self.c.pack(side='top', fill='both', expand=True)
        self.c.bind('<Configure>', lambda e: self.redraw())
        self.font = lyric_font(app)
        self.scroll = 0
        self.maximize()

    def _title(self):
        return 'Lyrics - %s' % self.app.song_name()

    def refresh(self, what=None):
        self.set_title(self._title())
        self.font = lyric_font(self.app)
        self.redraw()

    def layout(self):
        """[(index, x, line, text)] with word wrap at the window width; '\\n' ends a line."""
        W = self.c.winfo_width() // ui.S - 2 * MARGIN
        f = self.font
        out = []
        x = 0
        line = 0
        word = []                  # syllables of the word being placed (wrap whole words)
        lyr = self.app.song.lyric_list()

        def place(items):
            nonlocal x, line
            width = sum(f.measure(t) for _i, t in items) / ui.S
            if x > 0 and x + width > W:
                x, line = 0, line + 1
            for i, t in items:
                out.append((i, x, line, t))
                x += f.measure(t) / ui.S

        for i, (_tick, text) in enumerate(lyr):
            brk = text.endswith('\n') or text.endswith('\r')
            t = text.rstrip('\r\n')
            word.append((i, t))
            if brk or t.endswith(' ') or not t.endswith('-'):
                place(word)
                word = []
            if brk:
                x, line = 0, line + 1
        if word:
            place(word)
        return out

    def redraw(self):
        if not self.winfo_exists():
            return
        c = self.c
        c.delete('all')
        lh = self.font.metrics('linespace') / ui.S
        self.items = []
        cur = self._current_index()
        self.current = cur
        H = c.winfo_height() // ui.S
        lay = self.layout()
        cur_line = next((ln for i, _x, ln, _t in lay if i == cur), 0)
        visible = max(1, int(H // lh))
        if cur_line < self.scroll or cur_line >= self.scroll + visible:
            self.scroll = max(0, cur_line - visible // 3)
        for i, x, ln, t in lay:
            y = MARGIN + (ln - self.scroll) * lh
            if y + lh < 0 or y > H:
                continue
            c.create_text(s(MARGIN + x), s(y), text=t, font=self.font, anchor='nw',
                          fill=HILITE if i == cur else '#000000', tags=('l%d' % i,))

    def _current_index(self):
        pos = self.app.seq.position
        cur = -1
        for i, (tick, _t) in enumerate(self.app.song.lyric_list()):
            if tick <= pos:
                cur = i
            else:
                break
        return cur

    def set_position(self, tick, follow=False):
        cur = self._current_index()
        if cur != self.current:
            self.redraw()


class FontDialog(tk.Toplevel):
    """Windows 'Font' common dialog: Font, Font style, Size and a Sample."""
    SIZES = [8, 9, 10, 11, 12, 14, 16, 18, 20, 22, 24, 26, 28, 36, 48, 72]
    STYLES = ['Regular', 'Italic', 'Bold', 'Bold Italic']

    def __init__(self, app, cur):
        super().__init__(app)
        self.withdraw()
        self.title('Font')
        self.configure(bg=ui.FACE)
        self.resizable(False, False)
        self.transient(app)
        self.result = None
        fam, pts, bold, italic = cur
        self.fams = sorted({f for f in tkfont.families(app) if not f.startswith('@')}, key=str.lower)
        self.v_fam = tk.StringVar(value=fam)
        self.v_style = tk.StringVar(value=self.STYLES[(2 if bold else 0) + (1 if italic else 0)])
        self.v_size = tk.StringVar(value=str(pts))
        df = ui.f('dialog')
        cols = [('Font:', self.v_fam, self.fams, 22), ('Font style:', self.v_style, self.STYLES, 14),
                ('Size:', self.v_size, [str(x) for x in self.SIZES], 6)]
        self.lists = []
        for col, (lab, var, values, w) in enumerate(cols):
            tk.Label(self, text=lab, font=df, bg=ui.FACE, anchor='w').grid(row=0, column=col, sticky='w',
                                                                         padx=s(6), pady=(s(6), 0))
            e = tk.Entry(self, textvariable=var, font=df, width=w, relief='sunken', bd=2)
            e.grid(row=1, column=col, sticky='we', padx=s(6))
            lb = tk.Listbox(self, font=df, height=7, width=w, exportselection=False, relief='sunken', bd=2)
            for v in values:
                lb.insert('end', v)
            lb.grid(row=2, column=col, sticky='we', padx=s(6))
            lb.bind('<<ListboxSelect>>', lambda e, lb=lb, var=var: (var.set(lb.get(lb.curselection()[0]))
                                                                     if lb.curselection() else None,
                                                                     self._sample()))
            if var.get() in values:
                i = values.index(var.get())
                lb.selection_set(i)
                lb.see(i)
            var.trace_add('write', lambda *_a: self._sample())
            self.lists.append(lb)
        bf = tk.Frame(self, bg=ui.FACE)
        bf.grid(row=0, column=3, rowspan=3, sticky='n', padx=s(6), pady=s(6))
        tk.Button(bf, text='OK', width=9, font=df, command=self._ok).pack(pady=(s(12), s(4)))
        tk.Button(bf, text='Cancel', width=9, font=df, command=self.destroy).pack()
        sf = tk.LabelFrame(self, text='Sample', font=df, bg=ui.FACE)
        sf.grid(row=3, column=1, columnspan=2, sticky='we', padx=s(6), pady=s(8))
        self.sample = tk.Label(sf, text='AaBbYyZz', bg=ui.FACE, height=2)
        self.sample.pack(fill='both', expand=True)
        self._sample()
        self.bind('<Return>', lambda e: self._ok())
        self.bind('<Escape>', lambda e: self.destroy())
        self.update_idletasks()
        x = app.winfo_rootx() + (app.winfo_width() - self.winfo_reqwidth()) // 2
        y = app.winfo_rooty() + (app.winfo_height() - self.winfo_reqheight()) // 3
        self.geometry('+%d+%d' % (x, y))
        self.deiconify()
        self.grab_set()

    def _values(self):
        try:
            pts = max(4, min(127, int(self.v_size.get())))
        except ValueError:
            pts = 14
        st = self.v_style.get()
        return [self.v_fam.get(), pts, 'Bold' in st, 'Italic' in st]

    def _sample(self):
        fam, pts, bold, italic = self._values()
        try:
            self.sample.configure(font=(fam, -int(round(pts * 96 / 72.0)) * ui.S, ('bold' if bold else 'normal'),
                                        ('italic' if italic else 'roman')))
        except tk.TclError:
            pass

    def _ok(self):
        self.result = self._values()
        self.destroy()


def choose_lyric_font(app):
    cur = list(app.settings.get('lyric_font') or DEFAULT_FONT)
    if len(cur) < 4:
        cur = (cur + DEFAULT_FONT[len(cur):])[:4]
    d = FontDialog(app, cur)
    app.wait_window(d)
    if d.result:
        app.settings['lyric_font'] = d.result
        app.song_changed('lyrics')
