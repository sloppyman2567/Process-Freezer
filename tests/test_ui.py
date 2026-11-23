"""Tests for what the window says when the global hotkey is unavailable.

Only the shortcut service discovery is exercised here: no window is built and
no QApplication is started, so the suite stays headless.
"""

import os
import sys

import pytest

pytest.importorskip("PyQt6")

from PyQt6.QtGui import QKeySequence  # noqa: E402

from processfreezer import ui  # noqa: E402


def make_hotkey(errors, notices):
    """A GlobalHotkey whose gi import fails, collecting what it reports."""
    return ui.GlobalHotkey(
        lambda: None, lambda: None, lambda *_: None, errors.append, notices.append,
    )


def test_missing_pygobject_names_the_package(monkeypatch):
    monkeypatch.setitem(sys.modules, "gi", None)
    monkeypatch.delattr(sys, "frozen", raising=False)
    errors, notices = [], []
    make_hotkey(errors, notices)
    assert notices == []
    assert len(errors) == 1
    assert "python-gobject" in errors[0]


def test_frozen_executable_says_the_hotkey_is_not_built_in(monkeypatch):
    # A bundled executable cannot import the system PyGObject, so pointing at
    # a package to install would send the user nowhere.
    monkeypatch.setitem(sys.modules, "gi", None)
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    errors, notices = [], []
    make_hotkey(errors, notices)
    assert errors == []
    assert "not built into this executable" in notices[0]
    assert f"{sys.executable} --freeze" in notices[0]


class FakeVariant:
    """A stand-in for GLib.Variant that records what the app asked KDE for."""

    def __init__(self, signature, value):
        self.signature = signature
        self.value = value


class FakeReply:
    def __init__(self, value):
        self.value = value

    def unpack(self):
        return self.value


class FakeBus:
    """A session bus that records calls and answers ``shortcutKeys``."""

    def __init__(self, sequences=()):
        self.calls = []
        # a(ai): one struct per stored key sequence, holding the chord ints.
        self.reply = (tuple((list(chords),) for chords in sequences),)

    def call_sync(self, _service, _path, _interface, method, variant, *_rest):
        self.calls.append((method, variant))
        return FakeReply(self.reply)

    def methods(self):
        return [method for method, _variant in self.calls]


class FakeGLib:
    Variant = FakeVariant


class FakeGio:
    class DBusCallFlags:
        NONE = 0


F10 = 16777273


@pytest.fixture
def no_pygobject(monkeypatch):
    """Never import the system PyGObject: the fake bus stands in for it.

    Importing it here would also make the gi test below see a usable module,
    and it would then take the session-bus path instead of the frozen one.
    """
    monkeypatch.setitem(sys.modules, "gi", None)


def wired_hotkey(*sequences):
    """A GlobalHotkey whose D-Bus calls go to a recording bus instead."""
    errors, notices = [], []
    hotkey = make_hotkey(errors, notices)
    hotkey.bus = FakeBus(sequences)
    hotkey.Gio, hotkey.GLib = FakeGio, FakeGLib
    return hotkey


def test_startup_asks_kde_without_registering_anything(no_pygobject):
    # Registering here put Process Freezer into KDE's shortcut settings on
    # every launch, whether or not a key had ever been bound.
    hotkey = wired_hotkey((F10, 0, 0, 0))
    assert hotkey.current_sequence() == "F10"
    assert hotkey.bus.methods() == ["shortcutKeys"]
    hotkey.stop()


def test_activate_keeps_the_key_kde_already_has(no_pygobject):
    hotkey = wired_hotkey()
    hotkey.activate("Ctrl+Alt+P")
    method, variant = hotkey.bus.calls[0]
    assert method == "setShortcutKeys"
    action_id, sequences, flags = variant.value
    assert action_id == hotkey.action_id
    # Autoloading and present: the daemon keeps the key it stores and only
    # marks the action present. Sending new keys here put a stale key back.
    assert flags == ui.GlobalHotkey.SET_PRESENT
    assert not flags & ui.GlobalHotkey.NO_AUTOLOADING
    assert sequences == [([int(QKeySequence("Ctrl+Alt+P")[0].toCombined())],)]
    hotkey.stop()


def test_deactivate_gives_the_key_back(no_pygobject):
    hotkey = wired_hotkey()
    hotkey.deactivate()
    method, variant = hotkey.bus.calls[0]
    assert method == "setInactive"
    assert variant.value == (hotkey.action_id,)
    hotkey.stop()


