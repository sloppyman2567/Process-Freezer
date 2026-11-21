# Changelog

## Unreleased

- Starting a second copy now raises the window that is already open instead of opening another one, and a socket left behind by a crash is cleared on the next start.
- The menu entry uses one application category, so it no longer shows up twice in menus that group both.

## 1.0.0

- Split the single script into an installable `processfreezer` package with `docs/` and `pyproject.toml`. `./install.sh` creates the virtualenv, installs the `process-freezer` command and adds the menu entry.
- Added System, Light and Dark themes. The app now sets its palette as well as its stylesheet, so menus, dialogs and the process list all follow the theme instead of flashing white in dark mode.
- Preferences (theme, duration, hold mode, hotkey, window size) are stored in `~/.config/ProcessFreezer/ProcessFreezer.conf`, and settings from the old `gamingpc/ProcessFreezer.conf` are carried over on first run.
- A timed freeze now lasts the duration you set. The safety watchdog used to start counting before systemctl applied the freeze, so every pause came up short by the freeze latency.
- Holding the button and the hotkey at once no longer strands a process: the freeze is shared, and it resumes when the last trigger is released.
- A machine without PyGObject starts normally instead of crashing, and the status line names the missing package. The hotkey is simply unavailable.
- Error messages no longer leave the status line red for the rest of the session.
- Docs now list KDE's global shortcut service instead of `pynput`, and drop `systemd-run`, neither of which the app ever used.
