#!/usr/bin/env python3
"""Build a stand-alone Sound Studio Gold program with PyInstaller.

    python build.py              # one folder:  dist/SoundStudioGold/
    python build.py --onefile    # single file: dist/SoundStudioGold(.exe)
    python build.py --test       # run the tests first

Installs the requirements and PyInstaller into the current Python if they are missing.
"""
import argparse
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
NAME = 'SoundStudioGold'


def pip(*pkgs):
    subprocess.check_call([sys.executable, '-m', 'pip', 'install', '--upgrade', *pkgs])


def ensure(module, package):
    try:
        __import__(module)
    except ImportError:
        pip(package)


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


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--onefile', action='store_true', help='build a single executable')
    ap.add_argument('--test', action='store_true', help='run the unit tests before building')
    args = ap.parse_args()
    os.chdir(HERE)

    ensure('PyInstaller', 'pyinstaller')
    ensure('mido', 'mido')
    ensure('rtmidi', 'python-rtmidi')

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

    if args.onefile:
        out = os.path.join('dist', NAME + ('.exe' if sys.platform == 'win32' else ''))
    elif sys.platform == 'darwin':
        out = os.path.join('dist', NAME + '.app')
    else:
        out = os.path.join('dist', NAME)
    print('\nBuilt:', os.path.abspath(out))


if __name__ == '__main__':
    main()
