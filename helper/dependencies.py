from __future__ import annotations

from dataclasses import dataclass
import importlib.util
import shutil


@dataclass(frozen=True)
class DependencyStatus:
    yt_dlp: bool
    ffmpeg: bool
    messages: list[str]


def check_dependencies() -> DependencyStatus:
    yt_dlp_available = importlib.util.find_spec("yt_dlp") is not None
    ffmpeg_available = shutil.which("ffmpeg") is not None
    messages: list[str] = []
    if not yt_dlp_available:
        messages.append("yt-dlp is not installed. Run scripts/setup.ps1.")
    if not ffmpeg_available:
        messages.append("FFmpeg is not available on PATH. Install FFmpeg and restart the helper.")
    return DependencyStatus(yt_dlp_available, ffmpeg_available, messages)
