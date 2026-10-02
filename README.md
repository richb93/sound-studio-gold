# Sound Studio Gold — Python/Tkinter port

A cross-platform re-creation of **Evolution Sound Studio Gold v4.00** (Evolution Electronics,
1995–97), the 16-bit Windows MIDI sequencer. It aims to be a 1:1 clone of the MIDI sequencing
side of the program: the same windows, dialogs, bitmaps, menus, shortcuts, file formats and
behaviour, written in Python with Tkinter. It runs on Windows, macOS and Linux.

The audio and video parts of the original are **not** ported (see below).

## Running

Requires Python 3.8+ with Tkinter.

```sh
pip install -r requirements.txt      # mido + python-rtmidi, for MIDI in/out
python run.py                        # start with a new song
python run.py song.sng               # open a song or a MIDI file
python run.py --scale 2              # pixel-double everything (high-DPI screens)
```

Without `mido`/`python-rtmidi` the program still runs, but it has no MIDI ports: the Mixer is grey,
as the original's is for a disabled port. Choose MIDI ports in **Options › Devices…**.

Settings (devices, column choices, preferences, window and dialog defaults) are kept in
`~/.ssgold_settings.json`.

On macOS the textured backgrounds are very slow to repaint (Tk copies every pixel each time the
window is redrawn), so there the program starts with plain colours; **Options › Preferences ›
Backgrounds** can switch the textures back on (choose **None** for plain colours on any system).

