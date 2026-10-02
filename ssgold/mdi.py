"""A small MDI implementation: child windows with Windows 95 captions inside a client area,
plus always-on-top floating panels (Transport, Editors, Fast Menu, Time)."""
import tkinter as tk

from . import ui
from .ui import s

CAPTION_H = 18
BORDER = 4


# Windows 95 close glyph, drawn pixel by pixel (lines would be antialiased on some systems)
CLOSE_GLYPH = ['XX....XX', '.XX..XX.', '..XXXX..', '...XX...', '..XXXX..', '.XX..XX.', 'XX....XX']


def pixels(c, x, y, rows, fill='#000000'):
    for j, row in enumerate(rows):
        i = 0
        while i < len(row):
            if row[i] == 'X':
                k = i
                while k < len(row) and row[k] == 'X':
                    k += 1
                c.create_rectangle(s(x + i), s(y + j), s(x + k), s(y + j + 1), fill=fill, outline='', width=0)
                i = k
            else:
                i += 1


class MDIClient(tk.Canvas):
    def __init__(self, master, app):
        super().__init__(master, highlightthickness=0, bd=0, bg=ui.DESKTOP)
        self.app = app
        self.children_ = []          # stacking order, last = top
        self.floating = []
        self.active = None
        self.bg_image = None
        self.reserved_right = 0      # width kept free for the Editors strip
        self.bind('<Configure>', self._on_resize)
        self.bind('<Button-1>', lambda e: None)

    # ---- background tiles (Preferences > Backgrounds > Program Window)
    def set_background(self, img):
        self.bg_image = img
        self._tile()

    def _tile(self):
        self.delete('bg')
        if not self.bg_image or ui.diag('nobg'):
            return
        self.create_image(0, 0, image=ui.tiled(self.bg_image, self.winfo_width(), self.winfo_height()),
                          anchor='nw', tags='bg')
        self.tag_lower('bg')

    def _on_resize(self, _e):
        self._tile()
        for c in self.children_:
            if c.state == 'max':
                c.maximize(force=True)
            elif c.state == 'min':
                pass
        self.arrange_icons()
        for f in self.floating:
            f.keep_inside()

    # ---- children
    def add(self, child):
        self.children_.append(child)
        self.activate(child)

    def remove(self, child):
        if child in self.children_:
            self.children_.remove(child)
        if self.active is child:
            self.active = None
            if self.children_:
                self.activate(self.children_[-1])
        self.arrange_icons()

    def activate(self, child):
        if child not in self.children_:
            return
        if self.active is not child:
            prev = self.active
            self.active = child
            if prev is not None and prev in self.children_:
                prev.draw_caption()
            child.draw_caption()
        self.children_.remove(child)
        self.children_.append(child)
        child.lift()
        self.raise_floating()
        try:
            child.on_activate()
        except Exception:
            pass
        if self.app:
            self.app.on_child_activated(child)

    def raise_floating(self):
        for f in self.floating:
            if f.winfo_ismapped():
                f.lift()

    def cascade(self):
        x = y = 0
        w = max(200, int(self.winfo_width() * 0.75 / ui.S))
        h = max(150, int(self.winfo_height() * 0.75 / ui.S))
        for c in self.children_:
            if c.state == 'min':
                continue
            c.restore()
            c.move_to(x, y, w, h)
            x += CAPTION_H + 4
            y += CAPTION_H + 4
            c.lift()
        self.raise_floating()

    def tile(self):
        cs = [c for c in self.children_ if c.state != 'min']
        if not cs:
            return
        import math
        n = len(cs)
        cols = int(math.ceil(math.sqrt(n)))
        rows = int(math.ceil(n / cols))
        W = self.winfo_width() / ui.S
        H = self.winfo_height() / ui.S
        i = 0
        for col in range(cols):
            nrows = rows if col < cols - (cols * rows - n) else rows - 1
            nrows = max(1, nrows)
            for r in range(nrows):
                if i >= n:
                    break
                c = cs[i]
                c.restore()
                c.move_to(int(col * W / cols), int(r * H / nrows), int(W / cols), int(H / nrows))
                i += 1
        self.raise_floating()

    def arrange_icons(self):
        x = 0
        H = self.winfo_height() / ui.S
        for c in self.children_:
            if c.state == 'min':
                c.place(x=s(x), y=s(H - CAPTION_H - 4), width=s(160), height=s(CAPTION_H + 4))
                x += 162

    def close_all(self, keep=None):
        for c in list(self.children_):
            if c is not keep and getattr(c, 'closable', True):
                c.close()


