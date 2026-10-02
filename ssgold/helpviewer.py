"""Help: a WinHelp-style viewer for the original GOLDHELP.HLP.

tools/extract_assets.py decodes the help file into assets/help.json (each topic a list of
paragraphs, each a list of runs [text, style] or [None, {bm}] for a picture) and the pictures into
assets/help/.  Links go to the topics the original's hotspots point at; popup links open the
topic in a small window, as WinHelp does.
"""
import json
import os
import tkinter as tk
import tkinter.font as tkfont

from . import resources, ui

_topics = None
_viewer = None
_fonts = {}
_images = {}

LINK = '#008000'
TAB = 36                # default tab stop (pixels)


def topics():
    global _topics
    if _topics is None:
        p = resources.path('help.json')
        _topics = {}
        if os.path.exists(p):
            with open(p, encoding='utf-8') as f:
                _topics = json.load(f)
    return _topics


def _font(size, bold, italic):
    px = max(8, round((size or 10) * 96 / 72)) * ui.S
    key = (px, bold, italic)
    if key not in _fonts:
        fam = ui._family(_viewer or tk._default_root, ('Arial', 'Liberation Sans', 'Helvetica', 'DejaVu Sans'))
        _fonts[key] = tkfont.Font(family=fam, size=-px, weight='bold' if bold else 'normal',
                                  slant='italic' if italic else 'roman')
    return _fonts[key]


def _image(n):
    if n not in _images:
        p = resources.path('help', 'bm%d.png' % n)
        img = None
        if os.path.exists(p):
            img = tk.PhotoImage(file=p)
            if ui.S > 1:
                img = img.zoom(ui.S)
        _images[n] = img
    return _images[n]


