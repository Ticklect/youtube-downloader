from __future__ import annotations

import re
from pathlib import Path

from .settings import safe_child


ARTIFACT_KINDS = {"video", "audio", "transcript"}
INVALID_WINDOWS_CHARS = re.compile(r'[<>:"/\\|?*]')
WINDOWS_DEVICE_NAMES = {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))}


def sanitize_component(value: str) -> str:
    cleaned = INVALID_WINDOWS_CHARS.sub("_", value)
    cleaned = re.sub(r"[\x00-\x1f]", "", cleaned).strip().rstrip(". ")
    if not cleaned:
        cleaned = "untitled"
    if cleaned.upper() in WINDOWS_DEVICE_NAMES:
        cleaned = f"_{cleaned}"
    return cleaned[:120].rstrip(". ") or "untitled"


def build_video_dir(root: Path, channel: str, title: str, video_id: str) -> Path:
    channel_part = sanitize_component(channel)[:100]
    id_part = sanitize_component(video_id)[:32]
    suffix = f" [{id_part}]"
    title_part = sanitize_component(title)[: max(1, 150 - len(suffix))].rstrip(". ")
    return safe_child(root, channel_part, f"{title_part}{suffix}")


def _video_format(quality: str) -> str:
    if quality == "best":
        return "bestvideo*+bestaudio/best"
    if quality not in {"360", "720", "1080"}:
        raise ValueError("Unsupported video quality.")
    height = int(quality)
    return (
        f"bestvideo*[height<={height}][ext=mp4]+bestaudio[ext=m4a]/"
        f"bestvideo*[height<={height}]+bestaudio/best[height<={height}]/best"
    )


def build_ydl_options(mode: str, quality: str, output_dir: Path) -> dict:
    if mode not in {"video", "audio", "transcript", "everything"}:
        raise ValueError("Unsupported download mode.")
    if quality not in {"360", "720", "1080", "best"}:
        raise ValueError("Unsupported video quality.")

    output_dir = Path(output_dir)
    options: dict = {
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "overwrites": True,
    }

    if mode in {"video", "everything"}:
        options["format"] = _video_format(quality)
        options["merge_output_format"] = "mp4"
        options["outtmpl"] = str(output_dir / "video.%(ext)s")

    if mode == "audio":
        options.update(
            {
                "format": "bestaudio/best",
                "outtmpl": str(output_dir / "audio.%(ext)s"),
                "postprocessors": [
                    {"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": "0"}
                ],
            }
        )

    if mode in {"transcript", "everything"}:
        options.update(
            {
                "writesubtitles": True,
                "writeautomaticsub": True,
                "subtitlesformat": "vtt",
            }
        )
        if mode == "transcript":
            options["skip_download"] = True
            options["outtmpl"] = str(output_dir / "transcript.%(ext)s")

    if mode == "everything":
        options["keepvideo"] = True
        options["postprocessors"] = [
            {"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": "0"}
        ]

    return options


class ArtifactArchives:
    def __init__(self, root: Path):
        self.root = Path(root).resolve()
        self.meta_dir = safe_child(self.root, ".youtube-channel-downloader")

    def _path(self, kind: str) -> Path:
        if kind not in ARTIFACT_KINDS:
            raise ValueError("Unknown artifact kind.")
        return safe_child(self.meta_dir, f"archive-{kind}.txt")

    def contains(self, kind: str, video_id: str) -> bool:
        path = self._path(kind)
        if not path.exists():
            return False
        return video_id in {line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip()}

    def mark_complete(self, kind: str, video_id: str) -> None:
        path = self._path(kind)
        path.parent.mkdir(parents=True, exist_ok=True)
        existing = set()
        if path.exists():
            existing = {line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip()}
        if video_id not in existing:
            with path.open("a", encoding="utf-8", newline="\n") as handle:
                handle.write(video_id + "\n")
