from __future__ import annotations

import json
from pathlib import Path
import sys

from native_host.controller import ControllerError, HelperController
from native_host.protocol import ProtocolError, read_message, set_binary_stdio, write_message


HOST_NAME = "com.ycd.helper_control"
ALLOWED_COMMANDS = {"status", "start", "stop"}


def default_config_path() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent.parent / "install" / "config.json"
    return Path(__file__).resolve().parent / "install" / "config.json"


def load_controller(config_path: Path | None = None) -> HelperController:
    path = Path(config_path or default_config_path())
    data = json.loads(path.read_text(encoding="utf-8"))
    repo_root = data.get("repo_root")
    if not isinstance(repo_root, str) or not repo_root.strip():
        raise ControllerError("Native host configuration is invalid. Run scripts/setup.ps1.", "config_invalid")
    return HelperController(repo_root, path.parent)


def dispatch_message(controller, message) -> dict:
    command = message.get("command") if isinstance(message, dict) else None
    if not isinstance(command, str) or command not in ALLOWED_COMMANDS or set(message) != {"command"}:
        return {"ok": False, "error": {"code": "invalid_command", "message": "Command must be exactly status, start, or stop."}}
    try:
        return getattr(controller, command)()
    except ControllerError as exc:
        return {"ok": False, "error": {"code": exc.code, "message": str(exc)}}
    except Exception:
        return {"ok": False, "error": {"code": "internal_error", "message": "Native helper control failed."}}


def run_once(instream, outstream, controller) -> None:
    try:
        message = read_message(instream)
        if message is None:
            return
        response = dispatch_message(controller, message)
    except ProtocolError as exc:
        response = {"ok": False, "error": {"code": "protocol_error", "message": str(exc)}}
    write_message(outstream, response)


def main() -> int:
    set_binary_stdio()
    instream = sys.stdin.buffer
    outstream = sys.stdout.buffer
    try:
        controller = load_controller()
        run_once(instream, outstream, controller)
        return 0
    except Exception as exc:
        write_message(outstream, {"ok": False, "error": {"code": "host_start_failed", "message": str(exc)}})
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