def render(t, name, on_link, on_popup):
    """Write topic `name` into Text widget t."""
    t.configure(state='normal')
    t.delete('1.0', 'end')
    t.configure(tabs=(ui.s(TAB),))
    t.update_idletasks()
    width = max(ui.s(300), t.winfo_width() - ui.s(24))
    n = 0
    tags_made = []
    for para in topics().get(name, []):
        cols = next((st['cell'] for txt, st in para if st.get('cell')), None)
        ptag = 'para'
        if cols:                                  # a table row: the columns in the original's proportions
            cols = cols if isinstance(cols, list) and all(c > 0 for c in cols) else [1] * (len(para) + 1)
            ptag = 'table%d' % len(tags_made)
            tags_made.append(ptag)
            total, edge, stops = sum(cols), 0, []
            for c in cols[:-1]:
                edge += c
                stops.append(width * edge // total)
            t.tag_configure(ptag, tabs=tuple(stops))
        for txt, st in para:
            if txt is None:
                img = _image(st.get('bm'))
                if img is not None:
                    t.image_create('end', image=img, padx=ui.s(2), pady=ui.s(2))
                continue
            tags = [ptag, _style_tag(t, st)]
            target = st.get('link') or st.get('popup')
            if target and target in topics() and not st.get('cell'):
                n += 1
                tag = 'hot%d' % n
                tags += ['link' if st.get('link') else 'popup', tag]
                fn = on_link if st.get('link') else on_popup
                t.tag_bind(tag, '<Button-1>', lambda e, x=target, f=fn: f(x, e))
            t.insert('end', txt, tuple(tags))
        t.insert('end', '\n', ptag)
    t.configure(state='disabled')


def _style_tag(t, st):
    size, b, i = st.get('size', 10), bool(st.get('b')), bool(st.get('i'))
    color = st.get('color') or '#000000'
    name = 'f%s_%d%d_%s' % (size, b, i, color[1:])
    if name not in t.tag_names():
        t.tag_configure(name, font=_font(size, b, i), foreground=color)
        t.tag_lower(name)
    return name


def _setup_text(t):
    t.tag_configure('link', foreground=LINK, underline=True)
    t.tag_configure('popup', foreground=LINK, underline=True)
    for tag in ('link', 'popup'):
        t.tag_raise(tag)
        t.tag_bind(tag, '<Enter>', lambda e, w=t: w.configure(cursor='hand2'))
        t.tag_bind(tag, '<Leave>', lambda e, w=t: w.configure(cursor='arrow'))


class HelpViewer(tk.Toplevel):
    def __init__(self, app):
        super().__init__(app)
        self.app = app
        self.title('Sound Studio Gold Help')
        self.configure(bg=ui.FACE)
        self.geometry('%dx%d' % (ui.s(600), ui.s(500)))
        self.history = []
        self.current = None
        self.pop = None
        bar = tk.Frame(self, bg=ui.FACE)
        bar.pack(side='top', fill='x', padx=ui.s(2), pady=ui.s(2))
        for label, cmd in (('Contents', lambda: self.show_topic('Contents')), ('Index', self.show_index),
                           ('Back', self.back)):
            tk.Button(bar, text=label, font=ui.f('dialog'), width=8, command=cmd, relief='raised', bd=2,
                      bg=ui.FACE, fg=ui.TEXT, activebackground=ui.FACE).pack(side='left', padx=ui.s(1))
        fr = tk.Frame(self, bd=2, relief='sunken')
        fr.pack(side='top', fill='both', expand=True)
        sb = tk.Scrollbar(fr)
        sb.pack(side='right', fill='y')
        self.txt = tk.Text(fr, wrap='word', font=_font(10, False, False), padx=ui.s(8), pady=ui.s(6), bd=0,
                           bg='#ffffff', fg=ui.TEXT, yscrollcommand=sb.set, cursor='arrow', spacing1=ui.s(1),
                           spacing3=ui.s(2))
        self.txt.pack(side='left', fill='both', expand=True)
        sb.configure(command=self.txt.yview)
        _setup_text(self.txt)
        self.txt.tag_configure('h', font=_font(14, True, False), spacing3=ui.s(6))
        self.txt.tag_configure('index', foreground=LINK, underline=True)
        self.txt.tag_bind('index', '<Enter>', lambda e: self.txt.configure(cursor='hand2'))
        self.txt.tag_bind('index', '<Leave>', lambda e: self.txt.configure(cursor='arrow'))
        self.protocol('WM_DELETE_WINDOW', self._close)
        self.bind('<Escape>', lambda e: self._close_popup())

    def _close(self):
        global _viewer
        _viewer = None
        self._close_popup()
        self.destroy()

    def back(self):
        if self.history:
            self.current = None
            self.show_topic(self.history.pop(), remember=False)

    def show_index(self):
        self._close_popup()
        if self.current:
            self.history.append(self.current)
        self.current = None
        t = self.txt
        t.configure(state='normal')
        t.delete('1.0', 'end')
        t.insert('end', 'Index\n', 'h')
        for k, n in enumerate(sorted(topics(), key=str.lower)):
            tag = 'ix%d' % k
            t.insert('end', n, ('index', tag))
            t.tag_bind(tag, '<Button-1>', lambda e, x=n: self.show_topic(x))
            t.insert('end', '\n')
        t.configure(state='disabled')
        t.yview_moveto(0)

    def show_topic(self, name, remember=True):
        if name not in topics():
            return
        self._close_popup()
        if remember and self.current and self.current != name:
            self.history.append(self.current)
        self.current = name
        render(self.txt, name, lambda x, e: self.show_topic(x), self.popup)
        self.txt.yview_moveto(0)
        self.lift()

    # ---- popups
    def popup(self, name, ev=None):
        self._close_popup()
        top = tk.Toplevel(self)
        top.overrideredirect(True)
        top.configure(bg='#000000')
        t = tk.Text(top, wrap='word', width=48, height=4, bd=0, bg='#ffffe1', fg=ui.TEXT, padx=ui.s(6),
                    pady=ui.s(4), cursor='arrow', font=_font(10, False, False))
        t.pack(padx=1, pady=1)
        _setup_text(t)
        render(t, name, lambda x, e: self.show_topic(x), self.popup)
        t.update_idletasks()
        lines = t.count('1.0', 'end', 'displaylines')
        t.configure(height=min(20, max(1, (lines[0] if lines else 4) - 1)))
        x = (ev.x_root if ev else self.winfo_rootx() + 40) - ui.s(20)
        y = (ev.y_root if ev else self.winfo_rooty() + 40) + ui.s(12)
        top.geometry('+%d+%d' % (x, y))
        t.bind('<Button-1>', lambda e: self.after_idle(self._close_popup), add='+')
        self.pop = top

    def _close_popup(self):
        if self.pop is not None:
            try:
                self.pop.destroy()
            except tk.TclError:
                pass
            self.pop = None


def show(app, title):
    global _viewer
    if _viewer is None or not _viewer.winfo_exists():
        _viewer = HelpViewer(app)
    _viewer.show_topic(title if title in topics() else 'Contents')
    _viewer.lift()
    _viewer.focus_set()
