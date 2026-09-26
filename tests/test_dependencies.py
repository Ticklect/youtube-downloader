from unittest.mock import patch

from helper.dependencies import check_dependencies


def test_check_dependencies_reports_each_dependency_separately():
    with patch("helper.dependencies.importlib.util.find_spec", return_value=object()), patch(
        "helper.dependencies.shutil.which", return_value="C:/ffmpeg/bin/ffmpeg.exe"
    ):
        status = check_dependencies()

    assert status.yt_dlp is True
    assert status.ffmpeg is True
    assert status.messages == []


def test_check_dependencies_returns_readable_missing_messages_without_raising():
    with patch("helper.dependencies.importlib.util.find_spec", return_value=None), patch(
        "helper.dependencies.shutil.which", return_value=None
    ):
        status = check_dependencies()

    assert status.yt_dlp is False
    assert status.ffmpeg is False
    assert any("yt-dlp" in message for message in status.messages)
    assert any("FFmpeg" in message for message in status.messages)
