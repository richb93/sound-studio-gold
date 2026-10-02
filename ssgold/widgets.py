"""Owner-drawn controls in the style of Gold's windows: bitmap buttons, label boxes, drop-down
selectors, information-line fields and scrollbars."""
import tkinter as tk

from . import ui
from .ui import s


class Toolbar(tk.Canvas):
    """A row of Gold toolbar items.  Bitmap buttons share their 1px black edge (stride = w-1)."""

    def __init__(self, master, app, height=18, bg=ui.FACE):
        super().__init__(master, height=s(height), bg=bg, highlightthickness=0, bd=0)
        self.app = app
        self.h = height
        self.x = 0
        self.items = []
        self.bind('<Button-1>', self._press)
        self.bind('<ButtonRelease-1>', self._release)
        ui.bind_right(self, '', self._rpress)
        self._down = None

    def add_button(self, name, cmd, pressed=None, tip=None, rcmd=None, width=None):
        img = self.app.images.get(name)
        w = img.width() // ui.S
        it = {'kind': 'button', 'x': self.x, 'w': w, 'img': name, 'pressed': pressed, 'cmd': cmd,
              'rcmd': rcmd, 'state': False}
        self.items.append(it)
        self.x += w - 1
        self._draw_item(it)
        return it

    def add_toggle(self, off, on, cmd, state=False):
        it = self.add_button(off, cmd)
        it.update(kind='toggle', on=on, off=off, state=state)
        self._draw_item(it)
        return it

    def add_label(self, txt, w=None, font='small'):
        w = w or int(ui.text_width(txt, font)) + 6
        it = {'kind': 'label', 'x': self.x, 'w': w, 'text': txt, 'font': font}
        self.items.append(it)
        self.x += w
        self._draw_item(it)
        return it

    def add_space(self, w):
        self.x += w

    def add_combo(self, values, w, value=None, cmd=None, bold=True, listw=None, rows=None):
        combo = Combo(self, self.app, values, w, value, cmd, bold=bold, listw=listw, rows=rows)
        it = {'kind': 'combo', 'x': self.x, 'w': w, 'combo': combo}
        self.items.append(it)
        self.create_window(s(self.x), 0, window=combo, anchor='nw', width=s(w), height=s(self.h))
        self.x += w
        return combo

    def add_widget(self, widget, w):
        self.create_window(s(self.x), 0, window=widget, anchor='nw', width=s(w), height=s(self.h))
        it = {'kind': 'widget', 'x': self.x, 'w': w}
        self.items.append(it)
        self.x += w
        return it

    def _draw_item(self, it):
        tag = 'it%d' % id(it)
        self.delete(tag)
        if it['kind'] in ('button', 'toggle'):
            name = it['img']
            if it['kind'] == 'toggle':
                name = it['on'] if it['state'] else it['off']
            elif it.get('down') and it.get('pressed'):
                name = it['pressed']
            ui.image(self, it['x'], 0, self.app.images.get(name), tags=tag)
            if it.get('down') and not it.get('pressed') and it['kind'] == 'button':
                self.move(tag, ui.S, ui.S)
        elif it['kind'] == 'label':
            ui.raised(self, it['x'], 0, it['x'] + it['w'], self.h, tags=tag, outer=False)
            ui.text(self, it['x'] + 2, self.h // 2, it['text'], it['font'], anchor='w', tags=tag)

    def set_toggle(self, it, state):
        it['state'] = bool(state)
        self._draw_item(it)

    def set_label(self, it, txt):
        it['text'] = txt
        self._draw_item(it)

    def _hit(self, ev):
        x = ev.x / ui.S
        for it in reversed(self.items):
            if it['kind'] in ('button', 'toggle') and it['x'] <= x < it['x'] + it['w']:
                return it
        return None

    def _press(self, ev):
        it = self._hit(ev)
        if not it:
            return
        self._down = it
        if it['kind'] == 'button':
            it['down'] = True
            self._draw_item(it)

    def _release(self, ev):
        it = self._down
        self._down = None
        if not it:
            return
        if it['kind'] == 'button':
            it['down'] = False
            self._draw_item(it)
        if self._hit(ev) is it:
            if it['kind'] == 'toggle':
                it['state'] = not it['state']
                self._draw_item(it)
                it['cmd'](it['state'])
            else:
                it['cmd']() if not _wants_event(it['cmd']) else it['cmd'](ev)

    def _rpress(self, ev):
        it = self._hit(ev)
        if it and it.get('rcmd'):
            it['rcmd'](ev)


def _wants_event(fn):
    try:
        import inspect
        return len(inspect.signature(fn).parameters) == 1
    except (TypeError, ValueError):
        return False


class Combo(tk.Canvas):
    """Windows drop-down list: white field with the selection, and a 16px arrow button."""

    def __init__(self, master, app, values, w, value=None, cmd=None, bold=True, listw=None, rows=None,
                 h=18):
        super().__init__(master, width=s(w), height=s(h), bg=ui.WINDOW, highlightthickness=0, bd=0)
        self.app = app
        self.values = list(values)
        self.value = value if value is not None else (self.values[0] if self.values else '')
        self.cmd = cmd
        self.w, self.h = w, h
        self.bold = bold
        self.listw = listw
        self.rows = rows or 12
        self.enabled = True
        self.bind('<Button-1>', self.drop)
        self.bind('<Configure>', lambda e: self.draw())
        self.popup = None
        self.draw()

    def set(self, value, notify=False):
        self.value = value
        self.draw()
        if notify and self.cmd:
            self.cmd(value)

    def set_values(self, values):
        self.values = list(values)

    def draw(self):
        self.delete('all')
        w = self.winfo_width() // ui.S or self.w
        h = self.winfo_height() // ui.S or self.h
        self.create_rectangle(0, 0, s(w), s(h), fill=ui.WINDOW, outline='')
        fg = ui.TEXT if self.enabled else ui.GREYTEXT
        ui.text(self, 3, h // 2, str(self.value), 'system' if self.bold else 'small', fill=fg, anchor='w')
        bx = w - 17
        ui.raised(self, bx, 1, bx + 16, h - 1)
        cx, cy = bx + 8, h // 2
        for i in range(4):
            ui.line(self, cx - 3 + i, cy - 1 + i, cx + 4 - i, cy - 1 + i)

    def drop(self, _ev=None):
        if not self.enabled or not self.values:
            return
        if self.popup:
            self.close()
            return
        top = tk.Toplevel(self)
        top.overrideredirect(True)
        top.configure(bg=ui.DARK)
        w = self.listw or self.winfo_width() // ui.S
        rows = min(len(self.values), self.rows)
        lb = tk.Listbox(top, font=ui.f('system' if self.bold else 'small'), height=rows,
                        activestyle='none', bd=0, highlightthickness=0, selectbackground=ui.SELECT,
                        selectforeground='white', exportselection=False)
        sb = None
        if len(self.values) > rows:
            sb = tk.Scrollbar(top, command=lb.yview)
            lb.configure(yscrollcommand=sb.set)
            sb.pack(side='right', fill='y')
        lb.pack(side='left', fill='both', expand=True, padx=ui.S, pady=ui.S)
        for v in self.values:
            lb.insert('end', str(v))
        if self.value in self.values:
            i = self.values.index(self.value)
            lb.selection_set(i)
            lb.see(i)
        x = self.winfo_rootx()
        y = self.winfo_rooty() + self.winfo_height()
        top.geometry('%dx%d+%d+%d' % (s(w), lb.winfo_reqheight() + 2 * ui.S, x, y))
        self.popup = top

        def pick(_e=None):
            sel = lb.curselection()
            self.close()
            if sel:
                self.set(self.values[sel[0]], notify=True)

        def motion(e):
            i = lb.nearest(e.y)
            lb.selection_clear(0, 'end')
            lb.selection_set(i)

        lb.bind('<ButtonRelease-1>', pick)
        lb.bind('<Return>', pick)
        lb.bind('<Motion>', motion)
        lb.bind('<Escape>', lambda e: self.close())
        top.bind('<FocusOut>', lambda e: self.after(100, self._maybe_close))
        top.after(10, lambda: (top.grab_set(), lb.focus_set()))
        top.bind('<Button-1>', lambda e: self.close() if e.widget is top else None)

    def _maybe_close(self):
        if self.popup and self.focus_get() is None:
            self.close()

    def close(self):
        if self.popup:
            try:
                self.popup.grab_release()
                self.popup.destroy()
            except tk.TclError:
                pass
            self.popup = None


class InfoLine(tk.Canvas):
    """Gold's information line: a row of 3D fields 'Label   value', adjustable with the mouse."""

    def __init__(self, master, app, fields, height=18):
        super().__init__(master, height=s(height), bg=ui.FACE, highlightthickness=0, bd=0)
        self.app = app
        self.h = height
        self.fields = []     # dicts: label, w, value, adjust(delta, big, field) callback
        x = 0
        for label, w in fields:
            self.fields.append({'label': label, 'x': x, 'w': w, 'value': '', 'adjust': None,
                                'edit': None})
            x += w
        self.total = x
        self.bind('<Configure>', lambda e: self.draw())
        self.rep = ui.Repeater(self)
        self.bind('<ButtonPress-1>', lambda e: self._press(e, 1))
        self.bind('<ButtonRelease-1>', lambda e: self.rep.stop(1))
        ui.bind_right(self, 'ButtonPress', lambda e: self._press(e, 3))
        ui.bind_right(self, 'ButtonRelease', lambda e: self.rep.stop(3))
        self.bind('<Double-Button-1>', self._double)

    def set(self, i, value, adjust=None, edit=None):
        f = self.fields[i]
        f['value'] = value
        if adjust is not None:
            f['adjust'] = adjust
        if edit is not None:
            f['edit'] = edit
        self.draw()

    def clear(self):
        for f in self.fields:
            f['value'] = ''
            f['adjust'] = None
            f['edit'] = None
        self.draw()

    def draw(self):
        self.delete('all')
        W = self.winfo_width() // ui.S
        for i, f in enumerate(self.fields):
            x0 = f['x']
            x1 = x0 + f['w'] if i < len(self.fields) - 1 else max(x0 + f['w'], W)
            self._field(x0, x1, f)
        if self.fields:
            last = self.fields[-1]
            if last['x'] + last['w'] < W:
                self._field(last['x'] + last['w'], W, {'label': '', 'value': ''})

    def _field(self, x0, x1, f):
        h = self.h
        ui.raised(self, x0, 0, x1, h, outer=False)
        ui.sunken(self, x0 + 2, 2, x1 - 1, h - 1, fill=ui.FACE, deep=False)
        ui.text(self, x0 + 4, h // 2, f['label'], 'small', anchor='w')
        if f['value'] != '':
            if f.get('align') == 'w':
                lw = ui.text_width(f['label'], 'small') if f['label'] else 0
                ui.text(self, x0 + 10 + lw, h // 2, str(f['value']), 'system', anchor='w')
            else:
                ui.text(self, x1 - 4, h // 2, str(f['value']), 'system', anchor='e')

    def _which(self, ev):
        x = ev.x / ui.S
        for f in self.fields:
            if f['x'] <= x < f['x'] + f['w']:
                return f
        return None

    def _press(self, ev, button):
        f = self._which(ev)
        if not f or not f['adjust']:
            return
        self.rep.start(ev, lambda d, big: f['adjust'](d, big), button)

    def _double(self, ev):
        f = self._which(ev)
        if f and f['edit']:
            f['edit']()


class ValueRepeater:
    """Helper for list cells changed with left (-) / right (+) buttons."""

    def __init__(self, widget):
        self.rep = ui.Repeater(widget)

    def bind(self, widget, hit, apply):
        """hit(ev) -> key or None; apply(key, delta, big)."""
        def press(ev, b):
            key = hit(ev)
            if key is None:
                return False
            self.rep.start(ev, lambda d, big: apply(key, d, big), b)
            return True
        return press


class BevelButton(tk.Canvas):
    """Plain push button drawn like Gold's text buttons ('Add', 'Delete' ...)."""

    def __init__(self, master, text, cmd, w=40, h=18, font='small'):
        super().__init__(master, width=s(w), height=s(h), bg=ui.FACE, highlightthickness=0, bd=0)
        self.text, self.cmd, self.w, self.h, self.font = text, cmd, w, h, font
        self.down = False
        self.enabled = True
        self.bind('<Button-1>', self._press)
        self.bind('<ButtonRelease-1>', self._release)
        self.bind('<Configure>', lambda e: self.draw())
        self.draw()

    def draw(self):
        self.delete('all')
        w = self.winfo_width() // ui.S or self.w
        h = self.winfo_height() // ui.S or self.h
        if self.down:
            ui.sunken(self, 0, 0, w, h, fill=ui.FACE)
        else:
            ui.raised(self, 0, 0, w, h)
        o = 1 if self.down else 0
        ui.text(self, w // 2 + o, h // 2 + o, self.text, self.font,
                fill=ui.TEXT if self.enabled else ui.GREYTEXT, anchor='center')

    def _press(self, _e):
        if self.enabled:
            self.down = True
            self.draw()

    def _release(self, e):
        if not self.down:
            return
        self.down = False
        self.draw()
        if 0 <= e.x < self.winfo_width() and 0 <= e.y < self.winfo_height():
            self.cmd()


class PopupMenu:
    """Right-click / 'Functions' pop-up menu."""

    @staticmethod
    def show(widget, items, x_root, y_root):
        m = tk.Menu(widget, tearoff=0)
        for it in items:
            if it is None:
                m.add_separator()
            else:
                label, cmd = it[0], it[1]
                state = 'normal' if (len(it) < 3 or it[2]) else 'disabled'
                u = label.find('&')
                m.add_command(label=label.replace('&', ''), underline=u if u >= 0 else -1,
                              command=cmd, state=state)
        try:
            m.tk_popup(x_root, y_root)
        finally:
            m.grab_release()
