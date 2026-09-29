from __future__ import annotations

from dataclasses import dataclass
import re
from pathlib import Path
import threading
from typing import Callable

from .settings import safe_child
from .transcripts import vtt_to_text

try:
    from yt_dlp import YoutubeDL
except ImportError:
    YoutubeDL = None  # type: ignore[assignment]


ARTIFACT_KINDS = {"video", "audio", "transcript"}
INVALID_WINDOWS_CHARS = re.compile(r'[<>:"/\\|?*]')
WINDOWS_DEVICE_NAMES = {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))}
_ARTIFACT_LOCKS: dict[tuple[str, str, str], threading.Lock] = {}
_ARTIFACT_LOCKS_GUARD = threading.Lock()


@dataclass(frozen=True)
class DownloadRequest:
    video_id: str
    url: str
    title: str
    channel_name: str
    mode: str
    quality: str


@dataclass(frozen=True)
class ItemResult:
    state: str
    message: str = ""


def sanitize_component(value: str) -> str:
    cleaned = INVALID_WINDOWS_CHARS.sub("_", value)
    cleaned = re.sub(r"[\x00-\x1f]", "", cleaned).strip().rstrip(". ")
    if not cleaned:
        cleaned = "untitled"
    if cleaned.split(".", 1)[0].upper() in WINDOWS_DEVICE_NAMES:
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
        return (
            "bestvideo*[vcodec^=avc1]+bestaudio[acodec^=mp4a]/"
            "best[ext=mp4][vcodec^=avc1][acodec^=mp4a]"
        )
    if quality not in {"360", "720", "1080"}:
        raise ValueError("Unsupported video quality.")
    height = int(quality)
    return (
        f"bestvideo*[vcodec^=avc1][height<={height}]+bestaudio[acodec^=mp4a]/"
        f"best[ext=mp4][vcodec^=avc1][acodec^=mp4a][height<={height}]"
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
        if kind == "video":
            return safe_child(self.meta_dir, "archive-video-h264.txt")
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


def _artifact_kinds(mode: str) -> list[str]:
    if mode == "everything":
        return ["video", "audio", "transcript"]
    if mode in ARTIFACT_KINDS:
        return [mode]
    raise ValueError("Unsupported download mode.")


def _artifact_lock(root: Path, kind: str, video_id: str) -> threading.Lock:
    key = (str(Path(root).resolve()).casefold(), kind, video_id)
    with _ARTIFACT_LOCKS_GUARD:
        lock = _ARTIFACT_LOCKS.get(key)
        if lock is None:
            lock = threading.Lock()
            _ARTIFACT_LOCKS[key] = lock
        return lock


def _progress_hook(progress_cb: Callable[[dict], None], artifact: str):
    def hook(data: dict) -> None:
        status = data.get("status")
        update: dict = {"artifact": artifact, "status": status or "active"}
        downloaded = data.get("downloaded_bytes")
        total = data.get("total_bytes") or data.get("total_bytes_estimate")
        if isinstance(downloaded, (int, float)) and isinstance(total, (int, float)) and total > 0:
            update["percent"] = max(0.0, min(100.0, (downloaded / total) * 100.0))
        progress_cb(update)
    return hook


def _run_yt_dlp(request: DownloadRequest, root: Path, artifact: str, progress_cb: Callable[[dict], None]) -> None:
    if YoutubeDL is None:
        raise RuntimeError("yt-dlp is not installed.")
    output_dir = build_video_dir(root, request.channel_name, request.title, request.video_id)
    output_dir.mkdir(parents=True, exist_ok=True)
    options = build_ydl_options(artifact, request.quality, output_dir)
    options["progress_hooks"] = [_progress_hook(progress_cb, artifact)]
    with YoutubeDL(options) as ydl:
        result = ydl.download([request.url])
    if result not in (None, 0):
        raise RuntimeError(f"yt-dlp failed for {artifact}.")


def _finalize_transcript(request: DownloadRequest, root: Path) -> bool:
    output_dir = build_video_dir(root, request.channel_name, request.title, request.video_id)
    candidates = sorted(output_dir.glob("transcript*.vtt"), key=lambda path: (path.name != "transcript.vtt", len(path.name), path.name))
    if not candidates:
        return False
    selected = candidates[0]
    target = output_dir / "transcript.vtt"
    if selected != target:
        if target.exists():
            target.unlink()
        selected.replace(target)
    text = vtt_to_text(target.read_text(encoding="utf-8", errors="replace"))
    (output_dir / "transcript.txt").write_text(text, encoding="utf-8")
    return True


def download_item(request: DownloadRequest, root: Path, progress_cb: Callable[[dict], None]) -> ItemResult:
    root = Path(root).resolve()
    archives = ArtifactArchives(root)
    kinds = _artifact_kinds(request.mode)
    transcript_unavailable = False
    produced_artifact = False
    try:
        for artifact in kinds:
            with _artifact_lock(root, artifact, request.video_id):
                if archives.contains(artifact, request.video_id):
                    continue
                _run_yt_dlp(request, root, artifact, progress_cb)
                if artifact == "transcript":
                    if not _finalize_transcript(request, root):
                        transcript_unavailable = True
                        continue
                archives.mark_complete(artifact, request.video_id)
                produced_artifact = True
    except Exception as exc:
        return ItemResult("failed", str(exc))

    if transcript_unavailable and request.mode == "transcript":
        return ItemResult("unavailable", "No captions were available for this video.")
    if transcript_unavailable:
        return ItemResult("completed", "Media downloaded; transcript was unavailable.")
    if not produced_artifact:
        return ItemResult("skipped", "Requested output already exists in the archive.")
    return ItemResult("completed")
