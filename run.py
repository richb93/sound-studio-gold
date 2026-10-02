#!/usr/bin/env python3
"""Sound Studio Gold - Python/Tkinter port of Evolution Electronics' MIDI sequencer."""
import argparse

from ssgold.app import App


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('file', nargs='?', help='song (.SNG) or MIDI file (.MID) to open')
    ap.add_argument('--scale', type=int, choices=(1, 2, 3), help='pixel zoom for this run')
    args = ap.parse_args()
    App(scale=args.scale, path=args.file).run()


if __name__ == '__main__':
    main()
