from concurrent.futures import ThreadPoolExecutor
import os
from pathlib import Path

import pytest

import helper.downloader as downloader
from helper.downloader import ArtifactArchives, DownloadRequest, build_video_dir, build_ydl_options, sanitize_component


@pytest.mark.parametrize("value", ['bad<>:"/\\|?*name', 'trailing. ', 'CON', 'COM1', 'CON.txt', 'LPT1.log'])
def test_sanitize_component_removes_windows_invalid_names(value):
    result = sanitize_component(value)
    assert result
    assert not any(char in result for char in '<>:"/\\|?*')
    assert not result.endswith((".", " "))
    assert result.split(".", 1)[0].upper() not in {"CON", "COM1", "LPT1"}


def test_build_video_dir_keeps_video_id_and_limits_long_title(tmp_path):
    result = build_video_dir(tmp_path, "Channel", "x" * 400, "abc123")
    assert result.name.endswith("[abc123]")
    assert len(result.name) <= 150
    assert result.parent.name == "Channel"


@pytest.mark.parametrize(("quality", "height"), [("360", 360), ("720", 720), ("1080", 1080)])
def test_video_options_cap_requested_height(tmp_path, quality, height):
    options = build_ydl_options("video", quality, tmp_path)
    assert f"height<={height}" in options["format"]
    assert str(options["outtmpl"]).endswith("video.%(ext)s")


def test_capped_video_format_keeps_height_cap_and_forces_windows_compatible_mp4(tmp_path):
    options = build_ydl_options("video", "720", tmp_path)
    assert options["format"] == (
        "bestvideo*[vcodec^=avc1][height<=720]+bestaudio[acodec^=mp4a]/"
        "best[ext=mp4][vcodec^=avc1][acodec^=mp4a][height<=720]"
    )
    assert options["merge_output_format"] == "mp4"
    assert options["concurrent_fragment_downloads"] == 4


def test_best_video_options_have_no_height_cap(tmp_path):
    assert "height<=" not in build_ydl_options("video", "best", tmp_path)["format"]


def test_audio_options_extract_mp3(tmp_path):
    options = build_ydl_options("audio", "best", tmp_path)
    pp = options["postprocessors"][0]
    assert pp["key"] == "FFmpegExtractAudio"
    assert pp["preferredcodec"] == "mp3"


def test_transcript_options_request_manual_and_auto_vtt(tmp_path):
    options = build_ydl_options("transcript", "best", tmp_path)
    assert options["skip_download"] is True
    assert options["writesubtitles"] is True
    assert options["writeautomaticsub"] is True
    assert options["subtitlesformat"] == "vtt"


def test_everything_options_keep_video_and_request_audio_and_captions(tmp_path):
    options = build_ydl_options("everything", "720", tmp_path)
    assert "height<=720" in options["format"]
    assert options["writesubtitles"] is True
    assert options["writeautomaticsub"] is True
    assert options["keepvideo"] is True
    assert options["postprocessors"][0]["preferredcodec"] == "mp3"


def test_fresh_everything_uses_one_yt_dlp_pass_and_normalizes_outputs(monkeypatch, tmp_path):
    request = DownloadRequest(
        video_id="abc123",
        url="https://www.youtube.com/watch?v=abc123",
        title="Video",
        channel_name="Channel",
        mode="everything",
        quality="720",
    )
    calls = []

    def fake_run(req, root, artifact, progress_cb):
        calls.append(artifact)
        output_dir = build_video_dir(root, req.channel_name, req.title, req.video_id)
        output_dir.mkdir(parents=True, exist_ok=True)
        assert artifact == "everything"
        (output_dir / "video.mp4").write_bytes(b"video")
        (output_dir / "video.mp3").write_bytes(b"audio")
        (output_dir / "video.en.vtt").write_text(
            "WEBVTT\n\n00:00:00.000 --> 00:00:01.000\nhello\n",
            encoding="utf-8",
        )

    monkeypatch.setattr(downloader, "_run_yt_dlp", fake_run)

    result = downloader.download_item(request, tmp_path, lambda update: None)
    output_dir = build_video_dir(tmp_path, request.channel_name, request.title, request.video_id)
    archives = ArtifactArchives(tmp_path)

    assert result.state == "completed"
    assert calls == ["everything"]
    assert (output_dir / "video.mp4").is_file()
    assert (output_dir / "audio.mp3").is_file()
    assert (output_dir / "transcript.vtt").is_file()
    assert (output_dir / "transcript.txt").read_text(encoding="utf-8") == "hello"
    assert all(archives.contains(kind, request.video_id) for kind in ("video", "audio", "transcript"))


