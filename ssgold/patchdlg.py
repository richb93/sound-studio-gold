"""Patch Lists dialog (PATCH_DLG): choose instrument lists, browse names, set banks and routings."""
import tkinter as tk
from tkinter import filedialog

from . import resources, ui
from .bwcc import Dialog, message_box


class PatchListDialog:
    def __init__(self, app, select, port, channel, prog, bank):
        self.app, self.select = app, select
        self.port, self.channel = port, channel
        self.prog, self.bank = max(0, prog or 0), (-1 if bank is None or bank < 0 else bank)

    def show(self):
        app = self.app
        pm = app.patches
        d = Dialog(app, 'PATCH_DLG')
        self.d = d
        cur = pm.list_for(self.port, self.channel) or pm.lists[0]
        names = [p.instrument for p in pm.lists]
        state = {'list': cur, 'prog': self.prog, 'bank': self.bank}
        lb = d.ctrls[1806]
        lb.pack_forget()
        hs = tk.Scrollbar(lb.master, orient='horizontal')
        hs.pack(side='bottom', fill='x')
        grid = tk.Canvas(lb.master, bg=ui.FACE, highlightthickness=0, bd=0)
        grid.pack(side='left', fill='both', expand=True)
        self.grid = grid
        COLW, LH = 150, 13          # LB_SETCOLUMNWIDTH 150, item height of the 8pt font

        def rows():
            return max(1, grid.winfo_height() // ui.s(LH))

        def draw():
            grid.delete('all')
            pl = state['list']
            nr = rows()
            fo = ui.f('dialog')
            for i in range(128):
                c, r = divmod(i, nr)
                x, y = c * ui.s(COLW), r * ui.s(LH)
                nm = pl.raw_name(i, state['bank'])
                sel = i == state['prog']
                if sel:
                    grid.create_rectangle(x, y, x + ui.s(COLW) - 1, y + ui.s(LH) - 1, fill=ui.SELECT, outline='')
                grid.create_text(x + ui.s(2), y + ui.s(LH) // 2, text=nm, anchor='w', font=fo,
                                 fill='white' if sel else 'black')
            ncols = (127 // nr) + 1
            grid.configure(scrollregion=(0, 0, ncols * ui.s(COLW), nr * ui.s(LH)))
            d.set_text(1802, pl.instrument)
            d.set_text(1803, ('%s %s' % (pl.prefix, pl.bank_name(state['bank']))).strip())
            d.set_text(1804, pl.raw_name(state['prog'], state['bank']))
            d.set_text(1805, str(state['prog'] + (1 if app.settings['prefs'].get('number_from_1') else 0)))
            d.set_text(1816, 'OFF' if state['bank'] < 0 else str(state['bank']))

        def click(ev):
            x = grid.canvasx(ev.x)
            c = int(x // ui.s(COLW))
            r = int(ev.y // ui.s(LH))
            nr = rows()
            if 0 <= r < nr and c >= 0 and c * nr + r < 128:
                state['prog'] = c * nr + r
                draw()

        grid.bind('<Configure>', lambda e: draw())
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
                state['bank'] = -1
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
        if mode != 'XG':
            for iid in (1824, 1825, 1826, 1827, 1828):
                d.hide(iid)
            d.hide_shade(1829)
        draw()

        def ok():
            d.result = (state['prog'] if state['prog'] >= 0 else -1, max(0, state['bank']) if state['bank'] >= 0 else -1)
        d.on_ok = ok
        d.show()
        return d.result if self.select and d.result not in (None, True) else None
