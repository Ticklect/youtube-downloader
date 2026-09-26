import time
from pathlib import Path

import pytest

import helper.jobs as jobs
from helper.downloader import ArtifactArchives, download_item


def request(video_id: str, mode: str = "video") -> jobs.DownloadRequest:
    return jobs.DownloadRequest(
        video_id=video_id,
        url=f"https://www.youtube.com/watch?v={video_id}",
        title=f"Video {video_id}",
        channel_name="Channel",
        mode=mode,
        quality="720",
    )


def wait_done(manager: jobs.JobManager, job_id: str, timeout: float = 3.0) -> dict:
    deadline = time.time() + timeout
    while time.time() < deadline:
        state = manager.get_job(job_id)
        if state["status"] == "completed":
            return state
        time.sleep(0.01)
    raise AssertionError("job did not finish")


def test_job_manager_reports_terminal_states_and_aggregate_counts(monkeypatch, tmp_path):
    monkeypatch.setattr(jobs, "download_item", lambda req, root, progress_cb: jobs.ItemResult("completed"))
    manager = jobs.JobManager(max_workers=2)

    job_id = manager.create_job([request("a"), request("b")], tmp_path)
    result = wait_done(manager, job_id)

    assert result["status"] == "completed"
    assert result["counts"]["completed"] == 2
    assert {item["state"] for item in result["items"]} == {"completed"}


def test_one_failed_item_does_not_cancel_later_items(monkeypatch, tmp_path):
    def fake_download(req, root, progress_cb):
        if req.video_id == "b":
            raise RuntimeError("boom")
        return jobs.ItemResult("completed")

    monkeypatch.setattr(jobs, "download_item", fake_download)
    manager = jobs.JobManager(max_workers=2)
    result = wait_done(manager, manager.create_job([request("a"), request("b"), request("c")], tmp_path))

    states = {item["video_id"]: item["state"] for item in result["items"]}
    assert states == {"a": "completed", "b": "failed", "c": "completed"}
    assert result["counts"]["failed"] == 1


def test_retry_failed_creates_new_job_with_only_failed_items(monkeypatch, tmp_path):
    attempts = {"b": 0}

    def fake_download(req, root, progress_cb):
        if req.video_id == "b" and attempts["b"] == 0:
            attempts["b"] += 1
            raise RuntimeError("first try fails")
        return jobs.ItemResult("completed")

    monkeypatch.setattr(jobs, "download_item", fake_download)
    manager = jobs.JobManager(max_workers=2)
    first = manager.create_job([request("a"), request("b")], tmp_path)
    wait_done(manager, first)

    retry = manager.retry_failed(first)
    result = wait_done(manager, retry)

    assert [item["video_id"] for item in result["items"]] == ["b"]
    assert result["items"][0]["state"] == "completed"


def test_unknown_job_id_is_rejected(tmp_path):
    with pytest.raises(KeyError):
        jobs.JobManager().get_job("missing")


def test_download_item_skips_when_requested_artifact_is_already_archived(monkeypatch, tmp_path):
    ArtifactArchives(tmp_path).mark_complete("video", "abc")
    monkeypatch.setattr("helper.downloader.YoutubeDL", lambda *_: (_ for _ in ()).throw(AssertionError("must not download")))

    result = download_item(request("abc"), tmp_path, lambda update: None)

    assert result.state == "skipped"


def test_transcript_unavailable_is_not_archived(monkeypatch, tmp_path):
    class FakeYDL:
        def __init__(self, options):
            self.options = options
        def __enter__(self):
            return self
        def __exit__(self, *args):
            return False
        def download(self, urls):
            return 0

    monkeypatch.setattr("helper.downloader.YoutubeDL", FakeYDL)
    result = download_item(request("abc", mode="transcript"), tmp_path, lambda update: None)

    assert result.state == "unavailable"
    assert ArtifactArchives(tmp_path).contains("transcript", "abc") is False
