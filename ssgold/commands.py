"""Menu command dispatch (WM_COMMAND ids from the MAIN_MENU resource)."""
from tkinter import messagebox

from . import resources, procedures


def _active_editor(app):
    w = app.client.active
    return w


def run(app, cid):
    w = _active_editor(app)
    s = app.settings
    table = {
        # File
        1: app.new_song,
        2: lambda: app.open_dialog('open'),
        3: app.save_song,
        5: app.save_as,
        6: lambda: app.merge(False),
        7: lambda: app.merge(True),
        8: lambda: app.open_dialog('delete'),
        9: app.quit_app,
        # Edit
        10: app.undo,
        11: app.redo,
        12: lambda: edit(app, 'copy'),
        13: lambda: edit(app, 'cut'),
        14: lambda: edit(app, 'paste'),
        15: lambda: edit(app, 'clear'),
        16: lambda: edit(app, 'select_all'),
        17: lambda: describe_clipboard(app),
        # View
        80: app.open_track_window,
        81: lambda: open_editor(app, 'proll'),
        82: lambda: open_editor(app, 'event'),
        83: lambda: open_editor(app, 'score'),
        84: lambda: open_editor(app, 'drum'),
        85: lambda: open_single(app, 'conductor'),
        86: lambda: open_single(app, 'notepad'),
        87: lambda: open_single(app, 'mixer'),
        88: lambda: open_single(app, 'keyboard'),
        89: lambda: open_single(app, 'lyrics'),
        90: lambda: open_single(app, 'ict'),
        91: lambda: not_ported(app, 'Audio'),
        92: lambda: track_settings(app),
        93: lambda: pattern_settings(app),
        # Procedures
        20: lambda: procedure(app, 'transpose'),
        21: lambda: procedure(app, 'velocity'),
        22: lambda: procedure(app, 'lengths'),
        23: lambda: procedure(app, 'quantize'),
        24: lambda: procedure(app, 'move'),
        25: lambda: procedure(app, 'timing'),
        26: lambda: procedure(app, 'delete'),
        27: lambda: procedure(app, 'thinout'),
        30: lambda: procedure(app, 'identical'),
        31: lambda: procedure(app, 'reverse'),
        # Options
        36: lambda: dialog(app, 'PREFERENCES_DLG'),
        37: lambda: dialog(app, 'DEFINITION_DLG'),
        38: lambda: dialog(app, 'SYNC_DLG'),
        39: lambda: dialog(app, 'METRONOME_DLG'),
        40: lambda: dialog(app, 'MIXDEF_DLG'),
        41: lambda: dialog(app, 'DEVICES_DLG'),
        42: lambda: dialog(app, 'PATCH_DLG'),
        45: lambda: dialog(app, 'SCORE_DLG'),
        46: lambda: lyric_font(app),
        47: lambda: dialog(app, 'TRACK_COLUMN_DLG'),
        48: lambda: dialog(app, 'DRUM_COLUMN_DLG'),
        # Window
        49: app.client.cascade,
        50: app.client.tile,
        51: app.client.arrange_icons,
        52: lambda: app.client.close_all(keep=app.windows.get('track')),
        53: lambda: dialog(app, 'CONFIGURE_DLG'),
        54: lambda: app.toggle_panel('show_transport'),
        55: lambda: app.toggle_panel('show_editors'),
        56: lambda: app.toggle_panel('show_fast'),
        57: lambda: app.toggle_caption(app.transport, 'cap_transport'),
        58: lambda: app.toggle_caption(app.editors, 'cap_editors'),
        59: lambda: app.toggle_caption(app.fastmenu, 'cap_fast'),
        67: lambda: app.toggle_panel('show_time'),
        # Help
        60: lambda: help_topic(app, 'Contents'),
        61: lambda: help_topic(app, 'Menus'),
        62: lambda: help_topic(app, 'Windows'),
        63: lambda: help_topic(app, 'Keyboard Shortcuts'),
        64: lambda: help_topic(app, 'How to Use Help'),
        65: lambda: dialog(app, 'ABOUT_DLG'),
    }
    fn = table.get(cid)
    if fn is None:
        not_ported(app, 'Audio and Video')
        return
    fn()


