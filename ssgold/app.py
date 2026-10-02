"""Main window (MAINWNDPROC): menus, MDI client, floating panels, transport control, files."""
import collections
import json
import os
import sys
import time
import tkinter as tk
from tkinter import filedialog, messagebox

from . import __version__, resources, ui
from .mdi import MDIClient
from .midi_io import MidiIO
from .patches import PatchManager, DrumKit
from .resources import Images
from .sequencer import Sequencer
from .song import Song, SongError, new_song, MIDI, AUDIO, CHORD, save_pattern, load_pattern
from .timing import TimeMap, smpte
from . import smf

SETTINGS = os.path.join(os.path.expanduser('~'), '.ssgold_settings.json')

# Configure Fast Menu 'Functions' list, in the original's order (name, menu command id)
FAST_TABLE = [
    ('New', 1), ('Open...', 2), ('Save Song', 3), ('Save As...', 5), ('Merge Song...', 6),
    ('Merge Midi File...', 7), ('Delete...', 8), ('Quit', 9), ('Undo', 10), ('Redo', 11), ('Copy', 12),
    ('Cut', 13), ('Paste', 14), ('Clear', 15), ('Select All', 16), ('Describe Clipboard...', 17),
    ('Print...', 18), ('Printer Setup...', 19), ('Transpose...', 20), ('Change Velocity...', 21),
    ('Change Lengths...', 22), ('Quantize...', 23), ('Move Events...', 24), ('Change Timing...', 25),
    ('Delete Events...', 26), ('Thin Out Continuous Events...', 27), ('Delete Identical Events', 30),
    ('Reverse Notes', 31), ('Preferences...', 36), ('MIDI Settings...', 37),
    ('Synchronization Settings...', 38), ('Metronome Settings...', 39), ('Mixer Settings...', 40),
    ('Devices...', 41), ('Patch Lists...', 42), ('Audio System Settings...', 43), ('Wave Files in use...', 44),
    ('Score Settings...', 45), ('Lyric Font...', 46), ('Track Columns...', 47), ('Drum Columns...', 48),
    ('Cascade Windows', 49), ('Tile Windows', 50), ('Arrange Icons', 51), ('Close All', 52),
    ('Configure Fast Menu...', 53), ('Hide Transport', 54), ('Hide Editors', 55), ('Hide Fast Menu', 56),
    ('Toggle Transport Caption', 57), ('Toggle Editors Caption', 58), ('Toggle Fast Menu Caption', 59),
    ('Contents', 60), ('Menus', 61), ('Windows', 62), ('Keyboard Shortcuts', 63), ('How to Use Help', 64),
    ('About Sound Studio Gold...', 65)]
FAST_FUNCTIONS = [n for n, _i in FAST_TABLE]
FAST_IDS = dict(FAST_TABLE)
# names used by earlier versions of the settings file
FAST_IDS.update({'Thin Out...': 27, 'Delete Identical': 30, 'Synchronization...': 38, 'Metronome...': 39,
                 'Cascade': 49, 'Tile': 50})

DEFAULT_SETTINGS = {
    'scale': 0,
    'outputs': [], 'inputs': [], 'port_modes': {},
    'fast_menu': ['Transpose...', 'Change Velocity...', 'Quantize...', 'Change Lengths...',
                  'Delete Events...', 'Copy', 'Cut', 'Paste', 'Open...', 'Save As...'],
    'track_columns': [551, 552, 553, 555, 560, 561, 567, 568],
    'drum_columns': [651, 652, 653, 654, 655, 656, 657],
    'prefs': {'copy_as_parents': False, 'chord_conflict': True, 'conductor_warning': True,
              'ask_type0': False, 'leave_midi': False, 'number_from_1': False, 'single_edit': False,
              'timer_ms': 1, 'dbl_midi': 'Piano Roll', 'dbl_audio': 'Audio Window',
              'bg_track': 'None', 'bg_program': 'None', 'kbd_velocity': 100},
    'show_transport': True, 'show_editors': True, 'show_fast': True, 'show_time': True,
    'cap_transport': False, 'cap_editors': False, 'cap_fast': False,
    'mixer': {'users': [[93, 0, 0, 127], [91, 0, 0, 127]], 'under': 2, 'midi_in': False, 'song_data': True,
              'record': True, 'volumes_only': False},
    'drum_kit': 'GM.DRM', 'recent_dir': '',
    'score': {'left': 4, 'right': 4, 'top': 4, 'bottom': 4, 'internote': 11, 'interstave': 53,
              'title': 18, 'names': 11, 'clef': 0, 'split': 60, 'auto': True, 'pagenums': True,
              'maxstaves': 12, 'beam_screen': True, 'beam_printer': True, 'barnums': True,
              'simplify': True, 'lyric_ch': 4},
}