def test_window_takes_the_key_while_open_and_releases_it_on_close(tmp_path, monkeypatch, no_pygobject):
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    from PyQt6.QtWidgets import QApplication

    from processfreezer import core
    from processfreezer.core import Config

    recording = {}

    class RecordingHotkey(ui.GlobalHotkey):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.bus = FakeBus(((F10, 0, 0, 0),))
            self.Gio, self.GLib = FakeGio, FakeGLib
            recording["bus"] = self.bus

    monkeypatch.setattr(ui, "GlobalHotkey", RecordingHotkey)
    app = QApplication.instance() or QApplication(["process-freezer-test"])
    window = ui.ProcessFreezerWindow(
        Config(), core.TargetStore(tmp_path / "target.json", tmp_path / "legacy.json"),
    )
    methods = recording["bus"].methods()
    assert "doRegister" not in methods
    # Ask KDE what it has, then take that key; the refresh asks it again.
    assert methods[:2] == ["shortcutKeys", "setShortcutKeys"]
    assert window.hotkey_label.text() == "F10"
    window.close()
    assert recording["bus"].methods()[-1] == "setInactive"
    app.processEvents()


def build_window(tmp_path, monkeypatch):
    """A real window, with its process list replaced by the test's own later."""
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    from PyQt6.QtWidgets import QApplication

    from processfreezer import core

    app = QApplication.instance() or QApplication(["process-freezer-test"])
    window = ui.ProcessFreezerWindow(
        core.Config(), core.TargetStore(tmp_path / "target.json", tmp_path / "legacy.json"),
    )
    # Qt caches the config directory for the whole process, so a test that ran
    # before this one can leave hold mode and the duration behind. Pin what the
    # window tests depend on instead of inheriting another test's settings.
    window.hold_mode.setChecked(False)
    window.duration.setValue(core.DEFAULT_DURATION_MS)
    return app, core, window


def three_processes(core):
    return [
        core.Process(500, "app", "S", 10, 900, "/user.slice/app.slice/app-500.scope", False, 1),
        core.Process(501, "app", "S", 4, 901, "/user.slice/app.slice/app-500.scope", False, 500),
        core.Process(502, "app", "S", 4, 902, "/user.slice/app.slice/app-500.scope", False, 501),
        core.Process(600, "other", "S", 4, 903, "/user.slice/app.slice/app-600.scope", False, 1),
    ]


def test_tree_view_freezes_a_process_with_everything_below_it(tmp_path, monkeypatch, no_pygobject):
    app, core, window = build_window(tmp_path, monkeypatch)
    window.processes = {process.pid: process for process in three_processes(core)}
    window.tree_view.setChecked(True)
    window.render_rows()
    item = window.item_for((500, 900))
    assert item is not None
    assert item.childCount() == 1
    window.tree.setCurrentItem(item)
    assert [process.pid for process in window.selected_members()] == [500, 501, 502]
    assert window.freeze_button.text() == "Freeze 3 processes"
    window.close()
    app.processEvents()


def test_flat_view_selects_only_the_row_it_shows(tmp_path, monkeypatch, no_pygobject):
    app, core, window = build_window(tmp_path, monkeypatch)
    window.processes = {process.pid: process for process in three_processes(core)}
    window.tree_view.setChecked(False)
    window.render_rows()
    item = window.item_for((500, 900))
    assert item is not None and item.childCount() == 0
    window.tree.setCurrentItem(item)
    assert [process.pid for process in window.selected_members()] == [500]
    assert window.freeze_button.text() == "Freeze selected"
    window.close()
    app.processEvents()


def test_a_timed_freeze_resumes_the_scopes_it_started(tmp_path, monkeypatch, no_pygobject):
    # The timer used to call the freezer with the old single-scope arguments,
    # so the process was never thawed when the pause ran out.
    app, core, window = build_window(tmp_path, monkeypatch)
    resumed = []

    class FakeFreeze:
        def resume(self):
            resumed.append(True)

    window.active[(1, 2)] = (FakeFreeze(), window.refresh_timer)
    window.finish_pause((1, 2), FakeFreeze())
    assert resumed == [True]
    assert window.status.text() == "Process resumed."
    assert (1, 2) not in window.active
    window.close()
    app.processEvents()


