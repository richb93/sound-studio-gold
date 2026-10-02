"""Mouse tools: the right-button Mouse Tool Selector and Gold's custom cursors."""
import sys
import tkinter as tk

from . import ui, resources
from .ui import s

# Built-in cursor used where custom bitmap cursors are not supported (macOS Tk).
FALLBACK = {'CUR_PENCIL': 'pencil', 'CUR_ERASER': 'X_cursor', 'CUR_MUTE': 'circle', 'CUR_KNIFE': 'sb_v_double_arrow',
            'CUR_GLUE': 'dotbox', 'CUR_MODIFY': 'crosshair', 'CUR_DRUM1': 'hand2', 'CUR_DRUM2': 'hand1',
            'CUR_DRUMPLUS': 'sb_up_arrow', 'CUR_DRUMMINUS': 'sb_down_arrow', 'CUR_NOTE': 'dotbox',
            'CUR_SHARP': 'plus', 'CUR_FLAT': 'sb_down_arrow', 'CUR_PEN': 'pencil', 'CUR_PENNOTE': 'pencil',
            'CUR_SNAPLEFT': 'sb_left_arrow', 'CUR_SNAPRIGHT': 'sb_right_arrow'}


def cursor(name):
    """Tk cursor spec for one of Gold's CUR_* cursors (or '' for the arrow)."""
    if not name or name == 'CUR_ARROW':
        return ''
    if ui.S == 1:
        if sys.platform == 'win32':
            return '@' + resources.path('cursors', name + '.cur').replace('\\', '/')
        if sys.platform != 'darwin':
            return ('@%s' % resources.path('cursors', name + '.xbm'),
                    resources.path('cursors', name + '_mask.xbm'), 'black', 'white')
    return FALLBACK.get(name, '')


def set_cursor(widget, name):
    spec = cursor(name)
    try:
        widget.configure(cursor=spec)
    except tk.TclError:
        widget.configure(cursor=FALLBACK.get(name, ''))


class ToolSelector:
    """Pops up a grid of tool bitmaps under the mouse while the right button is held.
    Releasing over a tool selects it; a quick click selects the Arrow (top left)."""

    def __init__(self, app, tools, cols=2):
        # tools: list of (key, bitmap name, cursor name)
        self.app = app
        self.tools = tools
        self.cols = cols
        self.top = None
        self.current = tools[0][0]
        self.on_change = None

    def popup(self, ev):
        if self.top:
            return
        rows = (len(self.tools) + self.cols - 1) // self.cols
        W = self.cols * 31 + 3
        H = rows * 31 + 3
        top = tk.Toplevel(self.app)
        top.overrideredirect(True)
        c = tk.Canvas(top, width=s(W), height=s(H), bg=ui.FACE, highlightthickness=0, bd=0)
        c.pack()
        ui.raised(c, 0, 0, W, H)
        self.cells = []
        for i, (key, bmp, _cur) in enumerate(self.tools):
            r, col = divmod(i, self.cols) if self.cols > 1 else (i, 0)
            if self.cols > 1:
                col, r = i // rows, i % rows
            x, y = 1 + col * 31, 1 + r * 31
            ui.image(c, x, y, self.app.images.get(bmp))
            self.cells.append((x, y, key))
        self.c = c
        x = ev.x_root - s(16)
        y = ev.y_root - s(16)
        top.geometry('+%d+%d' % (x, y))
        self.top = top
        self.hl = None
        self.press_xy = (ev.x_root, ev.y_root)
        top.update_idletasks()

    def motion(self, ev):
        if not self.top:
            return
        k = self._at(ev)
        if k != self.hl:
            self.hl = k
            self.c.delete('hl')
            for x, y, key in self.cells:
                if key == k:
                    ui.rect(self.c, x, y, x + 32, y + 32, outline='#ff0000', tags='hl')
                    ui.rect(self.c, x + 1, y + 1, x + 31, y + 31, outline='#ff0000', tags='hl')

    def _at(self, ev):
        x = (ev.x_root - self.top.winfo_rootx()) / ui.S
        y = (ev.y_root - self.top.winfo_rooty()) / ui.S
        for cx, cy, key in self.cells:
            if cx <= x < cx + 31 and cy <= y < cy + 31:
                return key
        return None

    def release(self, ev):
        if not self.top:
            return
        k = self._at(ev)
        moved = abs(ev.x_root - self.press_xy[0]) + abs(ev.y_root - self.press_xy[1]) > 4
        if k is None and not moved:
            k = self.tools[0][0]
        self.top.destroy()
        self.top = None
        if k is not None:
            self.current = k
            if self.on_change:
                self.on_change(k)

    def cursor_name(self):
        for key, _b, cur in self.tools:
            if key == self.current:
                return cur
        return ''

    def bind(self, widget):
        ui.bind_right(widget, 'ButtonPress', self.popup)
        widget.bind('<B%d-Motion>' % ui.RIGHT_BUTTON, self.motion)
        ui.bind_right(widget, 'ButtonRelease', self.release)
