"""Help: shows topics decoded from the original GOLDHELP.HLP (assets/help.json)."""
import json
import os
import tkinter as tk

from . import resources, ui

_topics = None


def topics():
    global _topics
    if _topics is None:
        p = resources.path('help.json')
        _topics = json.load(open(p)) if os.path.exists(p) else {}
    return _topics


def show(app, title):
    t = topics()
    top = tk.Toplevel(app)
    top.title('Sound Studio Gold Help')
    top.geometry('%dx%d' % (ui.s(520), ui.s(420)))
    pw = tk.PanedWindow(top, orient='horizontal')
    pw.pack(fill='both', expand=True)
    lb = tk.Listbox(pw, font=ui.f('dialog'), width=28, exportselection=False)
    txt = tk.Text(pw, wrap='word', font=ui.f('dialog'), padx=8, pady=8)
    pw.add(lb)
    pw.add(txt)
    names = sorted(t)
    for n in names:
        lb.insert('end', n)

    def show_topic(name):
        txt.configure(state='normal')
        txt.delete('1.0', 'end')
        txt.insert('end', name + '\n\n', 'h')
        for para in t.get(name, []):
            txt.insert('end', para + '\n\n')
        txt.tag_configure('h', font=ui.f('dialogbold'))
        txt.configure(state='disabled')
    lb.bind('<<ListboxSelect>>', lambda e: show_topic(names[lb.curselection()[0]]) if lb.curselection() else None)
    if title in t:
        i = names.index(title)
        lb.selection_set(i)
        lb.see(i)
        show_topic(title)
    elif names:
        show_topic(names[0])
