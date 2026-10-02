"""Notepad window (MDINOTEPADWNDPROC): free text saved with the song."""
import tkinter as tk

from .. import ui
from ..mdi import MDIChild
from ..widgets import Toolbar


class NotepadWindow(MDIChild):
    icon_name = 'IC_NOTEPAD'

    def __init__(self, client, app):
        self.app = app
        W = max(300, client.winfo_width() // ui.S - client.reserved_right)
        H = max(200, client.winfo_height() // ui.S)
        x, y = W * 52 // 100, H * 48 // 100
        super().__init__(client, self._title(), app.small_icon(self.icon_name), x, y, W - x, H - y)
        b = self.body
        tb = Toolbar(b, app)
        tb.pack(side='top', fill='x')
        tb.add_button('BUT_CLOSE', self.close, pressed='BUT_CLOSE_PR')
        fr = tk.Frame(b, bg=ui.WINDOW, bd=0)
        fr.pack(side='top', fill='both', expand=True)
        self.vbar = tk.Scrollbar(fr, orient='vertical')
        self.vbar.pack(side='right', fill='y')
        self.text = tk.Text(fr, wrap='word', font=ui.f('system'), bg=ui.WINDOW, fg=ui.TEXT, bd=0,
                            highlightthickness=0, undo=True, padx=ui.s(2), pady=0,
                            yscrollcommand=self.vbar.set, insertwidth=ui.s(1))
        self.text.pack(side='left', fill='both', expand=True)
        self.vbar.configure(command=self.text.yview)
        self.load()
        self.text.bind('<<Modified>>', self._modified)
        self.text.focus_set()

    def _title(self):
        return 'Notepad - %s' % self.app.song_name()

    def load(self):
        self._loading = True
        self.text.delete('1.0', 'end')
        self.text.insert('1.0', self.app.song.notepad.replace('\r\n', '\n'))
        self.text.edit_reset()
        self.text.edit_modified(False)
        self._loading = False

    def _modified(self, _e=None):
        if not self.text.edit_modified():
            return
        self.text.edit_modified(False)
        if self._loading:
            return
        self.app.song.notepad = self.text.get('1.0', 'end-1c')
        self.app.song.modified = True

    def refresh(self, what=None):
        self.set_title(self._title())
        if what is None and self.text.get('1.0', 'end-1c') != self.app.song.notepad.replace('\r\n', '\n'):
            self.load()

    def on_activate(self):
        self.text.focus_set()

    # ---- Edit menu acts on the text (the clipboard's patterns/events are kept)
    def edit_copy(self):
        self.text.event_generate('<<Copy>>')

    def edit_cut(self):
        self.text.event_generate('<<Cut>>')

    def edit_paste(self):
        self.text.event_generate('<<Paste>>')

    def edit_clear(self):
        try:
            self.text.delete('sel.first', 'sel.last')
        except tk.TclError:
            pass

    def edit_select_all(self):
        self.text.tag_add('sel', '1.0', 'end-1c')

    def edit_undo(self):
        try:
            self.text.edit_undo()
        except tk.TclError:
            pass

    def edit_redo(self):
        try:
            self.text.edit_redo()
        except tk.TclError:
            pass