def load_settings():
    s = json.loads(json.dumps(DEFAULT_SETTINGS))
    try:
        with open(SETTINGS) as f:
            data = json.load(f)
        for k, v in data.items():
            if isinstance(v, dict) and isinstance(s.get(k), dict):
                s[k].update(v)
            else:
                s[k] = v
    except (OSError, ValueError):
        pass
    pr = s['prefs']
    if not pr.get('bg_plain_default'):
        # textured backgrounds are slow to repaint (a CPU core on macOS while playing): plain grey
        # is the default, set once for settings saved before; textures can be chosen in Preferences
        pr['bg_track'] = pr['bg_program'] = 'None'
        pr['bg_plain_default'] = True
    return s


def auto_scale(root):
    h = root.winfo_screenheight()
    return 1 if h < 1400 else 2


FONTCONF = '''<?xml version="1.0"?>
<!DOCTYPE fontconfig SYSTEM "fonts.dtd">
<fontconfig>
  <include ignore_missing="yes">/etc/fonts/fonts.conf</include>
  <match target="font">
    <edit name="antialias" mode="assign"><bool>false</bool></edit>
    <edit name="hinting" mode="assign"><bool>true</bool></edit>
    <edit name="hintstyle" mode="assign"><const>hintfull</const></edit>
    <edit name="rgba" mode="assign"><const>none</const></edit>
  </match>
</fontconfig>
'''


def _read(p):
    with open(p) as f:
        return f.read()


def light_appearance(root):
    """Draw in the light Windows 95 colours whatever the desktop's theme.  On macOS in dark
    mode Tk would otherwise give text and entry fields the system's dark-mode colours."""
    for k, v in (('*foreground', ui.TEXT), ('*disabledForeground', '#808080'),
                 ('*Entry.background', ui.WINDOW), ('*Listbox.background', ui.WINDOW),
                 ('*Text.background', ui.WINDOW), ('*insertBackground', ui.TEXT),
                 ('*selectBackground', '#000080'), ('*selectForeground', '#ffffff'),
                 ('*highlightBackground', ui.FACE), ('*Menu.background', ui.FACE),
                 ('*Menu.activeBackground', '#000080'), ('*Menu.activeForeground', '#ffffff')):
        root.option_add(k, v)
    # macOS: the built app is kept in light mode by NSRequiresAquaSystemAppearance (build.py).
    # Tk's MacWindowStyle appearance command is not used: it crashed Tk at times.


def crisp_fonts():
    """On X11, draw text without antialiasing (like Windows 95) through a private fontconfig file.
    Must run before Tk starts; set SSGOLD_ANTIALIAS=1 to keep the desktop's smoothing."""
    if not sys.platform.startswith('linux') or os.environ.get('FONTCONFIG_FILE') \
            or os.environ.get('SSGOLD_ANTIALIAS') == '1' or not os.path.exists('/etc/fonts/fonts.conf'):
        return
    try:
        d = os.path.join(os.path.expanduser('~'), '.cache', 'ssgold')
        os.makedirs(d, exist_ok=True)
        p = os.path.join(d, 'fonts.conf')
        if not os.path.exists(p) or _read(p) != FONTCONF:
            with open(p, 'w') as f:
                f.write(FONTCONF)
        os.environ['FONTCONFIG_FILE'] = p
    except OSError:
        pass


