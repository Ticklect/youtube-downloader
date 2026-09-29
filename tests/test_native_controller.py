import json
from pathlib import Path

import pytest

from native_host.controller import ControllerError, HelperController, probe_helper_health


class FakePopen:
    def __init__(self, pid=4242):
        self.pid = pid


class FakeProcess:
    def __init__(self, pid, *, create_time=10.0, exe="", cmdline=None, running=True, children=None):
        self.pid = pid
        self._create_time = create_time
        self._exe = exe
        self._cmdline = list(cmdline or [])
        self._running = running
        self._children = list(children or [])
        self.terminated = False
        self.killed = False

    def create_time(self):
        return self._create_time
    def exe(self):
        return self._exe
    def cmdline(self):
        return list(self._cmdline)
    def is_running(self):
        return self._running
    def children(self, recursive=False):
        return list(self._children)
    def terminate(self):
        self.terminated = True
        self._running = False
    def kill(self):
        self.killed = True
        self._running = False
    def wait(self, timeout=None):
        return 0


class SequenceProbe:
    def __init__(self, values):
        self.values = list(values)
        self.calls = 0
    def __call__(self):
        self.calls += 1
        if self.values:
            value = self.values.pop(0)
            self.values.append(value)
            return value
        return False


def make_repo(tmp_path):
    repo = tmp_path / "repo"
    python = repo / ".venv" / "Scripts" / "python.exe"
    python.parent.mkdir(parents=True)
    python.write_bytes(b"")
    return repo, python


def matching_process(python_path, pid=4242, create_time=10.0):
    return FakeProcess(
        pid,
        create_time=create_time,
        exe=str(python_path),
        cmdline=[str(python_path), "-m", "helper.app"],
    )


def write_state(config_dir, process):
    config_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / "helper-process.json").write_text(json.dumps({
        "pid": process.pid,
        "create_time": process.create_time(),
        "exe": process.exe(),
        "cmdline": process.cmdline(),
    }), encoding="utf-8")


def test_probe_helper_health_requires_exact_service_marker():
    class Response:
        def __init__(self, body):
            self.body = body
        def __enter__(self):
            return self
        def __exit__(self, *_):
            return False
        def read(self):
            return json.dumps(self.body).encode()

    assert probe_helper_health(opener=lambda *a, **k: Response({"service": "other"})) is False
    assert probe_helper_health(opener=lambda *a, **k: Response({"service": "youtube-channel-downloader"})) is True


def test_start_uses_fixed_helper_command_and_waits_for_health(tmp_path):
    repo, python = make_repo(tmp_path)
    config = tmp_path / "control"
    process = matching_process(python)
    calls = []
    probe_values = iter([False, True])
    controller = HelperController(
        repo,
        config,
        health_probe=lambda: next(probe_values, True),
        popen_factory=lambda command, **kwargs: calls.append((command, kwargs)) or FakePopen(process.pid),
        process_factory=lambda pid: process,
        sleep=lambda _: None,
        startup_timeout=1,
    )

    result = controller.start()

    assert result["ok"] is True and result["healthy"] is True and result["owned"] is True
    assert calls[0][0] == [str(python), "-m", "helper.app"]
    assert Path(calls[0][1]["cwd"]) == repo
    assert calls[0][1]["stdin"] is not None
    assert calls[0][1]["stdout"] is not None
    assert calls[0][1]["stderr"] is not None


def test_start_is_noop_when_expected_helper_is_already_healthy(tmp_path):
    repo, _ = make_repo(tmp_path)
    spawned = []
    controller = HelperController(repo, tmp_path / "control", health_probe=lambda: True, popen_factory=lambda *a, **k: spawned.append(1))
    result = controller.start()
    assert result["healthy"] is True
    assert result["already_running"] is True
    assert spawned == []


