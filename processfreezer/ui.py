"""Everything on screen: colour themes, the global shortcut and the main window."""

import os
import re
import shlex
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from string import Template

from PyQt6.QtCore import QObject, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import (
    QColor, QGuiApplication, QIcon, QKeySequence, QPainter, QPainterPath, QPalette, QPen,
    QShortcut,
)
from PyQt6.QtWidgets import (
    QAbstractItemView, QApplication, QCheckBox, QComboBox, QDialog, QDialogButtonBox,
    QDoubleSpinBox, QHBoxLayout, QHeaderView, QKeySequenceEdit, QLabel, QLineEdit,
    QMainWindow, QPushButton, QStackedWidget, QTreeWidget, QTreeWidgetItem, QVBoxLayout,
    QWidget,
)

from .core import (
    MAX_DURATION_MS, MIN_DURATION_MS, Freezer, TargetStore, TreeNode, app_forest, app_id,
    filter_forest, list_processes, read_process, subtree, unit_of,
)


# --------------------------------------------------------------------------- themes

@dataclass(frozen=True)
class Palette:
    background: str
    panel: str
    text: str
    muted: str
    line: str
    selected: str
    focus: str
    accent: str
    accent_text: str
    accent_hover: str
    accent_disabled: str
    accent_disabled_text: str
    danger: str
    scroll: str
    scroll_hover: str


LIGHT = Palette(
    background="#f5f5f3",
    panel="#ffffff",
    text="#20201e",
    muted="#777772",
    line="#deded9",
    selected="#ecece8",
    focus="#999994",
    accent="#292927",
    accent_text="#ffffff",
    accent_hover="#444440",
    accent_disabled="#d6d6d1",
    accent_disabled_text="#888882",
    danger="#9a3b32",
    scroll="#c9c9c4",
    scroll_hover="#a8a8a2",
)

DARK = Palette(
    background="#191918",
    panel="#232322",
    text="#eceae4",
    muted="#94948d",
    line="#37372f",
    selected="#30302c",
    focus="#5a5a52",
    accent="#eceae4",
    accent_text="#191918",
    accent_hover="#ffffff",
    accent_disabled="#2b2b28",
    accent_disabled_text="#6d6d66",
    danger="#ef8d80",
    scroll="#46463f",
    scroll_hover="#5c5c54",
)

PALETTES = {"light": LIGHT, "dark": DARK}

STYLE = Template("""
QWidget { color: $text; font-family: 'Noto Sans', 'Inter', sans-serif; font-size: 10pt; }
QMainWindow, QWidget#root, QDialog { background: $background; }
QLabel#title { font-size: 19pt; font-weight: 650; }
QLabel#dialogTitle { font-size: 13pt; font-weight: 650; }
QLabel#muted { color: $muted; }
QLabel#status { color: $muted; }
QLabel#status[tone="error"] { color: $danger; }
QLineEdit, QComboBox, QDoubleSpinBox, QKeySequenceEdit {
    background: $panel; border: 1px solid $line; border-radius: 7px; padding: 8px 10px;
}
QLineEdit:focus, QComboBox:focus, QDoubleSpinBox:focus, QKeySequenceEdit:focus {
    border-color: $focus;
}
QDoubleSpinBox { padding-right: 24px; }
QDoubleSpinBox::up-button, QDoubleSpinBox::down-button {
    subcontrol-origin: padding; width: 20px; border: 0; background: transparent;
}
QDoubleSpinBox::up-button { subcontrol-position: top right; }
QDoubleSpinBox::down-button { subcontrol-position: bottom right; }
QComboBox QAbstractItemView {
    background: $panel; border: 1px solid $line; outline: 0;
    selection-background-color: $selected; selection-color: $text;
}
QPushButton { border: 1px solid $line; border-radius: 7px; background: $panel; padding: 8px 12px; }
QPushButton:hover { background: $selected; }
QPushButton:disabled { color: $muted; }
QPushButton#primary {
    background: $accent; color: $accent_text; border-color: $accent;
    font-weight: 600; padding: 9px 15px;
}
QPushButton#primary:hover { background: $accent_hover; border-color: $accent_hover; }
QPushButton#primary:disabled {
    background: $accent_disabled; color: $accent_disabled_text; border-color: $accent_disabled;
}
QTreeWidget, QLabel#empty {
    background: $panel; border: 1px solid $line; border-radius: 8px;
    selection-background-color: $selected; selection-color: $text;
    outline: 0;
}
QHeaderView::section {
    background: $background; color: $muted; border: 0; border-bottom: 1px solid $line;
    padding: 8px; font-size: 8pt; font-weight: 600;
}
QTreeWidget::item { padding: 6px 2px; border: 0; }
QCheckBox { spacing: 7px; }
QScrollBar:vertical { background: transparent; width: 8px; margin: 0; }
QScrollBar::handle:vertical { background: $scroll; border-radius: 4px; min-height: 24px; }
QScrollBar::handle:vertical:hover { background: $scroll_hover; }
QScrollBar:horizontal { background: transparent; height: 8px; margin: 0; }
QScrollBar::handle:horizontal { background: $scroll; border-radius: 4px; min-width: 24px; }
QScrollBar::handle:horizontal:hover { background: $scroll_hover; }
QScrollBar::add-line, QScrollBar::sub-line { width: 0; height: 0; }
QScrollBar::add-page, QScrollBar::sub-page { background: transparent; }
QToolTip { background: $panel; color: $text; border: 1px solid $line; padding: 4px 6px; }
""")


def stylesheet(palette):
    return STYLE.substitute(asdict(palette))


