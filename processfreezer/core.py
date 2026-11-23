"""Reading processes, freezing them, and remembering what the app should recall."""

import json
import os
import re
import subprocess
import sys
import time
from dataclasses import dataclass, field
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
    # 0 when the parent is not ours to see: init, another user's process, or a
    # parent that exited before this scan.
    ppid: int = 0

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
        state, ppid, start_time = fields[0], int(fields[1]), int(fields[19])
        with open(f"/proc/{pid}/status", encoding="utf-8") as file:
            status = file.read().splitlines()
        uid = int(next(line for line in status if line.startswith("Uid:")).split()[1])
        if uid != os.getuid() or state == "Z":
            return None
        rss = next((line for line in status if line.startswith("VmRSS:")), None)
        group = cgroup_path(pid)
        return Process(pid, name, state, int(rss.split()[1]) // 1024 if rss else 0,
                       start_time, group, is_frozen(group), ppid)
    except (OSError, ValueError, StopIteration, IndexError):
        return None


def list_processes():
    try:
        pids = [int(name) for name in os.listdir("/proc") if name.isdigit()]
    except OSError:
        return []
    processes = [process for pid in pids if (process := read_process(pid)) is not None]
    return sorted(processes, key=lambda process: process.name.casefold())


# The init process. Every app in the session descends from it, so the tree
# starts at its children rather than at one enormous row.
MANAGERS = frozenset({"systemd", "init"})
UNIT_ESCAPE = re.compile(r"\\x([0-9a-fA-F]{2})")


def unit_of(cgroup):
    """The systemd unit that names the app a process runs in, or ``""``.

    A cgroup path looks like
    ``/user.slice/user-1000.slice/user@1000.service/app.slice/app-org.kde.konsole-4004.scope/main.scope``.
    The first unit below the per-user manager is the one the launcher made for
    the app. Units that belong to the session itself — the manager, the login
    session — name no app, so those processes are shown on their own.
    """
    for part in cgroup.split("/"):
        if part.endswith(".service") and part.startswith("user@"):
            continue
        if part == "init.scope" or part.startswith("session-"):
            continue
        if part.endswith((".service", ".scope")):
            return part
    return ""


def app_id(unit):
    """The desktop app id inside an app unit, such as ``org.kde.konsole``.

    systemd escapes characters that are not allowed in a unit name, so
    ``app-brave\\x2dorigin@….service`` names the app ``brave-origin``.
    """
    stem = unit.rsplit(".", 1)[0]
    if not stem.startswith("app-"):
        return ""
    stem = stem[len("app-"):].removeprefix("flatpak-").split("@", 1)[0]
    stem = UNIT_ESCAPE.sub(lambda match: chr(int(match.group(1), 16)), stem)
    return re.sub(r"-\d+$", "", stem).strip()


@dataclass
class TreeNode:
    """A process and the processes it started, nested the way the app shows them.

    ``process`` is empty for a row that gathers several roots of one app.
    """

    process: Process | None = None
    children: list = field(default_factory=list)
    unit: str = ""

    @property
    def size(self):
        return (0 if self.process is None else 1) + sum(child.size for child in self.children)

    def members(self):
        """This process, then everything below it, parents before children."""
        if self.process is not None:
            yield self.process
        for child in self.children:
            yield from child.members()


def _leads_to(nodes, start, pid):
    """Whether following ``start`` up the parent chain comes back to ``pid``."""
    seen = set()
    current = start
    while current is not None and current.process.pid not in seen:
        if current.process.pid == pid:
            return True
        seen.add(current.process.pid)
        current = nodes.get(current.process.ppid)
    return False


def build_forest(processes):
    """Nest ``processes`` by parent and return the roots.

    A process whose parent is missing from ``processes`` starts a tree of its
    own: the parent may have exited, run as another user, or be a kernel
    thread. PID reuse can also leave two processes naming each other as
    parent, so a parent is only used when following it upwards cannot come
    back to the child.
    """
    nodes = {process.pid: TreeNode(process) for process in processes}
    roots = []
    for process in processes:
        node = nodes[process.pid]
        parent = nodes.get(process.ppid)
        if parent is None or parent is node or _leads_to(nodes, parent, node.process.pid):
            roots.append(node)
        else:
            parent.children.append(node)
    return roots


def app_forest(processes):
    """The rows the tree view starts from: one per app, not one per manager.

    Every process descends from the session's systemd, so nesting from it put
    all of them, apps included, below a single row that is useless to select.
    The manager is left out and its children become the top level. A launcher
    such as bubblewrap can leave several roots inside one app unit, and those
    share a row, so the app appears once instead of once per root.
    """
    roots = []
    for node in build_forest(processes):
        if node.process.name in MANAGERS:
            roots.extend(node.children)
        else:
            roots.append(node)
    units = {}
    for node in roots:
        units.setdefault(unit_of(node.process.cgroup), []).append(node)
    forest = []
    for unit, nodes in units.items():
        if unit and len(nodes) > 1:
            forest.append(TreeNode(None, nodes, unit))
        else:
            forest.extend(nodes)
    return forest


def filter_forest(roots, keep):
    """Drop what ``keep`` rejects, but hold on to the parents leading to a match."""
    kept = []
    for node in roots:
        children = filter_forest(node.children, keep)
        if children or (node.process is not None and keep(node.process)):
            kept.append(TreeNode(node.process, children, node.unit))
    return kept


