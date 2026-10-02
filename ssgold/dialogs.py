"""Behaviour of each dialog (the *DLGPROC functions of Goldlib.dll)."""
import os
import glob as _glob

from . import resources, procedures, midi_io, ui
from .bwcc import Dialog, message_box
from .song import OFF, PAN_OFF, COND_TEMPO, MIDI
from .timing import TimeMap

FILE_TYPES = {411: '.SNG', 412: '.PAT', 413: '.DRM', 414: '.PLS', 415: '.MID', 416: '.DEF', 417: '.WND',
              418: '.WAV'}


def msg(app, text, kind='info', buttons=('ok',)):
    return message_box(app, text, kind=kind, buttons=buttons)


def run(app, name, **kw):
    fn = HANDLERS.get(name)
    if fn is None:
        return None
    return fn(app, **kw)


def _off(v, off=-1):
    return 'OFF' if v == off or v is None else str(v)


def _prog_text(app, v):
    if v is None or v < 0:
        return 'OFF'
    return str(v + 1 if app.settings['prefs'].get('number_from_1') else v)


def _prog_value(app, text):
    t = text.strip().upper()
    if t in ('OFF', ''):
        return OFF
    try:
        v = int(t) - (1 if app.settings['prefs'].get('number_from_1') else 0)
    except ValueError:
        return OFF
    return max(0, min(127, v))


def _int(text, default, lo, hi, off=None):
    t = text.strip().upper()
    if off is not None and t in ('OFF', ''):
        return off
    try:
        return max(lo, min(hi, int(t)))
    except ValueError:
        return default


# ----------------------------------------------------------------------------- about
def about(app, **kw):
    d = Dialog(app, 'ABOUT_DLG', title='About Sound Studio Gold')
    d.set_text(103, 'Sound Studio Gold')
    d.set_text(104, 'Python/Tkinter port %s' % __import__('ssgold').__version__)
    try:
        import psutil
        free = psutil.virtual_memory().available // 1024
    except Exception:
        free = 0
    d.set_text(105, '%7u K' % free if free else '')
    d.show()


# ----------------------------------------------------------------------------- file dialogs
def open_file_dialog(app, kind='open'):
    title = {'open': 'Open File', 'delete': 'Delete File', 'merge': 'Merge File'}[kind]
    res = _file_dialog(app, title, save=False)
    if not res:
        return
    path, ext = res
    if kind == 'delete':
        if msg(app, resources.string(817) % os.path.basename(path), 'question', ('yes', 'no')) == 'yes':
            try:
                os.remove(path)
            except OSError:
                msg(app, resources.string(23) % path, 'stop')
        return
    if ext == '.SNG' or ext == '.MID':
        if not app.confirm_discard():
            return
    app.open_path(path)


def save_file_dialog(app):
    return _file_dialog(app, 'Save File', save=True)