def native_palette(palette):
    """A QPalette so menus, dialogs and text cursors match the theme too."""
    colors = QPalette()
    for role, color in (
        (QPalette.ColorRole.Window, palette.background),
        (QPalette.ColorRole.WindowText, palette.text),
        (QPalette.ColorRole.Base, palette.panel),
        (QPalette.ColorRole.AlternateBase, palette.selected),
        (QPalette.ColorRole.Text, palette.text),
        (QPalette.ColorRole.Button, palette.panel),
        (QPalette.ColorRole.ButtonText, palette.text),
        (QPalette.ColorRole.Highlight, palette.accent),
        (QPalette.ColorRole.HighlightedText, palette.accent_text),
        (QPalette.ColorRole.ToolTipBase, palette.panel),
        (QPalette.ColorRole.ToolTipText, palette.text),
        (QPalette.ColorRole.PlaceholderText, palette.muted),
        (QPalette.ColorRole.Mid, palette.line),
        (QPalette.ColorRole.Dark, palette.line),
        (QPalette.ColorRole.Shadow, palette.line),
    ):
        colors.setColor(role, QColor(color))
    return colors


def system_is_dark():
    scheme = QGuiApplication.styleHints().colorScheme()
    if scheme == Qt.ColorScheme.Unknown:
        return QGuiApplication.palette().color(QPalette.ColorRole.Window).lightness() < 128
    return scheme == Qt.ColorScheme.Dark


def resolve(mode):
    if mode in PALETTES:
        return PALETTES[mode]
    return DARK if system_is_dark() else LIGHT


def apply_theme(app, mode):
    """Style the whole application for ``mode``: ``system``, ``light`` or ``dark``."""
    palette = resolve(mode)
    app.setPalette(native_palette(palette))
    app.setStyleSheet(stylesheet(palette))
    return palette


class DurationSpinBox(QDoubleSpinBox):
    """A spin box that draws its own chevrons.

    The stylesheet flattens the native stepper so it stops drawing a light
    box on the dark field, but Qt will not draw arrow images from CSS, which
    would leave two invisible click targets. Draw the arrows instead.
    """

    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        color = QColor(self.palette().color(QPalette.ColorRole.WindowText))
        color.setAlpha(120 if self.isEnabled() else 70)
        painter.setPen(QPen(
            color, 1.5, Qt.PenStyle.SolidLine,
            Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin,
        ))
        centre = self.width() - 11
        middle = self.height() // 2
        for y, rise in ((middle - 8, 2.0), (middle + 8, -2.0)):
            chevron = QPainterPath()
            chevron.moveTo(centre - 3.5, y + rise)
            chevron.lineTo(centre, y - rise)
            chevron.lineTo(centre + 3.5, y + rise)
            painter.drawPath(chevron)


# ---------------------------------------------------------------------- global hotkey

def shortcut_command():
    """The command a desktop keybinding should run.

    A frozen build has no interpreter and cannot see the system PyGObject, so
    its only route to a global hotkey is a desktop shortcut that runs the
    executable itself with ``--freeze``.
    """
    if getattr(sys, "frozen", False):
        return f"{sys.executable} --freeze"
    return "process-freezer --freeze"


