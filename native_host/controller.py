from __future__ import annotations

from contextlib import contextmanager
import json
import os
from pathlib import Path
import subprocess
import time
from urllib.request import urlopen

import psutil


HEALTH_URL = "http://127.0.0.1:17865/health"
SERVICE_MARKER = "youtube-channel-downloader"


class ControllerError(RuntimeError):
    def __init__(self, message: str, code: str = "control_failed"):
        super().__init__(message)
        self.code = code


def probe_helper_health(url: str = HEALTH_URL, *, opener=urlopen) -> bool:
    try:
        with opener(url, timeout=0.75) as response:
            data = json.loads(response.read().decode("utf-8"))
    except Exception:
        return False
    return isinstance(data, dict) and data.get("service") == SERVICE_MARKER


class HelperController:
    def __init__(
        self,
        repo_root,
        config_dir,
        *,
        health_probe=None,
        popen_factory=None,
        process_factory=None,
        sleep=None,
        monotonic=None,
        startup_timeout: float = 8.0,
    ):
        self.repo_root = Path(repo_root).resolve()
        self.config_dir = Path(config_dir).resolve()
        self.config_dir.mkdir(parents=True, exist_ok=True)
        self.state_path = self.config_dir / "helper-process.json"
        self.lock_path = self.config_dir / "helper-control.lock"
        self.health_probe = health_probe or probe_helper_health
        self.popen_factory = popen_factory or subprocess.Popen
        self.process_factory = process_factory or psutil.Process
        self.sleep = sleep or time.sleep
        self.monotonic = monotonic or time.monotonic
        self.startup_timeout = float(startup_timeout)

    @property
    def python_path(self) -> Path:
        return self.repo_root / ".venv" / "Scripts" / "python.exe"

    @property
    def helper_command(self) -> list[str]:
        return [str(self.python_path), "-m", "helper.app"]

    @contextmanager
    def _exclusive_lock(self):
        self.config_dir.mkdir(parents=True, exist_ok=True)
        with self.lock_path.open("a+b") as lock_file:
            if self.lock_path.stat().st_size == 0:
                lock_file.write(b"\0")
                lock_file.flush()
            lock_file.seek(0)
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(lock_file.fileno(), msvcrt.LK_LOCK, 1)
                try:
                    yield
                finally:
                    lock_file.seek(0)
                    msvcrt.locking(lock_file.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
                try:
                    yield
                finally:
                    fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)

    def _load_state(self) -> dict | None:
        try:
            raw = json.loads(self.state_path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return None
        except (OSError, json.JSONDecodeError):
            self._clear_state()
            return None
        if not isinstance(raw, dict):
            self._clear_state()
            return None
        return raw

    def _save_state(self, state: dict) -> None:
        temp = self.state_path.with_suffix(".tmp")
        temp.write_text(json.dumps(state, separators=(",", ":")), encoding="utf-8")
        temp.replace(self.state_path)

    def _clear_state(self) -> None:
        try:
            self.state_path.unlink()
        except FileNotFoundError:
            pass

    @staticmethod
    def _normalize_exe(value: str) -> str:
        return os.path.normcase(os.path.abspath(value))

    def _capture_identity(self, process) -> dict:
        return {
            "pid": int(process.pid),
            "create_time": float(process.create_time()),
            "exe": str(process.exe()),
            "cmdline": list(process.cmdline()),
        }

    def _verified_owned_process(self):
        state = self._load_state()
        if state is None:
            return None
        try:
            pid = int(state["pid"])
            expected_create_time = float(state["create_time"])
            expected_exe = str(state["exe"])
            expected_cmdline = list(state["cmdline"])
            process = self.process_factory(pid)
            if hasattr(process, "is_running") and not process.is_running():
                raise ProcessLookupError(pid)
            actual_create_time = float(process.create_time())
            actual_exe = str(process.exe())
            actual_cmdline = list(process.cmdline())
        except Exception:
            self._clear_state()
            return None

        identity_matches = (
            abs(actual_create_time - expected_create_time) < 0.01
            and self._normalize_exe(actual_exe) == self._normalize_exe(expected_exe)
            and actual_cmdline == expected_cmdline
        )
        if not identity_matches:
            self._clear_state()
            return None
        return process

    def _wait_for_health(self, timeout: float) -> bool:
        deadline = self.monotonic() + max(0.0, timeout)
        while True:
            if self.health_probe():
                return True
            if self.monotonic() >= deadline:
                return False
            self.sleep(0.1)

    def _terminate_verified(self, process) -> None:
        process.terminate()
        try:
            process.wait(timeout=4)
        except Exception:
            if hasattr(process, "is_running") and process.is_running():
                process.kill()
                process.wait(timeout=2)

    def status(self) -> dict:
        with self._exclusive_lock():
            process = self._verified_owned_process()
            return {
                "ok": True,
                "healthy": bool(self.health_probe()),
                "owned": process is not None,
            }

    def start(self) -> dict:
        with self._exclusive_lock():
            owned_process = self._verified_owned_process()
            if self.health_probe():
                return {
                    "ok": True,
                    "healthy": True,
                    "owned": owned_process is not None,
                    "already_running": True,
                }

            if owned_process is not None:
                if self._wait_for_health(self.startup_timeout):
                    return {"ok": True, "healthy": True, "owned": True, "already_running": True}
                raise ControllerError("An owned helper process is running but did not become ready in time.", "helper_not_ready")

            if not self.python_path.is_file():
                raise ControllerError("Helper environment is missing. Run scripts/setup.ps1.", "venv_missing")

            creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
            try:
                child = self.popen_factory(
                    self.helper_command,
                    cwd=str(self.repo_root),
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    creationflags=creationflags,
                )
                process = self.process_factory(child.pid)
                self._save_state(self._capture_identity(process))
            except Exception as exc:
                self._clear_state()
                raise ControllerError(f"Could not start helper: {exc}", "start_failed") from exc

            if self._wait_for_health(self.startup_timeout):
                return {"ok": True, "healthy": True, "owned": True, "already_running": False}

            verified = self._verified_owned_process()
            if verified is not None:
                self._terminate_verified(verified)
            self._clear_state()
            raise ControllerError("Helper did not become ready in time.", "start_timeout")

    def stop(self) -> dict:
        with self._exclusive_lock():
            if self._load_state() is None:
                raise ControllerError("Helper process ownership could not be verified; nothing was stopped.", "ownership_unverified")
            process = self._verified_owned_process()
            if process is None:
                raise ControllerError("Helper process ownership could not be verified; nothing was stopped.", "ownership_unverified")
            self._terminate_verified(process)
            self._clear_state()
            deadline = self.monotonic() + 3.0
            while self.health_probe() and self.monotonic() < deadline:
                self.sleep(0.1)
            return {"ok": True, "healthy": bool(self.health_probe()), "owned": False}