def test_partial_everything_only_downloads_missing_artifacts(monkeypatch, tmp_path):
    request = DownloadRequest(
        video_id="abc123",
        url="https://www.youtube.com/watch?v=abc123",
        title="Video",
        channel_name="Channel",
        mode="everything",
        quality="720",
    )
    output_dir = build_video_dir(tmp_path, request.channel_name, request.title, request.video_id)
    output_dir.mkdir(parents=True)
    (output_dir / "video.mp4").write_bytes(b"video")
    ArtifactArchives(tmp_path).mark_complete("video", request.video_id)
    ArtifactArchives(tmp_path).set_video_quality(request.video_id, request.quality, output_dir / "video.mp4")
    calls = []

    def fake_run(req, root, artifact, progress_cb):
        calls.append(artifact)
        if artifact == "audio":
            (output_dir / "audio.mp3").write_bytes(b"audio")
        elif artifact == "transcript":
            (output_dir / "transcript.en.vtt").write_text(
                "WEBVTT\n\n00:00:00.000 --> 00:00:01.000\nhello\n",
                encoding="utf-8",
            )

    monkeypatch.setattr(downloader, "_run_yt_dlp", fake_run)

    result = downloader.download_item(request, tmp_path, lambda update: None)

    assert result.state == "completed"
    assert calls == ["audio", "transcript"]


def test_artifact_archives_are_independent(tmp_path):
    archives = ArtifactArchives(tmp_path)
    archives.mark_complete("video", "abc123")
    assert archives.contains("video", "abc123") is True
    assert archives.contains("audio", "abc123") is False
    assert archives.contains("transcript", "abc123") is False


def test_video_archive_does_not_reuse_pre_h264_completion_marker(tmp_path):
    legacy = tmp_path / ".youtube-channel-downloader" / "archive-video.txt"
    legacy.parent.mkdir(parents=True)
    legacy.write_text("abc123\n", encoding="utf-8")

    archives = ArtifactArchives(tmp_path)

    assert archives.contains("video", "abc123") is False


def test_archive_rejects_unknown_kind(tmp_path):
    with pytest.raises(ValueError):
        ArtifactArchives(tmp_path).contains("other", "abc")


@pytest.mark.parametrize("mode", ["video", "audio", "transcript"])
def test_stale_archive_marker_redownloads_missing_artifact(monkeypatch, tmp_path, mode):
    request = DownloadRequest(
        video_id="abc123",
        url="https://www.youtube.com/watch?v=abc123",
        title="Video",
        channel_name="Channel",
        mode=mode,
        quality="720",
    )
    ArtifactArchives(tmp_path).mark_complete(mode, request.video_id)
    calls = []

    def fake_run(req, root, artifact, progress_cb):
        calls.append(artifact)
        output_dir = build_video_dir(root, req.channel_name, req.title, req.video_id)
        output_dir.mkdir(parents=True, exist_ok=True)
        if artifact == "video":
            (output_dir / "video.mp4").write_bytes(b"video")
        elif artifact == "audio":
            (output_dir / "audio.mp3").write_bytes(b"audio")
        else:
            (output_dir / "transcript.en.vtt").write_text("WEBVTT\n\n00:00:00.000 --> 00:00:01.000\nhello\n", encoding="utf-8")

    monkeypatch.setattr(downloader, "_run_yt_dlp", fake_run)

    result = downloader.download_item(request, tmp_path, lambda update: None)

    assert result.state == "completed"
    assert calls == [mode]


