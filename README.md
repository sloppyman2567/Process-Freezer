# Process Freezer

Freeze one of your own processes for a moment and thaw it again, using the Linux cgroup v2 freezer. It never sends `SIGSTOP` and never kills anything, so the process keeps its memory, its sockets and its open files exactly as they were.

Handy when something hogs the CPU and you want a few seconds without it, without losing the state you waited to load.

## Install

```sh
./install.sh
```

That creates `.venv`, installs the `process-freezer` command into `~/.local/bin`, and adds a Process Freezer entry to your application menu. Run it again after moving the folder or pulling changes.

You need Python 3.10 or newer, PyQt6, and a Linux system with cgroup v2 and a systemd user manager. Package names for each distribution are in [docs/install.md](docs/install.md).

## Use

Pick a process from the list, choose how long to pause it, then press **Freeze selected**. The pause ends when the time is up, or immediately with **Resume now**.

- **Tree** (on by default) groups each process with the ones it started and shows the app's own icon. Selecting an app pauses all of it: one row for Firefox, with its renderers and helpers underneath. Untick it for a flat list of single processes.
- **Hold** keeps the process frozen while you hold the button, and resumes it when you let go.
- **Bind** sets a global hotkey that freezes the saved process (or the whole saved tree) from anywhere. It needs KDE's shortcut service; on other desktops bind the command `process-freezer --freeze` in your desktop's own keyboard settings. See [docs/usage.md](docs/usage.md#if-the-hotkey-does-not-work).
- **Theme** switches between System, Light and Dark. System follows your desktop's colour scheme.

Double-clicking a row freezes or resumes it. **Ctrl+F** jumps to the filter, **Esc** clears it, **F5** refreshes.

Theme, duration, hold setting, tree or flat view, hotkey and window size are remembered in `~/.config/ProcessFreezer/ProcessFreezer.conf`, and the process the hotkey targets is kept in `~/.config/ProcessFreezer/target.json`.

## Documentation

- [Installing and uninstalling](docs/install.md)
- [Using the app](docs/usage.md)
- [How freezing actually works](docs/how-it-works.md)

## Uninstall

```sh
rm ~/.local/bin/process-freezer
rm ~/.local/share/applications/process-freezer.desktop
rm -rf .venv ~/.config/ProcessFreezer
```
