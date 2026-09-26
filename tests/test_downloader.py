from pathlib import Path

import pytest

from helper.downloader import ArtifactArchives, build_video_dir, build_ydl_options, sanitize_component


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


def test_capped_video_format_never_falls_back_above_cap_and_does_not_force_mp4(tmp_path):
    options = build_ydl_options("video", "720", tmp_path)
    assert options["format"] == "bestvideo*[height<=720]+bestaudio/best[height<=720]"
    assert options["format_sort"] == ["res", "ext:mp4:m4a"]
    assert "merge_output_format" not in options


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


def test_artifact_archives_are_independent(tmp_path):
    archives = ArtifactArchives(tmp_path)
    archives.mark_complete("video", "abc123")
    assert archives.contains("video", "abc123") is True
    assert archives.contains("audio", "abc123") is False
    assert archives.contains("transcript", "abc123") is False


def test_archive_rejects_unknown_kind(tmp_path):
    with pytest.raises(ValueError):
        ArtifactArchives(tmp_path).contains("other", "abc")