@pytest.mark.parametrize(
    ("mode", "artifact_names"),
    [
        ("video", ["video.mp4"]),
        ("audio", ["audio.mp3"]),
        ("transcript", ["transcript.vtt", "transcript.txt"]),
    ],
)
def test_archive_marker_still_skips_when_artifact_exists(monkeypatch, tmp_path, mode, artifact_names):
    request = DownloadRequest(
        video_id="abc123",
        url="https://www.youtube.com/watch?v=abc123",
        title="Video",
        channel_name="Channel",
        mode=mode,
        quality="720",
    )
    output_dir = build_video_dir(tmp_path, request.channel_name, request.title, request.video_id)
    output_dir.mkdir(parents=True)
    for name in artifact_names:
        (output_dir / name).write_text("present", encoding="utf-8")
    ArtifactArchives(tmp_path).mark_complete(mode, request.video_id)
    if mode == "video":
        ArtifactArchives(tmp_path).set_video_quality(request.video_id, request.quality, output_dir / "video.mp4")
    monkeypatch.setattr(downloader, "_run_yt_dlp", lambda *args: (_ for _ in ()).throw(AssertionError("must not download")))

    result = downloader.download_item(request, tmp_path, lambda update: None)

    assert result.state == "skipped"


def test_archive_marker_finds_existing_artifact_after_title_and_channel_change(monkeypatch, tmp_path):
    video_id = "abc123"
    old_dir = build_video_dir(tmp_path, "Old Channel", "Old Title", video_id)
    old_dir.mkdir(parents=True)
    (old_dir / "video.mp4").write_bytes(b"video")
    ArtifactArchives(tmp_path).mark_complete("video", video_id)
    ArtifactArchives(tmp_path).set_video_quality(video_id, "720", old_dir / "video.mp4")
    request = DownloadRequest(
        video_id=video_id,
        url=f"https://www.youtube.com/watch?v={video_id}",
        title="New Title",
        channel_name="New Channel",
        mode="video",
        quality="720",
    )
    monkeypatch.setattr(downloader, "_run_yt_dlp", lambda *args: (_ for _ in ()).throw(AssertionError("must not download")))

    result = downloader.download_item(request, tmp_path, lambda update: None)

    assert result.state == "skipped"


def test_archive_lookups_and_appends_do_not_keep_rereading_history(monkeypatch, tmp_path):
    archives = ArtifactArchives(tmp_path)
    archives.mark_complete("video", "first")
    archive_path = archives._path("video")
    original_read = Path.read_text
    reads = 0

    def traced_read(path, *args, **kwargs):
        nonlocal reads
        if path == archive_path:
            reads += 1
        return original_read(path, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", traced_read)
    for index in range(100):
        assert archives.contains("video", "first")
        archives.mark_complete("video", f"id-{index}")
    assert reads == 0
    assert archives.contains("video", "id-99")

    # Out-of-process archive updates must invalidate the in-memory index.
    with archive_path.open("a", encoding="utf-8") as handle:
        handle.write("external-id\n")
    assert archives.contains("video", "external-id")
    assert reads == 1


def test_concurrent_archive_marks_do_not_lose_entries(tmp_path):
    archives = ArtifactArchives(tmp_path)
    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(lambda i: ArtifactArchives(tmp_path).mark_complete("audio", f"video-{i}"), range(100)))
    for index in range(100):
        assert archives.contains("audio", f"video-{index}")
    assert len(archives._path("audio").read_text(encoding="utf-8").splitlines()) == 100