def not_ported(app, what):
    messagebox.showinfo('Sound Studio Gold', '%s functions are not part of this port.' % what, parent=app)


def dialog(app, name, **kw):
    from . import dialogs
    return dialogs.run(app, name, **kw)


def edit(app, op):
    w = app.client.active
    if w is not None and hasattr(w, 'edit_' + op):
        getattr(w, 'edit_' + op)()


def describe_clipboard(app):
    from . import resources as r
    cb = app.clipboard
    if not cb:
        txt = r.string(0)
    else:
        txt = r.string(1) + cb.describe()
    messagebox.showinfo('Clipboard Contents', txt, parent=app)


def selected_pattern(app, quiet=False):
    tw = app.windows.get('track')
    sel = [p for p in app.song.all_patterns() if p.selected]
    if len(sel) == 1:
        return sel[0]
    if not quiet:
        messagebox.showinfo('Sound Studio Gold', resources.string(14 if sel else 13), parent=app)
    return None


def open_editor(app, kind):
    from . import editors
    p = selected_pattern(app, quiet=True)
    w = app.client.active
    if p is None and w is not None and getattr(w, 'pattern', None) is not None:
        p = w.pattern
    if p is None:
        messagebox.showinfo('Sound Studio Gold', resources.string(13), parent=app)
        return
    if p.track.kind != 0 and kind != 'event':
        messagebox.showinfo('Sound Studio Gold', resources.string(3) if False else 'Please select a MIDI Pattern',
                            parent=app)
        return
    editors.open_editor(app, kind, p)


def open_single(app, kind):
    from . import editors
    editors.open_single(app, kind)


def track_settings(app):
    tw = app.windows.get('track')
    t = tw.current_track() if tw else None
    if t is None:
        messagebox.showinfo('Sound Studio Gold', resources.string(12), parent=app)
        return
    dialog(app, 'AUDIOTRACK_INFO_DLG' if t.kind == 1 else 'TRACK_INFO_DLG', track=t)


def pattern_settings(app):
    p = selected_pattern(app)
    if p is None:
        return
    dialog(app, 'AUDIOPAT_INFO_DLG' if p.track.kind == 1 else 'PATTERN_INFO_DLG', pattern=p)


def procedure(app, name):
    w = app.client.active
    target = procedures.Target.from_window(app, w)
    if target is None:
        messagebox.showinfo('Sound Studio Gold', resources.string(11), parent=app)
        return
    if name in ('identical', 'reverse'):
        app.checkpoint()
        getattr(procedures, name)(target)
        app.song_changed('events')
        return
    dialog(app, {'transpose': 'TRANSPOSE_DLG', 'velocity': 'VELOCITY_DLG', 'lengths': 'LENGTH_DLG',
                 'quantize': 'QUANTIZE_DLG', 'move': 'MOVE_DLG', 'timing': 'TIMING_DLG',
                 'delete': 'DELETE_DLG', 'thinout': 'THINOUT_DLG'}[name], target=target)


def quantize_now(app):
    w = app.client.active
    target = procedures.Target.from_window(app, w)
    if target is None:
        return
    app.checkpoint()
    q = app.settings.setdefault('quantize', {'value': '16', 'percent': 100, 'all': True, 'from': 0, 'to': 127})
    procedures.quantize(target, procedures.note_ticks(q['value'], app.song.timebase), q['percent'],
                        None if q['all'] else (q['from'], q['to']))
    app.song_changed('events')


def lyric_font(app):
    from tkinter import font as tkfont, simpledialog
    cur = app.settings.get('lyric_font', ['Arial', 24])
    fam = simpledialog.askstring('Lyric Font', 'Font family:', initialvalue=cur[0], parent=app)
    if not fam:
        return
    size = simpledialog.askinteger('Lyric Font', 'Size:', initialvalue=cur[1], minvalue=6, maxvalue=96, parent=app)
    if size:
        app.settings['lyric_font'] = [fam, size]
        app.song_changed('lyrics')


def help_topic(app, title):
    from . import helpviewer
    helpviewer.show(app, title)