class GlobalHotkey(QObject):
    """Register the freeze shortcut with KDE's global shortcut daemon.

    A Wayland session only lets the compositor grab keys, so listening on
    pynput's X11 connection sees nothing. KWin owns the grab instead and tells
    us over D-Bus when the shortcut fires.
    """

    activated = pyqtSignal()
    released = pyqtSignal()

    SERVICE = "org.kde.kglobalaccel"
    CONTROL_PATH = "/kglobalaccel"
    CONTROL_INTERFACE = "org.kde.KGlobalAccel"
    COMPONENT_INTERFACE = "org.kde.kglobalaccel.Component"
    COMPONENT = "process-freezer"
    ACTION = "freeze-selected"
    FRIENDLY_COMPONENT = "Process Freezer"
    FRIENDLY_ACTION = "Freeze saved process"
    SET_PRESENT = 2
    # kglobalaccel only applies new keys when the caller says it is not
    # autoloading; without this flag the call is treated as an app syncing its
    # own stored shortcut and the current keys come back unchanged.
    NO_AUTOLOADING = 0x4

    def __init__(self, on_activated, on_released, changed, error, notice=None):
        super().__init__()
        self.activated.connect(on_activated)
        self.released.connect(on_released)
        self.changed_callback = changed
        self.error_callback = error
        # For conditions that are a limitation rather than a mistake, such as
        # a frozen build that cannot see PyGObject at all: those get a plain
        # status line instead of a red error.
        self.notice_callback = notice or error
        self.bus = None
        try:
            from gi.repository import Gio, GLib
        except ImportError:
            if getattr(sys, "frozen", False):
                self.notice_callback(
                    "Global hotkeys are not built into this executable. Bind "
                    f"\"{shortcut_command()}\" to a key in your desktop's "
                    "keyboard settings instead."
                )
            else:
                self.error_callback(
                    "Global hotkeys need PyGObject; install python-gobject "
                    "(or your distribution's equivalent)."
                )
            return
        self.Gio, self.GLib = Gio, GLib
        self.component_path = "/component/" + re.sub(r"[^A-Za-z0-9_]", "_", self.COMPONENT)
        try:
            self.bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
        except Exception as error:
            self.bus = None
            self.error_callback(f"Global shortcuts need a session bus: {error}")
            return
        if not self.shortcut_service_running():
            self.bus = None
            self.error_callback(
                "This desktop has no KDE shortcut service. Bind a key to the "
                f"command \"{shortcut_command()}\" in your desktop's keyboard "
                "settings instead."
            )
            return
        self.context = GLib.MainContext.default()
        self.pump_timer = QTimer(self)
        self.pump_timer.timeout.connect(self.pump)
        self.pump_timer.start(20)
        self.bus.signal_subscribe(
            self.SERVICE, self.COMPONENT_INTERFACE, "globalShortcutPressed",
            self.component_path, None, Gio.DBusSignalFlags.NONE, self.pressed, None,
        )
        self.bus.signal_subscribe(
            self.SERVICE, self.COMPONENT_INTERFACE, "globalShortcutReleased",
            self.component_path, None, Gio.DBusSignalFlags.NONE, self.shortcut_released, None,
        )

    @property
    def action_id(self):
        return [self.COMPONENT, self.ACTION, self.FRIENDLY_COMPONENT, self.FRIENDLY_ACTION]

    def shortcut_service_running(self):
        try:
            owned = self.bus.call_sync(
                "org.freedesktop.DBus", "/org/freedesktop/DBus", "org.freedesktop.DBus",
                "NameHasOwner", self.GLib.Variant("(s)", (self.SERVICE,)), None,
                self.Gio.DBusCallFlags.NONE, 1000, None,
            ).unpack()[0]
        except Exception:
            return False
        return bool(owned)

    @staticmethod
    def first_sequence(result):
        """The chord list out of an ``a(ai)`` reply, or [] when it was empty.

        PyGObject hands the array of one-field structs back as nested
        one-tuples, so peel those before reading the chord ints.
        """
        value = result
        while isinstance(value, (list, tuple)) and len(value) == 1 and isinstance(value[0], (list, tuple)):
            value = value[0]
        if not isinstance(value, (list, tuple)):
            return []
        return [int(chord) for chord in value]

    @staticmethod
    def sequence_text(chords):
        # KDE pads every key sequence with zero slots, which are not chords.
        return ", ".join(
            QKeySequence(chord).toString(QKeySequence.SequenceFormat.PortableText)
            for chord in chords if chord
        )

    def current_sequence(self, register=False):
        """The keys KDE has stored for our action.

        ``""`` means KDE says there are none; ``None`` means KDE could not be
        asked, so callers should keep what they already know.
        """
        if self.bus is None:
            return None
        try:
            if register:
                self.call("doRegister", "(as)", (self.action_id,))
            chords = self.first_sequence(
                self.call("shortcutKeys", "(as)", (self.action_id,)).unpack()
            )
        except Exception:
            return None
        return self.sequence_text(chords)

    def key_owner(self, chords):
        """Friendly name of another component holding this key, if there is one."""
        try:
            infos = self.call("getGlobalShortcutsByKey", "(i)", (chords[0],)).unpack()[0]
        except Exception:
            return None
        for info in infos:
            if len(info) >= 4 and info[2] != self.COMPONENT:
                return info[3] or info[2]
        return None

    def pump(self):
        # iteration(False) also polls the bus socket; pending() alone cannot
        # discover a signal that has not been dispatched yet.
        self.context.iteration(False)
        while self.context.pending():
            self.context.iteration(False)

    def call(self, method, signature, values):
        return self.bus.call_sync(
            self.SERVICE, self.CONTROL_PATH, self.CONTROL_INTERFACE, method,
            self.GLib.Variant(signature, values), None, self.Gio.DBusCallFlags.NONE, 5000, None,
        )

    def bind(self, sequence):
        if self.bus is None:
            self.error_callback(
                "Hotkeys are not available here, so the key was not saved. Bind "
                f"\"{shortcut_command()}\" in your desktop's keyboard settings instead."
            )
            return
        keys = QKeySequence(sequence)
        chords = [int(keys[index].toCombined()) for index in range(keys.count())]
        if not chords:
            self.error_callback("Press a key before saving.")
            return
        # kglobalaccel hands over a key that another component already owns,
        # which quietly breaks that app's shortcut, so ask first.
        try:
            available = self.call(
                "globalShortcutAvailable", "((ai)s)", ((chords,), self.COMPONENT),
            ).unpack()[0]
        except Exception:
            available = True
        if not available:
            owner = self.key_owner(chords)
            self.error_callback(
                f"KDE already uses {sequence}" + (f" for {owner}" if owner else "")
                + ". Pick another key."
            )
            return
        try:
            self.call("doRegister", "(as)", (self.action_id,))
            # a(ai) is an array of structs, so each key sequence must be wrapped
            # in a one-tuple; a bare list makes GLib refuse to build the variant.
            result = self.call(
                "setShortcutKeys", "(asa(ai)u)",
                (self.action_id, [(chords,)], self.SET_PRESENT | self.NO_AUTOLOADING),
            ).unpack()
        except Exception as error:
            self.error_callback(str(error))
            return
        # kglobalaccel answers with the keys it actually stored, which is the
        # old set when it refused the change. Trusting the call itself made the
        # app claim success for keys KDE never took.
        applied = self.first_sequence(result)
        if applied[:len(chords)] != chords:
            kept = self.sequence_text(applied) or "another key"
            self.error_callback(f"KDE kept {kept}. Pick another key.")
            return
        self.changed_callback(sequence)

    def activate(self, sequence):
        """Take KDE's stored key for as long as this instance runs.

        kglobalacceld forgets that an action is present when it restarts, so a
        key it still has stored would never fire again. Autoloading (no
        NO_AUTOLOADING flag) means this only marks the action present: the key
        KDE already has stays the one in use, and nothing is written back.
        """
        if self.bus is None:
            return
        keys = QKeySequence(sequence)
        chords = [int(keys[index].toCombined()) for index in range(keys.count())]
        if not chords:
            return
        try:
            self.call(
                "setShortcutKeys", "(asa(ai)u)",
                (self.action_id, [(chords,)], self.SET_PRESENT),
            )
        except Exception:
            pass

    def deactivate(self):
        """Give the key back, so KDE stops using it while the app is closed."""
        if self.bus is None:
            return
        try:
            self.call("setInactive", "(as)", (self.action_id,))
        except Exception:
            pass

    def pressed(self, _connection, _sender, _path, _interface, _signal, parameters, _user_data):
        _component, action, _timestamp = parameters.unpack()
        if action == self.ACTION:
            self.activated.emit()

    def shortcut_released(self, _connection, _sender, _path, _interface, _signal, parameters, _user_data):
        _component, action, _timestamp = parameters.unpack()
        if action == self.ACTION:
            self.released.emit()

    def stop(self):
        if getattr(self, "pump_timer", None) is not None:
            self.pump_timer.stop()
        self.bus = None


# ---------------------------------------------------------------------- app icons

ICON_FALLBACK = "application-x-executable"