def test_historical_directory_index_reuses_scans_and_detects_deleted_files(monkeypatch, tmp_path):
    channel = tmp_path / "Original Channel"
    channel.mkdir()
    for index in range(100):
        video_dir = build_video_dir(tmp_path, "Original Channel", f"Earlier {index}", f"old-{index}")
        video_dir.mkdir()
    old_dir = build_video_dir(tmp_path, "Original Channel", "Original Title", "changed")
    old_dir.mkdir()
    (old_dir / "audio.mp3").write_bytes(b"audio")
    ArtifactArchives(tmp_path).mark_complete("audio", "changed")
    request = DownloadRequest("changed", "https://www.youtube.com/watch?v=changed", "New Title", "New Channel", "audio", "720")
    original_iterdir = Path.iterdir
    scans = 0

    def traced_iterdir(path):
        nonlocal scans
        if path == channel:
            scans += 1
        return original_iterdir(path)

    monkeypatch.setattr(Path, "iterdir", traced_iterdir)
    calls = []

    def fake_download(req, root, artifact, progress_cb):
        calls.append(artifact)
        output = build_video_dir(root, req.channel_name, req.title, req.video_id)
        output.mkdir(parents=True, exist_ok=True)
        (output / "audio.mp3").write_bytes(b"fresh")

    monkeypatch.setattr(downloader, "_run_yt_dlp", fake_download)
    for _ in range(20):
        assert downloader.download_item(request, tmp_path, lambda _: None).state == "skipped"
    assert scans == 1
    assert calls == []

    (old_dir / "audio.mp3").unlink()
    assert downloader.download_item(request, tmp_path, lambda _: None).state == "completed"
    assert calls == ["audio"]


def test_historical_directory_index_refreshes_when_video_folder_is_added(monkeypatch, tmp_path):
    channel = tmp_path / "Old Channel"
    channel.mkdir()
    # Populate the index before the old artifact folder exists.
    assert downloader._historical_video_dirs(tmp_path, "new-id") == ()
    old_dir = build_video_dir(tmp_path, "Old Channel", "Old Title", "new-id")
    old_dir.mkdir()
    (old_dir / "video.mp4").write_bytes(b"present")
    os.utime(channel, (channel.stat().st_atime + 5, channel.stat().st_mtime + 5))
    ArtifactArchives(tmp_path).mark_complete("video", "new-id")
    ArtifactArchives(tmp_path).set_video_quality("new-id", "720", old_dir / "video.mp4")
    request = DownloadRequest("new-id", "https://www.youtube.com/watch?v=new-id", "New Title", "New Channel", "video", "720")
    monkeypatch.setattr(downloader, "_run_yt_dlp", lambda *args: pytest.fail("Existing file must be reused"))
    assert downloader.download_item(request, tmp_path, lambda _: None).state == "skipped"


def test_video_quality_change_redownloads_both_upgrade_and_downgrade(monkeypatch, tmp_path):
    calls = []
    output = build_video_dir(tmp_path, "Channel", "Video", "abc123")

    def fake_run(req, root, artifact, progress_cb):
        calls.append((artifact, req.quality))
        output.mkdir(parents=True, exist_ok=True)
        (output / "video.mp4").write_bytes(req.quality.encode())

    monkeypatch.setattr(downloader, "_run_yt_dlp", fake_run)
    request = DownloadRequest("abc123", "https://www.youtube.com/watch?v=abc123", "Video", "Channel", "video", "360")
    for quality, expected in [("360", "completed"), ("360", "skipped"), ("1080", "completed"), ("best", "completed"), ("360", "completed"), ("360", "skipped")]:
        result = downloader.download_item(DownloadRequest(**{**request.__dict__, "quality": quality}), tmp_path, lambda _: None)
        assert result.state == expected
        if expected == "completed":
            assert (output / "video.mp4").read_text() == quality
            assert ArtifactArchives(tmp_path).video_quality("abc123") == quality
    assert calls == [("video", "360"), ("video", "1080"), ("video", "best"), ("video", "360")]


