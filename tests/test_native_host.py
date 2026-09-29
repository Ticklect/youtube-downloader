import io

from native_host.host import dispatch_message, run_once
from native_host.protocol import read_message, write_message


class FakeController:
    def __init__(self):
        self.calls = []
    def status(self):
        self.calls.append("status")
        return {"ok": True, "healthy": False, "owned": False}
    def start(self):
        self.calls.append("start")
        return {"ok": True, "healthy": True, "owned": True}
    def stop(self):
        self.calls.append("stop")
        return {"ok": True, "healthy": False, "owned": False}


def test_dispatch_accepts_exact_control_commands():
    controller = FakeController()
    assert dispatch_message(controller, {"command": "status"})["ok"] is True
    assert dispatch_message(controller, {"command": "start"})["healthy"] is True
    assert dispatch_message(controller, {"command": "stop"})["healthy"] is False
    assert controller.calls == ["status", "start", "stop"]


def test_dispatch_rejects_unknown_or_malformed_commands_without_action():
    controller = FakeController()
    for message in [{}, {"command": "run"}, {"command": ["start"]}, "start"]:
        response = dispatch_message(controller, message)
        assert response["ok"] is False
        assert response["error"]["code"] == "invalid_command"
    assert controller.calls == []


def test_run_once_reads_one_message_writes_one_response_and_exits():
    controller = FakeController()
    incoming = io.BytesIO()
    outgoing = io.BytesIO()
    write_message(incoming, {"command": "status"})
    incoming.seek(0)

    run_once(incoming, outgoing, controller)

    outgoing.seek(0)
    assert read_message(outgoing) == {"ok": True, "healthy": False, "owned": False}
    assert controller.calls == ["status"]
