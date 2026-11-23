"""Tests for the parts that do not need a desktop session.

Everything here reads /proc, /sys/fs/cgroup and temporary config files, so the
suite runs headless.
"""

import io
import json
import os
import sys

import pytest

from processfreezer import core, watchdog


def test_reads_this_process():
    process = core.read_process(os.getpid())
    assert process is not None
    assert process.pid == os.getpid()
    assert process.start_time > 0
    assert process.state != "Z"
    assert process.memory_mb >= 0
    assert process.scope is None


def test_list_processes_includes_this_process():
    assert os.getpid() in {process.pid for process in core.list_processes()}


def test_list_processes_is_sorted_by_name():
    names = [process.name.casefold() for process in core.list_processes()]
    assert names == sorted(names)


def fake_process(pid, name="app", ppid=0, state="S", frozen=False,
                 cgroup="/user.slice/app.scope"):
    return core.Process(pid, name, state, 0, 1000 + pid, cgroup, frozen, ppid)


def test_the_tree_nests_children_under_their_parent():
    parent = fake_process(100, "firefox", ppid=1)
    child = fake_process(101, "firefox", ppid=100)
    grandchild = fake_process(102, "firefox", ppid=101)
    forest = core.build_forest([parent, child, grandchild])
    assert len(forest) == 1
    assert [process.pid for process in forest[0].members()] == [100, 101, 102]
    assert forest[0].size == 3


def test_a_process_whose_parent_is_not_in_the_list_starts_its_own_tree():
    forest = core.build_forest([
        fake_process(1, "init", ppid=0),
        fake_process(200, "app", ppid=1),
        fake_process(300, "orphan", ppid=999),
    ])
    assert sorted(node.process.pid for node in forest) == [1, 300]


def test_a_pid_loop_leaves_every_process_in_the_forest():
    # PID reuse can leave two processes naming each other as parent.
    forest = core.build_forest([
        fake_process(10, "a", ppid=11), fake_process(11, "b", ppid=10),
    ])
    assert sum(node.size for node in forest) == 2


def test_filtering_a_tree_keeps_the_parent_of_a_match():
    forest = core.build_forest([
        fake_process(100, "firefox", ppid=1),
        fake_process(101, "firefox", ppid=100),
        fake_process(102, "Web Content", ppid=101),
    ])
    filtered = core.filter_forest(forest, lambda process: process.pid == 102)
    assert len(filtered) == 1
    assert filtered[0].process.pid == 100
    assert [child.process.pid for child in filtered[0].children] == [101]
    assert [child.process.pid for child in filtered[0].children[0].children] == [102]


APP_SLICE = "/user.slice/user-1000.slice/user@1000.service/app.slice"


def test_unit_of_names_the_app_the_launcher_started():
    assert core.unit_of(f"{APP_SLICE}/app-org.kde.konsole-4004.scope/main.scope") == (
        "app-org.kde.konsole-4004.scope"
    )


@pytest.mark.parametrize("path", [
    "/user.slice/user-1000.slice/session-2.scope",
    "/user.slice/user-1000.slice/user@1000.service/init.scope",
    "/user.slice",
    "",
])
def test_unit_of_ignores_units_that_belong_to_the_session(path):
    assert core.unit_of(path) == ""


def test_app_id_reads_the_desktop_id_out_of_a_unit():
    assert core.app_id("app-org.kde.konsole-4004.scope") == "org.kde.konsole"
    assert core.app_id(r"app-brave\x2dorigin@64f78c90.service") == "brave-origin"
    assert core.app_id("app-flatpak-rocks.shy.VacuumTube-1184160112.scope") == (
        "rocks.shy.VacuumTube"
    )
    assert core.app_id("plasma-plasmashell.service") == ""


def test_the_tree_starts_at_the_apps_not_at_the_session_manager():
    forest = core.app_forest([
        fake_process(1, "systemd", ppid=0),
        fake_process(100, "konsole", ppid=1, cgroup=f"{APP_SLICE}/app-konsole-4.scope"),
        fake_process(101, "bash", ppid=100, cgroup=f"{APP_SLICE}/app-konsole-4.scope"),
        fake_process(200, "firefox", ppid=1, cgroup=f"{APP_SLICE}/app-firefox-9.scope"),
    ])
    # The manager's own row is gone; its children are the top level.
    assert [node.process.pid for node in forest] == [100, 200]
    assert [process.pid for process in forest[0].members()] == [100, 101]