class MDIChild(tk.Frame):
    """Frame with a Win95 caption bar and resizable border.  Put content in self.body."""
    closable = True

    def __init__(self, client, title, icon=None, x=0, y=0, w=400, h=300):
        super().__init__(client, bg=ui.FACE, bd=0, highlightthickness=0)
        self.client = client
        self.app = client.app
        self.title = title
        self.icon = icon
        self.state = 'normal'
        self.normal_geom = (x, y, w, h)
        self.cap = tk.Canvas(self, height=s(CAPTION_H), bg=ui.CAPTION, highlightthickness=0, bd=0)
        self.cap.pack(side='top', fill='x', padx=s(BORDER), pady=(s(BORDER), 0))
        self.body = tk.Frame(self, bg=ui.FACE, bd=0, highlightthickness=0)
        self.body.pack(side='top', fill='both', expand=True, padx=s(BORDER), pady=(0, s(BORDER)))
        self.cap.bind('<Configure>', lambda e: self.draw_caption())
        self.cap.bind('<Button-1>', self._cap_press)
        self.cap.bind('<B1-Motion>', self._cap_drag)
        self.cap.bind('<ButtonRelease-1>', self._cap_release)
        self.cap.bind('<Double-Button-1>', self._cap_double)
        self.bind('<Button-1>', self._border_press)
        self.bind('<B1-Motion>', self._border_drag)
        self.bind('<Motion>', self._border_cursor)
        self.bind('<Configure>', lambda e: self._draw_border())
        self._mdi_drag = None
        self.move_to(x, y, w, h)
        client.add(self)

    # ---- geometry
    def move_to(self, x, y, w, h):
        self.normal_geom = (x, y, w, h)
        self.place(x=s(x), y=s(y), width=s(w), height=s(h))

    def geometry(self):
        return (self.winfo_x() // ui.S, self.winfo_y() // ui.S,
                self.winfo_width() // ui.S, self.winfo_height() // ui.S)

    def maximize(self, force=False):
        if self.state == 'max' and not force:
            return self.restore()
        if self.state == 'normal':
            self.normal_geom = self.geometry()
        self.state = 'max'
        self.place(x=-s(BORDER), y=-s(BORDER),
                   width=self.client.winfo_width() - s(self.client.reserved_right) + 2 * s(BORDER),
                   height=self.client.winfo_height() + 2 * s(BORDER))
        self.lift()
        self.client.raise_floating()
        self.draw_caption()

    def minimize(self):
        if self.state == 'normal':
            self.normal_geom = self.geometry()
        self.state = 'min'
        self.body.pack_forget()
        self.client.arrange_icons()
        self.draw_caption()

    def restore(self):
        if self.state == 'min':
            self.body.pack(side='top', fill='both', expand=True, padx=s(BORDER), pady=(0, s(BORDER)))
        self.state = 'normal'
        x, y, w, h = self.normal_geom
        self.place(x=s(x), y=s(y), width=s(w), height=s(h))
        self.client.arrange_icons()
        self.draw_caption()

    def close(self):
        if not self.can_close():
            return
        self.on_close()
        self.client.remove(self)
        self.destroy()

    def can_close(self):
        return True

    def on_close(self):
        pass

    def on_activate(self):
        pass

    def set_title(self, t):
        self.title = t
        self.draw_caption()

    # ---- drawing
    def _draw_border(self):
        pass

    def draw_caption(self):
        c = self.cap
        c.delete('all')
        active = self.client.active is self
        bg = ui.CAPTION if active else ui.INACTIVE
        fg = ui.CAPTION_TEXT if active else ui.INACTIVE_TEXT
        c.configure(bg=bg)
        w = c.winfo_width() // ui.S
        x = 2
        if self.icon is not None:
            c.create_image(s(1), s(1), image=self.icon, anchor='nw')
            x = 19
        c.create_text(s(x), s(CAPTION_H // 2), text=self.title, anchor='w', font=ui.f('caption'), fill=fg)
        # buttons: minimize, maximize/restore, close (Win95 16x14)
        bx = w - 2
        self._btns = []
        for kind in ('close', 'max', 'min'):
            bw = 16
            x1 = bx
            x0 = bx - bw
            if kind == 'close':
                bx = x0 - 2
            else:
                bx = x0
            ui.raised(c, x0, 2, x1, 16)
            cx, cy = (x0 + x1) // 2, 9
            if kind == 'close':
                pixels(c, cx - 4, cy - 4, CLOSE_GLYPH)     # centred on the face above the shadow
            elif kind == 'max':
                if self.state == 'max':
                    ui.rect(c, cx - 2, cy - 5, cx + 5, cy + 1)
                    ui.line(c, cx - 2, cy - 4, cx + 4, cy - 4)
                    c.create_rectangle(s(cx - 5), s(cy - 2), s(cx + 2) - 1, s(cy + 4) - 1, fill=ui.FACE,
                                       outline=ui.DARK, width=ui.S)
                    ui.line(c, cx - 5, cy - 1, cx + 2, cy - 1)
                else:
                    ui.rect(c, cx - 5, cy - 5, cx + 4, cy + 4)
                    ui.line(c, cx - 5, cy - 4, cx + 4, cy - 4)
            else:
                ui.line(c, cx - 4, cy + 3, cx + 2, cy + 3)
                ui.line(c, cx - 4, cy + 2, cx + 2, cy + 2)
            self._btns.append((kind, x0, x1))

    # ---- mouse
    def _hit_button(self, ev):
        x = ev.x / ui.S
        for kind, x0, x1 in getattr(self, '_btns', []):
            if x0 <= x < x1 and 2 <= ev.y / ui.S < 16:
                return kind
        return None

    def _cap_press(self, ev):
        self.client.activate(self)
        kind = self._hit_button(ev)
        if kind:
            self._mdi_drag = ('button', kind)
            return
        self._mdi_drag = ('move', ev.x_root, ev.y_root, self.winfo_x(), self.winfo_y())

    def _cap_drag(self, ev):
        if not self._mdi_drag or self._mdi_drag[0] != 'move' or self.state != 'normal':
            return
        _k, x0, y0, wx, wy = self._mdi_drag
        self.place(x=wx + ev.x_root - x0, y=wy + ev.y_root - y0)

    def _cap_release(self, ev):
        p = self._mdi_drag
        self._mdi_drag = None
        if not p:
            return
        if p[0] == 'button' and self._hit_button(ev) == p[1]:
            {'close': self.close, 'max': self.maximize,
             'min': self.minimize if self.state != 'min' else self.restore}[p[1]]()
        elif p[0] == 'move' and self.state == 'normal':
            self.normal_geom = self.geometry()

    def _cap_double(self, ev):
        if self._hit_button(ev):
            return
        if self.state == 'min':
            self.restore()
        else:
            self.maximize()

    def _edge(self, ev):
        w, h = self.winfo_width(), self.winfo_height()
        b = s(BORDER) + 2
        e = ''
        if ev.y < b:
            e += 'n'
        elif ev.y >= h - b:
            e += 's'
        if ev.x < b:
            e += 'w'
        elif ev.x >= w - b:
            e += 'e'
        return e

    def _border_cursor(self, ev):
        if self.state != 'normal':
            self.configure(cursor='')
            return
        cur = {'n': 'sb_v_double_arrow', 's': 'sb_v_double_arrow', 'e': 'sb_h_double_arrow',
               'w': 'sb_h_double_arrow', 'nw': 'top_left_corner', 'se': 'bottom_right_corner',
               'ne': 'top_right_corner', 'sw': 'bottom_left_corner'}.get(self._edge(ev), '')
        self.configure(cursor=cur)

    def _border_press(self, ev):
        self.client.activate(self)
        self._mdi_drag = ('size', self._edge(ev), ev.x_root, ev.y_root, self.winfo_x(), self.winfo_y(),
                       self.winfo_width(), self.winfo_height())

    def _border_drag(self, ev):
        p = self._mdi_drag
        if not p or p[0] != 'size' or self.state != 'normal':
            return
        _k, edge, x0, y0, wx, wy, ww, wh = p
        dx, dy = ev.x_root - x0, ev.y_root - y0
        x, y, w, h = wx, wy, ww, wh
        if 'e' in edge:
            w = max(s(100), ww + dx)
        if 's' in edge:
            h = max(s(CAPTION_H + 30), wh + dy)
        if 'w' in edge:
            w = max(s(100), ww - dx)
            x = wx + ww - w
        if 'n' in edge:
            h = max(s(CAPTION_H + 30), wh - dy)
            y = wy + wh - h
        self.place(x=x, y=y, width=w, height=h)
        self.normal_geom = (x // ui.S, y // ui.S, w // ui.S, h // ui.S)


class Floating(tk.Frame):
    """Borderless panel kept above the MDI children (Gold's popup tool windows).

    'Toggle Caption' adds a small caption by which it can be dragged; without one it can be
    moved with the Move item of its right-button menu (or by dragging with Alt held)."""

    def __init__(self, client, title, w, h, caption=False):
        super().__init__(client, bg=ui.FACE, bd=0, highlightthickness=0)
        self.client = client
        self.title = title
        self.w, self.h = w, h
        self.has_caption = caption
        self.cap = tk.Canvas(self, height=s(12), bg=ui.CAPTION, highlightthickness=0, bd=0)
        self.body = tk.Frame(self, bg=ui.FACE, bd=0, highlightthickness=0)
        self.body.pack(side='bottom', fill='both', expand=True)
        self.cap.bind('<Button-1>', self._press)
        self.cap.bind('<B1-Motion>', self._drag)
        self.cap.bind('<Configure>', lambda e: self._draw_cap())
        self.pos = (0, 0)
        self.rel = None        # anchoring: ('bottom-centre' etc.) used until moved
        self._moving = None
        client.floating.append(self)
        self.set_caption(caption)

    def set_caption(self, on):
        self.has_caption = on
        if on:
            self.cap.pack(side='top', fill='x', before=self.body)
        else:
            self.cap.pack_forget()
        self.place_at(*self.pos)

    def _draw_cap(self):
        self.cap.delete('all')
        self.cap.create_text(s(2), s(6), text=self.title, anchor='w', font=ui.f('smallbold'), fill='white')

    def size(self):
        return self.w, self.h + (12 if self.has_caption else 0)

    def place_at(self, x, y):
        self.pos = (x, y)
        w, h = self.size()
        self.place(x=s(x), y=s(y), width=s(w), height=s(h))
        self.lift()

    def keep_inside(self):
        if self.rel and self.winfo_ismapped():
            self.rel()

    def start_move(self, ev=None):
        """Keyboard-free move: follow the mouse until the next click (Move menu item)."""
        self.rel = None
        top = self.client
        def follow(e):
            x = (e.x_root - top.winfo_rootx()) // ui.S - self.w // 2
            y = (e.y_root - top.winfo_rooty()) // ui.S - 6
            self.place_at(x, y)
        def done(e):
            top.unbind('<Motion>')
            top.unbind('<Button-1>')
            self.unbind_all('<Motion>')
        self.bind_all('<Motion>', follow)
        top.bind('<Button-1>', done)
        self.after(50, lambda: self.bind_all('<Button-1>', lambda e: (self.unbind_all('<Motion>'),
                                                                        self.unbind_all('<Button-1>'))))

    def _press(self, ev):
        self.rel = None
        self._moving = (ev.x_root, ev.y_root, self.pos)

    def _drag(self, ev):
        if not self._moving:
            return
        x0, y0, (px, py) = self._moving
        self.place_at(px + (ev.x_root - x0) // ui.S, py + (ev.y_root - y0) // ui.S)