def test_a_tree_that_includes_the_window_is_refused(tmp_path, monkeypatch, no_pygobject):
    # Freezing the tree this window sits in would stop the window itself, and
    # look like the app crashed until the watchdog thawed it.
    app, core, window = build_window(tmp_path, monkeypatch)
    pid = os.getpid()
    window.processes = {pid: core.Process(pid, "process-freezer", "S", 5, 1, "/x", False, 0)}
    window.render_rows()
    window.tree.setCurrentItem(window.item_for((pid, 1)))
    calls = []
    monkeypatch.setattr(window.freezer, "pause", lambda *args: calls.append(args))
    window.freeze_selected()
    assert calls == []
    assert "Process Freezer itself" in window.status.text()
    assert window.status.property("tone") == "error"
    window.close()
    app.processEvents()


def test_a_filter_keeps_the_parents_of_a_matching_child(tmp_path, monkeypatch, no_pygobject):
    app, core, window = build_window(tmp_path, monkeypatch)
    window.processes = {process.pid: process for process in three_processes(core)}
    window.tree_view.setChecked(True)
    window.search.setText("other")
    shown = [
        window.tree.topLevelItem(row).text(0)
        for row in range(window.tree.topLevelItemCount())
    ]
    assert shown == ["other"]
    assert window.count_label.text() == "1 of 4"
    window.search.setText("nothing-matches-this")
    assert window.tree.topLevelItemCount() == 0
    assert window.view.currentWidget() is window.empty_label
    window.close()
    app.processEvents()


def test_the_window_lists_apps_instead_of_one_systemd_row(tmp_path, monkeypatch, no_pygobject):
    app, core, window = build_window(tmp_path, monkeypatch)
    unit = "/user.slice/app.slice/app-flatpak-MyApp-1.scope"
    window.processes = {
        1: core.Process(1, "systemd", "S", 4, 900, "/user.slice/init.scope", False, 0),
        100: core.Process(100, "bwrap", "S", 5, 901, unit, False, 1),
        200: core.Process(200, "bwrap", "S", 5, 902, unit, False, 1),
        300: core.Process(300, "konsole", "S", 5, 903,
                          "/user.slice/app.slice/app-org.kde.konsole-4.scope", False, 1),
    }
    window.tree_view.setChecked(True)
    window.render_rows()
    rows = [
        window.tree.topLevelItem(row).text(0)
        for row in range(window.tree.topLevelItemCount())
    ]
    # The manager is not a row, and the two bwrap roots are one app.
    assert rows == ["MyApp", "konsole"]
    window.tree.setCurrentItem(window.tree.topLevelItem(0))
    assert sorted(process.pid for process in window.selected_members()) == [100, 200]
    assert window.freeze_button.text() == "Freeze 2 processes"
    # Remembered by unit, because the PIDs inside the app are not stable.
    assert window.saved_target["unit"] == "app-flatpak-MyApp-1.scope"
    window.close()
    app.processEvents()


def test_the_hotkey_finds_a_gathered_app_again(tmp_path, monkeypatch, no_pygobject):
    app, core, window = build_window(tmp_path, monkeypatch)
    unit = "/user.slice/app.slice/app-flatpak-MyApp-1.scope"
    processes = [
        core.Process(100, "bwrap", "S", 5, 901, unit, False, 1),
        core.Process(200, "bwrap", "S", 5, 902, unit, False, 1),
    ]
    window.processes = {process.pid: process for process in processes}
    window.render_rows()
    window.saved_target = {
        "pid": 100, "start_time": 901, "name": "MyApp",
        "unit": "app-flatpak-MyApp-1.scope",
    }
    monkeypatch.setattr(ui, "list_processes", lambda: processes)
    paused = []

    class FakeFreeze:
        def resume(self):
            pass

    def fake_pause(members, seconds):
        paused.append([process.pid for process in members])
        return FakeFreeze()

    monkeypatch.setattr(window.freezer, "pause", fake_pause)
    window.freeze_saved_target()
    assert paused == [[100, 200]]
    assert window.status.text().startswith("Paused MyApp")
    window.close()
    app.processEvents()


def test_window_reports_it_as_a_note_not_an_error(monkeypatch):
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    monkeypatch.setitem(sys.modules, "gi", None)
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    from PyQt6.QtWidgets import QApplication

    from processfreezer.core import Config

    app = QApplication.instance() or QApplication(["process-freezer-test"])
    window = ui.ProcessFreezerWindow(Config())
    assert window.status.property("tone") != "error"
    assert f"{sys.executable} --freeze" in window.status.text()
    # A stored key that nothing can register must not look active.
    assert window.hotkey_label.text() == "Not set"
    assert window.hotkey_button.text() == "Bind"
    window.deleteLater()
    app.processEvents()
