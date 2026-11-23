"""The thaw safety net: a separate process that outlives a crashed window.

Each freeze starts this module as its own process, so a GUI that dies while a
process is frozen cannot leave that process frozen forever. One watchdog
covers every scope of a freeze, however many the process tree needed. It reads
a single ``b"start"`` from its input first: the app writes that byte only once
``systemctl freeze`` has returned, which keeps the countdown equal to the pause
you asked for. A closed input without the byte means the GUI died before the
freeze landed, so it thaws at once instead of sleeping through a freeze that
may or may not have happened.
"""

import subprocess
import sys
import time


def thaw(units):
    subprocess.run(
        ["systemctl", "--user", "thaw", *units],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )


def main(argv=None):
    args = sys.argv[1:] if argv is None else list(argv)
    # The duration comes last, so a freeze of any number of scopes still needs
    # only one watchdog process.
    if len(args) < 2:
        print("usage: process-freezer --watchdog <unit>... <seconds>", file=sys.stderr)
        return 2
    units, seconds = args[:-1], args[-1]
    try:
        duration = float(seconds)
    except ValueError:
        print("usage: process-freezer --watchdog <unit>... <seconds>", file=sys.stderr)
        return 2
    if sys.stdin.buffer.read(5) == b"start":
        time.sleep(duration)
    thaw(units)
    return 0


if __name__ == "__main__":
    sys.exit(main())