def subtree(processes, root):
    """``root`` and everything below it, as a fresh scan of ``processes`` sees it."""
    stack = list(build_forest(processes))
    while stack:
        node = stack.pop()
        if node.process.key == root.key:
            return list(node.members())
        stack.extend(node.children)
    return [root]


def watchdog_command(units, seconds):
    """How to start the thaw safety net for ``units``, one or many.

    A source checkout runs :mod:`processfreezer.watchdog` with this
    interpreter. A PyInstaller build has no interpreter left to run ``-m``
    with, so the same code sits behind the app's hidden ``--watchdog`` flag.
    """
    if isinstance(units, str):
        units = [units]
    if getattr(sys, "frozen", False):
        command = [sys.executable, "--watchdog"]
    else:
        command = [sys.executable, "-m", "processfreezer.watchdog"]
    return [*command, *units, str(seconds)]


class Freezer:
    manager = ["org.freedesktop.systemd1", "/org/freedesktop/systemd1",
               "org.freedesktop.systemd1.Manager"]

    @staticmethod
    def run(args, timeout=8):
        try:
            result = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
        except (FileNotFoundError, subprocess.TimeoutExpired) as error:
            raise RuntimeError(str(error)) from error
        if result.returncode:
            raise RuntimeError((result.stderr or result.stdout).strip() or f"{args[0]} failed")
        return result.stdout.strip()

    def ensure_scope(self, process):
        """The freezer scope holding ``process``, creating one if it has none.

        Moving a process into a scope of its own is the expensive step, and
        systemd answers before the move has landed, so wait until /proc reports
        the new scope instead of freezing the old cgroup.
        """
        if process.scope:
            return process.scope
        unit = f"process-freezer-{process.pid}-{process.start_time}.scope"
        self.run([
            "busctl", "--user", "call", *self.manager, "StartTransientUnit",
            "ssa(sv)a(sa(sv))", unit, "fail", "2", "Description", "s",
            f"Process Freezer target {process.name} ({process.pid})",
            "PIDs", "au", "1", str(process.pid), "0",
        ])
        for _ in range(30):
            current = read_process(process.pid)
            if current is None or current.start_time != process.start_time:
                raise RuntimeError(f"{process.name} exited while preparing its freezer scope.")
            if current.scope == unit:
                return unit
            time.sleep(.05)
        raise RuntimeError("systemd did not create the process freezer scope.")

    def pause(self, processes, seconds):
        """Freeze every process in ``processes`` for ``seconds``.

        Each process gets a scope of its own, then a single systemctl call
        freezes them all, so an app with thirty children costs one freeze
        instead of thirty.
        """
        targets = []
        for process in processes:
            current = read_process(process.pid)
            if current is None or current.start_time != process.start_time:
                if len(processes) == 1:
                    raise RuntimeError("That process exited. Refresh the list and try again.")
                # A child can exit between the scan and the freeze: freeze the
                # rest rather than refusing the tree the user asked for.
                continue
            if current.state in {"T", "t"}:
                continue
            targets.append(current)
        if not targets:
            raise RuntimeError(
                "That process is already paused." if len(processes) == 1
                else "Those processes are already paused."
            )
        units, watchdogs = [], []
        try:
            units = [self.ensure_scope(target) for target in targets]
            # One watchdog for the whole freeze: a tree can hold dozens of
            # scopes, and one process per scope would cost more memory than
            # the app being frozen.
            watchdogs = [subprocess.Popen(
                watchdog_command(units, seconds),
                stdin=subprocess.PIPE, stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL, start_new_session=True, close_fds=True,
            )]
            self.run(["systemctl", "--user", "freeze", *units], timeout=30)
        except Exception:
            # A half-frozen tree is worse than none of it: put back whatever
            # landed before giving up.
            self.thaw_quietly(units)
            for watchdog in watchdogs:
                self.stop_watchdog(watchdog)
            raise
        # Start the countdown only now: the freeze already cost a systemctl
        # spawn and a D-Bus round trip, and that time must not come off the pause.
        for watchdog in watchdogs:
            try:
                watchdog.stdin.write(b"start")
                watchdog.stdin.close()
            except OSError:
                pass
        return Freeze(self, units, watchdogs)

    def thaw(self, units):
        if not units:
            return
        self.run(["systemctl", "--user", "thaw", *units], timeout=30)

    def thaw_quietly(self, units):
        if not units:
            return
        try:
            self.thaw(units)
        except Exception:
            pass

    @staticmethod
    def stop_watchdog(watchdog):
        if watchdog is None:
            return
        if watchdog.poll() is None:
            watchdog.terminate()
            try:
                watchdog.wait(timeout=1)
            except subprocess.TimeoutExpired:
                watchdog.kill()
        Freezer._close_input(watchdog)

    @staticmethod
    def _close_input(watchdog):
        if watchdog is None or watchdog.stdin is None or watchdog.stdin.closed:
            return
        try:
            watchdog.stdin.close()
        except OSError:
            pass


class Freeze:
    """What one press froze, and the safety net that thaws it without the window."""

    def __init__(self, freezer, units, watchdogs):
        self.freezer = freezer
        self.units = units
        self.watchdogs = watchdogs

    def resume(self):
        self.freezer.thaw(self.units)
        for watchdog in self.watchdogs:
            self.freezer.stop_watchdog(watchdog)


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
    def tree_view(self):
        return bool(self.settings.value("tree_view", True, type=bool))

    @tree_view.setter
    def tree_view(self, value):
        self.settings.setValue("tree_view", bool(value))

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