def icon_directories():
    """Where desktop entries live, in the order a desktop reads them."""
    home = os.environ.get("XDG_DATA_HOME") or os.path.expanduser("~/.local/share")
    system = (os.environ.get("XDG_DATA_DIRS") or "/usr/local/share:/usr/share").split(":")
    return [Path(directory) / "applications" for directory in (home, *system) if directory]


def exec_program(command):
    """The executable an ``Exec=`` line runs, without arguments or field codes."""
    try:
        tokens = shlex.split(command)
    except ValueError:
        return None
    # Many entries start with env and its variables: Exec=env FOO=1 app %U.
    while tokens and (tokens[0] == "env" or re.fullmatch(r"[A-Za-z_]\w*=\S*", tokens[0])):
        tokens = tokens[1:]
    for token in tokens:
        if not token.startswith("%"):
            return os.path.basename(token)
    return None


class AppIcons:
    """Icons for processes, taken from the desktop entry that launches them.

    A process carries no icon of its own, so the closest honest source is the
    ``.desktop`` file whose ``Exec=`` runs the same executable: its ``Icon=``
    is what the menu shows for the app. The directories are scanned once,
    because they change far more rarely than the process list does.
    """

    def __init__(self):
        self.entries = None
        self.identities = None
        self.cache = {}

    def icon_for(self, process):
        program = self.executable(process.pid) or process.name
        if program not in self.cache:
            self.cache[program] = self.lookup(program)
        return self.cache[program]

    def identity(self, app, fallback):
        """The name and icon to show for an app, from its desktop entry.

        The entry's ``Name=`` is what the menu shows. The app id is a readable
        fallback, and the process name the last resort.
        """
        name, icon_name = (self.apps().get(app) if app else None) or ("", "")
        icon = self.first_icon(icon_name) if icon_name else QIcon()
        if icon.isNull() and fallback is not None:
            icon = self.icon_for(fallback)
        return name or app or (fallback.name if fallback is not None else ""), icon

    def lookup(self, program):
        return self.first_icon(self.programs().get(program, ""), program)

    @staticmethod
    def first_icon(name, program=""):
        candidates = []
        if name and "/" in name:
            # An entry may name a file instead of a theme icon, but only when
            # that file is actually there.
            if Path(name).exists():
                candidates.append(QIcon(name))
        elif name:
            candidates.append(QIcon.fromTheme(name))
        if program:
            candidates.append(QIcon.fromTheme(program))
        candidates.append(QIcon.fromTheme(ICON_FALLBACK))
        for icon in candidates:
            if not icon.isNull():
                return icon
        # A theme without the fallback: an empty icon still beats a broken one.
        return QIcon()

    def apps(self):
        """Desktop id -> (name, icon), straight from the menu entries."""
        self.programs()
        return self.identities

    def programs(self):
        """Executable name -> the icon its desktop entry names.

        Several entries can run the same binary, and a shared interpreter such
        as python3 is launched by many unrelated apps. Only an entry named
        after the binary, or a set of entries that agree on one icon, is trusted:
        a wrong icon is worse than the generic one.
        """
        if self.entries is not None:
            return self.entries
        candidates = {}
        self.identities = {}
        for directory in icon_directories():
            for path in sorted(directory.glob("*.desktop")):
                found = self.read_entry(path)
                if not found:
                    continue
                program, icon, name = found
                self.identities.setdefault(path.stem, (name, icon))
                if icon:
                    candidates.setdefault(program, []).append((path.stem, icon))
        self.entries = {}
        for program, found in candidates.items():
            named = [icon for stem, icon in found if stem.casefold() == program.casefold()]
            icons = {icon for _stem, icon in found}
            if named:
                self.entries[program] = named[0]
            elif len(icons) == 1:
                self.entries[program] = icons.pop()
        return self.entries

    @staticmethod
    def read_entry(path):
        program = icon = name = None
        try:
            with open(path, encoding="utf-8", errors="replace") as file:
                section = None
                for line in file:
                    line = line.strip()
                    if line.startswith("["):
                        if section == "[Desktop Entry]":
                            break
                        section = line
                        continue
                    if section != "[Desktop Entry]" or "=" not in line:
                        continue
                    key, value = line.split("=", 1)
                    if key == "Exec":
                        program = exec_program(value)
                    elif key == "Icon":
                        icon = value.strip()
                    elif key == "Name":
                        name = value.strip()
        except OSError:
            return None
        if not program or not icon:
            return None
        return program, icon, name

    @staticmethod
    def executable(pid):
        try:
            target = os.readlink(f"/proc/{pid}/exe")
        except OSError:
            return None
        # An updated or deleted binary keeps its path plus a suffix.
        return os.path.basename(target.removesuffix(" (deleted)")) or None


# ---------------------------------------------------------------------- main window

