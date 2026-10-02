"""Help: a WinHelp-style viewer for the topics decoded from the original GOLDHELP.HLP (assets/help.json)."""
import json
import os
import re
import tkinter as tk

from . import resources, ui

_topics = None
_pattern = None
_viewer = None


def topics():
    global _topics
    if _topics is None:
        p = resources.path('help.json')
        raw = json.load(open(p)) if os.path.exists(p) else {}
        _topics = {}
        for name, paras in raw.items():
            out = []
            for para in paras:
                try:      # the .hlp text is Windows-1252
                    para = para.encode('latin1').decode('cp1252')
                except UnicodeError:
                    pass
                para = ' '.join(para.split())
                if para and not (not out and para == name):
                    out.append(para)
            _topics[name] = out
    return _topics


def _link_re():
    """Regex matching any topic title (longest first) as a whole phrase."""
    global _pattern
    if _pattern is None:
        names = sorted((n for n in topics() if len(n) > 3), key=len, reverse=True)
        _pattern = re.compile(r'(?<![\w])(' + '|'.join(re.escape(n) for n in names) + r')(?![\w])') \
            if names else None
    return _pattern


class HelpViewer(tk.Toplevel):
    def __init__(self, app):
        super().__init__(app)
        self.app = app
        self.title('Sound Studio Gold Help')
        self.configure(bg=ui.FACE)
        self.geometry('%dx%d' % (ui.s(560), ui.s(460)))
        self.history = []
        self.current = None
        bar = tk.Frame(self, bg=ui.FACE)
        bar.pack(side='top', fill='x', padx=ui.s(2), pady=ui.s(2))
        for label, cmd in (('Contents', lambda: self.show_topic('Contents')), ('Index', self.show_index),
                           ('Back', self.back)):
            tk.Button(bar, text=label, font=ui.f('dialog'), width=8, command=cmd, relief='raised', bd=2,
                      bg=ui.FACE, activebackground=ui.FACE).pack(side='left', padx=ui.s(1))
        fr = tk.Frame(self, bd=2, relief='sunken')
        fr.pack(side='top', fill='both', expand=True)
        sb = tk.Scrollbar(fr)
        sb.pack(side='right', fill='y')
        self.txt = tk.Text(fr, wrap='word', font=ui.f('dialog'), padx=ui.s(8), pady=ui.s(6), bd=0,
                           bg='#ffffff', yscrollcommand=sb.set, cursor='arrow', spacing2=ui.s(1))
        self.txt.pack(side='left', fill='both', expand=True)
        sb.configure(command=self.txt.yview)
        self.txt.tag_configure('h', font=ui.f('dialogbold'), spacing3=ui.s(6))
        self.txt.tag_configure('link', foreground='#008000', underline=True)
        self.txt.tag_bind('link', '<Enter>', lambda e: self.txt.configure(cursor='hand2'))
        self.txt.tag_bind('link', '<Leave>', lambda e: self.txt.configure(cursor='arrow'))
        self.txt.tag_bind('link', '<Button-1>', self._click)
        self.protocol('WM_DELETE_WINDOW', self._close)

    def _close(self):
        global _viewer
        _viewer = None
        self.destroy()

    def _click(self, ev):
        idx = self.txt.index('@%d,%d' % (ev.x, ev.y))
        for name in self.txt.tag_names(idx):
            if name.startswith('to:'):
                self.show_topic(name[3:])
                return

    def back(self):
        if self.history:
            self.current = None
            self.show_topic(self.history.pop(), remember=False)

    def show_index(self):
        if self.current:
            self.history.append(self.current)
        self.current = None
        t = self.txt
        t.configure(state='normal')
        t.delete('1.0', 'end')
        t.insert('end', 'Index\n', 'h')
        for n in sorted(topics(), key=str.lower):
            t.insert('end', n, ('link', 'to:' + n))
            t.insert('end', '\n')
        t.configure(state='disabled')

    def show_topic(self, name, remember=True):
        tp = topics()
        if name not in tp:
            return
        if remember and self.current and self.current != name:
            self.history.append(self.current)
        self.current = name
        t = self.txt
        t.configure(state='normal')
        t.delete('1.0', 'end')
        t.insert('end', name + '\n', 'h')
        rx = _link_re()
        for para in tp[name]:
            pos = 0
            for m in (rx.finditer(para) if rx else ()):
                target = m.group(1)
                if target == name:
                    continue
                t.insert('end', para[pos:m.start()])
                t.insert('end', target, ('link', 'to:' + target))
                pos = m.end()
            t.insert('end', para[pos:] + '\n\n')
        t.configure(state='disabled')
        t.yview_moveto(0)
        self.lift()


def show(app, title):
    global _viewer
    if _viewer is None or not _viewer.winfo_exists():
        _viewer = HelpViewer(app)
    _viewer.show_topic(title if title in topics() else 'Contents')
    _viewer.lift()
    _viewer.focus_set()
