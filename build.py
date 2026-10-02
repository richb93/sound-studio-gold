#!/usr/bin/env python3
"""Build a stand-alone Sound Studio Gold program with PyInstaller.

    python build.py              # one folder:  dist/SoundStudioGold/
    python build.py --onefile    # single file: dist/SoundStudioGold(.exe)
    python build.py --test       # run the tests first

PyInstaller and the MIDI libraries are installed if they are missing.  When the Python
running this is not a virtual environment (Homebrew's and many Linux distributions' Pythons
refuse pip installs), a private one is made in .build-venv/ and the build runs from there.
"""
import argparse
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
NAME = 'SoundStudioGold'
VENV = os.path.join(HERE, '.build-venv')
NEEDED = [('PyInstaller', 'pyinstaller', True), ('mido', 'mido', True),
          ('rtmidi', 'python-rtmidi', False), ('PIL', 'pillow', False)]   # (module, package, required)


def have(module):
    try:
        __import__(module)
        return True
    except ImportError:
        return False


def in_venv():
    return sys.prefix != getattr(sys, 'base_prefix', sys.prefix)


def check_tk():
    if have('tkinter'):
        return
    v = '%d.%d' % sys.version_info[:2]
    hint = ('brew install python-tk@%s' % v if sys.platform == 'darwin'
            else 'install your distribution\'s python3-tk package' if sys.platform.startswith('linux')
            else 'reinstall Python with the "tcl/tk" option ticked')
    sys.exit('This Python (%s) has no Tkinter, which the program needs.\nFix: %s' % (sys.executable, hint))


def venv_python():
    if sys.platform == 'win32':
        return os.path.join(VENV, 'Scripts', 'python.exe')
    return os.path.join(VENV, 'bin', 'python')


def ensure_packages():
    """Install whatever is missing; returns False if a required package could not be installed."""
    ok = True
    for module, package, required in NEEDED:
        if have(module):
            continue
        print('Installing', package, '...')
        r = subprocess.call([sys.executable, '-m', 'pip', 'install', '--upgrade', package])
        if r != 0:
            if required:
                print('Could not install %s.' % package)
                ok = False
            else:
                print('Warning: could not install %s; building without it%s.' % (
                    package, ' (the program will have no MIDI ports)' if module == 'rtmidi' else ''))
    return ok


def bootstrap():
    """Make sure the build has what it needs, re-running inside .build-venv/ if necessary."""
    check_tk()
    if all(have(m) for m, _p, req in NEEDED if req):
        ensure_packages()        # optional extras, best effort
        return
    if not in_venv():
        if not os.path.exists(venv_python()):
            print('Creating a virtual environment for the build in', VENV)
            import venv
            venv.create(VENV, with_pip=True)
        print('Re-running the build with', venv_python())
        sys.exit(subprocess.call([venv_python(), os.path.abspath(__file__)] + sys.argv[1:]))
    if not ensure_packages():
        sys.exit(1)


def make_icon(build_dir):
    """Turn the original's 'e' icon into the platform's icon format (needs Pillow; optional)."""
    src = os.path.join(HERE, 'ssgold', 'assets', 'icons', 'IC_ABOUT.png')
    try:
        from PIL import Image
    except ImportError:
        return None
    os.makedirs(build_dir, exist_ok=True)
    im = Image.open(src).convert('RGBA')
    if sys.platform == 'win32':
        out = os.path.join(build_dir, 'gold.ico')
        im.resize((64, 64), Image.NEAREST).save(out, sizes=[(16, 16), (32, 32), (64, 64)])
    elif sys.platform == 'darwin':
        out = os.path.join(build_dir, 'gold.icns')
        im.resize((256, 256), Image.NEAREST).save(out)
    else:
        return None
    return out


def mac_plist(path):
    """App name and Retina support.  (Not forced into light mode: the program sets its own text
    and field colours, so it reads correctly in dark mode too.)"""
    import plistlib
    if not os.path.exists(path):
        return
    with open(path, 'rb') as f:
        pl = plistlib.load(f)
    pl['NSHighResolutionCapable'] = True
    pl['CFBundleName'] = pl['CFBundleDisplayName'] = 'Sound Studio Gold'
    with open(path, 'wb') as f:
        plistlib.dump(pl, f)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--onefile', action='store_true', help='build a single executable')
    ap.add_argument('--test', action='store_true', help='run the unit tests before building')
    args = ap.parse_args()
    os.chdir(HERE)

    bootstrap()

    if args.test:
        subprocess.check_call([sys.executable, '-m', 'unittest', 'discover', 'tests'])

    sep = ';' if sys.platform == 'win32' else ':'
    cmd = [sys.executable, '-m', 'PyInstaller', '--noconfirm', '--clean', '--windowed', '--name', NAME,
           '--add-data', os.path.join('ssgold', 'assets') + sep + os.path.join('ssgold', 'assets'),
           '--collect-submodules', 'ssgold',          # editors are imported on demand
           '--hidden-import', 'mido.backends.rtmidi',
           '--onefile' if args.onefile else '--onedir']
    icon = make_icon(os.path.join(HERE, 'build'))
    if icon:
        cmd += ['--icon', icon]
    cmd.append('run.py')
    print(' '.join(cmd))
    subprocess.check_call(cmd)

    if sys.platform == 'darwin' and not args.onefile:
        mac_plist(os.path.join('dist', NAME + '.app', 'Contents', 'Info.plist'))

    if args.onefile:
        out = os.path.join('dist', NAME + ('.exe' if sys.platform == 'win32' else ''))
    elif sys.platform == 'darwin':
        out = os.path.join('dist', NAME + '.app')
    else:
        out = os.path.join('dist', NAME)
    print('\nBuilt:', os.path.abspath(out))


if __name__ == '__main__':
    main()
