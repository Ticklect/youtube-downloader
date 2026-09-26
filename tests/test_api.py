from pathlib import Path
from unittest.mock import patch

from helper.channel import ChannelResult, VideoInfo
from helper.dependencies import DependencyStatus
from helper.settings import SettingsStore
from helper.app import create_app


ORIGIN = "chrome-extension://abcdefghijklmnopabcdefghijklmnop"
HEADERS = {"Origin": ORIGIN, "X-YCD-Client": "1"}


class FakeJobs:
    def __init__(self):
        self.created = []
    def create_job(self, items, root):
        self.created.append((items, root))
        return "job-1"
    def get_job(self, job_id):
        if job_id != "job-1":
            raise KeyError(job_id)
        return {"id": job_id, "status": "completed", "items": [], "counts": {}}
    def retry_failed(self, job_id):
        if job_id != "job-1":
            raise KeyError(job_id)
        return "job-2"


def make_client(tmp_path, **kwargs):
    store = kwargs.pop("settings_store", SettingsStore(tmp_path / "settings.json"))
    app = create_app(settings_store=store, job_manager=kwargs.pop("job_manager", FakeJobs()), **kwargs)
    app.config.update(TESTING=True)
    return app.test_client(), store


def test_health_requires_extension_origin_and_reports_dependencies(tmp_path):
    checker = lambda: DependencyStatus(True, False, ["FFmpeg missing"])
    client, _ = make_client(tmp_path, dependency_checker=checker)

    assert client.get("/health").status_code == 403
    assert client.get("/health", headers={"Origin": "https://example.com"}).status_code == 403
    response = client.get("/health", headers={"Origin": ORIGIN})

    assert response.status_code == 200
    assert response.get_json()["dependencies"] == {"yt_dlp": True, "ffmpeg": False, "messages": ["FFmpeg missing"]}


def test_state_changing_requests_require_custom_header(tmp_path):
    client, _ = make_client(tmp_path)
    response = client.post("/folder/pick", headers={"Origin": ORIGIN})
    assert response.status_code == 403
    assert response.get_json()["error"]["code"] == "client_header_required"


def test_preflight_is_narrow_and_echoes_accepted_extension_origin(tmp_path):
    client, _ = make_client(tmp_path)
    response = client.options(
        "/jobs",
        headers={
            "Origin": ORIGIN,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type,x-ycd-client",
        },
    )
    assert response.status_code == 204
    assert response.headers["Access-Control-Allow-Origin"] == ORIGIN
    assert response.headers["Access-Control-Allow-Methods"] == "GET, POST, OPTIONS"
    assert response.headers["Access-Control-Allow-Headers"] == "Content-Type, X-YCD-Client"


def test_invalid_channel_url_returns_400_without_loading(tmp_path):
    calls = []
    def loader(url):
        calls.append(url)
        raise ValueError("bad channel")
    client, _ = make_client(tmp_path, channel_loader=loader)
    response = client.post("/channel", json={"url": "https://example.com/x"}, headers=HEADERS)
    assert response.status_code == 400
    assert response.get_json()["error"]["code"] == "invalid_channel_url"
    assert len(calls) == 1


def test_channel_with_no_public_videos_returns_clear_error(tmp_path):
    client, _ = make_client(tmp_path, channel_loader=lambda url: ChannelResult("Empty", []))
    response = client.post("/channel", json={"url": "https://youtube.com/@empty"}, headers=HEADERS)
    assert response.status_code == 404
    assert response.get_json()["error"]["code"] == "no_videos"


def test_cancelled_folder_picker_keeps_existing_root(tmp_path):
    root = tmp_path / "downloads"
    root.mkdir()
    store = SettingsStore(tmp_path / "settings.json")
    store.save_download_root(root)
    client, _ = make_client(tmp_path, settings_store=store, folder_picker=lambda: None)

    response = client.post("/folder/pick", headers=HEADERS)

    assert response.status_code == 200
    assert response.get_json()["cancelled"] is True
    assert store.get_download_root() == root.resolve()


def test_stale_folder_rejects_job_creation(tmp_path):
    root = tmp_path / "downloads"
    root.mkdir()
    store = SettingsStore(tmp_path / "settings.json")
    store.save_download_root(root)
    root.rmdir()
    client, _ = make_client(tmp_path, settings_store=store)

    response = client.post("/jobs", json={"videos": [], "mode": "video", "quality": "720"}, headers=HEADERS)
    assert response.status_code == 400
    assert response.get_json()["error"]["code"] == "folder_required"


def test_valid_job_request_returns_job_id(tmp_path):
    root = tmp_path / "downloads"
    root.mkdir()
    store = SettingsStore(tmp_path / "settings.json")
    store.save_download_root(root)
    manager = FakeJobs()
    client, _ = make_client(tmp_path, settings_store=store, job_manager=manager)
    payload = {
        "videos": [{"video_id": "abc", "url": "https://www.youtube.com/watch?v=abc", "title": "Title", "channel_name": "Channel"}],
        "mode": "audio",
        "quality": "best",
    }

    response = client.post("/jobs", json=payload, headers=HEADERS)

    assert response.status_code == 202
    assert response.get_json()["job_id"] == "job-1"
    assert len(manager.created[0][0]) == 1