def test_everything_quality_upgrade_keeps_existing_audio_and_transcript(monkeypatch, tmp_path):
    req = DownloadRequest("abc123", "https://www.youtube.com/watch?v=abc123", "Video", "Channel", "everything", "1080")
    folder = build_video_dir(tmp_path, req.channel_name, req.title, req.video_id)
    folder.mkdir(parents=True)
    (folder / "video.mp4").write_bytes(b"360")
    (folder / "audio.mp3").write_bytes(b"previous-audio")
    (folder / "transcript.vtt").write_text("WEBVTT", encoding="utf-8")
    (folder / "transcript.txt").write_text("old text", encoding="utf-8")
    archives = ArtifactArchives(tmp_path)
    for kind in ("video", "audio", "transcript"):
        archives.mark_complete(kind, req.video_id)
    archives.set_video_quality(req.video_id, "360", folder / "video.mp4")
    calls = []

    def fake_run(request, root, artifact, progress_cb):
        calls.append(artifact)
        assert artifact == "video"
        (folder / "video.mp4").write_bytes(request.quality.encode())

    monkeypatch.setattr(downloader, "_run_yt_dlp", fake_run)
    assert downloader.download_item(req, tmp_path, lambda _: None).state == "completed"
    assert downloader.download_item(req, tmp_path, lambda _: None).state == "skipped"
    assert calls == ["video"]
    assert (folder / "video.mp4").read_bytes() == b"1080"
    assert (folder / "audio.mp3").read_bytes() == b"previous-audio"
    assert (folder / "transcript.txt").read_text(encoding="utf-8") == "old text"


def test_unknown_legacy_quality_is_replaced_and_failure_never_reuses_stale_marker(monkeypatch, tmp_path):
    req = DownloadRequest("abc123", "https://www.youtube.com/watch?v=abc123", "Video", "Channel", "video", "1080")
    folder = build_video_dir(tmp_path, req.channel_name, req.title, req.video_id)
    folder.mkdir(parents=True)
    (folder / "video.mp4").write_bytes(b"old-unknown")
    archives = ArtifactArchives(tmp_path)
    archives.mark_complete("video", req.video_id)

    calls = []

    def fail_once(*args):
        calls.append("failure")
        raise RuntimeError("download interrupted")

    monkeypatch.setattr(downloader, "_run_yt_dlp", fail_once)
    assert downloader.download_item(req, tmp_path, lambda _: None).state == "failed"
    assert archives.video_quality(req.video_id) is None

    def successful(*args):
        calls.append("success")
        (folder / "video.mp4").write_bytes(b"1080")

    monkeypatch.setattr(downloader, "_run_yt_dlp", successful)
    assert downloader.download_item(req, tmp_path, lambda _: None).state == "completed"
    assert downloader.download_item(req, tmp_path, lambda _: None).state == "skipped"
    assert calls == ["failure", "success"]


def test_quality_metadata_tracks_folder_containing_requested_version(monkeypatch, tmp_path):
    req = DownloadRequest("abc123", "https://www.youtube.com/watch?v=abc123", "New", "New Channel", "video", "1080")
    old = build_video_dir(tmp_path, "Old Channel", "Old", req.video_id)
    old.mkdir(parents=True)
    (old / "video.mp4").write_bytes(b"360")
    archives = ArtifactArchives(tmp_path)
    archives.mark_complete("video", req.video_id)
    archives.set_video_quality(req.video_id, "360", old / "video.mp4")
    calls = []

    def download(request, root, artifact, cb):
        calls.append(request.quality)
        output = build_video_dir(root, request.channel_name, request.title, request.video_id)
        output.mkdir(parents=True, exist_ok=True)
        (output / "video.mp4").write_bytes(request.quality.encode())

    monkeypatch.setattr(downloader, "_run_yt_dlp", download)
    assert downloader.download_item(req, tmp_path, lambda _: None).state == "completed"
    assert downloader.download_item(req, tmp_path, lambda _: None).state == "skipped"
    # The old folder still contains 360p; changing back to it must not claim 1080p.
    old_request = DownloadRequest(**{**req.__dict__, "title": "Old", "channel_name": "Old Channel"})
    assert downloader.download_item(old_request, tmp_path, lambda _: None).state == "completed"
    assert calls == ["1080", "1080"]
