"""Reading processes, freezing them, and remembering what the app should recall."""

import json
import os
import re
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

from PyQt6.QtCore import QByteArray, QSettings

ORGANIZATION = "ProcessFreezer"
APPLICATION = "ProcessFreezer"

CONFIG_HOME = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config")
CONFIG_DIR = CONFIG_HOME / APPLICATION
TARGET_FILE = CONFIG_DIR / "target.json"

# Written by the single-script version; read once and carried over.
LEGACY_TARGET_FILE = CONFIG_HOME / "process-freezer" / "target.json"
LEGACY_SETTINGS_FILE = CONFIG_HOME / "gamingpc" / "ProcessFreezer.conf"

THEMES = ("system", "light", "dark")
MIN_DURATION_MS = 1
MAX_DURATION_MS = 60_000
DEFAULT_DURATION_MS = 3000


@dataclass
class Process:
    pid: int
    name: str
    state: str
    memory_mb: int
    start_time: int
    cgroup: str
    frozen: bool

    @property
    def key(self):
        return self.pid, self.start_time

    @property
    def scope(self):
        match = re.search(r"(?:^|/)process-freezer-(\d+)-(\d+)\.scope(?:/|$)", self.cgroup)
        return f"process-freezer-{match.group(1)}-{match.group(2)}.scope" if match else None


def cgroup_path(pid):
    try:
        with open(f"/proc/{pid}/cgroup", encoding="utf-8") as file:
            for line in file:
                if line.startswith("0::"):
                    return line[3:].strip()
    except OSError:
        pass
    return ""


def is_frozen(path):
    try:
        with open(f"/sys/fs/cgroup{path}/cgroup.events", encoding="utf-8") as file:
            return "frozen 1" in file.read().splitlines()
    except OSError:
        return False


def read_process(pid):
    try:
        with open(f"/proc/{pid}/stat", encoding="utf-8") as file:
            stat = file.read()
        end = stat.rfind(")")
        name = stat[stat.find("(") + 1:end]
        fields = stat[end + 2:].split()
        state, start_time = fields[0], int(fields[19])
        with open(f"/proc/{pid}/status", encoding="utf-8") as file:
            status = file.read().splitlines()
        uid = int(next(line for line in status if line.startswith("Uid:")).split()[1])
        if uid != os.getuid() or state == "Z":
            return None
        rss = next((line for line in status if line.startswith("VmRSS:")), None)
        group = cgroup_path(pid)
        return Process(pid, name, state, int(rss.split()[1]) // 1024 if rss else 0,
                       start_time, group, is_frozen(group))
    except (OSError, ValueError, StopIteration, IndexError):
        return None


def list_processes():
    try:
        pids = [int(name) for name in os.listdir("/proc") if name.isdigit()]
    except OSError:
        return []
    processes = [process for pid in pids if (process := read_process(pid)) is not None]
    return sorted(processes, key=lambda process: process.name.casefold())


class Freezer:
    manager = ["org.freedesktop.systemd1", "/org/freedesktop/systemd1",
               "org.freedesktop.systemd1.Manager"]

    # The watchdog sleeps only after the parent writes b"start", which happens
    # once systemctl freeze has returned. Its stdin closing without that byte
    # means the GUI died before the freeze finished, so it thaws at once.
    WATCHDOG = (
        "import subprocess, sys, time\n"
        "unit, seconds = sys.argv[1], sys.argv[2]\n"
        "if sys.stdin.buffer.read(5) == b'start':\n"
        "    time.sleep(float(seconds))\n"
        "subprocess.run(['systemctl', '--user', 'thaw', unit],\n"
        "               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)\n"
    )

    @staticmethod
    def run(args, timeout=8):
        try:
            result = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
        except (FileNotFoundError, subprocess.TimeoutExpired) as error:
            raise RuntimeError(str(error)) from error
        if result.returncode:
            raise RuntimeError((result.stderr or result.stdout).strip() or f"{args[0]} failed")
        return result.stdout.strip()

    def pause(self, process, seconds):
        current = read_process(process.pid)
        if current is None or current.start_time != process.start_time:
            raise RuntimeError("That process exited. Refresh the list and try again.")
        if current.state in {"T", "t"}:
            raise RuntimeError("That process is already paused.")
        unit = current.scope or f"process-freezer-{current.pid}-{current.start_time}.scope"
        if not current.scope:
            self.run([
                "busctl", "--user", "call", *self.manager, "StartTransientUnit",
                "ssa(sv)a(sa(sv))", unit, "fail", "2", "Description", "s",
                f"Process Freezer target {current.name} ({current.pid})",
                "PIDs", "au", "1", str(current.pid), "0",
            ])
            for _ in range(30):
                current = read_process(process.pid)
                if current is None or current.start_time != process.start_time:
                    raise RuntimeError("Process exited while preparing its freezer scope.")
                if current.scope == unit:
                    break
                time.sleep(.05)
            else:
                raise RuntimeError("systemd did not create the process freezer scope.")
        watchdog = subprocess.Popen(
            [sys.executable, "-c", self.WATCHDOG, unit, str(seconds)],
            stdin=subprocess.PIPE, stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL, start_new_session=True, close_fds=True,
        )
        try:
            self.run(["systemctl", "--user", "freeze", unit])
        except Exception:
            # EOF makes it thaw straight away, in case the freeze landed anyway.
            self._close_input(watchdog)
            raise
        # Start the countdown only now: the freeze already cost a systemctl
        # spawn and a D-Bus round trip, and that time must not come off the pause.
        try:
            watchdog.stdin.write(b"start")
            watchdog.stdin.close()
        except OSError:
            pass
        return unit, watchdog

    @staticmethod
    def _close_input(watchdog):
        if watchdog is None or watchdog.stdin is None or watchdog.stdin.closed:
            return
        try:
            watchdog.stdin.close()
        except OSError:
            pass

    def resume(self, unit, watchdog=None):
        if watchdog and watchdog.poll() is None:
            watchdog.terminate()
            try:
                watchdog.wait(timeout=1)
            except subprocess.TimeoutExpired:
                watchdog.kill()
        self._close_input(watchdog)
        self.run(["systemctl", "--user", "thaw", unit])