class App(tk.Tk):
    def __init__(self, scale=None, path=None):
        crisp_fonts()
        super().__init__(className='SoundStudioGold')
        self.withdraw()
        self.settings = load_settings()
        sc = scale or self.settings.get('scale') or auto_scale(self)
        ui.set_scale(self, sc)
        self.images = Images(self, sc)
        self.title('Sound Studio Gold')
        self.configure(bg=ui.FACE)
        light_appearance(self)
        try:
            self.iconphoto(True, self.images.icon('IC_ABOUT'))
        except tk.TclError:
            pass
        # engine
        self.midi = MidiIO()
        self.midi.open_outputs(self.settings['outputs'])
        self.midi.open_inputs(self.settings['inputs'])
        self.seq = Sequencer(self.midi, self)
        self.midi.on_input = self._midi_in
        self.patches = PatchManager()
        for port, mode in self.settings['port_modes'].items():
            self.patches.set_mode(int(port), mode)
        self.drumkit = DrumKit(resources.path('drums', self.settings.get('drum_kit', 'GM.DRM'))
                               if os.path.exists(resources.path('drums', self.settings.get('drum_kit', 'GM.DRM')))
                               else resources.path('drums', 'GM.DRM'))
        self.clipboard = None
        self.undo_stack = []
        self.redo_stack = []
        self.chord_name = ''
        self.song = new_song(self.port_names())
        self.tmap = TimeMap(self.song)
        self.seq.set_song(self.song)
        from .chords import ChordPlayer
        self.seq.chord_player = ChordPlayer()
        # windows
        self._build_menu()
        self.client = MDIClient(self, self)
        self.client.pack(fill='both', expand=True)
        self.windows = {}
        from . import panels
        self.transport = panels.Transport(self.client, self)
        self.editors = panels.Editors(self.client, self)
        self.fastmenu = panels.FastMenu(self.client, self)
        self.bigtime = panels.BigTime(self.client, self)
        self._bind_keys()
        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        w, h = min(sw - 40, ui.s(1024)), min(sh - 80, ui.s(740))
        self.geometry('%dx%d+%d+%d' % (w, h, max(0, (sw - w) // 2), max(0, (sh - h) // 3)))
        self.protocol('WM_DELETE_WINDOW', self.quit_app)
        self._mac_app_menu()
        self.set_backgrounds()
        self.deiconify()
        self.update_idletasks()
        self.layout_panels()
        self.open_track_window()
        try:
            self.state('zoomed')
        except tk.TclError:
            try:
                self.attributes('-zoomed', True)
            except tk.TclError:
                pass
        if path:
            self.after(50, lambda: self.open_path(path))
        self._last_pos = None
        self._from_threads = collections.deque()   # work queued by the MIDI and playback threads
        self.after(30, self._poll)

    # ------------------------------------------------------------------ settings
    def save_settings(self):
        try:
            with open(SETTINGS, 'w') as f:
                json.dump(self.settings, f, indent=1)
        except OSError:
            pass

    def port_names(self):
        labels = self.midi.port_labels()
        return labels

    def fps(self):
        return {24: 24, 25: 25, 29: 30, 30: 30}.get(self.song.frame_format, 25)

    # 'BD%02d' % (1-based position in the alphabetically sorted name list) - see sub_28_26b6
    BACKGROUNDS = {n: 'BD%02d' % (i + 1) for i, n in
                   enumerate(sorted(resources.string(864 + i) for i in range(25)))}


    PLAIN_PROGRAM = '#848284'   # the 'None' backgrounds: dark and light grey
    PLAIN_TRACK = '#c6c3c6'

    def set_backgrounds(self):
        bg = self.settings['prefs'].get('bg_program')
        if bg in self.BACKGROUNDS:
            self.client.configure(bg=ui.DESKTOP)
            self.client.set_background(self.images.get(self.BACKGROUNDS[bg]))
        else:
            self.client.set_background(None)
            self.client.configure(bg=self.PLAIN_PROGRAM)
        for w in self.client.children_:
            if hasattr(w, 'set_background'):
                w.set_background()

    # ------------------------------------------------------------------ menus
    def _build_menu(self):
        self.menubar = tk.Menu(self, tearoff=0)
        self.menu_items = {}
        self.accels = []

        def build(menu, items):
            for text, mid, flags in items:
                if isinstance(mid, list):
                    sub = tk.Menu(menu, tearoff=0)
                    label, u = self._menu_label(text)
                    menu.add_cascade(label=label, underline=u, menu=sub)
                    build(sub, mid)
                elif not text:
                    menu.add_separator()
                else:
                    lab, acc = (text.split('\t') + [''])[:2]
                    label, u = self._menu_label(lab)
                    menu.add_command(label=label, underline=u, accelerator=acc,
                                     command=lambda m=mid: self.command(m),
                                     state='disabled' if (flags & 1 or mid in self.UNPORTED) else 'normal')
                    self.menu_items[mid] = (menu, menu.index('end'))
        build(self.menubar, resources.res()['menu'])
        self.configure(menu=self.menubar)

    @staticmethod
    def _menu_label(t):
        u = t.find('&')
        return t.replace('&', ''), u

    UNPORTED = {43, 100, 101, 44, 102, 103, 104, 105, 106, 107, 108, 110, 111, 112, 18, 19}

    def set_menu_state(self, mid, enabled):
        m = self.menu_items.get(mid)
        if m:
            m[0].entryconfigure(m[1], state='normal' if enabled else 'disabled')

    def set_menu_label(self, mid, text):
        m = self.menu_items.get(mid)
        if m:
            lab, acc = (text.split('\t') + [''])[:2]
            label, u = self._menu_label(lab)
            m[0].entryconfigure(m[1], label=label, underline=u, accelerator=acc)

    def _bind_keys(self):
        mod = 'Command' if sys.platform == 'darwin' else 'Control'
        keys = {
            '<%s-o>' % mod: 2, '<%s-s>' % mod: 3, '<%s-z>' % mod: 10, '<%s-a>' % mod: 11,
            '<%s-c>' % mod: 12, '<%s-x>' % mod: 13, '<%s-v>' % mod: 14, '<%s-t>' % mod: 20,
            '<%s-h>' % mod: 21, '<%s-l>' % mod: 22, '<%s-u>' % mod: 23, '<%s-j>' % mod: 24,
            '<%s-i>' % mod: 25, '<%s-d>' % mod: 26, '<%s-n>' % mod: 27, '<%s-y>' % mod: 30,
            '<%s-r>' % mod: 31, '<F2>': 80, '<F3>': 81, '<F4>': 82, '<F5>': 83, '<F6>': 84,
            '<F7>': 85, '<F8>': 86, '<F9>': 87, '<F11>': 88, '<F12>': 89, '<Shift-F7>': 90,
            '<Shift-F8>': 91, '<Shift-F9>': 92, '<Shift-F10>': 93, '<Shift-F5>': 49,
            '<Shift-F4>': 50, '<%s-F7>' % mod: 54, '<%s-F8>' % mod: 55, '<%s-F9>' % mod: 56,
            '<F1>': 60, '<Alt-BackSpace>': 10, '<Shift-Alt-BackSpace>': 11, '<%s-Insert>' % mod: 12,
            '<Shift-Delete>': 13, '<Shift-Insert>': 14, '<Delete>': 15,
        }
        for k, cid in keys.items():
            try:
                self.bind_all(k, lambda e, c=cid: self._key_command(e, c))
            except tk.TclError:
                pass
        # transport keys (only when no text field has focus)
        plain = {'<Home>': self.return_to_zero, '<End>': self.go_to_end,
                 '<space>': self.space_key, '<Return>': self.play, '<KP_Enter>': self.play,
                 '<plus>': self.record, '<KP_Add>': self.record,
                 '<Left>': lambda: self.wind(-1, False), '<Right>': lambda: self.wind(1, False),
                 '<Up>': lambda: None, '<Down>': lambda: None}
        for k, fn in plain.items():
            self.bind_all(k, lambda e, f=fn: self._plain_key(e, f))
        for ch, opt in (('m', 'metronome'), ('c', 'cycle'), ('f', 'follow'), ('o', 'conductor'),
                        ('e', 'edit_solo'), ('s', 'sync'), ('p', 'punch')):
            self.bind_all('<KeyPress-%s>' % ch, lambda e, o=opt: self._plain_key(e, lambda: self.toggle_option(o)))
        self.bind_all('<KeyPress-l>', lambda e: self._plain_key(e, lambda: self.locate(self.song.left)))
        self.bind_all('<KeyPress-r>', lambda e: self._plain_key(e, lambda: self.locate(self.song.right)))
        self.bind_all('<KeyPress-q>', lambda e: self._plain_key(e, self.quick_quantize))

    def _typing(self, ev):
        w = ev.widget
        return isinstance(w, (tk.Entry, tk.Text, tk.Spinbox, tk.Listbox))

    def _key_command(self, ev, cid):
        if cid in (12, 13, 14, 15, 11, 10) and self._typing(ev):
            return
        self.command(cid)
        return 'break'

    def _plain_key(self, ev, fn):
        if self._typing(ev) or (ev.state & 0x4):
            return
        w = self.client.active
        if w is not None and hasattr(w, 'key') and w.key(ev):
            return 'break'
        fn()
        return 'break'

    # ------------------------------------------------------------------ dispatch
    def command(self, cid):
        from . import commands
        commands.run(self, cid)

    def fast_command(self, name):
        cid = FAST_IDS.get(name)
        if cid:
            self.command(cid)

    # ------------------------------------------------------------------ panels
    def layout_panels(self):
        self.update_idletasks()
        cl = self.client

        def size():
            return cl.winfo_width() // ui.S, cl.winfo_height() // ui.S
        t, e, fm, bt = self.transport, self.editors, self.fastmenu, self.bigtime
        st = self.settings
        ew = e.w if st.get('show_editors', True) else 0
        cl.reserved_right = ew
        t.rel = lambda: t.place_at(max(0, (size()[0] - ew - t.w) // 2), size()[1] - t.size()[1])
        e.rel = lambda: e.place_at(size()[0] - e.w, 0)
        fm.rel = lambda: fm.place_at(size()[0] - fm.w - ew - 2, size()[1] - fm.size()[1])
        bt.rel = lambda: bt.place_at(size()[0] - bt.w - ew - 26, 0)
        for p, key, cap in ((t, 'show_transport', 'cap_transport'), (e, 'show_editors', 'cap_editors'),
                            (fm, 'show_fast', 'cap_fast'), (bt, 'show_time', 'cap_time')):
            p.has_caption = st.get(cap, False)
            if st.get(key, True):
                p.set_caption(p.has_caption)
                p.rel()
            else:
                p.place_forget()
        for c in cl.children_:
            if c.state == 'max':
                c.maximize(force=True)
        self._update_window_menu()

    def toggle_panel(self, key):
        self.settings[key] = not self.settings.get(key, True)
        self.layout_panels()

    def toggle_caption(self, panel, key):
        self.settings[key] = not self.settings.get(key, False)
        panel.set_caption(self.settings[key])

    def _update_window_menu(self):
        st = self.settings
        self.set_menu_label(54, resources.string(803 if st.get('show_transport', True) else 804))
        self.set_menu_label(55, resources.string(805 if st.get('show_editors', True) else 806))
        self.set_menu_label(56, resources.string(807 if st.get('show_fast', True) else 808))

    def floating_menu(self, panel, ev):
        """Right-click on a tool window: Move / Hide / Toggle Caption (strings 800-802)."""
        from .widgets import PopupMenu
        keys = {self.transport: ('show_transport', 'cap_transport'), self.editors: ('show_editors', 'cap_editors'),
                self.fastmenu: ('show_fast', 'cap_fast'), self.bigtime: ('show_time', 'cap_time')}
        show, cap = keys[panel]
        PopupMenu.show(self, [(resources.string(800), panel.start_move),
                              (resources.string(801), lambda: self.toggle_panel(show)),
                              (resources.string(802), lambda: self.toggle_caption(panel, cap))],
                       ev.x_root, ev.y_root)

    # ------------------------------------------------------------------ windows
    def open_track_window(self):
        from .trackwin import TrackWindow
        w = self.windows.get('track')
        if w is None or not w.winfo_exists():
            w = TrackWindow(self.client, self)
            self.windows['track'] = w
        if w.state == 'min':
            w.restore()
        self.client.activate(w)
        return w

    def small_icon(self, name):
        """16x16 caption icon (pre-reduced from the 32x32 IC_* icon by tools/extract_assets.py)."""
        return self.images.icon(name + '_SM')

    def on_child_activated(self, child):
        pass

    def all_windows(self):
        return list(self.client.children_)

    # ------------------------------------------------------------------ song changes
    def checkpoint(self):
        """Record the song for Undo before an edit."""
        self.undo_stack.append(self.song.to_bytes())
        if len(self.undo_stack) > 30:
            self.undo_stack.pop(0)
        self.redo_stack.clear()
        self.song.modified = True

    def _swap_song(self, data):
        path, modified = self.song.path, True
        locs = self._window_refs()
        self.song = Song.from_bytes(data)
        self.song.path = path
        self.song.modified = modified
        self.seq.song = self.song
        self._restore_window_refs(locs)
        self.song_changed()

    def undo(self):
        if not self.undo_stack:
            return
        self.redo_stack.append(self.song.to_bytes())
        self._swap_song(self.undo_stack.pop())

    def redo(self):
        if not self.redo_stack:
            return
        self.undo_stack.append(self.song.to_bytes())
        self._swap_song(self.redo_stack.pop())

    def pattern_ref(self, p):
        for ti, t in enumerate(self.song.tracks):
            for pi, q in enumerate(t.patterns):
                if q is p:
                    return ti, pi
        return None

    def pattern_at(self, ref):
        if ref is None:
            return None
        ti, pi = ref
        try:
            return self.song.tracks[ti].patterns[pi]
        except IndexError:
            return None

    def _window_refs(self):
        return [(w, self.pattern_ref(getattr(w, 'pattern', None))) for w in self.client.children_]

    def _restore_window_refs(self, refs):
        for w, ref in refs:
            if hasattr(w, 'rebind'):
                w.rebind(self.pattern_at(ref))

    def song_changed(self, what=None):
        self.tmap = TimeMap(self.song)
        if what not in ('mixer',):                 # mute / solo are checked as the song plays
            self.seq.song_edited()
        for w in list(self.client.children_):
            if hasattr(w, 'refresh'):
                try:
                    w.refresh(what)
                except tk.TclError:
                    pass
        self.transport.update_values(force=True)
        self.set_menu_state(10, bool(self.undo_stack))
        self.set_menu_state(11, bool(self.redo_stack))

    def set_song(self, song):
        self.seq.stop()
        self.song = song
        self.__dict__.pop('mixer_state', None)      # the Mixer starts from the new song's settings
        self.seq.set_song(song)
        self.undo_stack.clear()
        self.redo_stack.clear()
        self.tmap = TimeMap(song)
        for w in list(self.client.children_):
            if w is not self.windows.get('track'):
                w.close()
        tw = self.open_track_window()
        tw.new_song()
        self.song_changed()
        self.update_title()
        if song.notepad.strip():
            from .editors import open_single
            open_single(self, 'notepad')

    def update_title(self):
        tw = self.windows.get('track')
        if tw:
            tw.set_title('Track - %s' % self.song_name())

    def song_name(self):
        return os.path.basename(self.song.path).upper() if self.song.path else resources.res()['strings'].get('', '(Untitled)') or '(Untitled)'

    # ------------------------------------------------------------------ files
    def confirm_discard(self):
        if not self.song.modified:
            return True
        r = messagebox.askyesnocancel('Sound Studio Gold', resources.string(818) % self.song_name(), parent=self)
        if r is None:
            return False
        if r:
            return self.save_song()
        return True

    def new_song(self):
        if not self.confirm_discard():
            return
        self.set_song(new_song(self.port_names()))

    def open_path(self, path):
        from .dialogs import file_kind
        ext = file_kind(path).lower()
        try:
            if ext == '.mid':
                song = smf.read_smf(path, self)
                song.path = None
                self.set_song(song)
            elif ext == '.drm':
                self.drumkit = DrumKit(path)
                self.song_changed('drums')
                return
            elif ext == '.pls':
                self.patches.add(path)
                self.song_changed()
                return
            elif ext == '.pat':
                self.insert_pattern_file(path)
                return
            else:
                song = Song.load(path)
                self.set_song(song)
        except (OSError, SongError, ValueError) as e:
            messagebox.showerror('Sound Studio Gold', str(e), parent=self)
            return
        self.settings['recent_dir'] = os.path.dirname(path)

    def insert_pattern_file(self, path):
        """Open a .PAT: the pattern goes on the current track at the bar of the play position."""
        p = load_pattern(path)
        tw = self.windows.get('track')
        t = tw.current_track() if tw is not None else None
        if t is None or t.kind != MIDI:
            t = next((x for x in self.song.tracks if x.kind == MIDI), None)
        if t is None:
            return
        self.checkpoint()
        start = self.tmap.bar_tick(self.seq.position)
        length = p.end
        p.start, p.end = start, start + length
        p.track = t
        for q in self.song.all_patterns():
            q.selected = False
        p.selected = True
        t.patterns.append(p)
        t.patterns.sort(key=lambda q: q.start)
        self.song_changed('patterns')

    def open_dialog(self, kind='open'):
        from .dialogs import open_file_dialog
        return open_file_dialog(self, kind)

    def save_song(self):
        if not self.song.path:
            return self.save_as()
        try:
            self.song.save()
        except OSError:
            messagebox.showerror('Sound Studio Gold', resources.string(26) % self.song.path, parent=self)
            return False
        self.update_title()
        return True

    def save_as(self):
        from .dialogs import save_file_dialog
        res = save_file_dialog(self)
        if not res:
            return False
        path, kind = res
        try:
            if kind == '.MID':
                smf.write_smf(self.song, path, self)
            elif kind == '.DRM':
                self.drumkit.save(path)
            elif kind == '.PAT':
                pats = [q for q in self.song.all_patterns() if q.selected and q.track.kind == MIDI]
                if not pats:
                    messagebox.showinfo('Sound Studio Gold', resources.string(16), parent=self)
                    return False
                save_pattern(pats[0], path)
                return True
            else:
                self.song.save(path)
        except OSError:
            messagebox.showerror('Sound Studio Gold', resources.string(26) % path, parent=self)
            return False
        self.update_title()
        return True

    def merge(self, midi=False):
        from .dialogs import OPEN_TYPES, file_kind
        types = [OPEN_TYPES[2] if midi else OPEN_TYPES[1], OPEN_TYPES[0], OPEN_TYPES[-1]]
        path = filedialog.askopenfilename(parent=self, title='Merge File', initialdir=self.settings.get('recent_dir') or None,
                                          filetypes=types)
        if not path:
            return
        try:
            other = smf.read_smf(path, self) if file_kind(path) == '.MID' else Song.load(path)
        except (OSError, SongError, ValueError) as e:
            messagebox.showerror('Sound Studio Gold', str(e), parent=self)
            return
        self.checkpoint()
        free = 256 - len(self.song.tracks)
        if len([t for t in other.tracks if t.patterns]) > free:
            messagebox.showerror('Sound Studio Gold', resources.string(21) % os.path.basename(path), parent=self)
            return
        for t in other.tracks:
            if t.patterns:
                self.song.tracks.append(t)
        self.song_changed()

    def _mac_app_menu(self):
        """macOS: the application menu's About and Settings items open the program's own
        About and Preferences dialogs; Quit and files dropped on the Dock icon work too."""
        if sys.platform != 'darwin':
            return

        def open_docs(*paths):
            from .dialogs import file_kind
            for p in paths[:1]:
                if file_kind(p) not in ('.SNG', '.MID') or self.confirm_discard():
                    self.open_path(p)
        for name, fn in (('tkAboutDialog', lambda: self.command(65)),
                         ('::tk::mac::ShowPreferences', lambda: self.command(36)),
                         ('::tk::mac::Quit', self.quit_app),
                         ('::tk::mac::OpenDocument', open_docs)):
            try:
                self.createcommand(name, fn)
            except tk.TclError:
                pass

    def quit_app(self):
        if not self.confirm_discard():
            return
        self.seq.stop()
        self.midi.all_notes_off()
        self.midi.close()
        self.save_settings()
        self.destroy()

    # ------------------------------------------------------------------ transport
    def play(self):
        if self.seq.playing:
            return
        self.seq.solo_patterns = self._edit_solo_set()
        self.seq.play(False)
        self.transport.redraw_buttons()

    def record(self):
        if self.seq.playing:
            return
        tw = self.windows.get('track')
        rec = [t for t in self.song.tracks if t.rec]
        if not rec:
            messagebox.showinfo('Sound Studio Gold', resources.string(9), parent=self)
            return
        self.seq.solo_patterns = None
        self.seq.play(True)
        self.transport.redraw_buttons()

    def stop(self):
        if self.seq.playing:
            rec = self.seq.recording
            end = self.seq.position
            self.seq.stop()
            if rec:
                from .editors.keyboard import finish_sfc_recording
                if getattr(self, 'sfc_record', None):
                    self.checkpoint()
                    if finish_sfc_recording(self, end):
                        self.song_changed('patterns')
                self._finish_recording()
        else:
            self.seq.position = 0 if self.seq.position == self.seq.last_start else self.seq.last_start
        self.transport.redraw_buttons()
        self.transport.update_values()

    def on_sequencer_stopped(self):
        if self.seq.recording and self.seq.recorded:
            self._finish_recording()
        self.transport.redraw_buttons()

    def _finish_recording(self):
        from .sequencer import build_recorded_pattern
        data = self.seq.recorded
        self.seq.recorded = []
        tracks = [t for t in self.song.tracks if t.rec and t.kind == MIDI]
        if not data or not tracks:
            return
        self.checkpoint()
        for t in tracks:
            if self.seq.opts.multitrack and t.channel:
                msgs = [(tk_, d) for tk_, d in data if d[0] >= 0xF0 or (d[0] & 0x0F) + 1 == t.channel]
            else:
                msgs = data
            p = build_recorded_pattern(self.song, t, msgs)
            if not p:
                continue
            if self.seq.opts.record_mode == 0:
                for q in list(t.patterns):
                    if q.start < p.end and q.end > p.start:
                        t.patterns.remove(q)
            p.track = t
            p.selected = True
            t.patterns.append(p)
            t.patterns.sort(key=lambda q: q.start)
        self.song_changed()

    def space_key(self):
        w = self.client.active
        if w is not None and getattr(w, 'step_mode', False) and hasattr(w, 'step_rest'):
            w.step_rest()
            return
        if self.seq.playing:
            self.stop()
        else:
            self.stop()

    def return_to_zero(self):
        self.locate(0)

    def go_to_end(self):
        self.locate(self.song.end_tick())

    def locate(self, tick):
        self.seq.locate(max(0, tick))
        self.transport.update_values()
        self._follow(force=True)

    def wind(self, direction, big):
        step = self.tmap.sig_at(self.seq.position)[2] * (4 if big else 1)
        self.locate(self.seq.position + direction * step)

    def toggle_option(self, key):
        o = self.seq.opts
        setattr(o, key, not getattr(o, key))
        if key == 'multitrack':
            pass
        self.transport.redraw_buttons()
        self.transport.update_values()

    def adjust_transport(self, key, d, big):
        song = self.song
        tm = self.tmap
        if key in ('Position', 'Left Locator', 'Right Locator', 'Time'):
            cur = {'Position': self.seq.position, 'Left Locator': song.left,
                   'Right Locator': song.right, 'Time': self.seq.position}[key]
            step = tm.sig_at(cur)[2] if big else tm.sig_at(cur)[3]
            v = max(0, cur + d // (10 if big else 1) * step)
            if key == 'Left Locator':
                song.left = v
            elif key == 'Right Locator':
                song.right = v
            else:
                self.locate(v)
            self.song_changed('locators')
        elif key == 'Tempo':
            o = self.seq.opts
            if o.conductor:
                from .song import COND_TEMPO
                p = song.conductor.of(COND_TEMPO)[0]
                p.value = max(20, min(250, p.value + d))
                self.song_changed('conductor')
            else:
                o.fixed_tempo = max(20, min(250, o.fixed_tempo + d))
            self.transport.update_values()

    def _edit_solo_set(self):
        if not self.seq.opts.edit_solo:
            return None
        w = self.client.active
        p = getattr(w, 'pattern', None)
        return {p.source} if p is not None else None

    def quick_quantize(self):
        from . import commands
        commands.quantize_now(self)

    def send_track_settings(self, t, key=None):
        """Changing a track column sends the new value at once (as the original does)."""
        from .sequencer import initial_messages
        if t.kind != MIDI:
            return
        from .sequencer import track_channel
        msgs = initial_messages(t, track_channel(t))
        if key is not None:
            cc = {'volume': 7, 'pan': 10, 'reverb': 91, 'chorus': 93}.get(key)
            if cc is not None:
                msgs = [m for m in msgs if m[0] & 0xF0 == 0xB0 and m[1] == cc]
            elif key in ('prog', 'bank'):
                msgs = [m for m in msgs if m[0] & 0xF0 == 0xC0 or (m[0] & 0xF0 == 0xB0 and m[1] in (0, 32))]
            else:
                msgs = []
        for m in msgs:
            self.midi.send(max(0, t.port), m)
            self.seq.out_log.append((self.midi.real_port(max(0, t.port)), m))      # the Mixer follows

    # ------------------------------------------------------------------ MIDI input
    def _midi_in(self, data):
        self.seq.midi_in(data)
        o = self.seq.opts
        st = data[0]
        if not self.seq.playing or not self.seq.recording or True:
            if o.thru_channel and st < 0xF0:
                rec = next((t for t in self.song.tracks if t.rec and t.kind == MIDI), None)
                out = bytearray(data)
                port = 0
                if rec is not None:
                    port = max(0, rec.port)
                    if rec.channel and not o.multitrack:
                        out[0] = (st & 0xF0) | (rec.channel - 1)
                self.midi.send(port, bytes(out))
        if st >= 0xF8:          # clock / active sensing: nothing to show, and they arrive constantly
            return
        # Tk may only be used from the main thread (macOS crashes otherwise): _poll runs this
        self._from_threads.append(lambda d=bytes(data): self._midi_in_gui(d))

    def _midi_in_gui(self, data):
        from .chords import detect_input
        name = detect_input(self, data)
        if name is not None:
            self.chord_name = name
            self.transport.update_values()
        for w in self.client.children_:
            if hasattr(w, 'midi_in'):
                w.midi_in(data)

    # ------------------------------------------------------------------ poll
    def thread_call(self, fn):
        """Run fn on the GUI thread at the next poll (safe to call from any thread)."""
        self._from_threads.append(fn)

    def _poll(self):
        try:
            q = self._from_threads
            while q:
                try:
                    q.popleft()()
                except Exception:
                    import traceback
                    traceback.print_exc()
            pos = self.seq.position
            now = time.perf_counter()
            if pos != self._last_pos and now - getattr(self, '_last_draw', 0) >= self.update_ms() / 1000.0:
                self._last_draw = now
                self._last_pos = pos
                if not ui.diag('noupdate'):
                    if not ui.diag('notransport'):
                        self._timed('Transport boxes', self.transport.update_values)
                        self._timed('Big time display',
                                    lambda: self.bigtime.set(smpte(self.tmap.to_ms(pos), self.fps(),
                                                                   self.song.smpte_start)))
                    if not ui.diag('nofollow'):
                        self._follow()
            if not self.seq.playing and self.transport.values.get('playing'):
                self.transport.redraw_buttons()
            self.transport.values['playing'] = self.seq.playing
        finally:
            self.after(8, self._poll)          # often enough for 60 fps Screen Updates

    def update_ms(self):
        """Preferences' Screen Updates: the interval the play position is redrawn at (milliseconds)."""
        from .dialogs import screen_fps
        return 1000.0 / screen_fps(self.settings['prefs'])

    def _follow(self, force=False):
        for w in self.client.children_:
            if hasattr(w, 'set_position'):
                self._timed('%s: play position' % type(w).__name__,
                            lambda w=w: w.set_position(self.seq.position,
                                                       follow=self.seq.opts.follow and (self.seq.playing or force)))

    timings = None              # run.py --profile: {label: [calls, seconds]}

    def _timed(self, label, fn):
        """Run fn; when profiling, also draw at once and record how long that took."""
        if self.timings is None:
            return fn()
        t0 = time.perf_counter()
        r = fn()
        self.update_idletasks()
        rec = self.timings.setdefault(label, [0, 0.0])
        rec[0] += 1
        rec[1] += time.perf_counter() - t0
        return r

    def run(self):
        self.mainloop()
