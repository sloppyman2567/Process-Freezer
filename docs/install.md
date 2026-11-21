# Installing

## Requirements

- Linux with unified cgroup v2 (`stat -fc %T /sys/fs/cgroup` prints `cgroup2fs`)
- systemd running as your user (`systemctl --user status` works)
- Python 3.10 or newer
- PyQt6
- PyGObject, only if you want the global hotkey

Install the system packages:

```sh
# Arch
sudo pacman -S python-pyqt6 python-gobject

# Debian / Ubuntu
sudo apt install python3-pyqt6 python3-gi

# Fedora
sudo dnf install python3-pyqt6 python3-gobject
```

## Install the app

From the project folder:

```sh
./install.sh
```

The script does three things:

1. Creates `.venv` with `--system-site-packages`, so the virtualenv can see the system PyQt6 and PyGObject.
2. Installs the project into it in editable mode, which provides `.venv/bin/process-freezer`.
3. Symlinks that command to `~/.local/bin/process-freezer` and writes `~/.local/share/applications/process-freezer.desktop`.

Then start it with `process-freezer`, or from your application menu.

Re-running the script is safe; it upgrades the existing install in place. If you move the folder, run it again so the launcher and desktop entry point at the new location.

`--system-site-packages` matters more than it looks: PyGObject cannot be installed from pip, so a plain virtualenv would lose the hotkey. If you would rather not depend on the system copy, `pip install .` into a normal virtualenv works for everything except the hotkey, which reports that it is unavailable.

Once installed, `.venv/bin/process-freezer` is the real command; the file in `~/.local/bin` is a symlink to it.

## Uninstall

```sh
rm ~/.local/bin/process-freezer
rm ~/.local/share/applications/process-freezer.desktop
rm -rf .venv                 # and the project folder itself, if you are done
rm -rf ~/.config/ProcessFreezer
```

Removing the config deletes your saved hotkey, target and theme. Leave it if you plan to reinstall.