class Config:
    """Preferences that survive restarts.

    The native settings format on Linux is INI, written to
    ``~/.config/ProcessFreezer/ProcessFreezer.conf``.
    """

    def __init__(self):
        self.settings = QSettings(QSettings.Scope.UserScope, ORGANIZATION, APPLICATION)
        self._migrate_legacy()

    def _migrate_legacy(self):
        """Copy duration and hotkey out of the old ``gamingpc`` file exactly once."""
        if self.settings.contains("theme") or not LEGACY_SETTINGS_FILE.exists():
            return
        legacy = QSettings(str(LEGACY_SETTINGS_FILE), QSettings.Format.IniFormat)
        hotkey = legacy.value("hotkey")
        if hotkey:
            self.settings.setValue("hotkey", str(hotkey))
        try:
            self.duration_ms = round(float(legacy.value("duration")) * 1000)
        except (TypeError, ValueError):
            pass
        self.settings.sync()

    @property
    def theme(self):
        value = str(self.settings.value("theme", "system"))
        return value if value in THEMES else "system"

    @theme.setter
    def theme(self, value):
        self.settings.setValue("theme", value if value in THEMES else "system")
        self.settings.sync()

    @property
    def duration_ms(self):
        try:
            value = int(self.settings.value("duration_ms", DEFAULT_DURATION_MS))
        except (TypeError, ValueError):
            value = DEFAULT_DURATION_MS
        return min(max(value, MIN_DURATION_MS), MAX_DURATION_MS)

    @duration_ms.setter
    def duration_ms(self, value):
        self.settings.setValue("duration_ms", min(max(int(value), MIN_DURATION_MS), MAX_DURATION_MS))

    @property
    def hotkey(self):
        return str(self.settings.value("hotkey", ""))

    @hotkey.setter
    def hotkey(self, value):
        self.settings.setValue("hotkey", str(value))
        self.settings.sync()

    @property
    def hold_mode(self):
        return bool(self.settings.value("hold_mode", False, type=bool))

    @hold_mode.setter
    def hold_mode(self, value):
        self.settings.setValue("hold_mode", bool(value))

    @property
    def geometry(self):
        value = self.settings.value("geometry", QByteArray())
        return value if isinstance(value, QByteArray) else QByteArray()

    @geometry.setter
    def geometry(self, value):
        self.settings.setValue("geometry", value)

    def flush(self):
        self.settings.sync()


class TargetStore:
    """The process the global hotkey freezes, remembered across restarts."""

    def __init__(self, path=TARGET_FILE, legacy=LEGACY_TARGET_FILE):
        self.path = Path(path)
        self.legacy = Path(legacy)

    def load(self):
        for path in (self.path, self.legacy):
            target = self._read(path)
            if target:
                return target
        return None

    @staticmethod
    def _read(path):
        try:
            with open(path, encoding="utf-8") as file:
                target = json.load(file)
        except (OSError, ValueError):
            return None
        if isinstance(target, dict) and all(key in target for key in ("pid", "start_time", "name")):
            return target
        return None

    def save(self, target):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(".json.tmp")
        with open(temporary, "w", encoding="utf-8") as file:
            json.dump(target, file, indent=2)
        os.replace(temporary, self.path)