def test_roots_of_one_app_unit_share_a_row():
    unit = f"{APP_SLICE}/app-flatpak-rocks.shy.VacuumTube-1184160112.scope"
    forest = core.app_forest([
        fake_process(1, "systemd", ppid=0),
        fake_process(100, "bwrap", ppid=1, cgroup=unit),
        fake_process(200, "bwrap", ppid=1, cgroup=unit),
        fake_process(300, "konsole", ppid=1, cgroup=f"{APP_SLICE}/app-konsole-4.scope"),
    ])
    assert len(forest) == 2
    gathered = forest[0]
    # A row with no process of its own, holding both roots of the app.
    assert gathered.process is None
    assert gathered.unit.endswith("VacuumTube-1184160112.scope")
    assert gathered.size == 2
    # A unit with a single root stays an ordinary process row.
    assert forest[1].process.pid == 300


def test_subtree_of_an_app_lists_the_processes_it_started():
    processes = [
        fake_process(100, "firefox", ppid=1),
        fake_process(101, "firefox", ppid=100),
        fake_process(200, "other", ppid=1),
    ]
    members = core.subtree(processes, processes[0])
    assert [process.pid for process in members] == [100, 101]
    assert [process.pid for process in core.subtree(processes, processes[2])] == [200]


def test_subtree_falls_back_to_the_process_itself():
    root = fake_process(100, "firefox", ppid=1)
    assert core.subtree([fake_process(200, "other", ppid=1)], root) == [root]


def test_read_process_returns_none_for_a_pid_that_does_not_exist():
    assert core.read_process(0) is None


@pytest.mark.skipif(os.getuid() == 0, reason="root owns every process")
def test_read_process_skips_processes_of_other_users():
    assert core.read_process(1) is None


def test_cgroup_path_of_this_process_is_a_string():
    assert isinstance(core.cgroup_path(os.getpid()), str)


def test_scope_is_read_out_of_the_cgroup_path():
    process = core.Process(
        42, "sleep", "S", 0, 900, "/user.slice/process-freezer-42-900.scope", False,
    )
    assert process.scope == "process-freezer-42-900.scope"


@pytest.mark.parametrize("path", [
    "",
    "/user.slice/app.slice",
    "/user.slice/process-freezer-42-900.service",
])
def test_scope_ignores_cgroups_that_are_not_a_freezer_scope(path):
    assert core.Process(42, "sleep", "S", 0, 900, path, False).scope is None


def test_scope_is_found_for_a_cgroup_inside_the_scope():
    # Freezing the scope freezes everything below it, so a process in a child
    # cgroup still gets resumed by thawing the scope.
    process = core.Process(
        42, "sleep", "S", 0, 900, "/user.slice/process-freezer-42-900.scope/child", False,
    )
    assert process.scope == "process-freezer-42-900.scope"


def test_is_frozen_is_false_for_a_cgroup_that_does_not_exist():
    assert core.is_frozen("/process-freezer-tests-missing") is False


def test_target_store_round_trips(tmp_path):
    store = core.TargetStore(tmp_path / "target.json", tmp_path / "legacy.json")
    assert store.load() is None
    target = {"pid": 1234, "start_time": 5678, "name": "sleep", "duration": 2.5}
    store.save(target)
    assert store.load() == target


def test_target_store_reads_the_legacy_file_as_a_fallback(tmp_path):
    legacy = tmp_path / "legacy.json"
    legacy.write_text(json.dumps({"pid": 1, "start_time": 2, "name": "old"}))
    store = core.TargetStore(tmp_path / "target.json", legacy)
    assert store.load()["name"] == "old"


@pytest.mark.parametrize("content", ["{not json", "[]", '{"pid": 1}'])
def test_target_store_ignores_unusable_files(tmp_path, content):
    path = tmp_path / "target.json"
    path.write_text(content)
    assert core.TargetStore(path, tmp_path / "missing.json").load() is None


