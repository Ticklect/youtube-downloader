import time
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import threading

import pytest

import helper.jobs as jobs
import helper.downloader as downloader
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


def test_default_job_manager_allows_four_parallel_downloads(monkeypatch, tmp_path):
    active = 0
    peak = 0
    lock = threading.Lock()
    four_started = threading.Event()
    release = threading.Event()

    def fake_download(req, root, progress_cb):
        nonlocal active, peak
        with lock:
            active += 1
            peak = max(peak, active)
            if active >= 4:
                four_started.set()
        assert release.wait(1.0)
        with lock:
            active -= 1
        return jobs.ItemResult("completed")

    monkeypatch.setattr(jobs, "download_item", fake_download)
    manager = jobs.JobManager()
    job_id = manager.create_job([request(str(index)) for index in range(4)], tmp_path)

    assert four_started.wait(1.0)
    release.set()
    wait_done(manager, job_id)

    assert manager.max_workers == 4
    assert peak == 4


def test_download_item_skips_when_requested_artifact_is_already_archived(monkeypatch, tmp_path):
    req = request("abc")
    output_dir = downloader.build_video_dir(tmp_path, req.channel_name, req.title, req.video_id)
    output_dir.mkdir(parents=True)
    (output_dir / "video.mp4").write_bytes(b"video")
    ArtifactArchives(tmp_path).mark_complete("video", "abc")
    ArtifactArchives(tmp_path).set_video_quality("abc", req.quality, output_dir / "video.mp4")
    monkeypatch.setattr("helper.downloader.YoutubeDL", lambda *_: (_ for _ in ()).throw(AssertionError("must not download")))

    result = download_item(req, tmp_path, lambda update: None)

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


def test_overlapping_downloads_claim_same_artifact_once(monkeypatch, tmp_path):
    calls = 0
    calls_lock = threading.Lock()
    started = threading.Event()
    release = threading.Event()

    def fake_run(req, root, artifact, progress_cb):
        nonlocal calls
        with calls_lock:
            calls += 1
        started.set()
        assert release.wait(1.0)
        output_dir = downloader.build_video_dir(root, req.channel_name, req.title, req.video_id)
        output_dir.mkdir(parents=True, exist_ok=True)
        (output_dir / "video.mp4").write_bytes(b"video")

    monkeypatch.setattr(downloader, "_run_yt_dlp", fake_run)
    req = request("same")

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(downloader.download_item, req, tmp_path, lambda update: None) for _ in range(2)]
        assert started.wait(1.0)
        time.sleep(0.05)
        release.set()
        results = [future.result(timeout=2.0) for future in futures]

    assert calls == 1
    assert sorted(result.state for result in results) == ["completed", "skipped"]


def test_max_workers_is_global_across_overlapping_jobs(monkeypatch, tmp_path):
    active = 0
    peak = 0
    lock = threading.Lock()
    two_started = threading.Event()
    release = threading.Event()

    def fake_download(req, root, progress_cb):
        nonlocal active, peak
        with lock:
            active += 1
            peak = max(peak, active)
            if active >= 2:
                two_started.set()
        assert release.wait(1.0)
        with lock:
            active -= 1
        return jobs.ItemResult("completed")

    monkeypatch.setattr(jobs, "download_item", fake_download)
    manager = jobs.JobManager(max_workers=2)
    first = manager.create_job([request("a"), request("b")], tmp_path)
    second = manager.create_job([request("c"), request("d")], tmp_path)

    assert two_started.wait(1.0)
    time.sleep(0.05)
    with lock:
        observed_peak = peak
    release.set()
    wait_done(manager, first)
    wait_done(manager, second)

    assert observed_peak == 2
