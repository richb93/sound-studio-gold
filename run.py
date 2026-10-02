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
    """Run with a sampling profiler: about 200 times a second it notes what every thread is doing
    (Python allows only one tracing profiler at a time, so cProfile can't watch both threads)."""
    import collections
    import sys
    import threading
    import time

    own = collections.defaultdict(collections.Counter)    # thread -> innermost function: samples
    incl = collections.defaultdict(collections.Counter)   # thread -> any function on the stack
    totals = collections.Counter()
    stop = threading.Event()

    def where(f):
        return '%s (%s:%d)' % (f.f_code.co_name, os.path.basename(f.f_code.co_filename), f.f_lineno)

    def sampler():
        me = threading.get_ident()
        while not stop.wait(0.005):
            names = {t.ident: t.name for t in threading.enumerate()}
            for tid, frame in sys._current_frames().items():
                if tid == me:
                    continue
                name = 'MAIN THREAD (windows, drawing)' if tid == threading.main_thread().ident \
                    else 'THREAD %s' % names.get(tid, tid).split(' ', 1)[-1]
                if 'wait' in frame.f_code.co_name and name != 'MAIN THREAD (windows, drawing)':
                    continue                    # a sleeping playback/MIDI thread: not using the CPU
                totals[name] += 1
                own[name][where(frame)] += 1
                seen = set()
                f = frame
                while f is not None:
                    key = '%s (%s)' % (f.f_code.co_name, os.path.basename(f.f_code.co_filename))
                    if key not in seen:
                        seen.add(key)
                        incl[name][key] += 1
                    f = f.f_back

    th = threading.Thread(target=sampler, daemon=True)
    t0 = time.time()
    c0 = time.process_time()
    th.start()
    App.timings = {}            # time each kind of screen update (see App._timed)
    try:
        App(scale=args.scale, path=args.file).run()
    finally:
        stop.set()
        secs = time.time() - t0
        cpu = time.process_time() - c0           # the whole process, all threads
        lines = ['Ran %.0f s, CPU %.1f s (%.0f%% of one core), %s %s' % (
            secs, cpu, 100 * cpu / max(1, secs), sys.platform, sys.version.split()[0]), '']
        lines.append('==== Screen updates (each followed by drawing it) ====')
        for label, (calls, t) in sorted(App.timings.items(), key=lambda kv: -kv[1][1]):
            lines.append('%8.1f ms each  %6d calls  %7.1f s total  %s' % (1000 * t / max(1, calls), calls, t, label))
        lines.append('("mainloop" below is Tk itself: waiting for events, or drawing)')
        lines.append('')
        for name in sorted(totals, key=lambda n: -totals[n]):
            n = totals[name]
            lines.append('==== %s: %d samples ====' % (name, n))
            lines.append('-- where it was (innermost) --')
            for k, v in own[name].most_common(35):
                lines.append('%5.1f%%  %s' % (100.0 * v / n, k))
            lines.append('-- inside (anywhere on the stack) --')
            for k, v in incl[name].most_common(45):
                lines.append('%5.1f%%  %s' % (100.0 * v / n, k))
            lines.append('')
        path = os.path.expanduser('~/ssgold-profile.txt')
        with open(path, 'w') as f:
            f.write('\n'.join(lines))
        print('Profile written to', path)


if __name__ == '__main__':
    main()
