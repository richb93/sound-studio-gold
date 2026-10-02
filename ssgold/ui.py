"""Shared look: colours, fonts, the UI scale, and Windows 3.x/95 style drawing helpers."""
import sys
import tkinter as tk
import tkinter.font as tkfont

# Windows system colours of the period
FACE = '#c0c0c0'
SHADOW = '#808080'
HILITE = '#ffffff'
DARK = '#000000'
WINDOW = '#ffffff'
TEXT = '#000000'
CAPTION = '#000080'
CAPTION_TEXT = '#ffffff'
INACTIVE = '#808080'
INACTIVE_TEXT = '#c0c0c0'
SELECT = '#000080'
GREYTEXT = '#808080'
DESKTOP = '#808080'

S = 1                      # pixel scale, set once at start-up by set_scale()
FONTS = {}

if sys.platform == 'win32':
    _SANS = ('MS Sans Serif', 'Microsoft Sans Serif', 'Arial')
    _BOLD = ('MS Sans Serif', 'Microsoft Sans Serif', 'Arial')
elif sys.platform == 'darwin':
    _SANS = ('Arial', 'Helvetica Neue', 'Helvetica')      # closest in width to MS Sans Serif
    _BOLD = ('Arial', 'Helvetica Neue', 'Helvetica')
else:
    _SANS = ('Liberation Sans', 'Arial', 'Helvetica', 'DejaVu Sans')
    _BOLD = ('Liberation Sans', 'Arial', 'Helvetica', 'DejaVu Sans')


def _family(root, cands):
    have = {f.lower() for f in tkfont.families(root)}
    for c in cands:
        if c.lower() in have:
            return c
    return cands[-1]


def set_scale(root, scale):
    """Create the named fonts used throughout. Sizes are negative = pixels (Gold's LOGFONT heights)."""
    global S
    S = scale
    sans = _family(root, _SANS)
    bold = _family(root, _BOLD)
    adj = 0
    spec = {
        # 'System' 16px bold: track/drum/event lists and most value displays
        'system': (bold, -(12 + adj) * scale, 'bold'),
        # MS Sans Serif 8pt (h=-9 at 72dpi -> 11px at 96dpi): toolbar labels, headings
        'small': (sans, -(11 + adj) * scale, 'normal'),
        'smallbold': (sans, -(11 + adj) * scale, 'bold'),
        # dialogs ('Helv', 8)
        # mixer labels (MS Sans Serif 8 is narrower than its substitutes)
        'mixer': (sans, -(10 + adj) * scale, 'normal'),
        'dialog': (sans, -(11 + adj) * scale, 'normal'),
        'dialogbold': (sans, -(11 + adj) * scale, 'bold'),
        'caption': (sans, -(11 + adj) * scale, 'bold'),
        # big time display: Arial 30 bold
        'bigtime': (_family(root, ('Arial', 'Liberation Sans', 'Helvetica', 'DejaVu Sans')), -26 * scale, 'bold'),
        'fixed': (_family(root, ('Fixedsys', 'Courier New', 'Courier', 'DejaVu Sans Mono')), -12 * scale, 'normal'),
        'lyric': (_family(root, ('Arial', 'Liberation Sans', 'Helvetica')), -19 * scale, 'normal'),
        'score': (_family(root, ('Times New Roman', 'Liberation Serif', 'Times')), -11 * scale, 'normal'),
    }
    for k, (fam, size, weight) in spec.items():
        if k in FONTS:
            FONTS[k].configure(family=fam, size=size, weight=weight)
        else:
            FONTS[k] = tkfont.Font(root=root, family=fam, size=size, weight=weight)


def f(name):
    return FONTS[name]


_FIT = {}


def fit(name, txt, width, min_px=8):
    """Font `name`, made smaller if needed so txt fits in width pixels (fonts differ in width
    from platform to platform; the layouts are the original's)."""
    fo = FONTS[name]
    if width <= 0 or fo.measure(txt) <= width:
        return fo
    size = abs(int(fo.cget('size')))
    g = fo
    for px in range(size - 1, min_px * S - 1, -1):
        key = (fo.cget('family'), px, fo.cget('weight'))
        g = _FIT.get(key)
        if g is None:
            g = _FIT[key] = tkfont.Font(family=key[0], size=-px, weight=key[2])
        if g.measure(txt) <= width:
            break
    return g


def s(v):
    """Scale a pixel value."""
    return int(v * S)


def dlu(x, y):
    """Dialog units ('Helv' 8: avgchar 6x13 -> x*6/4, y*13/8) to pixels."""
    return int(round(x * 6 / 4 * S)), int(round(y * 13 / 8 * S))


