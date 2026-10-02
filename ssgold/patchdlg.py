"""Patch Lists dialog (PATCH_DLG): choose instrument lists, browse names, set banks and routings."""
import tkinter as tk
from tkinter import filedialog

from . import resources, ui
from .bwcc import Dialog, message_box


class PatchListDialog:
    def __init__(self, app, select, port, channel, prog, bank):
        self.app, self.select = app, select
        self.port, self.channel = port, channel
        self.prog, self.bank = max(0, prog or 0), max(0, bank or 0)

    def show(self):
        app = self.app
        pm = app.patches
        d = Dialog(app, 'PATCH_DLG')
        self.d = d
        cur = pm.list_for(self.port, self.channel) or pm.lists[0]
        names = [p.instrument for p in pm.lists]
        state = {'list': cur, 'prog': self.prog, 'bank': self.bank}
        lb = d.ctrls[1806]
        lb.configure(font=ui.f('dialogbold'))
        lb.pack_forget()
        grid = tk.Canvas(lb.master, bg=ui.FACE, highlightthickness=0, bd=0)
        grid.pack(side='left', fill='both', expand=True)
        hs = tk.Scrollbar(lb.master, orient='horizontal')
        self.grid = grid

        def draw():
            grid.delete('all')
            pl = state['list']
            rows = 16
            colw = ui.s(120)
            lh = ui.f('dialogbold').metrics('linespace')
            for i in range(128):
                c, r = divmod(i, rows)
                x, y = ui.s(4) + c * colw, ui.s(2) + r * lh
                nm = pl.raw_name(i, state['bank'])
                if i == state['prog']:
                    grid.create_rectangle(x - ui.s(2), y, x + colw - ui.s(6), y + lh, fill=ui.SELECT, outline='')
                grid.create_text(x, y, text=nm, anchor='nw', font=ui.f('dialogbold'),
                                 fill='white' if i == state['prog'] else 'black')
            grid.configure(scrollregion=(0, 0, colw * 8, rows * lh))
            d.set_text(1802, pl.instrument)
            d.set_text(1803, ('%s %s' % (pl.prefix, pl.bank_name(state['bank']))).strip())
            d.set_text(1804, pl.raw_name(state['prog'], state['bank']))
            d.set_text(1805, str(state['prog'] + (1 if app.settings['prefs'].get('number_from_1') else 0)))
            d.set_text(1816, str(state['bank']))

        def click(ev):
            lh = ui.f('dialogbold').metrics('linespace')
            x = grid.canvasx(ev.x)
            c = int((x - ui.s(4)) // ui.s(120))
            r = int((ev.y - ui.s(2)) // lh)
            if 0 <= r < 16 and c >= 0:
                state['prog'] = min(127, c * 16 + r)
                draw()

        grid.bind('<Button-1>', click)
        grid.bind('<Double-Button-1>', lambda e: (click(e), d.ok()))
        grid.configure(xscrollcommand=hs.set)
        hs.configure(command=grid.xview)

        def pick_list(name):
            for p in pm.lists:
                if p.instrument == name:
                    state['list'] = p
                    state['bank'] = 0
            draw()
        d.combo(1801, names, cur.instrument, cmd=pick_list)

        def add():
            path = filedialog.askopenfilename(parent=d, filetypes=[('Patch Lists', '*.pls *.PLS')])
            if path:
                try:
                    pl = pm.add(path)
                except ValueError as e:
                    message_box(app, str(e), kind='stop')
                    return
                d.combo(1801, [p.instrument for p in pm.lists], pl.instrument)
                pick_list(pl.instrument)

        def remove():
            if len(pm.lists) <= 1:
                message_box(app, resources.string(71), kind='stop')
                return
            pm.lists.remove(state['list'])
            state['list'] = pm.lists[0]
            d.combo(1801, [p.instrument for p in pm.lists], state['list'].instrument)
            draw()

        def bank_from_entry(_e=None):
            try:
                state['bank'] = max(0, min(127, int(d.text(1816))))
            except ValueError:
                return
            draw()

        def set_off():
            state['prog'] = -1
            d.ok()

        def gs(b):
            state['bank'] = b
            draw()
        d.ctrls[1816].bind('<Return>', bank_from_entry)
        d.ctrls[1816].bind('<FocusOut>', bank_from_entry)
        d.on_command.update({1811: add, 1813: remove, 1808: set_off,
                             1809: lambda: __import__('ssgold.dialogs', fromlist=['run']).run(app, 'ROUTING_DLG'),
                             1820: lambda: gs(0), 1821: lambda: gs(8), 1822: lambda: gs(16), 1823: lambda: gs(24)})
        mode = app.settings['port_modes'].get(str(self.port), 'GM')
        d.set_radio({'GM': 1817, 'GS': 1818, 'XG': 1819}[mode])
        for iid in (1820, 1821, 1822, 1823):
            d.enable(iid, mode == 'GS')
        draw()

        def ok():
            d.result = (state['prog'] if state['prog'] >= 0 else -1, state['bank'])
        d.on_ok = ok
        d.show()
        return d.result if self.select and d.result not in (None, True) else None
