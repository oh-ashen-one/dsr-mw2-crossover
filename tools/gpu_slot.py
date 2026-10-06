"""Exclusive local renderer lease. Does not launch a game unless explicitly given one.

Use a coordinator supplied by your machine if one exists. This fallback protects
cooperating launches only; it cannot arbitrate unrelated applications.
"""
import argparse
import fcntl
import os
from pathlib import Path
import subprocess
import time


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('slot', choices=['perf'])
    p.add_argument('--label', required=True)
    p.add_argument('--timeout', type=float, default=60)
    # argparse REMAINDER consumes options after the positional slot; split at --.
    import sys
    args, separator, command = [], False, []
    for value in sys.argv[1:]:
        if value == '--' and not separator:
            separator = True
        elif separator:
            command.append(value)
        else:
            args.append(value)
    options = p.parse_args(args)
    if not command:
        p.error('A command after -- is required')
    root = Path(os.environ['GPU_SLOT_DIR']).resolve()
    pause = root / 'PAUSED'
    lock = root / 'locks/perf.lock'
    if lock.is_symlink() or lock.resolve().parent != root / 'locks':
        raise ValueError('Renderer lock is redirected')
    with lock.open('r+') as stream:
        deadline = time.monotonic() + max(0, options.timeout)
        while True:
            if pause.exists():
                raise RuntimeError('Renderer coordinator has paused launches')
            try:
                fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    return 75
                time.sleep(.25)
        if pause.exists():
            return 75
        env = dict(os.environ, GPU_SLOT_HELD='perf', GPU_SLOT_DIR=str(root))
        # Lease follows the foreground launcher, which supervises its private
        # game/bottle lifetime and retains ownership through restoration.
        child = subprocess.Popen(command, env=env)
        try:
            return child.wait()
        except KeyboardInterrupt:
            # Do not release the lock while an owned child is still running.
            return child.wait()


if __name__ == '__main__':
    raise SystemExit(main())