# ----------------------------------------------------------------------------- canvas drawing
def raised(c, x0, y0, x1, y1, fill=FACE, tags=None, outer=True):
    """Win95 raised 3D box. Coordinates are unscaled and inclusive-exclusive like RECT."""
    x0, y0, x1, y1 = s(x0), s(y0), s(x1), s(y1)
    ids = [c.create_rectangle(x0, y0, x1 - 1, y1 - 1, fill=fill, outline=fill, tags=tags)]
    w = S
    if outer:
        ids.append(c.create_line(x0, y1 - w, x1 - w, y1 - w, x1 - w, y0 - 1, fill=DARK, width=w, tags=tags))
        ids.append(c.create_line(x0, y1 - 2 * w, x0, y0, x1 - 2 * w, y0, fill=HILITE, width=w, tags=tags))
        ids.append(c.create_line(x0 + w, y1 - 2 * w, x1 - 2 * w, y1 - 2 * w, x1 - 2 * w, y0, fill=SHADOW, width=w, tags=tags))
    else:
        ids.append(c.create_line(x0, y1 - w, x1 - w, y1 - w, x1 - w, y0 - 1, fill=SHADOW, width=w, tags=tags))
        ids.append(c.create_line(x0, y1 - 2 * w, x0, y0, x1 - 2 * w, y0, fill=HILITE, width=w, tags=tags))
    return ids


def sunken(c, x0, y0, x1, y1, fill=WINDOW, tags=None, deep=True):
    x0, y0, x1, y1 = s(x0), s(y0), s(x1), s(y1)
    w = S
    ids = [c.create_rectangle(x0, y0, x1 - 1, y1 - 1, fill=fill, outline=fill, tags=tags)]
    ids.append(c.create_line(x0, y1 - w, x0, y0, x1 - w, y0, fill=SHADOW, width=w, tags=tags))
    ids.append(c.create_line(x0, y1 - w, x1 - w, y1 - w, x1 - w, y0 - 1, fill=HILITE, width=w, tags=tags))
    if deep:
        ids.append(c.create_line(x0 + w, y1 - 2 * w, x0 + w, y0 + w, x1 - 2 * w, y0 + w, fill=DARK, width=w, tags=tags))
        ids.append(c.create_line(x0 + w, y1 - 2 * w, x1 - 2 * w, y1 - 2 * w, x1 - 2 * w, y0, fill=FACE, width=w, tags=tags))
    return ids


def rect(c, x0, y0, x1, y1, outline=DARK, fill='', tags=None, dash=None):
    return c.create_rectangle(s(x0), s(y0), s(x1) - 1, s(y1) - 1, outline=outline, fill=fill,
                              tags=tags, width=S, dash=dash)


def line(c, *pts, fill=DARK, tags=None, dash=None):
    return c.create_line(*[s(p) for p in pts], fill=fill, width=S, tags=tags, dash=dash)


def text(c, x, y, txt, font='small', fill=TEXT, anchor='nw', tags=None):
    return c.create_text(s(x), s(y), text=txt, font=f(font), fill=fill, anchor=anchor, tags=tags)


def image(c, x, y, img, anchor='nw', tags=None):
    return c.create_image(s(x), s(y), image=img, anchor=anchor, tags=tags)


def text_width(txt, font='small'):
    return f(font).measure(txt) / S


def clip_text(txt, width, font='system'):
    fo = f(font)
    w = s(width)
    if fo.measure(txt) <= w:
        return txt
    while txt and fo.measure(txt) > w:
        txt = txt[:-1]
    return txt


# ----------------------------------------------------------------------------- input helpers
def is_shift(ev):
    return bool(ev.state & 0x0001)


def is_ctrl(ev):
    return bool(ev.state & 0x0004) or (sys.platform == 'darwin' and bool(ev.state & 0x0008))


RIGHT_BUTTON = 2 if sys.platform == 'darwin' else 3


def bind_right(widget, seq, cb):
    """Bind the right mouse button (Button-2 on macOS Tk, plus Ctrl-click there)."""
    widget.bind('<%s-%d>' % (seq, RIGHT_BUTTON) if seq else '<Button-%d>' % RIGHT_BUTTON, cb)


class Repeater:
    """Auto-repeat for value cells: left button -1 / right +1, Shift x10, both buttons x10."""

    def __init__(self, widget):
        self.widget = widget
        self.job = None
        self.buttons = set()

    def start(self, ev, cb, button):
        self.buttons.add(button)
        self.cb = cb
        self.ev = ev
        self._fire(first=True)

    def step(self):
        big = is_shift(self.ev) or len(self.buttons) > 1
        sign = -1 if self.first_button() == 1 else 1
        return sign * (10 if big else 1), big

    def first_button(self):
        return self._first

    def _fire(self, first=False):
        if first:
            self._first = next(iter(self.buttons))
        self.cb(*self.step())
        self.job = self.widget.after(400 if first else 70, self._fire)

    def stop(self, button):
        self.buttons.discard(button)
        if not self.buttons and self.job:
            self.widget.after_cancel(self.job)
            self.job = None


class CanvasMixin:
    """Common Canvas setup for owner-drawn panes."""

    @staticmethod
    def make(parent, w, h, bg=FACE):
        return tk.Canvas(parent, width=s(w), height=s(h), bg=bg, highlightthickness=0, bd=0)
