# Using Process Freezer

## Freezing a process

The list shows your own processes: name, PID, memory and state. Type in the filter box to narrow it down; it matches names and PIDs.

Select a row, set a duration between 1 and 60,000 ms, and press **Freeze selected**. The process stops running until the timer expires. While it is frozen the row says **Frozen** and the button becomes **Resume now**, which thaws it early.

Selecting a row also saves it as the target: the process the global hotkey acts on. That choice survives restarts, so you can bind a key once and keep using it.

If the process exits or is restarted, its PID can be reused by something else. The saved target stores the start time as well, so a recycled PID is reported as "the saved process has exited" rather than freezing the wrong thing.

## Hold mode

With **Hold** ticked, the freeze lasts exactly as long as the trigger:

- Press and hold **Freeze selected**, release to resume.
- Press and hold the hotkey, release to resume.

Nothing is timed in this mode. Both triggers can hold the same freeze at once: the process stays frozen until the last one is released, so letting go of the button does not resume it while you are still holding the hotkey. If the window closes while a process is held, it is resumed on the way out.

## The global hotkey

Press **Bind**, press the key combination, press **Save**. From then on the key freezes the saved target even when Process Freezer is behind another window.

The key is registered with KDE's global shortcut service, which is what makes it work under Wayland: the compositor does the key grab, so it does not matter which window or which toolkit has focus. After you save a key, it also appears in **System Settings → Shortcuts → Process Freezer** as "Freeze saved process".

Hotkey gestures fire once per press, not on repeats, and the app never asks the system to swallow the key.

### If the hotkey does not work

- The global shortcut service is part of KDE. On GNOME, XFCE, sway, Hyprland and similar desktops there is nothing to register with, and the app says so in the status line. The button still works.
- Missing PyGObject does not stop the app. It starts, freezes and thaws normally, and the status line names the package to install before the hotkey can work.
- If KDE keeps the combination for something else, saving fails with a message naming the key. Pick another one.
- The shortcut is owned by the running instance. Starting a second copy only raises the first window; it does not re-register the key.

## Themes

The dropdown beside the title offers **System theme**, **Light** and **Dark**.

- **System theme** asks the desktop which colour scheme it is using and follows it live: switching your desktop to dark mode re-themes the window without a restart. On desktops that do not report a scheme, it falls back to the palette the app started with.
- **Light** and **Dark** pin one look regardless of the desktop.

The choice is saved, so the app opens in the theme you last picked. The app draws with Qt's Fusion style, which keeps the two themes identical across desktops instead of borrowing each vendor's widgets.

## Settings

Everything is stored in `~/.config/ProcessFreezer/ProcessFreezer.conf` (or `$XDG_CONFIG_HOME/ProcessFreezer/ProcessFreezer.conf`):

| Key | Meaning |
| --- | --- |
| `theme` | `system`, `light` or `dark` |
| `duration_ms` | last used pause length |
| `hold_mode` | whether Hold was ticked |
| `hotkey` | the bound key sequence, empty if none |
| `geometry` | window size and position |

The saved target lives next door in `target.json`, with the PID, start time, name and duration.

Settings written by the old single-file version are copied from `~/.config/gamingpc/ProcessFreezer.conf` the first time this version starts, so the hotkey and duration carry over. The old file is left untouched.

Deleting `ProcessFreezer.conf` resets the app to defaults; it is recreated on exit.