class ProcessFreezerWindow(QMainWindow):
    def __init__(self, config, targets=None):
        super().__init__()
        self.config = config
        self.targets = targets or TargetStore()
        self.freezer = Freezer()
        self.processes = {}
        self.active = {}
        # source -> process key: both triggers can hold the same freeze.
        self.holds = {}
        self.saved_target = self.targets.load()
        self.setWindowTitle("Process Freezer")
        self.setMinimumSize(640, 490)
        geometry = self.config.geometry
        if geometry.isEmpty():
            self.resize(760, 570)
        else:
            self.restoreGeometry(geometry)

        root = QWidget()
        root.setObjectName("root")
        self.setCentralWidget(root)
        layout = QVBoxLayout(root)
        layout.setContentsMargins(24, 22, 24, 18)
        layout.setSpacing(13)

        header = QHBoxLayout()
        header.setSpacing(8)
        title_stack = QVBoxLayout()
        title_stack.setSpacing(2)
        title = QLabel("Process Freezer")
        title.setObjectName("title")
        subtitle = QLabel("Select a process, then trigger a timed pause.")
        subtitle.setObjectName("muted")
        title_stack.addWidget(title)
        title_stack.addWidget(subtitle)
        header.addLayout(title_stack, 1)

        self.theme_combo = QComboBox()
        for label, value in (("System theme", "system"), ("Light", "light"), ("Dark", "dark")):
            self.theme_combo.addItem(label, value)
        self.theme_combo.setCurrentIndex(max(0, self.theme_combo.findData(self.config.theme)))
        self.theme_combo.setToolTip("Colour theme")
        self.theme_combo.currentIndexChanged.connect(self.change_theme)
        header.addWidget(self.theme_combo, 0, Qt.AlignmentFlag.AlignTop)

        self.refresh_button = QPushButton("Refresh")
        self.refresh_button.clicked.connect(self.refresh)
        header.addWidget(self.refresh_button, 0, Qt.AlignmentFlag.AlignTop)
        layout.addLayout(header)

        search_row = QHBoxLayout()
        search_row.setSpacing(8)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Filter processes…")
        self.search.textChanged.connect(self.render_rows)
        search_row.addWidget(self.search, 1)

        self.count_label = QLabel("")
        self.count_label.setObjectName("muted")
        search_row.addWidget(self.count_label)

        self.tree_view = QCheckBox("Tree")
        self.tree_view.setToolTip(
            "Nest each process's children under it and freeze them together"
        )
        self.tree_view.setChecked(self.config.tree_view)
        self.tree_view.toggled.connect(self.change_view)
        search_row.addWidget(self.tree_view)
        layout.addLayout(search_row)

        # The app icon each row shows, and the trees the user has collapsed.
        self.app_icons = AppIcons()
        self.collapsed = set()

        self.tree = QTreeWidget()
        self.tree.setColumnCount(4)
        self.tree.setHeaderLabels(["PROCESS", "PID", "MEMORY", "STATE"])
        # Headers line up with their cells: names are left, numbers right.
        for column in range(4):
            alignment = (
                Qt.AlignmentFlag.AlignLeft if column == 0 else Qt.AlignmentFlag.AlignRight
            ) | Qt.AlignmentFlag.AlignVCenter
            self.tree.headerItem().setTextAlignment(column, alignment)
        self.tree.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.tree.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.tree.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.tree.setRootIsDecorated(True)
        self.tree.setUniformRowHeights(True)
        self.tree.setIndentation(16)
        header_view = self.tree.header()
        header_view.setStretchLastSection(False)
        header_view.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for column, width in ((1, 80), (2, 100), (3, 90)):
            self.tree.setColumnWidth(column, width)
        self.tree.itemSelectionChanged.connect(self.selection_changed)
        self.tree.itemDoubleClicked.connect(self.double_clicked)
        self.tree.itemExpanded.connect(self.node_expanded)
        self.tree.itemCollapsed.connect(self.node_collapsed)

        self.empty_label = QLabel("")
        self.empty_label.setObjectName("empty")
        self.empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_label.setWordWrap(True)
        self.view = QStackedWidget()
        self.view.addWidget(self.tree)
        self.view.addWidget(self.empty_label)
        layout.addWidget(self.view, 1)

        for keys, slot in (
            (QKeySequence.StandardKey.Find, self.search.setFocus),
            (QKeySequence("Escape"), self.clear_filter),
            (QKeySequence("F5"), self.refresh),
        ):
            QShortcut(QKeySequence(keys), self).activated.connect(slot)

        controls = QHBoxLayout()
        controls.setSpacing(8)
        controls.addWidget(QLabel("Duration"))
        self.duration = DurationSpinBox()
        self.duration.setRange(MIN_DURATION_MS, MAX_DURATION_MS)
        self.duration.setSingleStep(50)
        self.duration.setSuffix(" ms")
        self.duration.setDecimals(0)
        self.duration.setValue(self.config.duration_ms)
        self.duration.valueChanged.connect(self.save_duration)
        controls.addWidget(self.duration)
        self.hold_mode = QCheckBox("Hold")
        self.hold_mode.setToolTip("Freeze while this button is held down")
        self.hold_mode.setChecked(self.config.hold_mode)
        self.hold_mode.toggled.connect(self.save_hold_mode)
        controls.addWidget(self.hold_mode)
        controls.addSpacing(10)
        controls.addWidget(QLabel("Hotkey"))
        self.hotkey_label = QLabel("Not set")
        self.hotkey_label.setObjectName("muted")
        controls.addWidget(self.hotkey_label, 1)
        self.hotkey_button = QPushButton("Bind")
        self.hotkey_button.clicked.connect(self.set_hotkey)
        controls.addWidget(self.hotkey_button)
        self.freeze_button = QPushButton("Freeze selected")
        self.freeze_button.setObjectName("primary")
        self.freeze_button.setEnabled(False)
        self.freeze_button.clicked.connect(self.freeze_selected)
        self.freeze_button.pressed.connect(self.hold_pressed)
        self.freeze_button.released.connect(self.hold_released)
        controls.addWidget(self.freeze_button)
        layout.addLayout(controls)

        self.status = QLabel("Select a process, bind a hotkey, then trigger a timed pause in the background.")
        self.status.setObjectName("status")
        # Some messages, notably the command to bind a shortcut, name a full
        # path and do not fit on one line.
        self.status.setWordWrap(True)
        layout.addWidget(self.status)

        self.hotkey = GlobalHotkey(
            self.freeze_saved_target, self.hotkey_released,
            self.set_hotkey_label, self.show_error, self.show_notice,
        )
        # KDE stores the binding, so it decides which key is active. Only ask it
        # about the key: registering here re-created Process Freezer in KDE's
        # shortcut settings on every launch, whether or not a key was bound.
        stored = self.hotkey.current_sequence()
        if stored is not None:
            self.config.hotkey = stored
        # Take the key while the window is open. Closing the window gives it
        # back, so KDE does not go on swallowing a shortcut for an app that is
        # not running.
        if stored:
            self.hotkey.activate(stored)
        # A key is only worth showing when something can deliver it: without a
        # shortcut service, naming a stored key would promise a hotkey that
        # does not fire.
        shown = self.config.hotkey if self.hotkey.bus is not None else ""
        self.hotkey_label.setText(shown or "Not set")
        self.hotkey_button.setText("Change" if shown else "Bind")

        hints = QApplication.instance().styleHints()
        if hasattr(hints, "colorSchemeChanged"):
            hints.colorSchemeChanged.connect(self.system_theme_changed)

        self.refresh()
        self.refresh_timer = QTimer(self)
        self.refresh_timer.setInterval(1800)
        self.refresh_timer.timeout.connect(self.refresh)
        self.refresh_timer.start()

    def sync_hotkey(self):
        """Adopt a binding changed in System Settings.

        kglobalaccel sends no signal when the key changes, so the periodic
        refresh asks it instead; the call is local and costs almost nothing.
        """
        stored = self.hotkey.current_sequence()
        if stored is None or stored == self.config.hotkey:
            return
        self.config.hotkey = stored
        self.hotkey_label.setText(stored or "Not set")
        self.hotkey_button.setText("Change" if stored else "Bind")

    def set_status(self, message, tone="muted"):
        self.status.setText(message)
        if self.status.property("tone") != tone:
            self.status.setProperty("tone", tone)
            self.status.style().unpolish(self.status)
            self.status.style().polish(self.status)

    def change_theme(self):
        mode = self.theme_combo.currentData()
        self.config.theme = mode
        apply_theme(QApplication.instance(), mode)

    def system_theme_changed(self, *_):
        if self.config.theme == "system":
            apply_theme(QApplication.instance(), "system")

    def save_hold_mode(self, checked):
        self.config.hold_mode = checked

    def refresh(self):
        self.sync_hotkey()
        self.processes = {process.pid: process for process in list_processes()}
        self.render_rows()

    def write_target(self):
        if not self.saved_target:
            return
        self.saved_target["duration"] = self.duration.value() / 1000
        try:
            self.targets.save(self.saved_target)
        except OSError as error:
            self.show_error(f"Could not save the target: {error}")

    def save_duration(self, value):
        self.config.duration_ms = int(value)
        self.write_target()

    def change_view(self, checked):
        self.config.tree_view = checked
        self.render_rows()

    def clear_filter(self):
        self.search.clear()

    @staticmethod
    def node_id(item):
        """What a row is remembered by: its PID, or the unit of a gathered app."""
        key = item.data(0, Qt.ItemDataRole.UserRole)
        if key:
            return key[0]
        return item.data(0, Qt.ItemDataRole.UserRole + 1)

    def node_expanded(self, item):
        identifier = self.node_id(item)
        if identifier:
            self.collapsed.discard(identifier)

    def node_collapsed(self, item):
        identifier = self.node_id(item)
        if identifier:
            self.collapsed.add(identifier)

    def double_clicked(self, item, _column):
        # The row under the pointer is what the user means, not whatever was
        # selected before the click.
        self.tree.setCurrentItem(item)
        self.freeze_selected()

    @staticmethod
    def describe(members, label=None):
        name = label or members[0].name
        if len(members) == 1:
            return name
        return f"{name} and {len(members) - 1} more processes"

    def current_label(self):
        item = self.tree.currentItem()
        return item.text(0) if item is not None else None

    def selection_changed(self):
        item = self.tree.currentItem()
        members = self.selected_members()
        process = members[0] if members else None
        if process:
            unit = item.data(0, Qt.ItemDataRole.UserRole + 1) if item is not None else None
            label = item.text(0) if item is not None else process.name
            target = {
                "pid": process.pid,
                "start_time": process.start_time,
                "name": label,
                "duration": self.duration.value() / 1000,
                # Remember whether the hotkey should take the whole tree or
                # just this process the next time it fires.
                "tree": len(members) > 1,
            }
            if unit:
                # A gathered app is remembered by its unit: its processes come
                # and go, and the hotkey looks them up again when it fires.
                target["unit"] = unit
            self.saved_target = target
            self.write_target()
            where = "" if unit else f" ({process.pid})"
            self.set_status(f"Saved target: {self.describe(members, label)}{where}.")
        self.update_selection()

    def app_row(self, node):
        """The row that gathers every root one app unit holds."""
        members = list(node.members())
        label, icon = self.app_icons.identity(
            app_id(node.unit), members[0] if members else None
        )
        frozen = any(member.scope and member.frozen for member in members)
        state = "Frozen" if frozen else (
            "Paused" if any(member.state in {"T", "t"} for member in members) else "Running"
        )
        item = QTreeWidgetItem([
            label, "", f"{sum(member.memory_mb for member in members)} MB", state,
        ])
        item.setData(0, Qt.ItemDataRole.UserRole + 1, node.unit)
        item.setIcon(0, icon)
        item.setToolTip(0, f"{label} · {len(members)} processes in this app")
        return item

    def add_node(self, parent, node):
        if node.process is None:
            item = self.app_row(node)
            identifier = node.unit
        else:
            process = node.process
            state = "Frozen" if process.frozen and process.scope else (
                "Paused" if process.state in {"T", "t"} else "Running"
            )
            item = QTreeWidgetItem(
                [process.name, str(process.pid), f"{process.memory_mb} MB", state]
            )
            item.setData(0, Qt.ItemDataRole.UserRole, process.key)
            item.setIcon(0, self.app_icons.icon_for(process))
            item.setToolTip(0, f"{process.name} ({process.pid})" + (
                f" · {node.size} processes in this tree" if node.children else ""
            ))
            identifier = process.pid
        for column in (1, 2, 3):
            item.setTextAlignment(column, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        if parent is None:
            self.tree.addTopLevelItem(item)
        else:
            parent.addChild(item)
        for child in node.children:
            self.add_node(item, child)
        if node.children:
            # Open unless the user closed this tree, so a refresh does not
            # reopen what they collapsed.
            item.setExpanded(identifier not in self.collapsed)
        return node.size

    def item_for(self, key):
        stack = [self.tree.topLevelItem(row) for row in range(self.tree.topLevelItemCount())]
        while stack:
            item = stack.pop()
            if item.data(0, Qt.ItemDataRole.UserRole) == key:
                return item
            stack.extend(item.child(row) for row in range(item.childCount()))
        return None

    def select_key(self, key):
        item = self.item_for(key)
        if item is None:
            return False
        parent = item.parent()
        while parent is not None:
            parent.setExpanded(True)
            parent = parent.parent()
        self.tree.setCurrentItem(item)
        self.tree.scrollToItem(item)
        return True

    def select_unit(self, unit):
        for row in range(self.tree.topLevelItemCount()):
            item = self.tree.topLevelItem(row)
            if item.data(0, Qt.ItemDataRole.UserRole + 1) == unit:
                self.tree.setCurrentItem(item)
                self.tree.scrollToItem(item)
                return True
        return False

    @staticmethod
    def matches(process, query):
        return query in process.name.casefold() or query in str(process.pid)

    def render_rows(self, *_):
        selected = self.selected_process()
        target_key = selected.key if selected else (
            (self.saved_target["pid"], int(self.saved_target["start_time"]))
            if self.saved_target else None
        )
        current = self.tree.currentItem()
        unit = current.data(0, Qt.ItemDataRole.UserRole + 1) if current is not None else None
        query = self.search.text().strip().casefold()
        self.tree.blockSignals(True)
        self.tree.clear()
        shown = 0
        if self.tree_view.isChecked():
            roots = app_forest(list(self.processes.values()))
            if query:
                # Parents stay as context for a matching child.
                roots = filter_forest(roots, lambda process: self.matches(process, query))
            for node in roots:
                shown += self.add_node(None, node)
        else:
            for process in self.processes.values():
                if query and not self.matches(process, query):
                    continue
                self.add_node(None, TreeNode(process))
                shown += 1
        if not (unit and self.select_unit(unit)):
            if not target_key or not self.select_key(target_key):
                # Nothing is saved yet, so no row should look selected.
                self.tree.clearSelection()
                self.tree.setCurrentItem(None)
        self.tree.blockSignals(False)
        total = len(self.processes)
        self.count_label.setText(f"{shown} of {total}" if shown != total else f"{total} processes")
        self.view.setCurrentWidget(self.tree if shown else self.empty_label)
        if not shown:
            text = self.search.text().strip()
            self.empty_label.setText(
                f"No processes match “{text}”." if text else "No processes to show."
            )
        self.update_selection()

    def item_processes(self, item):
        members = []
        stack = [item]
        while stack:
            current = stack.pop(0)
            key = current.data(0, Qt.ItemDataRole.UserRole)
            process = self.processes.get(key[0]) if key else None
            # The start time is part of the key: a recycled PID is a different
            # process, and freezing it would freeze the wrong thing.
            if process is not None and process.key == key:
                members.append(process)
            stack.extend(current.child(row) for row in range(current.childCount()))
        return members

    def selected_members(self):
        item = self.tree.currentItem()
        return self.item_processes(item) if item is not None else []

    def selected_process(self):
        members = self.selected_members()
        return members[0] if members else None

    def update_selection(self):
        members = self.selected_members()
        process = members[0] if members else None
        if process is None:
            self.freeze_button.setText("Freeze selected")
            self.freeze_button.setEnabled(False)
            return
        if self.holds_key(process.key):
            self.freeze_button.setText("Release to resume")
            self.freeze_button.setEnabled(True)
            return
        if any(member.scope and member.frozen for member in members):
            self.freeze_button.setText("Resume now")
            self.freeze_button.setEnabled(True)
            return
        self.freeze_button.setText(
            f"Freeze {len(members)} processes" if len(members) > 1 else "Freeze selected"
        )
        self.freeze_button.setEnabled(
            not any(member.state in {"T", "t"} for member in members)
        )

    @staticmethod
    def freezes_ourselves(members):
        # Freezing our own tree would hang the window until the watchdog thaws
        # it again, which looks exactly like a crash.
        return any(member.pid == os.getpid() for member in members)

    def freeze_selected(self, timed=False):
        if self.hold_mode.isChecked() and not timed:
            return
        members = self.selected_members()
        if not members:
            return
        if self.freezes_ourselves(members):
            self.show_error(
                "That tree includes Process Freezer itself. Select the process "
                "you want instead."
            )
            return
        if any(member.scope and member.frozen for member in members):
            self.resume_members(members)
            return
        seconds = self.duration.value() / 1000
        self.config.duration_ms = int(self.duration.value())
        self.freeze_button.setEnabled(False)
        try:
            freeze = self.freezer.pause(members, seconds)
            key = members[0].key
            timer = QTimer(self)
            timer.setSingleShot(True)
            timer.timeout.connect(lambda: self.finish_pause(key, freeze))
            self.active[key] = (freeze, timer)
            timer.start(round(self.duration.value()))
            self.set_status(
                f"Paused {self.describe(members, self.current_label())} "
                f"for {self.duration.value():g} ms."
            )
        except Exception as error:
            self.show_error(str(error))
        self.refresh()

    def resume_members(self, members):
        """Thaw what this window froze, or what was already frozen by hand."""
        active = self.active.pop(members[0].key, None)
        try:
            if active:
                active[0].resume()
            else:
                units = sorted({
                    member.scope for member in members if member.scope and member.frozen
                })
                self.freezer.thaw(units)
            self.set_status(f"Resumed {self.describe(members, self.current_label())}.")
        except Exception as error:
            self.show_error(str(error))
        self.refresh()

    def hold_pressed(self):
        if not self.hold_mode.isChecked():
            return
        members = self.selected_members()
        if not members or any(self.is_stopped(member) for member in members):
            return
        self.begin_hold(members, "Release the button to resume.", "button")

    @staticmethod
    def is_stopped(process):
        return process.state in {"T", "t"} or bool(process.scope and process.frozen)

    def holds_key(self, key):
        return key in self.holds.values()

    def begin_hold(self, members, release_hint, source):
        key = members[0].key
        if self.freezes_ourselves(members):
            self.show_error(
                "That tree includes Process Freezer itself. Select the process "
                "you want instead."
            )
            return
        if self.holds_key(key):
            # A second trigger for the same freeze: just note who else is holding
            # it, so releasing one does not resume it under the other.
            self.holds[source] = key
            self.set_status(
                f"Holding {self.describe(members, self.current_label())} paused. {release_hint}"
            )
            return
        try:
            # The watchdog is a safety net if the GUI dies while held.
            freeze = self.freezer.pause(members, 24 * 60 * 60)
            timer = QTimer(self)
            timer.setSingleShot(True)
            timer.timeout.connect(lambda: self.finish_pause(key, freeze))
            timer.start(24 * 60 * 60 * 1000)
            self.active[key] = (freeze, timer)
            self.holds[source] = key
            self.set_status(
                f"Holding {self.describe(members, self.current_label())} paused. {release_hint}"
            )
        except Exception as error:
            self.show_error(str(error))
        self.refresh()

    def hold_released(self, source="button"):
        key = self.holds.pop(source, None)
        if key is None or self.holds_key(key):
            # Another trigger is still holding this freeze.
            return
        active = self.active.pop(key, None)
        if not active:
            return
        freeze, timer = active
        timer.stop()
        try:
            freeze.resume()
            self.set_status("Process resumed.")
        except Exception as error:
            self.show_error(str(error))
        self.refresh()

    def freeze_saved_target(self):
        target = self.saved_target or self.targets.load()
        if not target:
            self.show_error("Choose a process first; no target is saved.")
            return
        unit = target.get("unit")
        if unit:
            # A gathered app is found again by its unit: the PIDs inside it are
            # not the ones that were selected.
            members = [
                process for process in list_processes()
                if unit_of(process.cgroup) == unit
            ]
            if not members:
                self.show_error(
                    "The saved app is no longer running. Choose it again from the list."
                )
                return
            process = members[0]
        else:
            process = read_process(int(target["pid"]))
            if process is None or process.start_time != int(target["start_time"]):
                self.show_error("The saved process has exited. Choose it again from the list.")
                return
            # The tree is rebuilt from a fresh scan rather than remembered from
            # the selection, so children that started or exited since then are
            # handled.
            members = subtree(list_processes(), process) if target.get("tree") else [process]
        if self.freezes_ourselves(members):
            self.show_error(
                "That tree includes Process Freezer itself. Select the process "
                "you want instead."
            )
            return
        if any(member.scope and member.frozen or member.state in {"T", "t"} for member in members):
            self.show_error("The saved process is already paused.")
            return
        if self.hold_mode.isChecked():
            self.begin_hold(members, "Release the hotkey to resume.", "hotkey")
            return
        if self.search.text():
            self.search.clear()
        if unit and self.select_unit(unit):
            self.freeze_selected(timed=True)
            return
        if self.select_key(process.key):
            self.freeze_selected(timed=True)
            return
        self.show_error("The saved process is hidden by the current filter.")

    def hotkey_released(self):
        self.hold_released("hotkey")

    def set_hotkey(self):
        current = self.hotkey_label.text()
        dialog = QDialog(self)
        dialog.setWindowTitle("Global hotkey")
        dialog.setMinimumWidth(430)
        form = QVBoxLayout(dialog)
        form.setContentsMargins(22, 20, 22, 18)
        form.setSpacing(11)
        heading = QLabel("Global hotkey")
        heading.setObjectName("dialogTitle")
        form.addWidget(heading)
        hint = QLabel(
            "Press the combination that freezes the saved process while you are in "
            "another app. KDE's shortcut service listens for it."
        )
        hint.setObjectName("muted")
        hint.setWordWrap(True)
        form.addWidget(hint)
        capture = QKeySequenceEdit(dialog)
        capture.setKeySequence(QKeySequence(current if current != "Not set" else "Ctrl+Alt+P"))
        form.addWidget(capture)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Cancel | QDialogButtonBox.StandardButton.Save,
            parent=dialog,
        )
        save_button = buttons.button(QDialogButtonBox.StandardButton.Save)
        save_button.setText("Save hotkey")
        save_button.setObjectName("primary")
        # Renaming a widget does not re-run the stylesheet selectors on it.
        save_button.style().unpolish(save_button)
        save_button.style().polish(save_button)
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("Cancel")
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        form.addSpacing(2)
        form.addWidget(buttons)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        sequence = capture.keySequence().toString(QKeySequence.SequenceFormat.PortableText)
        if not sequence:
            self.show_error("Press a key combination before saving.")
            return
        self.set_status(f"Listening for {sequence}…")
        self.hotkey.bind(sequence)

    def set_hotkey_label(self, value):
        self.hotkey_label.setText(value)
        self.config.hotkey = value if value != "Not set" else ""
        if value == "Not set":
            self.hotkey_button.setText("Bind")
            self.set_status("Select a process and bind a hotkey.")
        else:
            self.hotkey_button.setText("Change")
            self.set_status("Background hotkey is ready.")

    def finish_pause(self, key, freeze):
        for source, held in list(self.holds.items()):
            if held == key:
                del self.holds[source]
        try:
            freeze.resume()
            self.set_status("Process resumed.")
        except Exception as error:
            self.show_error(str(error))
        self.active.pop(key, None)
        self.refresh()

    def show_error(self, message):
        self.set_status(message, "error")

    def show_notice(self, message):
        self.set_status(message)

    def closeEvent(self, event):
        self.refresh_timer.stop()
        # Release the grab before the window goes away: KDE otherwise keeps the
        # shortcut active until the shortcut daemon restarts.
        self.hotkey.deactivate()
        self.hotkey.stop()
        for freeze, timer in self.active.values():
            timer.stop()
            try:
                freeze.resume()
            except Exception:
                pass
        self.config.geometry = self.saveGeometry()
        self.config.flush()
        event.accept()
