#!/usr/bin/env python3
"""Sound Studio Gold - Python/Tkinter port of Evolution Electronics' MIDI sequencer."""
import argparse
import os

from ssgold.app import App


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('file', nargs='?', help='song (.SNG) or MIDI file (.MID) to open')
    ap.add_argument('--scale', type=int, choices=(1, 2, 3), help='pixel zoom for this run')
    ap.add_argument('--profile', action='store_true',
                    help='record where the time goes; the report is written to ~/ssgold-profile.txt on quit')
    args = ap.parse_args()
    if args.profile or os.environ.get('SSGOLD_PROFILE'):
        return profiled(args)
    App(scale=args.scale, path=args.file).run()


def profiled(args):
    """Run with cProfile on the main (drawing) thread and the playback thread."""
    import cProfile
    import io
    import pstats
    import time
    from ssgold import sequencer

    seq_prof = cProfile.Profile()
    run = sequencer.Sequencer._run

    def profiled_run(self):
        seq_prof.enable()
        try:
            run(self)
        finally:
            seq_prof.disable()
    sequencer.Sequencer._run = profiled_run
    main_prof = cProfile.Profile()
    t0 = time.time()
    main_prof.enable()
    try:
        App(scale=args.scale, path=args.file).run()
    finally:
        main_prof.disable()
        cpu = time.process_time()          # the whole process, both threads
        secs = time.time() - t0
        out = io.StringIO()
        out.write('Ran %.0f s, CPU %.1f s (%.0f%% of one core)\n\n' % (secs, cpu, 100 * cpu / max(1, secs)))
        for name, prof in (('MAIN THREAD (windows, drawing)', main_prof), ('PLAYBACK THREAD', seq_prof)):
            out.write('==== %s ====\n' % name)
            try:
                st = pstats.Stats(prof, stream=out)
                st.sort_stats('tottime').print_stats(30)
                st.sort_stats('cumulative').print_stats(30)
            except TypeError:
                out.write('(no samples)\n')
        path = os.path.expanduser('~/ssgold-profile.txt')
        with open(path, 'w') as f:
            f.write(out.getvalue())
        print('Profile written to', path)


if __name__ == '__main__':
    main()
