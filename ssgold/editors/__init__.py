"""Editing windows opened from the View menu / Editors strip."""
import importlib

EDITORS = {'proll': ('pianoroll', 'PianoRoll'), 'event': ('eventlist', 'EventWindow'),
           'score': ('score', 'ScoreWindow'), 'drum': ('drum', 'DrumWindow')}
SINGLES = {'conductor': ('conductor', 'ConductorWindow'), 'notepad': ('notepad', 'NotepadWindow'),
           'mixer': ('mixer', 'MixerWindow'), 'keyboard': ('keyboard', 'KeyboardWindow'),
           'lyrics': ('lyrics', 'LyricsWindow'), 'ict': ('ict', 'ICTWindow')}


def _cls(table, kind):
    mod, name = table[kind]
    return getattr(importlib.import_module('ssgold.editors.' + mod), name)


def open_editor(app, kind, pattern):
    """Open (or raise) an editor on a pattern.  'Single Edit Window' reuses one window."""
    cls = _cls(EDITORS, kind)
    single = app.settings['prefs'].get('single_edit')
    for w in app.client.children_:
        if isinstance(w, cls) and w.pattern is not None and w.pattern.source is pattern.source:
            app.client.activate(w)
            return w
        if single and getattr(w, 'is_editor', False):
            w.close()
            break
    w = cls(app.client, app, pattern)
    return w


def open_single(app, kind):
    if kind == 'ict':
        from ..ict import InstantChordTrack
        return InstantChordTrack.open(app)
    cls = _cls(SINGLES, kind)
    for w in app.client.children_:
        if isinstance(w, cls):
            if w.state == 'min':
                w.restore()
            app.client.activate(w)
            return w
    return cls(app.client, app)