@pytest.fixture
def config(tmp_path, monkeypatch):
    """A Config in a temporary config home, with no legacy files in sight."""
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setattr(core, "LEGACY_SETTINGS_FILE", tmp_path / "missing.conf")
    return core.Config()


def test_config_defaults(config):
    assert config.theme == "system"
    assert config.duration_ms == core.DEFAULT_DURATION_MS
    assert config.hotkey == ""
    assert config.hold_mode is False


def test_config_stores_values_and_clamps_the_duration(config):
    config.theme = "dark"
    config.duration_ms = 10 * core.MAX_DURATION_MS
    config.hotkey = "Ctrl+Alt+P"
    config.hold_mode = True
    assert config.theme == "dark"
    assert config.duration_ms == core.MAX_DURATION_MS
    assert config.hotkey == "Ctrl+Alt+P"
    assert config.hold_mode is True


def test_config_falls_back_for_an_unknown_theme(config):
    config.theme = "solarized"
    assert config.theme == "system"


def test_watchdog_command_runs_the_module_from_source(monkeypatch):
    monkeypatch.delattr(sys, "frozen", raising=False)
    assert core.watchdog_command("unit.scope", 3) == [
        sys.executable, "-m", "processfreezer.watchdog", "unit.scope", "3",
    ]


def test_watchdog_command_uses_the_hidden_flag_in_a_frozen_build(monkeypatch):
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    assert core.watchdog_command("unit.scope", 3) == [
        sys.executable, "--watchdog", "unit.scope", "3",
    ]


class FakeStdin:
    def __init__(self, data):
        self.buffer = io.BytesIO(data)


@pytest.fixture
def thaw_calls(monkeypatch):
    calls = []
    monkeypatch.setattr(watchdog.subprocess, "run", lambda args, **kwargs: calls.append(args))
    return calls


def test_watchdog_thaws_at_once_when_the_parent_never_started(monkeypatch, thaw_calls):
    monkeypatch.setattr(watchdog.sys, "stdin", FakeStdin(b""))
    slept = []
    monkeypatch.setattr(watchdog.time, "sleep", slept.append)
    assert watchdog.main(["unit.scope", "5"]) == 0
    assert slept == []
    assert thaw_calls == [["systemctl", "--user", "thaw", "unit.scope"]]


def test_watchdog_sleeps_for_the_requested_seconds(monkeypatch, thaw_calls):
    monkeypatch.setattr(watchdog.sys, "stdin", FakeStdin(b"start"))
    slept = []
    monkeypatch.setattr(watchdog.time, "sleep", slept.append)
    assert watchdog.main(["unit.scope", "2.5"]) == 0
    assert slept == [2.5]
    assert thaw_calls == [["systemctl", "--user", "thaw", "unit.scope"]]


def test_one_watchdog_thaws_every_scope_of_a_tree(monkeypatch, thaw_calls):
    monkeypatch.setattr(watchdog.sys, "stdin", FakeStdin(b"start"))
    monkeypatch.setattr(watchdog.time, "sleep", lambda seconds: None)
    assert watchdog.main(["a.scope", "b.scope", "3"]) == 0
    # One watchdog, one thaw call, however many scopes the tree needed.
    assert thaw_calls == [["systemctl", "--user", "thaw", "a.scope", "b.scope"]]


def test_watchdog_rejects_a_wrong_argument_count(capsys, thaw_calls):
    assert watchdog.main(["unit.scope"]) == 2
    assert thaw_calls == []
    assert "usage" in capsys.readouterr().err


def test_watchdog_rejects_a_duration_that_is_not_a_number(capsys, thaw_calls):
    assert watchdog.main(["unit.scope", "soon"]) == 2
    assert thaw_calls == []
    assert "usage" in capsys.readouterr().err


def test_watchdog_command_takes_several_scopes(monkeypatch):
    monkeypatch.delattr(sys, "frozen", raising=False)
    assert core.watchdog_command(["a.scope", "b.scope"], 2) == [
        sys.executable, "-m", "processfreezer.watchdog", "a.scope", "b.scope", "2",
    ]
