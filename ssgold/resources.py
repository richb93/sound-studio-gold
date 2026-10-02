"""Access to the extracted original resources (bitmaps, dialogs, strings, tables)."""
import json
import os
import sys

if getattr(sys, 'frozen', False):
    ASSETS = os.path.join(sys._MEIPASS, 'ssgold', 'assets')
else:
    ASSETS = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'assets')

_res = None
_tables = None


def res():
    global _res
    if _res is None:
        with open(os.path.join(ASSETS, 'resources.json')) as f:
            _res = json.load(f)
    return _res


def tables():
    global _tables
    if _tables is None:
        with open(os.path.join(ASSETS, 'tables.json')) as f:
            _tables = json.load(f)
    return _tables


def string(i):
    return res()['strings'].get(str(i), '')


def dialog(name):
    return res()['dialogs'][name]


def path(*parts):
    return os.path.join(ASSETS, *parts)


class Images:
    """PhotoImage cache, zoomed to the UI scale."""

    def __init__(self, root, scale=1):
        self.root = root
        self.scale = scale
        self.cache = {}

    def get(self, name, folder='bitmaps'):
        key = (folder, name)
        img = self.cache.get(key)
        if img is None:
            import tkinter as tk
            p = os.path.join(ASSETS, folder, '%s.png' % name)
            img = tk.PhotoImage(master=self.root, file=p)
            if self.scale != 1:
                img = img.zoom(self.scale, self.scale)
            self.cache[key] = img
        return img

    def bwcc(self, ident):
        return self.get(str(ident), 'bwcc')

    def icon(self, name):
        return self.get(name, 'icons')
