from pathlib import Path
from unittest.mock import patch

from helper.channel import ChannelResult, VideoInfo
from helper.dependencies import DependencyStatus
from helper.settings import SettingsStore
from helper.app import EXTENSION_ORIGIN, create_app


ORIGIN = EXTENSION_ORIGIN
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


def test_health_allows_originless_get_but_rejects_web_origin(tmp_path):
    checker = lambda: DependencyStatus(True, False, ["FFmpeg missing"])
    client, _ = make_client(tmp_path, dependency_checker=checker)

    originless = client.get("/health")
    assert client.get("/health", headers={"Origin": "https://example.com"}).status_code == 403
    response = client.get("/health", headers={"Origin": ORIGIN})

    assert originless.status_code == 200
    assert originless.get_json()["service"] == "youtube-channel-downloader"
    assert originless.get_json()["dependencies"] == {"yt_dlp": True, "ffmpeg": False, "messages": ["FFmpeg missing"]}
    assert response.status_code == 200
    assert response.get_json()["service"] == "youtube-channel-downloader"
    assert response.get_json()["dependencies"] == {"yt_dlp": True, "ffmpeg": False, "messages": ["FFmpeg missing"]}


def test_rejects_dns_rebinding_host_before_originless_get(tmp_path):
    client, _ = make_client(tmp_path)
    for host in ["evil.test", "evil.test:17865", "youtube.com:17865"]:
        response = client.get("/health", headers={"Host": host})
        assert response.status_code == 403
        assert response.get_json()["error"]["code"] == "invalid_host"
        assert client.get("/folder", headers={"Host": host}).status_code == 403
        assert client.post("/jobs", headers={"Host": host, **HEADERS}, json={}).status_code == 403

    assert client.get("/health", headers={"Host": "127.0.0.1:17865"}).status_code == 200


def test_only_health_probe_allows_originless_get(tmp_path):
    client, _ = make_client(tmp_path)
    assert client.get("/health").status_code == 200
    for url in ("/folder", "/jobs/job-1"):
        response = client.get(url)
        assert response.status_code == 403
        assert response.get_json()["error"]["code"] == "extension_origin_required"
        assert client.get(url, headers={"Origin": ORIGIN}).status_code == 200


def test_rejects_other_chrome_extension_origin(tmp_path):
    client, _ = make_client(tmp_path)
    other_origin = "chrome-extension://abcdefghijklmnopabcdefghijklmnop"
    assert other_origin != ORIGIN

    response = client.get("/health", headers={"Origin": other_origin})

    assert response.status_code == 403
    assert "Access-Control-Allow-Origin" not in response.headers


def test_extension_origin_matches_manifest_identity():
    assert ORIGIN == "chrome-extension://jampplgmnpaekfdpicamgkabmbeihdcb"


def test_state_changing_requests_require_custom_header(tmp_path):
    client, _ = make_client(tmp_path)
    originless = client.post("/folder/pick", headers={"X-YCD-Client": "1"})
    assert originless.status_code == 403
    assert originless.get_json()["error"]["code"] == "extension_origin_required"

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


def test_job_request_rejects_mismatched_video_id_and_url(tmp_path):
    root = tmp_path / "downloads"
    root.mkdir()
    store = SettingsStore(tmp_path / "settings.json")
    store.save_download_root(root)
    manager = FakeJobs()
    client, _ = make_client(tmp_path, settings_store=store, job_manager=manager)
    payload = {
        "videos": [{
            "video_id": "expected-id",
            "url": "https://www.youtube.com/watch?v=different-id",
            "title": "Title",
            "channel_name": "Channel",
        }],
        "mode": "video",
        "quality": "720",
    }

    response = client.post("/jobs", json=payload, headers=HEADERS)

    assert response.status_code == 400
    assert response.get_json()["error"]["code"] == "invalid_video"
    assert manager.created == []


def test_job_request_accepts_common_youtube_url_forms_when_id_matches(tmp_path):
    root = tmp_path / "downloads"
    root.mkdir()
    store = SettingsStore(tmp_path / "settings.json")
    store.save_download_root(root)

    for url in [
        "https://www.youtube.com/watch?v=abc123&feature=share",
        "https://youtu.be/abc123?t=5",
        "https://www.youtube.com/shorts/abc123",
        "https://www.youtube.com/embed/abc123",
        "https://www.youtube.com/live/abc123?feature=share",
    ]:
        manager = FakeJobs()
        client, _ = make_client(tmp_path, settings_store=store, job_manager=manager)
        response = client.post(
            "/jobs",
            json={
                "videos": [{"video_id": "abc123", "url": url, "title": "Title", "channel_name": "Channel"}],
                "mode": "video",
                "quality": "720",
            },
            headers=HEADERS,
        )
        assert response.status_code == 202, url
        assert len(manager.created) == 1
