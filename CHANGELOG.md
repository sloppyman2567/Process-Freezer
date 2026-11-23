# Changelog

## Unreleased

- The process list is a tree now, and each row carries its app's icon: children sit under the process that started them, and selecting an app freezes everything below it. **Tree** switches back to the flat list, and the choice is remembered.
- The tree starts at your apps instead of at `systemd`. Everything in the session descends from the manager, so the old view hid the desktop shell, the browser and every other app behind one huge row that could not be frozen. Roots that share one systemd app unit now share a row named from the desktop entry, so a Flatpak app appears once instead of once per `bwrap` root, and the hotkey finds such a row again by its unit rather than by a PID.
- Freezing an app costs one `systemctl` call and one watchdog, however many processes the tree holds, and a failure part-way thaws what already froze instead of leaving half an app stopped.
- The filter keeps the parents of a match so a renderer still shows its app, the count beside it says how many processes are listed, and an empty result says so instead of showing a blank box. **Ctrl+F**, **Esc**, **F5** and double-clicking a row now work.
- KDE no longer keeps using Process Freezer's shortcut after the window closes. Starting the app registered the action with the shortcut service again on every launch, and nothing released it, so KDE went on grabbing the key (a bare `Insert`, for example) while the app was not running. The key is now taken when the window opens and given back when it closes, and starting the app adds nothing to KDE's shortcut settings until you save a key.
- The thaw watchdog started as an inline `python -c` command, which a bundled executable cannot run. It is now its own module, and the packaged build starts it through a hidden `--watchdog` flag.
- The app no longer puts back an old hotkey at startup. KDE's shortcut settings are the source of truth, and the window follows a key you change or clear there, even while it is open.

## 1.0.2

- The global hotkey dialog now looks like the rest of the app: a heading, a line explaining what the key does, roomy margins and a highlighted save button instead of a stock Qt popup.
- The duration box draws its own stepper arrows, so it no longer shows a stray light box in the dark theme, and the theme dropdown shows its arrow again.

## 1.0.1

- Starting a second copy now raises the window that is already open instead of opening another one, and a socket left behind by a crash is cleared on the next start.
- The menu entry uses one application category, so it no longer shows up twice in menus that group both.
- `process-freezer --freeze` freezes the saved target from a key binding, for desktops without KDE's shortcut service such as GNOME, sway or Hyprland.
- Changing the hotkey works now. KDE's shortcut daemon ignored every new key because the app asked it to autoload instead of to change the shortcut, and the old code reported success anyway.
- Saving a hotkey checks what KDE actually stored, and a combination another app already owns is refused with that app's name instead of being taken from it.
- On a desktop with no KDE shortcut service, the app explains that at startup and points at `process-freezer --freeze`, instead of showing a raw D-Bus error.

## 1.0.0

- Split the single script into an installable `processfreezer` package with `docs/` and `pyproject.toml`. `./install.sh` creates the virtualenv, installs the `process-freezer` command and adds the menu entry.
- Added System, Light and Dark themes. The app now sets its palette as well as its stylesheet, so menus, dialogs and the process list all follow the theme instead of flashing white in dark mode.
- Preferences (theme, duration, hold mode, hotkey, window size) are stored in `~/.config/ProcessFreezer/ProcessFreezer.conf`, and settings from the old `gamingpc/ProcessFreezer.conf` are carried over on first run.
- A timed freeze now lasts the duration you set. The safety watchdog used to start counting before systemctl applied the freeze, so every pause came up short by the freeze latency.
- Holding the button and the hotkey at once no longer strands a process: the freeze is shared, and it resumes when the last trigger is released.
- A machine without PyGObject starts normally instead of crashing, and the status line names the missing package. The hotkey is simply unavailable.
- Error messages no longer leave the status line red for the rest of the session.
- Docs now list KDE's global shortcut service instead of `pynput`, and drop `systemd-run`, neither of which the app ever used.