def test_start_missing_venv_is_actionable(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    controller = HelperController(repo, tmp_path / "control", health_probe=lambda: False)
    with pytest.raises(ControllerError, match="setup.ps1"):
        controller.start()


def test_start_timeout_cleans_owned_state_and_process(tmp_path):
    repo, python = make_repo(tmp_path)
    process = matching_process(python)
    controller = HelperController(
        repo,
        tmp_path / "control",
        health_probe=lambda: False,
        popen_factory=lambda *a, **k: FakePopen(process.pid),
        process_factory=lambda pid: process,
        sleep=lambda _: None,
        startup_timeout=0,
    )
    with pytest.raises(ControllerError, match="ready in time"):
        controller.start()
    assert process.terminated is True
    assert not controller.state_path.exists()


def test_status_cleans_stale_dead_process_state(tmp_path):
    repo, python = make_repo(tmp_path)
    config = tmp_path / "control"
    write_state(config, matching_process(python))
    controller = HelperController(repo, config, health_probe=lambda: False, process_factory=lambda pid: (_ for _ in ()).throw(ProcessLookupError()))
    result = controller.status()
    assert result == {"ok": True, "healthy": False, "owned": False}
    assert not controller.state_path.exists()


@pytest.mark.parametrize("mutation", ["create_time", "exe", "cmdline"])
def test_stop_refuses_pid_reuse_or_identity_mismatch(tmp_path, mutation):
    repo, python = make_repo(tmp_path)
    config = tmp_path / "control"
    expected = matching_process(python)
    write_state(config, expected)
    kwargs = {"create_time": 10.0, "exe": str(python), "cmdline": [str(python), "-m", "helper.app"]}
    if mutation == "create_time": kwargs["create_time"] = 99.0
    elif mutation == "exe": kwargs["exe"] = str(tmp_path / "other.exe")
    else: kwargs["cmdline"] = [str(python), "-c", "print('unrelated')"]
    actual = FakeProcess(expected.pid, **kwargs)
    controller = HelperController(repo, config, health_probe=lambda: True, process_factory=lambda pid: actual)

    with pytest.raises(ControllerError, match="ownership"):
        controller.stop()

    assert actual.terminated is False
    assert not controller.state_path.exists()


def test_stop_terminates_only_verified_owned_helper(tmp_path):
    repo, python = make_repo(tmp_path)
    config = tmp_path / "control"
    process = matching_process(python)
    write_state(config, process)
    controller = HelperController(repo, config, health_probe=lambda: False, process_factory=lambda pid: process, sleep=lambda _: None)

    result = controller.stop()

    assert result == {"ok": True, "healthy": False, "owned": False}
    assert process.terminated is True
    assert not controller.state_path.exists()


def test_stop_terminates_verified_helper_descendant_before_launcher(tmp_path):
    repo, python = make_repo(tmp_path)
    config = tmp_path / "control"
    child_python = tmp_path / "Python312" / "python.exe"
    child = FakeProcess(
        5151,
        create_time=10.1,
        exe=str(child_python),
        cmdline=[str(child_python), "-m", "helper.app"],
    )
    launcher = FakeProcess(
        4242,
        create_time=10.0,
        exe=str(python),
        cmdline=[str(python), "-m", "helper.app"],
        children=[child],
    )
    write_state(config, launcher)
    clock = iter([0.0, 4.0])
    controller = HelperController(
        repo,
        config,
        health_probe=lambda: child.is_running(),
        process_factory=lambda pid: launcher,
        sleep=lambda _: None,
        monotonic=lambda: next(clock, 4.0),
    )

    result = controller.stop()

    assert child.terminated is True
    assert launcher.terminated is True
    assert result == {"ok": True, "healthy": False, "owned": False}
    assert not controller.state_path.exists()


def test_stop_never_reports_success_while_expected_helper_is_still_healthy(tmp_path):
    repo, python = make_repo(tmp_path)
    config = tmp_path / "control"
    process = matching_process(python)
    write_state(config, process)
    clock = iter([0.0, 4.0])
    controller = HelperController(
        repo,
        config,
        health_probe=lambda: True,
        process_factory=lambda pid: process,
        sleep=lambda _: None,
        monotonic=lambda: next(clock, 4.0),
    )

    with pytest.raises(ControllerError, match="still running") as exc_info:
        controller.stop()

    assert exc_info.value.code == "stop_failed"


def test_duplicate_start_waits_for_existing_owned_process_instead_of_spawning(tmp_path):
    repo, python = make_repo(tmp_path)
    config = tmp_path / "control"
    process = matching_process(python)
    write_state(config, process)
    states = iter([False, True])
    spawned = []
    controller = HelperController(
        repo,
        config,
        health_probe=lambda: next(states, True),
        process_factory=lambda pid: process,
        popen_factory=lambda *a, **k: spawned.append(1),
        sleep=lambda _: None,
        startup_timeout=1,
    )

    result = controller.start()
    assert result["healthy"] is True and result["owned"] is True
    assert spawned == []