def _file_dialog(app, title, save):
    d = Dialog(app, 'OPENFILE_DLG', title=title)
    state = {'dir': app.settings.get('recent_dir') or os.getcwd(), 'ext': '.SNG'}
    if save and app.song.path:
        state['dir'] = os.path.dirname(app.song.path)
    for rid, ext in FILE_TYPES.items():
        if ext in ('.PLS', '.WAV', '.DEF', '.WND'):
            d.enable(rid, False)
    if save:
        for rid in (412,):
            d.enable(rid, False)
    d.set_radio(411)
    files, dirs = d.ctrls[403], d.ctrls[404]

    def refresh():
        files.delete(0, 'end')
        dirs.delete(0, 'end')
        p = state['dir']
        shown = p
        fo = ui.f('dialog')
        while len(shown) > 4 and fo.measure(shown) > ui.s(90 * 6 // 4):
            shown = '...' + shown[4:]
        d.set_text(402, shown)
        try:
            entries = sorted(os.listdir(p), key=str.lower)
        except OSError:
            entries = []
        for f in entries:
            if os.path.isfile(os.path.join(p, f)) and os.path.splitext(f)[1].upper() == state['ext']:
                files.insert('end', f.lower())
        dirs.insert('end', '[..]')
        for f in entries:
            if os.path.isdir(os.path.join(p, f)) and not f.startswith('.'):
                dirs.insert('end', '[%s]' % f)
        if os.name == 'nt':
            import string
            for letter in string.ascii_lowercase:
                if os.path.exists('%s:\\' % letter):
                    dirs.insert('end', '[-%s-]' % letter)
        cur = d.text(401)
        if not cur or cur.startswith('*'):
            d.set_text(401, '*' + state['ext'])

    def set_type(rid):
        state['ext'] = FILE_TYPES[rid]
        d.set_text(401, '*' + state['ext'])
        refresh()

    for rid in FILE_TYPES:
        d.on_command[rid] = lambda r=rid: set_type(r)

    def pick_file(_e=None):
        sel = files.curselection()
        if sel:
            d.set_text(401, files.get(sel[0]))

    def open_dir(_e=None):
        sel = dirs.curselection()
        if not sel:
            return
        name = dirs.get(sel[0])[1:-1]
        if name.startswith('-') and name.endswith('-'):
            state['dir'] = name[1] + ':\\'
        else:
            state['dir'] = os.path.normpath(os.path.join(state['dir'], name))
        refresh()

    files.bind('<<ListboxSelect>>', pick_file)
    files.bind('<Double-Button-1>', lambda e: (pick_file(), d.ok()))
    dirs.bind('<Double-Button-1>', open_dir)

    def ok():
        name = d.text(401).strip()
        if not name:
            return False
        full = os.path.join(state['dir'], name)
        if os.path.isdir(full):
            state['dir'] = os.path.normpath(full)
            d.set_text(401, '')
            refresh()
            return False
        if '*' in name or '?' in name:
            refresh()
            return False
        base = os.path.basename(name)
        if len(os.path.splitext(base)[0]) > 8 and save:
            msg(app, 'The File Name contains too many characters', 'info')
        if not os.path.splitext(name)[1]:
            name += state['ext']
            full = os.path.join(state['dir'], name)
        if not save and not os.path.exists(full):
            msg(app, resources.string(24) % name, 'stop')
            return False
        if save and os.path.exists(full):
            if msg(app, resources.string(819) % name, 'question', ('yes', 'no')) != 'yes':
                return False
        d.result = (full, os.path.splitext(full)[1].upper())
        app.settings['recent_dir'] = state['dir']
        return True

    d.on_ok = ok
    if save and app.song.path:
        d.set_text(401, os.path.basename(app.song.path).lower())
    refresh()
    r = d.show()
    return d.result if r else None


# ----------------------------------------------------------------------------- track / pattern
def track_info(app, track=None, **kw):
    t = track
    d = Dialog(app, 'TRACK_INFO_DLG')
    d.set_text(451, t.name)
    d.set_text(452, _prog_text(app, t.prog))
    d.set_text(453, _off(t.bank))
    d.set_text(454, str(t.channel))
    d.combo(455, app.port_names(), app.port_names()[t.port] if 0 <= t.port < len(app.port_names()) else app.port_names()[0])
    d.set_text(456, _off(t.volume))
    d.set_text(457, _off(t.pan, PAN_OFF))
    d.set_text(458, _off(t.reverb))
    d.set_text(459, _off(t.chorus))
    d.set_text(460, str(t.velocity))
    d.set_text(461, str(t.transpose))
    d.set_text(462, str(t.time))

    def patch_label():
        prog = _prog_value(app, d.text(452))
        bank = _int(d.text(453), OFF, 0, 16383, off=OFF)
        ch = _int(d.text(454), 1, 0, 16)
        nm = app.patches.name(t.port, ch or 1, prog, bank)
        b = d.buttons[465]
        b['text'] = nm
        d._draw_plain(465)

    def choose_patch():
        r = run(app, 'PATCH_DLG', select=True, port=t.port, channel=_int(d.text(454), 1, 1, 16),
                prog=_prog_value(app, d.text(452)), bank=_int(d.text(453), 0, 0, 16383, off=0))
        if r:
            prog, bank = r
            d.set_text(452, _prog_text(app, prog))
            d.set_text(453, _off(bank))
            patch_label()

    d.on_command[465] = choose_patch
    for iid in (452, 453, 454):
        d.ctrls[iid].bind('<KeyRelease>', lambda e: patch_label())
    patch_label()

    def ok():
        app.checkpoint()
        t.name = d.text(451)
        t.prog = _prog_value(app, d.text(452))
        t.bank = _int(d.text(453), OFF, 0, 16383, off=OFF)
        t.channel = _int(d.text(454), t.channel, 0, 16)
        names = app.port_names()
        if d.combo(455) in names:
            t.port = names.index(d.combo(455))
        t.volume = _int(d.text(456), OFF, 0, 127, off=OFF)
        t.pan = _int(d.text(457), PAN_OFF, -64, 63, off=PAN_OFF)
        t.reverb = _int(d.text(458), OFF, 0, 127, off=OFF)
        t.chorus = _int(d.text(459), OFF, 0, 127, off=OFF)
        t.velocity = _int(d.text(460), 0, -127, 127)
        t.transpose = _int(d.text(461), 0, -127, 127)
        t.time = _int(d.text(462), 0, -9999, 9999)
        app.send_track_settings(t)
        app.song_changed('tracks')
    d.on_ok = ok
    d.show()


def audiotrack_info(app, track=None, **kw):
    t = track
    d = Dialog(app, 'AUDIOTRACK_INFO_DLG')
    for iid, v in ((451, t.name), (456, _off(t.volume)), (457, _off(t.pan, PAN_OFF)), (458, _off(t.reverb)),
                   (459, _off(t.chorus)), (460, str(t.fx_type)), (462, str(t.time))):
        d.set_text(iid, v)

    def ok():
        app.checkpoint()
        t.name = d.text(451)
        t.volume = _int(d.text(456), OFF, 0, 127, off=OFF)
        t.pan = _int(d.text(457), PAN_OFF, -64, 63, off=PAN_OFF)
        t.reverb = _int(d.text(458), OFF, 0, 127, off=OFF)
        t.chorus = _int(d.text(459), OFF, 0, 127, off=OFF)
        t.fx_type = _int(d.text(460), 0, 0, 3)
        t.time = _int(d.text(462), 0, -9999, 9999)
        app.song_changed('tracks')
    d.on_ok = ok
    d.show()


def pattern_info(app, pattern=None, **kw):
    p = pattern
    t = p.track
    d = Dialog(app, 'PATTERN_INFO_DLG')
    d.set_text(1701, p.name)
    d.set_text(1702, _prog_text(app, p.prog))
    d.set_text(1703, _off(p.bank))
    d.set_text(1704, _off(p.channel, 0))
    d.set_text(1705, _off(p.volume))
    d.set_text(1706, _off(p.pan, PAN_OFF))
    d.set_text(1707, _off(p.reverb))
    d.set_text(1708, _off(p.chorus))
    d.set_text(1709, str(p.velocity))
    d.set_text(1710, str(p.transpose))
    d.set_text(1711, str(p.time))

    def patch_label():
        ch = _int(d.text(1704), 0, 0, 16, off=0) or t.channel or 1
        nm = app.patches.name(t.port, ch, _prog_value(app, d.text(1702)), _int(d.text(1703), OFF, 0, 16383, off=OFF))
        d.buttons[1714]['text'] = nm
        d._draw_plain(1714)

    def choose():
        ch = _int(d.text(1704), 0, 0, 16, off=0) or t.channel or 1
        r = run(app, 'PATCH_DLG', select=True, port=t.port, channel=ch, prog=_prog_value(app, d.text(1702)),
                bank=_int(d.text(1703), 0, 0, 16383, off=0))
        if r:
            d.set_text(1702, _prog_text(app, r[0]))
            d.set_text(1703, _off(r[1]))
            patch_label()
    d.on_command[1714] = choose
    for iid in (1702, 1703, 1704):
        d.ctrls[iid].bind('<KeyRelease>', lambda e: patch_label())
    patch_label()

    def ok():
        app.checkpoint()
        p.name = d.text(1701)
        if p.parent is None:
            for c in app.song.children_of(p):
                c.name = p.name
        p.prog = _prog_value(app, d.text(1702))
        p.bank = _int(d.text(1703), OFF, 0, 16383, off=OFF)
        p.channel = _int(d.text(1704), 0, 0, 16, off=0)
        p.volume = _int(d.text(1705), OFF, 0, 127, off=OFF)
        p.pan = _int(d.text(1706), PAN_OFF, -64, 63, off=PAN_OFF)
        p.reverb = _int(d.text(1707), OFF, 0, 127, off=OFF)
        p.chorus = _int(d.text(1708), OFF, 0, 127, off=OFF)
        p.velocity = _int(d.text(1709), 0, -127, 127)
        p.transpose = _int(d.text(1710), 0, -127, 127)
        p.time = _int(d.text(1711), 0, -9999, 9999)
        app.song_changed('patterns')
    d.on_ok = ok
    d.show()


def audiopat_info(app, pattern=None, **kw):
    p = pattern
    d = Dialog(app, 'AUDIOPAT_INFO_DLG')
    for iid, v in ((451, p.name), (456, _off(p.volume)), (457, _off(p.pan, PAN_OFF)), (458, _off(p.reverb)),
                   (459, _off(p.chorus)), (462, str(p.time))):
        d.set_text(iid, v)

    def ok():
        app.checkpoint()
        p.name = d.text(451)
        p.volume = _int(d.text(456), OFF, 0, 127, off=OFF)
        p.pan = _int(d.text(457), PAN_OFF, -64, 63, off=PAN_OFF)
        p.time = _int(d.text(462), 0, -9999, 9999)
        app.song_changed('patterns')
    d.on_ok = ok
    d.show()


def dim_pattern(app, pattern=None, **kw):
    p = pattern
    tm = app.tmap
    d = Dialog(app, 'DIM_PAT_DLG')
    d.set_text(1301, tm.fmt(p.start, 4).replace(' ', '0'))
    d.set_text(1302, tm.fmt(p.end, 4).replace(' ', '0'))
    d.set_text(1303, '0')

    def ok():
        s = tm.parse(d.text(1301))
        e = tm.parse(d.text(1302))
        if s is None or e is None or e <= s:
            msg(app, resources.string(35), 'stop')
            return False
        add = _int(d.text(1303), 0, 0, 999)
        app.checkpoint()
        keep = d.check(1304)
        if add:
            bar = tm.sig_at(s)[2]
            shift = add * bar
            for ev in p.source.events:
                ev.tick += shift
            if not keep:
                e += shift
        p.start, p.end = s, e
        app.song_changed('patterns')
    d.on_ok = ok
    d.show()


# ----------------------------------------------------------------------------- procedures
def _scope_init(d, ids, cfg):
    f, t, r_all, r_range = ids
    d.set_text(f, cfg.get('from', 'C -2'))
    d.set_text(t, cfg.get('to', 'G  8'))
    d.set_radio(r_all if cfg.get('all', True) else r_range)


NOTE_NAMES = ['C ', 'C#', 'D ', 'Eb', 'E ', 'F ', 'F#', 'G ', 'G#', 'A ', 'Bb', 'B ']


def note_name(n):
    return '%s%d' % (NOTE_NAMES[n % 12], n // 12 - 2)


def parse_note(text):
    t = text.strip().upper().replace(' ', '')
    if not t:
        return None
    try:
        return max(0, min(127, int(t)))
    except ValueError:
        pass
    names = {'C': 0, 'C#': 1, 'DB': 1, 'D': 2, 'D#': 3, 'EB': 3, 'E': 4, 'F': 5, 'F#': 6, 'GB': 6, 'G': 7,
             'G#': 8, 'AB': 8, 'A': 9, 'A#': 10, 'BB': 10, 'B': 11}
    for k in sorted(names, key=len, reverse=True):
        if t.startswith(k):
            try:
                octave = int(t[len(k):])
            except ValueError:
                return None
            return max(0, min(127, (octave + 2) * 12 + names[k]))
    return None


def _scope(d, ids, cfg):
    f, t, r_all, r_range = ids
    cfg['from'], cfg['to'] = d.text(f), d.text(t)
    cfg['all'] = d.radio([r_all, r_range]) == r_all
    if cfg['all']:
        return None
    lo, hi = parse_note(cfg['from']), parse_note(cfg['to'])
    if lo is None or hi is None:
        return None
    return (min(lo, hi), max(lo, hi))


def _proc_done(app, target):
    app.song_changed('events')


def transpose_dlg(app, target=None, **kw):
    cfg = app.settings.setdefault('transpose', {'semis': 0, 'up': True, 'all': False})
    d = Dialog(app, 'TRANSPOSE_DLG')
    d.set_text(206, str(cfg['semis']))
    d.set_radio(203 if cfg['up'] else 204)
    _scope_init(d, (207, 208, 209, 210), cfg)

    def ok():
        cfg['semis'] = _int(d.text(206), 12, 0, 127)
        cfg['up'] = d.radio([203, 204]) == 203
        sc = _scope(d, (207, 208, 209, 210), cfg)
        app.checkpoint()
        procedures.transpose(target, cfg['semis'] if cfg['up'] else -cfg['semis'], sc)
        _proc_done(app, target)
    d.on_ok = ok
    d.show()


def velocity_dlg(app, target=None, **kw):
    cfg = app.settings.setdefault('velocity', {'amount': 0, 'mode': 'up', 'min': 1, 'max': 127, 'all': False})
    d = Dialog(app, 'VELOCITY_DLG')
    d.set_text(751, str(cfg['amount']))
    d.set_radio({'up': 754, 'down': 755, 'fixed': 756}[cfg['mode']])
    d.set_text(761, str(cfg['min']))
    d.set_text(762, str(cfg['max']))
    _scope_init(d, (752, 753, 759, 760), cfg)

    def ok():
        cfg['amount'] = _int(d.text(751), 10, 0, 127)
        cfg['mode'] = {754: 'up', 755: 'down', 756: 'fixed'}[d.radio([754, 755, 756]) or 754]
        cfg['min'] = _int(d.text(761), 1, 1, 127)
        cfg['max'] = _int(d.text(762), 127, 1, 127)
        sc = _scope(d, (752, 753, 759, 760), cfg)
        app.checkpoint()
        procedures.velocity(target, cfg['amount'], cfg['mode'], cfg['min'], cfg['max'], sc)
        _proc_done(app, target)
    d.on_ok = ok
    d.show()


def length_dlg(app, target=None, **kw):
    cfg = app.settings.setdefault('lengths', {'mode': 1201, 'amount': 0, 'longer': True, 'fixed': '16', 'all': False})
    d = Dialog(app, 'LENGTH_DLG')
    d.set_radio(cfg['mode'])
    d.set_text(1205, str(cfg['amount']))
    d.set_radio(1206 if cfg['longer'] else 1207)
    d.combo(1214, procedures.QUANT_VALUES[1:], cfg['fixed'])
    _scope_init(d, (1208, 1209, 1210, 1211), cfg)

    def ok():
        cfg['mode'] = d.radio([1201, 1202, 1203, 1204]) or 1201
        cfg['amount'] = _int(d.text(1205), 10, 0, 9999)
        cfg['longer'] = d.radio([1206, 1207]) == 1206
        cfg['fixed'] = d.combo(1214)
        sc = _scope(d, (1208, 1209, 1210, 1211), cfg)
        mode = {1201: 'longer' if cfg['longer'] else 'shorter', 1202: 'legato', 1203: 'overlaps',
                1204: 'fixed'}[cfg['mode']]
        app.checkpoint()
        procedures.lengths(target, mode, cfg['amount'], procedures.note_ticks(cfg['fixed'], app.song.timebase), sc)
        _proc_done(app, target)
    d.on_ok = ok
    d.show()


def quantize_dlg(app, target=None, **kw):
    cfg = app.settings.setdefault('quantize', {'value': '16', 'percent': 100, 'all': False})
    d = Dialog(app, 'QUANTIZE_DLG')
    d.combo(354, procedures.QUANT_VALUES[1:], cfg['value'])
    d.set_text(351, str(cfg['percent']))
    _scope_init(d, (352, 353, 357, 358), cfg)

    def ok():
        cfg['value'] = d.combo(354)
        cfg['percent'] = _int(d.text(351), 100, 0, 100)
        sc = _scope(d, (352, 353, 357, 358), cfg)
        app.checkpoint()
        procedures.quantize(target, procedures.note_ticks(cfg['value'], app.song.timebase), cfg['percent'], sc)
        _proc_done(app, target)
    d.on_ok = ok
    d.show()


def move_dlg(app, target=None, **kw):
    cfg = app.settings.setdefault('move', {'amount': 0, 'later': False})
    d = Dialog(app, 'MOVE_DLG')
    d.set_text(1251, str(cfg['amount']))
    d.set_radio(1253 if cfg['later'] else 1252)

    def ok():
        cfg['amount'] = _int(d.text(1251), 0, 0, 999999)
        cfg['later'] = d.radio([1252, 1253]) == 1253
        app.checkpoint()
        try:
            procedures.move(target, cfg['amount'] if cfg['later'] else -cfg['amount'])
        except ValueError:
            app.undo()
            msg(app, resources.string(52), 'stop')
            return False
        _proc_done(app, target)
    d.on_ok = ok
    d.show()


def timing_dlg(app, target=None, **kw):
    cfg = app.settings.setdefault('timing', {'percent': 100})
    d = Dialog(app, 'TIMING_DLG')
    d.set_text(1451, str(cfg['percent']))

    def ok():
        cfg['percent'] = _int(d.text(1451), 100, 1, 1000)
        app.checkpoint()
        procedures.timing(target, cfg['percent'])
        _proc_done(app, target)
    d.on_ok = ok
    d.show()


CONTROLLERS = None


def controller_names():
    global CONTROLLERS
    if CONTROLLERS is None:
        from .editors.common import controller_label
        CONTROLLERS = [controller_label(i) for i in range(128)]
    return CONTROLLERS


def delete_dlg(app, target=None, **kw):
    cfg = app.settings.setdefault('delete', {'types': [1102, 1104, 1105, 1107], 'all_ctrl': True, 'ctrl': 1, 'all': False})
    d = Dialog(app, 'DELETE_DLG')
    for iid in range(1101, 1108):
        d.set_check(iid, iid in cfg['types'])
    d.combo(1114, controller_names(), controller_names()[cfg['ctrl']])
    d.set_radio(1115 if cfg['all_ctrl'] else 1116)
    _scope_init(d, (1108, 1109, 1112, 1113), cfg)

    def ok():
        cfg['types'] = [i for i in range(1101, 1108) if d.check(i)]
        cfg['all_ctrl'] = d.radio([1115, 1116]) == 1115
        cfg['ctrl'] = controller_names().index(d.combo(1114)) if d.combo(1114) in controller_names() else 0
        sc = _scope(d, (1108, 1109, 1112, 1113), cfg)
        kinds = {procedures.EVENT_TYPES[i] for i in cfg['types']}
        app.checkpoint()
        procedures.delete(target, kinds, None if cfg['all_ctrl'] else cfg['ctrl'], sc)
        _proc_done(app, target)
    d.on_ok = ok
    d.show()


def thinout_dlg(app, target=None, **kw):
    cfg = app.settings.setdefault('thinout', {'types': [1151, 1152, 1153, 1154], 'all_ctrl': True, 'ctrl': 1, 'every': 2})
    d = Dialog(app, 'THINOUT_DLG')
    for iid in range(1151, 1155):
        d.set_check(iid, iid in cfg['types'])
    d.combo(1158, controller_names(), controller_names()[cfg['ctrl']])
    d.set_radio(1159 if cfg['all_ctrl'] else 1160)
    d.set_text(1155, str(cfg['every']))

    def ok():
        cfg['types'] = [i for i in range(1151, 1155) if d.check(i)]
        cfg['all_ctrl'] = d.radio([1159, 1160]) == 1159
        cfg['ctrl'] = controller_names().index(d.combo(1158)) if d.combo(1158) in controller_names() else 0
        cfg['every'] = _int(d.text(1155), 2, 2, 99)
        kinds = {{1151: 0xA0, 1152: 0xB0, 1153: 0xD0, 1154: 0xE0}[i] for i in cfg['types']}
        app.checkpoint()
        procedures.thinout(target, kinds, cfg['every'], None if cfg['all_ctrl'] else cfg['ctrl'])
        _proc_done(app, target)
    d.on_ok = ok
    d.show()


# ----------------------------------------------------------------------------- options
TIMEBASE_IDS = dict(zip(range(1001, 1013), (48, 72, 96, 120, 144, 168, 192, 224, 240, 384, 480, 720)))


def midi_settings(app, **kw):
    o = app.seq.opts
    song = app.song
    d = Dialog(app, 'DEFINITION_DLG')
    for rid, tb in TIMEBASE_IDS.items():
        if tb == song.timebase:
            d.set_radio(rid)
    d.set_check(1013, o.thru_channel)
    d.set_check(1014, o.thru_realtime)
    d.set_check(1015, o.reset_on_stop)
    d.set_check(1016, o.kill_on_cycle)
    d.set_check(1042, o.chase)
    d.set_check(1043, o.send_reset)
    types = [0x90, 0xA0, 0xB0, 0xC0, 0xD0, 0xE0, 0xF0]
    for i, k in enumerate(types):
        d.set_check(1017 + i, k in o.filter_types)
    for ch in range(16):
        d.set_check(1024 + ch, (ch + 1) in o.filter_channels)

    def ok():
        rid = d.radio(list(TIMEBASE_IDS))
        tb = TIMEBASE_IDS.get(rid, song.timebase)
        if tb != song.timebase:
            r = msg(app, resources.string(49), 'question', ('yes', 'no', 'cancel'))
            if r == 'cancel':
                return False
            app.checkpoint()
            if r == 'yes':
                rescale_song(song, tb)
            else:
                song.timebase = tb
        o.thru_channel = d.check(1013)
        o.thru_realtime = d.check(1014)
        o.reset_on_stop = d.check(1015)
        o.kill_on_cycle = d.check(1016)
        o.chase = d.check(1042)
        o.send_reset = d.check(1043)
        o.filter_types = {k for i, k in enumerate(types) if d.check(1017 + i)}
        o.filter_channels = {ch + 1 for ch in range(16) if d.check(1024 + ch)}
        app.song_changed()
    d.on_ok = ok
    d.show()


def rescale_song(song, tb):
    old = song.timebase

    def sc(v):
        return int(round(v * tb / old))
    for p in song.all_patterns():
        if p.parent is None:
            for e in p.events:
                e.tick = sc(e.tick)
                e.length = sc(e.length)
        p.start, p.end = sc(p.start), sc(p.end)
        p.time = sc(p.time)
    for t in song.tracks:
        t.time = sc(t.time)
    for c in song.conductor.points:
        c.tick = sc(c.tick)
    song.left, song.right = sc(song.left), sc(song.right)
    song.timebase = tb


def preferences(app, **kw):
    pr = app.settings['prefs']
    d = Dialog(app, 'PREFERENCES_DLG')
    checks = {1401: 'copy_as_parents', 1402: 'chord_conflict', 1408: 'conductor_warning', 1409: 'ask_type0',
              1416: 'leave_midi', 1417: 'number_from_1', 1410: 'single_edit'}
    for iid, k in checks.items():
        d.set_check(iid, pr.get(k))
    sb = d.ctrls[1404]
    sb.lo, sb.hi = 1, 20
    sb.cmd = lambda v: d.set_text(1403, '%2d' % v)
    sb.set(pr.get('timer_ms', 5), notify=True)
    d.on_command[1405] = lambda: sb.set(1, notify=True)
    d.on_command[1406] = lambda: sb.set(5, notify=True)
    d.on_command[1407] = lambda: sb.set(10, notify=True)
    d.combo(1412, ['None', 'Piano Roll', 'Event', 'Score', 'Drum'], pr.get('dbl_midi', 'Piano Roll'))
    d.combo(1413, ['None', 'Audio Window'], pr.get('dbl_audio', 'Audio Window'))
    bgs = sorted(resources.string(864 + i) for i in range(25))
    d.combo(1415, bgs, pr.get('bg_track', 'Vellum'))
    d.combo(1414, bgs, pr.get('bg_program', 'Evolution Purple'))
    d.set_text(1411, str(pr.get('kbd_velocity', 100)))

    def ok():
        for iid, k in checks.items():
            pr[k] = d.check(iid)
        pr['timer_ms'] = sb.value
        pr['dbl_midi'] = d.combo(1412)
        pr['dbl_audio'] = d.combo(1413)
        pr['bg_track'] = d.combo(1415)
        pr['bg_program'] = d.combo(1414)
        pr['kbd_velocity'] = _int(d.text(1411), 100, 1, 127)
        app.set_backgrounds()
        app.song_changed()
    d.on_ok = ok
    d.show()


def metronome(app, **kw):
    o = app.seq.opts
    d = Dialog(app, 'METRONOME_DLG')
    d.set_check(1602, o.metro_midi)
    d.set_check(1601, o.metro_speaker)
    names = app.port_names()
    d.combo(1603, names, names[o.metro_port] if o.metro_port < len(names) else names[0])
    d.set_text(1604, str(o.metro_channel))
    d.set_text(1605, note_name(o.metro_pitch[0]))
    d.set_text(1606, note_name(o.metro_pitch[1]))
    d.set_text(1607, str(o.metro_vel[0]))
    d.set_text(1608, str(o.metro_vel[1]))
    d.set_check(1612, o.metro_record_only)
    d.set_text(1609, str(o.count_in))

    def ok():
        o.metro_midi = d.check(1602)
        o.metro_speaker = d.check(1601)
        if d.combo(1603) in names:
            o.metro_port = names.index(d.combo(1603))
        o.metro_channel = _int(d.text(1604), 10, 1, 16)
        o.metro_pitch = (parse_note(d.text(1605)) or 37, parse_note(d.text(1606)) or 37)
        o.metro_vel = (_int(d.text(1607), 127, 1, 127), _int(d.text(1608), 90, 1, 127))
        o.metro_record_only = d.check(1612)
        o.count_in = _int(d.text(1609), 1, 0, 4)
    d.on_ok = ok
    d.show()


def mixer_settings(app, **kw):
    m = app.settings['mixer']
    d = Dialog(app, 'MIXDEF_DLG')
    names = controller_names()
    cfg = m.setdefault('users', [[93, 0, 0, 127], [91, 0, 0, 127]])
    for (cb, e1, e2, e3), u in zip(((1356, 1357, 1358, 1359), (1351, 1352, 1353, 1354)), cfg):
        d.combo(cb, names, names[u[0]])
        d.set_text(e1, str(u[1]))
        d.set_text(e2, str(u[2]))
        d.set_text(e3, str(u[3]))
    d.set_radio({0: 1368, 1: 1369, 2: 1370}[m.get('under', 0)])
    d.set_check(1365, m.get('midi_in'))
    d.set_check(1366, m.get('song_data', True))
    d.set_check(1367, m.get('record'))
    d.set_check(1371, m.get('volumes_only'))

    def ok():
        for i, (cb, e1, e2, e3) in enumerate(((1356, 1357, 1358, 1359), (1351, 1352, 1353, 1354))):
            v = d.combo(cb)
            cfg[i] = [names.index(v) if v in names else 0, _int(d.text(e1), 0, 0, 127),
                      _int(d.text(e2), 0, 0, 127), _int(d.text(e3), 127, 0, 127)]
        m['under'] = {1368: 0, 1369: 1, 1370: 2}[d.radio([1368, 1369, 1370]) or 1368]
        m['midi_in'] = d.check(1365)
        m['song_data'] = d.check(1366)
        m['record'] = d.check(1367)
        m['volumes_only'] = d.check(1371)
        app.song_changed('mixer')
    d.on_ok = ok
    d.show()


def devices(app, **kw):
    d = Dialog(app, 'DEVICES_DLG')
    ins, outs = midi_io.input_names(), midi_io.output_names()
    if not midi_io.available():
        ins, outs = [], []
    lin, lout = d.ctrls[1652], d.ctrls[1653]
    lin.configure(selectmode='multiple')
    lout.configure(selectmode='multiple')
    for n in ins:
        lin.insert('end', n)
        if n in app.settings['inputs']:
            lin.selection_set('end')
    for n in outs:
        lout.insert('end', n)
        if n in app.settings['outputs']:
            lout.selection_set('end')
    modes = app.settings['port_modes']
    for row in range(16):
        base = 1654 + row * 3
        if row >= len(outs):
            for k in range(3):
                d.hide(base + k)
        m = modes.get(str(row), 'GM')
        d.set_radio(base + {'GM': 0, 'GS': 1, 'XG': 2}.get(m, 0))

    def ok():
        new_out = [outs[i] for i in lout.curselection()]
        new_in = [ins[i] for i in lin.curselection()]
        changed_modes = False
        sel_outs = list(lout.curselection())
        for k, i in enumerate(sel_outs):
            base = 1654 + i * 3
            r = d.radio([base, base + 1, base + 2])
            mode = {0: 'GM', 1: 'GS', 2: 'XG'}[(r - base) if r else 0]
            if modes.get(str(k)) != mode:
                changed_modes = True
            modes[str(k)] = mode
        app.settings['outputs'] = new_out
        app.settings['inputs'] = new_in
        app.midi.open_outputs(new_out)
        app.midi.open_inputs(new_in)
        app.song.ports = app.port_names()
        if msg(app, resources.string(822), 'question', ('yes', 'no')) == 'yes':
            for port, mode in modes.items():
                app.patches.set_mode(int(port), mode)
        app.save_settings()
        app.song_changed()
    def cancel():
        if msg(app, resources.string(822), 'question', ('yes', 'no')) == 'yes':
            for port, mode in modes.items():
                app.patches.set_mode(int(port), mode)
    d.on_ok = ok
    d.on_cancel = cancel
    d.show()


def sync_dlg(app, **kw):
    song = app.song
    d = Dialog(app, 'SYNC_DLG')
    d.set_text(901, song.smpte_start)
    fps = {24: 902, 25: 903, 29: 904, 30: 905}
    d.set_radio(fps.get(song.frame_format, 903))
    cfg = app.settings.setdefault('sync', {'receive': 906, 'in_port': '', 'clock': False, 'mtc': False,
                                           'out_port': '', 'delay': 0})
    d.set_radio(cfg['receive'])
    ins = midi_io.input_names() or ['(none)']
    names = app.port_names()
    d.combo(908, ins, cfg['in_port'] if cfg['in_port'] in ins else ins[0])
    d.set_check(909, cfg['clock'])
    d.set_check(910, cfg['mtc'])
    d.combo(911, names, cfg['out_port'] if cfg['out_port'] in names else names[0])
    d.set_text(912, str(cfg['delay']))

    def ok():
        song.smpte_start = d.text(901)[:11]
        r = d.radio(list(fps.values()))
        song.frame_format = {v: k for k, v in fps.items()}.get(r, 25)
        cfg['receive'] = d.radio([906, 907]) or 906
        cfg['in_port'] = d.combo(908)
        cfg['clock'] = d.check(909)
        cfg['mtc'] = d.check(910)
        cfg['out_port'] = d.combo(911)
        cfg['delay'] = _int(d.text(912), 0, 0, 9999)
        app.song_changed()
    d.on_ok = ok
    d.show()


def score_settings(app, **kw):
    sc = app.settings['score']
    d = Dialog(app, 'SCORE_DLG')
    pairs = {1501: 'left', 1502: 'right', 1503: 'top', 1504: 'bottom', 1505: 'internote', 1506: 'interstave',
             1507: 'title', 1508: 'names', 1517: 'maxstaves', 1522: 'lyric_ch'}
    for iid, k in pairs.items():
        d.set_text(iid, str(sc[k]))
    clefs = [resources.string(80 + i) for i in range(7)]
    d.combo(1509, clefs, clefs[sc['clef']])
    d.set_text(1510, note_name(sc['split']))
    for iid, k in ((1511, 'auto'), (1516, 'pagenums'), (1518, 'beam_screen'), (1519, 'beam_printer'),
                   (1520, 'barnums'), (1521, 'simplify')):
        d.set_check(iid, sc[k])

    def detect():
        w = app.client.active
        p = getattr(w, 'pattern', None)
        if p is not None:
            notes = [e.d1 for e in p.get_events() if e.is_note()]
            if notes:
                d.set_text(1510, note_name(sorted(notes)[len(notes) // 2]))
    d.on_command[1512] = detect

    def ok():
        for iid, k in pairs.items():
            sc[k] = _int(d.text(iid), sc[k], 0, 999)
        sc['clef'] = clefs.index(d.combo(1509)) if d.combo(1509) in clefs else 0
        sc['split'] = parse_note(d.text(1510)) or 60
        for iid, k in ((1511, 'auto'), (1516, 'pagenums'), (1518, 'beam_screen'), (1519, 'beam_printer'),
                       (1520, 'barnums'), (1521, 'simplify')):
            sc[k] = d.check(iid)
        app.song_changed('score')
    d.on_ok = ok
    d.show()


TRACK_COLUMNS = list(range(551, 569))
DRUM_COLUMNS = list(range(651, 659))


def track_columns(app, **kw):
    d = Dialog(app, 'TRACK_COLUMN_DLG')
    cur = app.settings['track_columns']
    for iid in TRACK_COLUMNS:
        d.set_check(iid, iid in cur)

    def ok():
        app.settings['track_columns'] = [i for i in TRACK_COLUMNS if d.check(i)] or [551]
        app.song_changed('columns')
    d.on_ok = ok
    d.show()


def drum_columns(app, **kw):
    d = Dialog(app, 'DRUM_COLUMN_DLG')
    cur = app.settings['drum_columns']
    for iid in DRUM_COLUMNS:
        d.set_check(iid, iid in cur)

    def ok():
        app.settings['drum_columns'] = [i for i in DRUM_COLUMNS if d.check(i)] or [651]
        app.song_changed('columns')
    d.on_ok = ok
    d.show()


def drum_info(app, drum=None, **kw):
    kit = app.drumkit
    dr = drum
    d = Dialog(app, 'DRUM_INFO_DLG')
    d.set_text(701, kit.name)
    d.set_text(702, dr.name)
    d.set_text(703, str(dr.channel))
    d.set_text(704, note_name(dr.key))
    d.set_text(705, str(dr.velocity))
    d.set_text(706, str(dr.length))

    def ok():
        ch = _int(d.text(703), dr.channel, 0, 16)
        key = parse_note(d.text(704))
        key = dr.key if key is None else key
        other = next((x for x in kit.drums if x is not dr and x.key == key and x.channel == ch), None)
        if other is not None:
            msg(app, resources.string(70) % other.name, 'warning')
        kit.name = d.text(701)[:20]
        dr.name = d.text(702)[:20]
        dr.channel, dr.key = ch, key
        dr.velocity = _int(d.text(705), dr.velocity, 1, 127)
        dr.length = _int(d.text(706), dr.length, 1, 9999)
        app.song_changed('drums')
    d.on_ok = ok
    d.show()


def configure_fast(app, **kw):
    from .app import FAST_FUNCTIONS
    d = Dialog(app, 'CONFIGURE_DLG')
    funcs, sel = d.ctrls[252], d.ctrls[253]
    for f in FAST_FUNCTIONS:
        funcs.insert('end', f)
    items = list(app.settings['fast_menu'])

    def refresh():
        sel.delete(0, 'end')
        for f in items:
            sel.insert('end', f)
        d.enable(254, len(items) < 10)

    def add():
        s = funcs.curselection()
        if s and len(items) < 10:
            items.append(FAST_FUNCTIONS[s[0]])
            refresh()

    def delete():
        s = sel.curselection()
        if s:
            items.pop(s[0])
            refresh()

    def move(dlt):
        s = sel.curselection()
        if not s:
            return
        i = s[0]
        j = i + dlt
        if 0 <= j < len(items):
            items[i], items[j] = items[j], items[i]
            refresh()
            sel.selection_set(j)

    def empty():
        items.clear()
        refresh()
    d.on_command.update({254: add, 255: delete, 256: empty, 257: lambda: move(-1), 258: lambda: move(1)})
    refresh()

    def ok():
        app.settings['fast_menu'] = items
        app.fastmenu.resize()
        app.layout_panels()
    d.on_ok = ok
    d.show()


def conflict(app, count=0, **kw):
    d = Dialog(app, 'CONFLICT_DLG')
    d.set_text(2101, '%2d' % count)
    d.show()


def message(app, text='', **kw):
    d = Dialog(app, 'MESSAGE_DLG')
    d.set_text(2151, text)
    d.show()


def sysex(app, event=None, **kw):
    d = Dialog(app, 'SYSEX_DLG')
    d.set_text(1751, ','.join('%02X' % b for b in event.data))

    def ok():
        txt = d.text(1751).replace('\n', '').replace(' ', '')
        parts = [p for p in txt.split(',') if p]
        try:
            data = bytes(int(p, 16) for p in parts)
            if any(len(p) > 2 for p in parts):
                raise ValueError
        except ValueError:
            msg(app, resources.string(34), 'stop')
            return False
        if not data or data[0] != 0xF0:
            msg(app, resources.string(32), 'stop')
            return False
        if data[-1] != 0xF7:
            msg(app, resources.string(33), 'stop')
            return False
        app.checkpoint()
        event.data = data
        app.song_changed('events')
    d.on_ok = ok
    d.show()


def patch_lists(app, select=False, port=0, channel=1, prog=0, bank=0, **kw):
    """Patch Lists dialog.  With select=True it returns (prog, bank) for the Patch buttons."""
    from .patchdlg import PatchListDialog
    if not select and 'channel' not in kw and not kw.get('explicit'):
        tw = app.windows.get('track')
        t = tw.current_track() if tw is not None else None
        if t is None or t.kind != MIDI or not t.channel:
            msg(app, resources.string(64), 'exclamation')
            return None
        port, channel, prog, bank = max(0, t.port), t.channel, max(0, t.prog), max(0, t.bank)
    return PatchListDialog(app, select, port, channel, prog, bank).show()


def routing(app, **kw):
    d = Dialog(app, 'ROUTING_DLG')
    names = app.port_names()
    lists = ['OFF'] + [p.filename for p in app.patches.lists]
    state = {'port': 0}

    def load():
        p = state['port']
        for ch in range(16):
            fn, drum = app.patches.routing.get((p, ch + 1), ('GMDRUMS.PLS' if ch == 9 else 'GM.PLS', ch == 9))
            d.combo(1852 + ch, lists, fn if fn in lists else lists[0])
            d.set_check(1870 + ch, drum)

    def save():
        p = state['port']
        for ch in range(16):
            app.patches.routing[(p, ch + 1)] = (d.combo(1852 + ch), d.check(1870 + ch))

    def port_change(v):
        save()
        state['port'] = names.index(v) if v in names else 0
        load()
    d.combo(1851, names, names[0], cmd=port_change)
    d.combo(1869, lists, 'GM.PLS')

    def set_all():
        v = d.combo(1869)
        for ch in range(16):
            d.combo(1852 + ch, value=v)
    d.on_command[1868] = set_all
    load()

    def ok():
        save()
        app.song_changed('tracks')
    d.on_ok = ok
    d.show()


def style_dlg(app, **kw):
    from .ict import InstantChordTrack
    InstantChordTrack.open(app)


def wavelist(app, **kw):
    d = Dialog(app, 'WAVELIST_DLG')
    lb = d.ctrls[2051]
    for p in app.song.all_patterns():
        if p.track.kind == 1 and p.parent is None:
            name = p.blob[:128].split(b'\0')[0].decode('latin1', 'replace') if p.blob else ''
            lb.insert('end', name or p.name)
    d.show()


def audio_unported(app, **kw):
    msg(app, 'Audio functions are not part of this port.', 'info')


HANDLERS = {
    'ABOUT_DLG': about, 'TRACK_INFO_DLG': track_info, 'AUDIOTRACK_INFO_DLG': audiotrack_info,
    'PATTERN_INFO_DLG': pattern_info, 'AUDIOPAT_INFO_DLG': audiopat_info, 'DIM_PAT_DLG': dim_pattern,
    'TRANSPOSE_DLG': transpose_dlg, 'VELOCITY_DLG': velocity_dlg, 'LENGTH_DLG': length_dlg,
    'QUANTIZE_DLG': quantize_dlg, 'MOVE_DLG': move_dlg, 'TIMING_DLG': timing_dlg, 'DELETE_DLG': delete_dlg,
    'THINOUT_DLG': thinout_dlg, 'DEFINITION_DLG': midi_settings, 'PREFERENCES_DLG': preferences,
    'METRONOME_DLG': metronome, 'MIXDEF_DLG': mixer_settings, 'DEVICES_DLG': devices, 'SYNC_DLG': sync_dlg,
    'SCORE_DLG': score_settings, 'TRACK_COLUMN_DLG': track_columns, 'DRUM_COLUMN_DLG': drum_columns,
    'DRUM_INFO_DLG': drum_info, 'CONFIGURE_DLG': configure_fast, 'CONFLICT_DLG': conflict,
    'MESSAGE_DLG': message, 'SYSEX_DLG': sysex, 'PATCH_DLG': patch_lists, 'ROUTING_DLG': routing,
    'STYLE_DLG': style_dlg, 'WAVELIST_DLG': wavelist, 'AUDIO_SYS_DLG': audio_unported,
    'AUDIO_PREFS_DLG': audio_unported,
}
