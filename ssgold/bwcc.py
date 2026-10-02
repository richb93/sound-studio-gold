"""Borland Windows Custom Controls look-alike: dialogs built from Gold's DIALOG templates.

Layout comes straight from the template (dialog units, 'Helv' 8).  BorBtn/BorCheck/BorRadio use
the bitmaps from BWCC.DLL; BorShade draws recessed group panels; the background is BWCC's
dotted pattern (bitmap 998)."""
import tkinter as tk

from . import ui, resources
from .ui import s, dlu

BS_TYPE = 0x0F
BSS_GROUP, BSS_HDIP, BSS_VDIP, BSS_HBUMP, BSS_VBUMP, BSS_RGROUP = 1, 2, 3, 4, 5, 6
WS_DISABLED = 0x08000000
WS_VSCROLL = 0x00200000
WS_HSCROLL = 0x00100000
WS_BORDER = 0x00800000

BUTTON_BITMAPS = {1: 1, 2: 2, 3: 3, 4: 4, 5: 5, 6: 6, 7: 7, 9: 9}


def _label(text):
    u = text.find('&')
    return text.replace('&&', '\0').replace('&', '').replace('\0', '&'), u


class HScroll(tk.Canvas):
    """Windows scroll bar used as a slider (SCROLLBAR controls in the templates)."""

    def __init__(self, master, w, h, lo=0, hi=100, value=0, cmd=None, vertical=False):
        super().__init__(master, width=w, height=h, bg=ui.FACE, highlightthickness=0, bd=0)
        self.lo, self.hi, self.value, self.cmd = lo, hi, value, cmd
        self.vertical = vertical
        self.bind('<Configure>', lambda e: self.draw())
        self.bind('<Button-1>', self._press)
        self.bind('<B1-Motion>', self._drag)
        self.bind('<ButtonRelease-1>', lambda e: self._stop())
        self.job = None
        self.dragging = False

    def set(self, v, notify=False):
        self.value = max(self.lo, min(self.hi, int(v)))
        self.draw()
        if notify and self.cmd:
            self.cmd(self.value)

    def draw(self):
        self.delete('all')
        W, H = self.winfo_width(), self.winfo_height()
        if self.vertical:
            W, H = H, W
        a = min(H, s(16))
        if a <= 0:
            return
        # track (dithered)
        self.create_rectangle(0, 0, W, H, fill='#e0e0e0', outline='')
        for x0, pts in ((0, (1, -1)), (W - a, (-1, 1))):
            self._box(x0, 0, x0 + a, H)
            cx, cy = x0 + a // 2, H // 2
            d = pts[0]
            for i in range(4):
                self._line(cx - d * (i - 1) - 1, cy - i, cx - d * (i - 1) - 1, cy + i + 1)
        span = max(1, self.hi - self.lo)
        tw = a
        x = a + (W - 2 * a - tw) * (self.value - self.lo) / span
        self._box(x, 0, x + tw, H)

    def _box(self, x0, y0, x1, y1):
        if self.vertical:
            x0, y0, x1, y1 = y0, x0, y1, x1
        self.create_rectangle(x0, y0, x1 - 1, y1 - 1, fill=ui.FACE, outline=ui.DARK)
        self.create_line(x0 + 1, y1 - 2, x0 + 1, y0 + 1, x1 - 2, y0 + 1, fill=ui.HILITE)
        self.create_line(x0 + 1, y1 - 2, x1 - 2, y1 - 2, x1 - 2, y0 + 1, fill=ui.SHADOW)

    def _line(self, x0, y0, x1, y1):
        if self.vertical:
            x0, y0, x1, y1 = y0, x0, y1, x1
        self.create_line(x0, y0, x1, y1, fill=ui.DARK)

    def _pos(self, ev):
        return (ev.y, self.winfo_height(), self.winfo_width()) if self.vertical else \
            (ev.x, self.winfo_width(), self.winfo_height())

    def _press(self, ev):
        x, W, H = self._pos(ev)
        a = min(H, s(16))
        span = max(1, self.hi - self.lo)
        tx = a + (W - 3 * a) * (self.value - self.lo) / span
        if x < a:
            self._repeat(-1)
        elif x >= W - a:
            self._repeat(1)
        elif tx <= x < tx + a:
            self.dragging = True
        else:
            self._repeat(-max(1, span // 10) if x < tx else max(1, span // 10))

    def _repeat(self, d, first=True):
        self.set(self.value + d, notify=True)
        self.job = self.after(400 if first else 60, lambda: self._repeat(d, False))

    def _drag(self, ev):
        if not self.dragging:
            return
        x, W, H = self._pos(ev)
        a = min(H, s(16))
        frac = (x - 1.5 * a) / max(1, W - 3 * a)
        self.set(self.lo + frac * (self.hi - self.lo), notify=True)

    def _stop(self):
        self.dragging = False
        if self.job:
            self.after_cancel(self.job)
            self.job = None


class Dialog(tk.Toplevel):
    """Build a dialog from its template. Controls are available by id via get/set helpers."""

    def __init__(self, app, name, title=None, modal=True, parent=None):
        super().__init__(parent or app)
        self.app = app
        self.name = name
        self.tpl = resources.dialog(name)
        self.withdraw()
        self.title(title or self.tpl['caption'])
        self.resizable(False, False)
        self.transient(parent or app)
        self.result = None
        self.ctrls = {}
        self.vars = {}
        self.focus_btn = None
        w, h = dlu(self.tpl['cx'], self.tpl['cy'])
        self.W, self.H = w, h
        self.c = tk.Canvas(self, width=w, height=h, highlightthickness=0, bd=0, bg=ui.FACE)
        self.c.pack()
        self._tile()
        self.on_ok = None
        self.on_cancel = None
        self.on_command = {}
        self.checks = {}
        self.radios = {}
        self.buttons = {}
        self.statics = {}
        self.groups = []           # radio group membership
        self._build()
        self.c.bind('<Button-1>', self._click)
        self.c.bind('<ButtonRelease-1>', self._release)
        self.bind('<Return>', lambda e: self._enter(e))
        self.bind('<Escape>', lambda e: self.cancel())
        self.protocol('WM_DELETE_WINDOW', self.cancel)
        self.modal = modal
        self._pressed = None

    # ---- construction
    def _tile(self):
        img = self.app.images.bwcc(998)
        iw = img.width()
        for y in range(0, self.H, iw):
            for x in range(0, self.W, iw):
                self.c.create_image(x, y, image=img, anchor='nw', tags='bg')

    def _rect(self, it):
        x, y = dlu(it['x'], it['y'])
        w, h = dlu(it['cx'], it['cy'])
        return x, y, w, h

    def _build(self):
        items = self.tpl['items']
        group = None
        for it in items:
            cls = it['class']
            st = it['style']
            if cls == 'BorShade':
                self._shade(it)
        for it in items:
            cls = it['class']
            st = it['style']
            if st & 0x00020000:
                group = []
                self.groups.append(group)
            iid = it['id']
            if cls == 'BorShade':
                continue
            if cls == 'BorBtn':
                self._borbtn(it)
            elif cls == 'BorCheck':
                self._check(it)
            elif cls == 'BorRadio':
                self._radio(it)
                if group is None:
                    group = []
                    self.groups.append(group)
                group.append(iid)
            elif cls == 'STATIC':
                self._static(it)
            elif cls == 'EDIT':
                self._edit(it)
            elif cls == 'LISTBOX':
                self._listbox(it)
            elif cls == 'COMBOBOX':
                self._combo(it)
            elif cls == 'SCROLLBAR':
                x, y, w, h = self._rect(it)
                sb = HScroll(self.c, w, h)
                self.c.create_window(x, y, window=sb, anchor='nw', width=w, height=h)
                self.ctrls[iid] = sb
            elif cls == 'BUTTON':
                self._button(it)

    def _shade(self, it):
        x, y, w, h = self._rect(it)
        typ = it['style'] & BS_TYPE
        c = self.c
        if typ == BSS_HDIP:
            c.create_line(x, y, x + w, y, fill=ui.SHADOW, width=ui.S)
            c.create_line(x, y + ui.S, x + w, y + ui.S, fill=ui.HILITE, width=ui.S)
            return
        if typ == BSS_VDIP:
            c.create_line(x, y, x, y + h, fill=ui.SHADOW, width=ui.S)
            c.create_line(x + ui.S, y, x + ui.S, y + h, fill=ui.HILITE, width=ui.S)
            return
        raised = typ in (BSS_RGROUP, BSS_HBUMP, BSS_VBUMP)
        c.create_rectangle(x, y, x + w - 1, y + h - 1, fill=ui.FACE, outline='')
        tl, br = (ui.HILITE, ui.SHADOW) if raised else (ui.SHADOW, ui.HILITE)
        c.create_line(x, y + h - 1, x, y, x + w - 1, y, fill=tl, width=ui.S)
        c.create_line(x + ui.S, y + h - ui.S, x + w - ui.S, y + h - ui.S, x + w - ui.S, y, fill=br, width=ui.S)
        if it['text']:
            txt, u = _label(it['text'])
            ty = y + s(1)
            c.create_text(x + s(3), ty, text=txt, anchor='nw', font=ui.f('dialog'))
            if u >= 0:
                self._underline(x + s(3), ty, txt, u)
            lh = ui.f('dialog').metrics('linespace') + s(2)
            c.create_line(x + ui.S, y + lh, x + w - ui.S, y + lh, fill=ui.HILITE, width=ui.S)
            c.create_line(x + ui.S, y + lh - ui.S, x + w - ui.S, y + lh - ui.S, fill=ui.SHADOW, width=ui.S)

    def _underline(self, x, y, txt, u, font='dialog'):
        fo = ui.f(font)
        x0 = x + fo.measure(txt[:u])
        x1 = x0 + fo.measure(txt[u])
        yy = y + fo.metrics('ascent') + ui.S
        self.c.create_line(x0, yy, x1, yy, width=ui.S)

    def _borbtn(self, it):
        iid = it['id']
        x, y, _w, _h = self._rect(it)
        bmp = BUTTON_BITMAPS.get(iid)
        self.buttons[iid] = {'x': x, 'y': y, 'bmp': bmp, 'enabled': not it['style'] & WS_DISABLED,
                             'default': bool(it['style'] & 1)}
        if it['style'] & 1:
            self.focus_btn = iid
        self._draw_borbtn(iid)

    def _draw_borbtn(self, iid, down=False):
        b = self.buttons[iid]
        tag = 'btn%d' % iid
        self.c.delete(tag)
        if b['bmp'] is None:
            return
        base = 3000 if down else (5000 if iid == self.focus_btn else 1000)
        img = self.app.images.bwcc(base + b['bmp'])
        self.c.create_image(b['x'], b['y'], image=img, anchor='nw', tags=tag)
        b['w'], b['h'] = img.width(), img.height()

    def _glyph(self, iid, kind):
        d = self.checks.get(iid) if kind == 'check' else self.radios.get(iid)
        tag = 'g%d' % iid
        self.c.delete(tag)
        on = d['value']
        base = 110 if kind == 'check' else 130
        n = base + (1 if on else 0)
        img = self.app.images.bwcc(n)
        self.c.create_image(d['x'], d['gy'], image=img, anchor='nw', tags=tag)
        if not d['enabled']:
            self.c.create_rectangle(d['x'], d['gy'], d['x'] + img.width(), d['gy'] + img.height(),
                                    fill=ui.FACE, outline='', stipple='gray50', tags=tag)

    def _toggle_text(self, it, d):
        txt, u = _label(it['text'])
        tx = d['x'] + s(16)
        ty = d['y'] + d['h'] // 2
        tag = 't%d' % it['id']
        self.c.delete(tag)
        fo = ui.f('dialog')
        if not d['enabled']:
            self.c.create_text(tx + ui.S, ty + ui.S, text=txt, anchor='w', font=fo, fill=ui.HILITE, tags=tag)
            self.c.create_text(tx, ty, text=txt, anchor='w', font=fo, fill=ui.SHADOW, tags=tag)
        else:
            self.c.create_text(tx, ty, text=txt, anchor='w', font=fo, tags=tag)
            if u >= 0:
                x0 = tx + fo.measure(txt[:u])
                yy = ty + fo.metrics('ascent') // 2 + ui.S
                self.c.create_line(x0, yy, x0 + fo.measure(txt[u]), yy, width=ui.S, tags=tag)

    def _check(self, it):
        x, y, w, h = self._rect(it)
        d = {'x': x, 'y': y, 'w': w, 'h': h, 'gy': y + (h - s(13)) // 2, 'value': False,
             'enabled': not it['style'] & WS_DISABLED, 'it': it}
        self.checks[it['id']] = d
        self._glyph(it['id'], 'check')
        self._toggle_text(it, d)

    def _radio(self, it):
        x, y, w, h = self._rect(it)
        d = {'x': x, 'y': y, 'w': w, 'h': h, 'gy': y + (h - s(13)) // 2, 'value': False,
             'enabled': not it['style'] & WS_DISABLED, 'it': it}
        self.radios[it['id']] = d
        self._glyph(it['id'], 'radio')
        if it['text']:
            self._toggle_text(it, d)

    def _static(self, it):
        x, y, w, h = self._rect(it)
        st = it['style']
        typ = st & 0x0F
        iid = it['id']
        if typ == 3:          # SS_ICON
            img = self.app.images.icon(it['text'])
            self.c.create_image(x, y, image=img, anchor='nw')
            return
        if st & WS_BORDER:
            self.c.create_rectangle(x, y, x + w, y + h, fill=ui.FACE, outline=ui.DARK, width=ui.S)
        txt, u = _label(it['text']) if not st & 0x80 else (it['text'], -1)
        anchor = {0: 'nw', 1: 'n', 2: 'ne'}.get(typ, 'nw')
        tx = {0: x, 1: x + w // 2, 2: x + w}.get(typ, x)
        if st & WS_BORDER:
            tx += s(2)
        tid = self.c.create_text(tx, y, text=txt, anchor=anchor, font=ui.f('dialog'),
                                 width=w if typ in (0, 1, 2) and h > s(10) else 0, justify={0: 'left', 1: 'center', 2: 'right'}.get(typ, 'left'))
        if iid != 0xFFFF:
            self.statics[iid] = tid
        if u >= 0 and typ == 0:
            self._underline(tx, y, txt, u)

    def _edit(self, it):
        x, y, w, h = self._rect(it)
        st = it['style']
        if st & 0x4:     # ES_MULTILINE
            fr = tk.Frame(self.c, bd=0)
            t = tk.Text(fr, font=ui.f('fixed'), wrap='word', bd=ui.S, relief='sunken')
            t.pack(side='left', fill='both', expand=True)
            if st & WS_VSCROLL:
                sb = tk.Scrollbar(fr, command=t.yview)
                t.configure(yscrollcommand=sb.set)
                sb.pack(side='right', fill='y')
            self.c.create_window(x, y, window=fr, anchor='nw', width=w, height=h)
            self.ctrls[it['id']] = t
            return
        e = tk.Entry(self.c, font=ui.f('dialog'), bd=ui.S, relief='sunken', bg=ui.WINDOW,
                     justify='right' if st & 2 else 'left', highlightthickness=0)
        if it['text']:
            e.insert(0, it['text'])
        self.c.create_window(x, y, window=e, anchor='nw', width=w, height=h)
        self.ctrls[it['id']] = e

    def _listbox(self, it):
        x, y, w, h = self._rect(it)
        st = it['style']
        fr = tk.Frame(self.c, bd=ui.S, relief='sunken', bg=ui.FACE)
        mode = 'extended' if st & 0x800 else ('multiple' if st & 0x8 else 'browse')
        lb = tk.Listbox(fr, font=ui.f('dialog'), bd=0, highlightthickness=0, bg=ui.FACE,
                        selectmode=mode, activestyle='none', exportselection=False,
                        selectbackground=ui.SELECT, selectforeground='white')
        lb.pack(side='left', fill='both', expand=True)
        if st & WS_VSCROLL:
            sb = tk.Scrollbar(fr, command=lb.yview)
            lb.configure(yscrollcommand=sb.set)
            sb.pack(side='right', fill='y')
        self.c.create_window(x, y, window=fr, anchor='nw', width=w, height=h)
        self.ctrls[it['id']] = lb

    def _combo(self, it):
        from .widgets import Combo
        x, y, w, h = self._rect(it)
        hh = s(18)
        cb = Combo(self.c, self.app, [], w // ui.S, '', bold=False, h=18)
        self.c.create_window(x, y - s(1), window=cb, anchor='nw', width=w, height=hh)
        self.ctrls[it['id']] = cb

    def _button(self, it):
        x, y, w, h = self._rect(it)
        txt, u = _label(it['text'])
        iid = it['id']
        self.buttons[iid] = {'x': x, 'y': y, 'w': w, 'h': h, 'bmp': None, 'text': txt, 'u': u,
                             'enabled': not it['style'] & WS_DISABLED, 'plain': True}
        self._draw_plain(iid)

    def _draw_plain(self, iid, down=False):
        b = self.buttons[iid]
        tag = 'btn%d' % iid
        c = self.c
        c.delete(tag)
        x, y, w, h = b['x'], b['y'], b['w'], b['h']
        c.create_rectangle(x, y, x + w - 1, y + h - 1, fill=ui.FACE, outline=ui.DARK, width=ui.S, tags=tag)
        if down:
            c.create_line(x + ui.S, y + h - 2 * ui.S, x + ui.S, y + ui.S, x + w - 2 * ui.S, y + ui.S,
                          fill=ui.SHADOW, width=ui.S, tags=tag)
        else:
            for k, col in ((1, ui.HILITE), (2, ui.HILITE)):
                c.create_line(x + k * ui.S, y + h - (k + 1) * ui.S, x + k * ui.S, y + k * ui.S,
                              x + w - (k + 1) * ui.S, y + k * ui.S, fill=col, width=ui.S, tags=tag)
            for k in (1, 2):
                c.create_line(x + k * ui.S, y + h - (k + 1) * ui.S + ui.S, x + w - k * ui.S, y + h - k * ui.S,
                              x + w - k * ui.S, y + k * ui.S, fill=ui.SHADOW, width=ui.S, tags=tag)
        o = ui.S if down else 0
        fill = ui.TEXT if b['enabled'] else ui.SHADOW
        if not b['enabled']:
            c.create_text(x + w // 2 + ui.S, y + h // 2 + ui.S, text=b['text'], font=ui.f('dialogbold'),
                          fill=ui.HILITE, tags=tag)
        tid = c.create_text(x + w // 2 + o, y + h // 2 + o, text=b['text'], font=ui.f('dialogbold'),
                            fill=fill, tags=tag)
        if b['u'] >= 0 and b['enabled']:
            fo = ui.f('dialogbold')
            tw = fo.measure(b['text'])
            x0 = x + w // 2 + o - tw // 2 + fo.measure(b['text'][:b['u']])
            yy = y + h // 2 + o + fo.metrics('ascent') // 2 + ui.S
            c.create_line(x0, yy, x0 + fo.measure(b['text'][b['u']]), yy, width=ui.S, tags=tag)

    # ---- mouse
    def _hit(self, ev):
        x, y = ev.x, ev.y
        for iid, b in self.buttons.items():
            if b['x'] <= x < b['x'] + b.get('w', 0) and b['y'] <= y < b['y'] + b.get('h', 0):
                return 'button', iid
        for iid, d in self.checks.items():
            if d['x'] <= x < d['x'] + d['w'] and d['y'] <= y < d['y'] + d['h']:
                return 'check', iid
        for iid, d in self.radios.items():
            if d['x'] <= x < d['x'] + max(d['w'], s(14)) and d['y'] <= y < d['y'] + max(d['h'], s(14)):
                return 'radio', iid
        return None

    def _click(self, ev):
        h = self._hit(ev)
        if not h:
            return
        kind, iid = h
        if kind == 'button' and self.buttons[iid]['enabled']:
            self._pressed = iid
            if self.buttons[iid].get('plain'):
                self._draw_plain(iid, True)
            else:
                self._draw_borbtn(iid, True)
        elif kind == 'check' and self.checks[iid]['enabled']:
            self.set_check(iid, not self.checks[iid]['value'])
            self._fire(iid)
        elif kind == 'radio' and self.radios[iid]['enabled']:
            self.set_radio(iid)
            self._fire(iid)

    def _release(self, ev):
        iid = self._pressed
        self._pressed = None
        if iid is None:
            return
        b = self.buttons[iid]
        if b.get('plain'):
            self._draw_plain(iid)
        else:
            self._draw_borbtn(iid)
        if self._hit(ev) == ('button', iid):
            self._button_cmd(iid)

    def _button_cmd(self, iid):
        if iid == 1:
            self.ok()
        elif iid in (2, 3) and iid not in self.on_command:
            self.cancel()
        else:
            self._fire(iid)

    def _fire(self, iid):
        fn = self.on_command.get(iid)
        if fn:
            fn()

    def _enter(self, ev):
        if isinstance(ev.widget, tk.Text):
            return
        if self.focus_btn is not None and self.focus_btn in self.buttons:
            self._button_cmd(self.focus_btn)

    # ---- value access
    def set_check(self, iid, v):
        if iid in self.checks:
            self.checks[iid]['value'] = bool(v)
            self._glyph(iid, 'check')

    def check(self, iid):
        return self.checks[iid]['value'] if iid in self.checks else False

    def set_radio(self, iid):
        for g in self.groups:
            if iid in g:
                for r in g:
                    self.radios[r]['value'] = (r == iid)
                    self._glyph(r, 'radio')
                return
        self.radios[iid]['value'] = True
        self._glyph(iid, 'radio')

    def radio(self, ids):
        for i in ids:
            if self.radios.get(i, {}).get('value'):
                return i
        return None

    def enable(self, iid, on=True):
        if iid in self.checks:
            self.checks[iid]['enabled'] = on
            self._glyph(iid, 'check')
            self._toggle_text(self.checks[iid]['it'], self.checks[iid])
        elif iid in self.radios:
            self.radios[iid]['enabled'] = on
            self._glyph(iid, 'radio')
            if self.radios[iid]['it']['text']:
                self._toggle_text(self.radios[iid]['it'], self.radios[iid])
        elif iid in self.buttons:
            self.buttons[iid]['enabled'] = on
            if self.buttons[iid].get('plain'):
                self._draw_plain(iid)
        elif iid in self.ctrls:
            w = self.ctrls[iid]
            try:
                w.configure(state='normal' if on else 'disabled')
            except tk.TclError:
                if hasattr(w, 'enabled'):
                    w.enabled = on
                    w.draw()

    def text(self, iid):
        w = self.ctrls.get(iid)
        if isinstance(w, tk.Entry):
            return w.get()
        if isinstance(w, tk.Text):
            return w.get('1.0', 'end-1c')
        if iid in self.statics:
            return self.c.itemcget(self.statics[iid], 'text')
        if hasattr(w, 'value'):
            return w.value
        return ''

    def set_text(self, iid, v):
        w = self.ctrls.get(iid)
        if isinstance(w, tk.Entry):
            st = w.cget('state')
            w.configure(state='normal')
            w.delete(0, 'end')
            w.insert(0, str(v))
            w.configure(state=st)
        elif isinstance(w, tk.Text):
            w.delete('1.0', 'end')
            w.insert('1.0', str(v))
        elif iid in self.statics:
            self.c.itemconfigure(self.statics[iid], text=str(v))
        elif w is not None and hasattr(w, 'set'):
            w.set(v)

    def int(self, iid, default=0, lo=None, hi=None, off=None):
        t = self.text(iid).strip()
        if off is not None and t.upper() == 'OFF':
            return off
        try:
            v = int(t)
        except ValueError:
            return default
        if lo is not None:
            v = max(lo, v)
        if hi is not None:
            v = min(hi, v)
        return v

    def combo(self, iid, values=None, value=None, cmd=None):
        cb = self.ctrls[iid]
        if values is not None:
            cb.set_values(values)
        if value is not None:
            cb.set(value)
        if cmd is not None:
            cb.cmd = cmd
        return cb.value

    # ---- run
    def show(self):
        self.update_idletasks()
        ax, ay = self.app.winfo_rootx(), self.app.winfo_rooty()
        x, y = dlu(self.tpl['x'], self.tpl['y'])
        self.geometry('+%d+%d' % (ax + x, ay + y + s(40)))
        self.deiconify()
        self.lift()
        if self.modal:
            self.grab_set()
            first = next((w for w in self.ctrls.values() if isinstance(w, (tk.Entry, tk.Text))), None)
            (first or self).focus_set()
            self.wait_window(self)
        return self.result

    def ok(self):
        if self.on_ok is not None:
            r = self.on_ok()
            if r is False:
                return
        self.result = True if self.result is None else self.result
        self.close()

    def cancel(self):
        if self.on_cancel is not None:
            self.on_cancel()
        self.result = None
        self.close()

    def close(self):
        try:
            self.grab_release()
        except tk.TclError:
            pass
        self.destroy()


def message_box(app, text, caption='Sound Studio Gold', kind='info', buttons=('ok',), parent=None):
    """BWCC message box (BWCCMessageBox): icon from BWCC 1901-1904 and bitmap buttons."""
    top = tk.Toplevel(parent or app)
    top.withdraw()
    top.title(caption)
    top.resizable(False, False)
    top.transient(parent or app)
    icon = {'stop': 1901, 'question': 1902, 'warning': 1903, 'info': 1904}[kind]
    fo = ui.f('dialog')
    tw = min(s(320), max(s(120), fo.measure(text) + s(10)))
    c = tk.Canvas(top, highlightthickness=0, bd=0, bg=ui.FACE)
    c.pack()
    img = app.images.bwcc(icon)
    tid = c.create_text(0, 0, text=text, font=fo, width=tw, anchor='nw')
    bb = c.bbox(tid)
    th = bb[3] - bb[1]
    pw = s(16) + img.width() + s(12) + tw + s(16)
    ph = max(img.height(), th) + s(24)
    bw = s(63)
    W = max(pw, len(buttons) * (bw + s(8)) + s(16))
    H = ph + s(12) + s(39) + s(10)
    c.configure(width=W, height=H)
    bg = app.images.bwcc(998)
    for y in range(0, H, bg.height()):
        for x in range(0, W, bg.width()):
            c.create_image(x, y, image=bg, anchor='nw')
    c.create_rectangle(s(6), s(6), W - s(7), ph + s(4), fill=ui.FACE, outline='')
    c.create_line(s(6), ph + s(4), s(6), s(6), W - s(7), s(6), fill=ui.SHADOW)
    c.create_line(s(6), ph + s(4), W - s(7), ph + s(4), W - s(7), s(6), fill=ui.HILITE)
    c.create_image(s(14), s(12), image=img, anchor='nw')
    c.tag_raise(tid)
    c.coords(tid, s(14) + img.width() + s(12), s(12) + max(0, (img.height() - th) // 2))
    ids = {'ok': 1, 'cancel': 2, 'abort': 3, 'retry': 4, 'ignore': 5, 'yes': 6, 'no': 7}
    result = {'v': None}
    x = (W - len(buttons) * bw - (len(buttons) - 1) * s(10)) // 2
    rects = []
    for i, b in enumerate(buttons):
        bid = ids[b]
        im = app.images.bwcc((5000 if i == 0 else 1000) + bid)
        c.create_image(x, ph + s(14), image=im, anchor='nw', tags='b%d' % i)
        rects.append((x, ph + s(14), x + im.width(), ph + s(14) + im.height(), b, bid, i))
        x += bw + s(10)

    def press(ev):
        for x0, y0, x1, y1, b, bid, i in rects:
            if x0 <= ev.x < x1 and y0 <= ev.y < y1:
                c.itemconfigure('b%d' % i, image=app.images.bwcc(3000 + bid))
                top.after(80, lambda: (result.__setitem__('v', b), top.destroy()))

    c.bind('<Button-1>', press)
    top.bind('<Return>', lambda e: (result.__setitem__('v', buttons[0]), top.destroy()))
    top.bind('<Escape>', lambda e: (result.__setitem__('v', 'cancel' if 'cancel' in buttons else buttons[-1]),
                                    top.destroy()))
    top.update_idletasks()
    p = parent or app
    top.geometry('+%d+%d' % (p.winfo_rootx() + (p.winfo_width() - W) // 2,
                             p.winfo_rooty() + (p.winfo_height() - H) // 3))
    top.deiconify()
    top.grab_set()
    top.focus_set()
    top.wait_window()
    return result['v']