If the program feels slow, **Options › Preferences › Screen Updates** (the original's Timer
Resolution) sets how often the play position, cursors and meters are redrawn while playing: High,
Medium or Low. Playback timing is not affected. To find out where the time goes, run
`python run.py --profile` (or the built app's executable with `--profile`); a report is written to
`~/ssgold-profile.txt` when you quit. To see which part of the display costs the time, start it with
`SSGOLD_DIAG` set to any of `nobg` (no background textures), `noupdate` (nothing redrawn while
playing), `notransport` (Transport and big time display not updated) or `nofollow` (play position
markers not moved), e.g. `SSGOLD_DIAG=nobg,nofollow ./SoundStudioGold`.

## What is there

Everything in the original's MIDI side, built from the original's own resources (bitmaps, icons,
cursors, menus, accelerators, dialog templates and string table are extracted from `Gold.exe`;
display tables from `Goldlib.dll`; help from `Goldhelp.hlp`):

* **Main window** – MDI workspace with the original backgrounds, the Transport (tape controls,
  toggles, Time/Position/Locators/Tempo/TimeSig/Chord boxes), the Editors strip, the Fast Menu and
  the large time display; floating panels with optional captions; all menus and shortcuts.
* **Track window** – track list with selectable columns, pattern arrangement with Arrow, Pencil,
  Eraser, Mute, Knife and Glue tools, parent/child (ghost) patterns, the chord track, snap,
  multitrack recording, Functions menu (slice, glue, merge, extract, chords to MIDI …), solo memory.
* **Editors** – Piano Roll (with velocity/controller display), Event list (filters, insert types,
  sysex), Score (notation, beaming, lyrics, mouse tools), Drum editor (drum kits, `.DRM` files),
  all with step-time entry, MIDI edit, the information line and Close/Recall.
* **Single windows** – Conductor (tempo, time-signature and key-signature points), Notepad
  (opens automatically when a song has notes), Mixer (16 channels per MIDI output, user knobs,
  fader groups, meters, snapshot, record mixer moves, Audio page), Keyboard (49 keys, Free / Drum /
  Playright / Chord play modes, chord buttons, octave, sustain, PC QWERTY keyboard, Single Finger
  Chord input), Lyrics (karaoke highlighting, Lyric Font), Instant Chord Track.
* **Dialogs** – all of the original's dialogs, laid out from its templates with the Borland
  (BWCC) look: Procedures (Transpose, Velocity, Lengths, Quantize, Move, Timing, Delete, Thin Out),
  Track/Pattern/Drum settings, MIDI Settings, Preferences, Metronome, Mixer Settings, Devices,
  Synchronization, Patch Lists and Routings, Score Settings, Track/Drum Columns, Configure Fast Menu,
  the Open/Save file dialog, About, and the message boxes.
* **Files** – `.SNG` songs (read and written; songs saved here open in the original), Standard MIDI
  Files (types 0 and 1, with the original's type-0 split option), `.PAT` patterns, `.DRM` drum kits
  and `.PLS` patch lists (GM/GS/XG, banks, per-port/channel routings).
* **Sequencer** – playback with chase, cycle, punch, metronome, count-in, conductor on/off,
  auto-return, edit-solo; recording (overdub/replace, multitrack); MIDI thru and input filters;
  GM/GS/XG reset.
* **Help** – the original help file's topics, with links between them.

## Not ported, or different

* **Audio and Video** menus and windows (wave recording/playback, bounce, effects, video) are
  disabled; Audio tracks and patterns are still loaded, shown, edited and saved.
* **Printing** (score printing, Printer Setup) is disabled.
* **Accompaniment**: the 16 styles are the original's own data (decoded from `Gold.exe` and
  `Goldlib.dll`) played by a re-implementation of its accompaniment engine; *Convert to MIDI
  Track* produces the same notes as the original for every style. The chord track is played live,
  so Single Finger Chord on the Keyboard window (Active; Synchro starts the song, Hold keeps the
  chord after you let go) drives the band as in the original. As there, it needs a chord track.
* `.DEF` (definitions) and `.WND` (window layout) files are not opened; settings live in
  `~/.ssgold_settings.json` instead.
* Fonts: MS Sans Serif / System are replaced by the closest installed font (Liberation Sans on
  Linux). On Linux text is drawn without antialiasing, like Windows 95; set `SSGOLD_ANTIALIAS=1` to
  keep the desktop's smoothing.
* Static text in dialogs is drawn on the dialog's grey; under Wine some labels of the original show
  a white background, which is a Win16 colour-message artefact of running it there.

## Repository layout

```
run.py                 start-up
ssgold/                the program
  app.py               main window, menus, settings, transport control, files
  song.py              .SNG model (tracks, patterns, events, conductor, lyrics, notepad)
  sequencer.py         playback / recording thread
  midi_io.py           MIDI ports (mido + python-rtmidi)
  smf.py               Standard MIDI Files
  timing.py            bars/beats/ticks, tempo map, SMPTE
  procedures.py        the Procedures menu
  patches.py           patch lists, drum kits, routings
  chords.py            chord detection
  styles.py            the accompaniment engine (styles data in assets/styles.json)
  bwcc.py dialogs.py   BWCC dialog engine and every dialog
  trackwin.py          Track window
  editors/             Piano Roll, Event, Score, Drum, Conductor, Notepad, Mixer, Keyboard, Lyrics
  panels.py mdi.py widgets.py ui.py tools.py helpviewer.py ict.py patchdlg.py
  assets/              resources extracted from the original program
tools/                 extract_assets.py (NE resource and WinHelp extraction), ne.py, winhelp.py
tests/                 unit tests and a GUI smoke test
```

The assets can be regenerated from an installation of the original program:

```sh
python tools/extract_assets.py /path/to/gold      # folder holding Gold.exe, Goldlib.dll, Goldhelp.hlp
```

## Tests

```sh
python -m unittest discover tests
SSGOLD_SONGS=/path/to/gold python -m unittest discover tests   # also round-trip the original songs
```

The GUI test needs a display (use `xvfb-run` on a headless Linux machine).

## Building a stand-alone program

```sh
python build.py              # dist/SoundStudioGold/  (SoundStudioGold.app on macOS)
python build.py --onefile    # one executable in dist/
python build.py --test       # run the tests first
```

`build.py` installs PyInstaller, mido and python-rtmidi if they are missing. If your Python won't
let pip install into it (Homebrew on macOS, most Linux distributions), it makes a private virtual
environment in `.build-venv/` and builds from there, so `python3 build.py` is all you need. The
Python must include Tkinter: on macOS with Homebrew, `brew install python-tk@3.x` for your
version. Builds are made for the platform you run it on.

Every push also builds Windows, macOS and Linux versions on GitHub Actions
(`.github/workflows/build.yml`): open the run under the repository's **Actions** tab and download
the `SoundStudioGold-Windows` / `-macOS` / `-Linux` artifacts. The macOS build is unsigned, so
the first time right-click the app and choose **Open**.

## Credits

Sound Studio Gold © 1995–1997 Evolution Electronics Ltd. This is an independent re-implementation
for preservation and personal use; the bitmaps, icons, dialog layouts, patch lists, drum kits and
help text in `ssgold/assets` come from the original program.
