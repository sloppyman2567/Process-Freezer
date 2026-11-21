"""Everything on screen: colour themes, the global shortcut and the main window."""

import re
from dataclasses import asdict, dataclass
from string import Template

from PyQt6.QtCore import QObject, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import (
    QColor, QGuiApplication, QKeySequence, QPainter, QPainterPath, QPalette, QPen,
)
from PyQt6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QDialog, QDialogButtonBox, QDoubleSpinBox,
    QHBoxLayout, QKeySequenceEdit, QLabel, QLineEdit, QMainWindow, QPushButton,
    QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from .core import (
    MAX_DURATION_MS, MIN_DURATION_MS, Freezer, TargetStore, list_processes, read_process,
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
QTableWidget {
    background: $panel; border: 1px solid $line; border-radius: 8px;
    gridline-color: $line; selection-background-color: $selected; selection-color: $text;
    outline: 0;
}
QHeaderView::section {
    background: $background; color: $muted; border: 0; border-bottom: 1px solid $line;
    padding: 8px; font-size: 8pt; font-weight: 600;
}
QTableWidget::item { padding: 6px; border: 0; }
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

    def __init__(self, on_activated, on_released, changed, error):
        super().__init__()
        self.activated.connect(on_activated)
        self.released.connect(on_released)
        self.changed_callback = changed
        self.error_callback = error
        self.bus = None
        try:
            from gi.repository import Gio, GLib
        except ImportError:
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
                "command \"process-freezer --freeze\" in your desktop's keyboard "
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
                "\"process-freezer --freeze\" in your desktop's keyboard settings instead."
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
            self.error_callback(f"KDE kept {sequence} for something else. Pick another key.")
            return
        self.changed_callback(sequence)

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
        self.search = QLineEdit()
        self.search.setPlaceholderText("Filter processes…")
        self.search.textChanged.connect(self.render_rows)
        search_row.addWidget(self.search)
        layout.addLayout(search_row)

        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["PROCESS", "PID", "MEMORY", "STATE"])
        # Headers line up with their cells: names are left, numbers right.
        for column in range(4):
            alignment = (
                Qt.AlignmentFlag.AlignLeft if column == 0 else Qt.AlignmentFlag.AlignRight
            ) | Qt.AlignmentFlag.AlignVCenter
            self.table.horizontalHeaderItem(column).setTextAlignment(alignment)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().hide()
        header_view = self.table.horizontalHeader()
        header_view.setStretchLastSection(False)
        header_view.setSectionResizeMode(0, header_view.ResizeMode.Stretch)
        for column, width in ((1, 80), (2, 100), (3, 90)):
            self.table.setColumnWidth(column, width)
        self.table.itemSelectionChanged.connect(self.selection_changed)
        layout.addWidget(self.table, 1)

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
        layout.addWidget(self.status)

        self.hotkey = GlobalHotkey(
            self.freeze_saved_target, self.hotkey_released,
            self.set_hotkey_label, self.show_error,
        )
        if self.config.hotkey:
            self.hotkey.bind(self.config.hotkey)
            self.hotkey_button.setText("Change")

        hints = QApplication.instance().styleHints()
        if hasattr(hints, "colorSchemeChanged"):
            hints.colorSchemeChanged.connect(self.system_theme_changed)

        self.refresh()
        self.refresh_timer = QTimer(self)
        self.refresh_timer.setInterval(1800)
        self.refresh_timer.timeout.connect(self.refresh)
        self.refresh_timer.start()

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
        selected = self.selected_process()
        self.processes = {p.pid: p for p in list_processes()}
        self.render_rows()
        if selected and selected.pid in self.processes and self.processes[selected.pid].key == selected.key:
            for row in range(self.table.rowCount()):
                if int(self.table.item(row, 1).text()) == selected.pid:
                    self.table.selectRow(row)
                    break
        self.update_selection()

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

    def selection_changed(self):
        process = self.selected_process()
        if process:
            self.saved_target = {
                "pid": process.pid,
                "start_time": process.start_time,
                "name": process.name,
                "duration": self.duration.value() / 1000,
            }
            self.write_target()
            self.set_status(f"Saved target: {process.name} ({process.pid}).")
        self.update_selection()

    def render_rows(self, *_):
        selected = self.selected_process()
        target_key = selected.key if selected else (
            (self.saved_target["pid"], self.saved_target["start_time"])
            if self.saved_target else None
        )
        query = self.search.text().strip().casefold()
        self.table.blockSignals(True)
        self.table.setRowCount(0)
        for process in self.processes.values():
            if query and query not in process.name.casefold() and query not in str(process.pid):
                continue
            row = self.table.rowCount()
            self.table.insertRow(row)
            state = "Frozen" if process.frozen and process.scope else "Paused" if process.state in {"T", "t"} else "Running"
            values = (process.name, str(process.pid), f"{process.memory_mb} MB", state)
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                if column in (1, 2, 3):
                    item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                self.table.setItem(row, column, item)
            if target_key and process.key == target_key:
                self.table.selectRow(row)
        if not target_key:
            # Nothing is saved yet, so no row should look selected.
            self.table.clearSelection()
            self.table.setCurrentCell(-1, -1)
        self.table.blockSignals(False)
        self.update_selection()

    def selected_process(self):
        row = self.table.currentRow() if hasattr(self, "table") else -1
        if row < 0 or self.table.item(row, 1) is None:
            return None
        try:
            return self.processes.get(int(self.table.item(row, 1).text()))
        except (ValueError, AttributeError):
            return None

    def update_selection(self):
        process = self.selected_process()
        frozen = bool(process and process.scope and process.frozen)
        if process and self.holds_key(process.key):
            self.freeze_button.setText("Release to resume")
            self.freeze_button.setEnabled(True)
            return
        self.freeze_button.setText("Resume now" if frozen else "Freeze selected")
        self.freeze_button.setEnabled(process is not None and (frozen or not process.frozen and process.state not in {"T", "t"}))

    def freeze_selected(self, timed=False):
        if self.hold_mode.isChecked() and not timed:
            return
        process = self.selected_process()
        if process is None:
            return
        if process.scope and process.frozen:
            active = self.active.pop(process.key, None)
            try:
                self.freezer.resume(process.scope, active[1] if active else None)
                if active:
                    active[2].stop()
                self.set_status(f"Resumed {process.name}.")
            except Exception as error:
                self.show_error(str(error))
            self.refresh()
            return
        seconds = self.duration.value() / 1000
        self.config.duration_ms = int(self.duration.value())
        self.freeze_button.setEnabled(False)
        try:
            unit, watchdog = self.freezer.pause(process, seconds)
            key = process.key
            timer = QTimer(self)
            timer.setSingleShot(True)
            timer.timeout.connect(lambda: self.finish_pause(key, unit, watchdog))
            self.active[key] = (unit, watchdog, timer)
            timer.start(round(self.duration.value()))
            self.set_status(f"Paused {process.name} for {self.duration.value():g} ms.")
        except Exception as error:
            self.show_error(str(error))
        self.refresh()

    def hold_pressed(self):
        if not self.hold_mode.isChecked():
            return
        process = self.selected_process()
        if process is None or process.state in {"T", "t"} or process.frozen:
            return
        self.begin_hold(process, "Release the button to resume.", "button")

    def holds_key(self, key):
        return key in self.holds.values()

    def begin_hold(self, process, release_hint, source):
        if self.holds_key(process.key):
            # A second trigger for the same freeze: just note who else is holding
            # it, so releasing one does not resume it under the other.
            self.holds[source] = process.key
            self.set_status(f"Holding {process.name} paused. {release_hint}")
            return
        try:
            # The watchdog is a safety net if the GUI dies while held.
            unit, watchdog = self.freezer.pause(process, 24 * 60 * 60)
            timer = QTimer(self)
            timer.setSingleShot(True)
            timer.timeout.connect(lambda: self.finish_pause(process.key, unit, watchdog))
            timer.start(24 * 60 * 60 * 1000)
            self.active[process.key] = (unit, watchdog, timer)
            self.holds[source] = process.key
            self.set_status(f"Holding {process.name} paused. {release_hint}")
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
        unit, watchdog, timer = active
        timer.stop()
        try:
            self.freezer.resume(unit, watchdog)
            self.set_status("Process resumed.")
        except Exception as error:
            self.show_error(str(error))
        self.refresh()

    def freeze_saved_target(self):
        target = self.saved_target or self.targets.load()
        if not target:
            self.show_error("Choose a process first; no target is saved.")
            return
        process = read_process(int(target["pid"]))
        if process is None or process.start_time != int(target["start_time"]):
            self.show_error("The saved process has exited. Choose it again from the list.")
            return
        if process.scope and process.frozen or process.state in {"T", "t"}:
            self.show_error("The saved process is already paused.")
            return
        if self.hold_mode.isChecked():
            self.begin_hold(process, "Release the hotkey to resume.", "hotkey")
            return
        if self.search.text():
            self.search.clear()
        for row in range(self.table.rowCount()):
            if int(self.table.item(row, 1).text()) == process.pid:
                self.table.selectRow(row)
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

    def finish_pause(self, key, unit, watchdog):
        for source, held in list(self.holds.items()):
            if held == key:
                del self.holds[source]
        try:
            self.freezer.resume(unit, watchdog)
            self.set_status("Process resumed.")
        except Exception as error:
            self.show_error(str(error))
        self.active.pop(key, None)
        self.refresh()

    def show_error(self, message):
        self.set_status(message, "error")

    def closeEvent(self, event):
        self.refresh_timer.stop()
        self.hotkey.stop()
        for unit, watchdog, timer in self.active.values():
            timer.stop()
            try:
                self.freezer.resume(unit, watchdog)
            except Exception:
                pass
        self.config.geometry = self.saveGeometry()
        self.config.flush()
        event.accept()
