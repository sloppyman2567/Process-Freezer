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

## Prebuilt binary

Every release publishes one executable, named `process-freezer-<version>-linux-x86_64-glibc2.39`. GitHub Actions cuts the release as soon as a new version lands on `main`, so nothing has to be tagged by hand. Download it from the repository's Releases page and put it on your `PATH`:

```sh
mkdir -p ~/.local/bin
mv process-freezer-*-linux-x86_64-glibc2.39 ~/.local/bin/process-freezer
chmod +x ~/.local/bin/process-freezer
```

The matching `.sha256` file holds the checksum: `sha256sum -c process-freezer-<version>-linux-x86_64-glibc2.39.sha256` checks the download.

It carries Python, Qt and the app, so it needs no Python install, virtualenv or `install.sh`. The system requirements are the rest of the list above: glibc 2.39 or newer (Ubuntu 24.04, Fedora 40, Arch and later), cgroup v2 and a systemd user manager.

The binary is built without the global hotkey. PyGObject and KDE's shortcut service are system libraries it does not carry, so its status line says the hotkey is not part of the build and prints the command to bind: the binary's own path followed by `--freeze` ([docs/usage.md](usage.md#if-the-hotkey-does-not-work)). To get the hotkey inside the window, install from source as above.

The file is a self-extracting single-file executable, so the first start takes a moment longer than later ones while it unpacks into a temporary directory.

## Uninstall

```sh
rm ~/.local/bin/process-freezer
rm ~/.local/share/applications/process-freezer.desktop
rm -rf .venv                 # and the project folder itself, if you are done
rm -rf ~/.config/ProcessFreezer
```

The same commands uninstall the prebuilt binary; it has no `.venv` of its own.

Removing the config deletes your saved hotkey, target and theme. Leave it if you plan to reinstall.
