from __future__ import annotations

from collections import OrderedDict
from contextlib import ExitStack
from dataclasses import dataclass
import json
import re
from pathlib import Path
import threading
from typing import Callable
import uuid

from .settings import safe_child
from .transcripts import vtt_to_text

try:
    from yt_dlp import YoutubeDL
except ImportError:
    YoutubeDL = None  # type: ignore[assignment]


ARTIFACT_KINDS = {"video", "audio", "transcript"}
CONCURRENT_FRAGMENT_DOWNLOADS = 4
INVALID_WINDOWS_CHARS = re.compile(r'[<>:"/\\|?*]')
WINDOWS_DEVICE_NAMES = {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))}
_ARTIFACT_LOCKS: dict[tuple[str, str, str], threading.Lock] = {}
_ARTIFACT_LOCKS_GUARD = threading.Lock()
_ARCHIVE_CACHE: OrderedDict[Path, tuple[tuple[int, int] | None, frozenset[str]]] = OrderedDict()
_ARCHIVE_CACHE_LOCK = threading.RLock()
_ARCHIVE_CACHE_LIMIT = 16
_VIDEO_QUALITY_CACHE: OrderedDict[Path, tuple[tuple[int, int] | None, dict[str, dict[str, str]]]] = OrderedDict()
_VIDEO_DIR_CACHE: OrderedDict[Path, dict[Path, tuple[int, dict[str, list[Path]]]]] = OrderedDict()
_VIDEO_DIR_CACHE_LOCK = threading.Lock()
_VIDEO_DIR_CACHE_LIMIT = 8


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
        "concurrent_fragment_downloads": CONCURRENT_FRAGMENT_DOWNLOADS,
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
            return self.meta_dir / "archive-video-h264.txt"
        return self.meta_dir / f"archive-{kind}.txt"

    @staticmethod
    def _entries(path: Path) -> frozenset[str]:
        # Every request gets its own ArtifactArchives object. Cache by the file's
        # identity so a large archive is not parsed for every item in a channel.
        try:
            stat = path.stat()
            version = (stat.st_mtime_ns, stat.st_size)
        except FileNotFoundError:
            version = None
        cached = _ARCHIVE_CACHE.get(path)
        if cached is not None and cached[0] == version:
            _ARCHIVE_CACHE.move_to_end(path)
            return cached[1]
        entries = frozenset(line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip()) if version else frozenset()
        _ARCHIVE_CACHE[path] = (version, entries)
        _ARCHIVE_CACHE.move_to_end(path)
        if len(_ARCHIVE_CACHE) > _ARCHIVE_CACHE_LIMIT:
            _ARCHIVE_CACHE.popitem(last=False)
        return entries

    def contains(self, kind: str, video_id: str) -> bool:
        path = self._path(kind)
        with _ARCHIVE_CACHE_LOCK:
            return video_id in self._entries(path)

    def mark_complete(self, kind: str, video_id: str) -> None:
        path = self._path(kind)
        with _ARCHIVE_CACHE_LOCK:
            existing = self._entries(path)
            if video_id in existing:
                return
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("a", encoding="utf-8", newline="\n") as handle:
                handle.write(video_id + "\n")
            stat = path.stat()
            _ARCHIVE_CACHE[path] = ((stat.st_mtime_ns, stat.st_size), existing | {video_id})
            _ARCHIVE_CACHE.move_to_end(path)
            if len(_ARCHIVE_CACHE) > _ARCHIVE_CACHE_LIMIT:
                _ARCHIVE_CACHE.popitem(last=False)

    def _video_quality_path(self) -> Path:
        return self.meta_dir / "archive-video-quality.json"

    @staticmethod
    def _video_qualities(path: Path) -> dict[str, dict[str, str]]:
        try:
            stat = path.stat()
            version = (stat.st_mtime_ns, stat.st_size)
        except FileNotFoundError:
            version = None
        cached = _VIDEO_QUALITY_CACHE.get(path)
        if cached is not None and cached[0] == version:
            _VIDEO_QUALITY_CACHE.move_to_end(path)
            return cached[1]
        try:
            data = json.loads(path.read_text(encoding="utf-8")) if version else {}
        except (OSError, ValueError):
            data = {}
        values = {
            video_id: record
            for video_id, record in data.items()
            if isinstance(video_id, str)
            and isinstance(record, dict)
            and isinstance(record.get("quality"), str)
            and record["quality"] in {"360", "720", "1080", "best"}
            and isinstance(record.get("path"), str)
        } if isinstance(data, dict) else {}
        _VIDEO_QUALITY_CACHE[path] = (version, values)
        _VIDEO_QUALITY_CACHE.move_to_end(path)
        if len(_VIDEO_QUALITY_CACHE) > _ARCHIVE_CACHE_LIMIT:
            _VIDEO_QUALITY_CACHE.popitem(last=False)
        return values

    def video_quality(self, video_id: str) -> str | None:
        with _ARCHIVE_CACHE_LOCK:
            record = self._video_qualities(self._video_quality_path()).get(video_id)
            return record["quality"] if record else None

    def video_path(self, video_id: str) -> Path | None:
        with _ARCHIVE_CACHE_LOCK:
            record = self._video_qualities(self._video_quality_path()).get(video_id)
            if not record:
                return None
            try:
                return safe_child(self.root, record["path"])
            except ValueError:
                return None

    def set_video_quality(self, video_id: str, quality: str | None, output_path: Path | None = None) -> None:
        if quality is not None and quality not in {"360", "720", "1080", "best"}:
            raise ValueError("Unsupported video quality.")
        if quality is not None and output_path is None:
            raise ValueError("Video output path is required to record video quality.")
        recorded_path = str(Path(output_path).resolve().relative_to(self.root)) if output_path else None
        next_record = {"quality": quality, "path": recorded_path} if quality is not None else None
        with _ARCHIVE_CACHE_LOCK:
            path = self._video_quality_path()
            current = self._video_qualities(path)
            if current.get(video_id) == next_record:
                return
            updated = dict(current)
            if quality is None:
                updated.pop(video_id, None)
            else:
                updated[video_id] = next_record
            path.parent.mkdir(parents=True, exist_ok=True)
            temp = path.with_name(f"{path.name}.{uuid.uuid4().hex}.tmp")
            try:
                temp.write_text(json.dumps(updated, separators=(",", ":")), encoding="utf-8")
                temp.replace(path)
            finally:
                temp.unlink(missing_ok=True)
            stat = path.stat()
            _VIDEO_QUALITY_CACHE[path] = ((stat.st_mtime_ns, stat.st_size), updated)
            _VIDEO_QUALITY_CACHE.move_to_end(path)
            if len(_VIDEO_QUALITY_CACHE) > _ARCHIVE_CACHE_LIMIT:
                _VIDEO_QUALITY_CACHE.popitem(last=False)


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


def _artifact_paths(output_dir: Path, kind: str) -> tuple[Path, ...]:
    if kind == "video":
        return (output_dir / "video.mp4",)
    if kind == "audio":
        return (output_dir / "audio.mp3",)
    if kind == "transcript":
        return (output_dir / "transcript.vtt", output_dir / "transcript.txt")
    raise ValueError("Unknown artifact kind.")


def _artifact_present_in(output_dir: Path, kind: str) -> bool:
    return all(path.is_file() for path in _artifact_paths(output_dir, kind))


def _historical_video_dirs(root: Path, video_id: str) -> tuple[Path, ...]:
    # A channel's directory mtime changes when videos are added, renamed or
    # removed. Reindex only those channels while keeping the cached paths
    # checked against disk for deleted artifact files.
    with _VIDEO_DIR_CACHE_LOCK:
        channels = _VIDEO_DIR_CACHE.setdefault(root, {})
        _VIDEO_DIR_CACHE.move_to_end(root)
        if len(_VIDEO_DIR_CACHE) > _VIDEO_DIR_CACHE_LIMIT:
            _VIDEO_DIR_CACHE.popitem(last=False)
        active: set[Path] = set()
        matches: list[Path] = []
        try:
            channel_paths = tuple(root.iterdir())
        except OSError:
            return ()
        for channel_dir in channel_paths:
            if channel_dir.name == ".youtube-channel-downloader" or channel_dir.is_symlink() or not channel_dir.is_dir():
                continue
            active.add(channel_dir)
            try:
                version = channel_dir.stat().st_mtime_ns
                cached = channels.get(channel_dir)
                if cached is None or cached[0] != version:
                    by_id: dict[str, list[Path]] = {}
                    for path in channel_dir.iterdir():
                        if path.is_symlink() or not path.is_dir():
                            continue
                        start = path.name.rfind(" [")
                        if start >= 0 and path.name.endswith("]"):
                            by_id.setdefault(path.name[start + 2:-1], []).append(path)
                    channels[channel_dir] = (version, by_id)
                matches.extend(channels[channel_dir][1].get(video_id, ()))
            except OSError:
                channels.pop(channel_dir, None)
        for removed in channels.keys() - active:
            del channels[removed]
        return tuple(matches)


def _artifact_exists(root: Path, request: DownloadRequest, kind: str) -> bool:
    current = build_video_dir(root, request.channel_name, request.title, request.video_id)
    if _artifact_present_in(current, kind):
        return True

    video_id = sanitize_component(request.video_id)[:32]
    return any(_artifact_present_in(video_dir, kind) for video_dir in _historical_video_dirs(root, video_id))


def _artifact_complete(archives: ArtifactArchives, root: Path, request: DownloadRequest, kind: str) -> bool:
    if not archives.contains(kind, request.video_id):
        return False
    if kind == "video":
        if archives.video_quality(request.video_id) != request.quality:
            return False
        recorded = archives.video_path(request.video_id)
        if recorded is None or not recorded.is_file():
            return False
        current = build_video_dir(root, request.channel_name, request.title, request.video_id) / "video.mp4"
        # If the selected folder has a different version, re-download it.
        return recorded == current if current.is_file() else True
    return _artifact_exists(root, request, kind)


def _mark_downloaded_video(archives: ArtifactArchives, root: Path, request: DownloadRequest) -> None:
    output_dir = build_video_dir(root, request.channel_name, request.title, request.video_id)
    if not _artifact_present_in(output_dir, "video"):
        raise RuntimeError("Video output was not created.")
    archives.mark_complete("video", request.video_id)
    archives.set_video_quality(request.video_id, request.quality, output_dir / "video.mp4")


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
    candidates = sorted(
        {*output_dir.glob("transcript*.vtt"), *output_dir.glob("video*.vtt")},
        key=lambda path: (
            path.name != "transcript.vtt",
            not path.name.startswith("transcript"),
            len(path.name),
            path.name,
        ),
    )
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


def _finalize_everything_audio(request: DownloadRequest, root: Path) -> bool:
    output_dir = build_video_dir(root, request.channel_name, request.title, request.video_id)
    target = output_dir / "audio.mp3"
    if target.is_file():
        return True
    candidates = sorted(output_dir.glob("video*.mp3"), key=lambda path: (len(path.name), path.name))
    if not candidates:
        return False
    candidates[0].replace(target)
    return True


def _download_fresh_everything(
    request: DownloadRequest,
    root: Path,
    archives: ArtifactArchives,
    progress_cb: Callable[[dict], None],
) -> ItemResult:
    archives.set_video_quality(request.video_id, None)
    _run_yt_dlp(request, root, "everything", progress_cb)
    output_dir = build_video_dir(root, request.channel_name, request.title, request.video_id)

    if not _artifact_present_in(output_dir, "video"):
        _run_yt_dlp(request, root, "video", progress_cb)
    if not _artifact_present_in(output_dir, "video"):
        raise RuntimeError("Video output was not created.")
    if not _finalize_everything_audio(request, root):
        _run_yt_dlp(request, root, "audio", progress_cb)
    if not _artifact_present_in(output_dir, "audio"):
        raise RuntimeError("Audio output was not created.")

    transcript_available = _finalize_transcript(request, root)
    _mark_downloaded_video(archives, root, request)
    archives.mark_complete("audio", request.video_id)
    if transcript_available:
        archives.mark_complete("transcript", request.video_id)
        return ItemResult("completed")
    return ItemResult("completed", "Media downloaded; transcript was unavailable.")


def download_item(request: DownloadRequest, root: Path, progress_cb: Callable[[dict], None]) -> ItemResult:
    root = Path(root).resolve()
    archives = ArtifactArchives(root)
    kinds = _artifact_kinds(request.mode)
    transcript_unavailable = False
    produced_artifact = False
    try:
        if request.mode == "everything":
            with ExitStack() as stack:
                for artifact in kinds:
                    stack.enter_context(_artifact_lock(root, artifact, request.video_id))
                missing = [artifact for artifact in kinds if not _artifact_complete(archives, root, request, artifact)]
                if not missing:
                    return ItemResult("skipped", "Requested output already exists in the archive.")
                if len(missing) == len(kinds):
                    return _download_fresh_everything(request, root, archives, progress_cb)
                for artifact in missing:
                    if artifact == "video":
                        archives.set_video_quality(request.video_id, None)
                    _run_yt_dlp(request, root, artifact, progress_cb)
                    if artifact == "transcript":
                        if not _finalize_transcript(request, root):
                            transcript_unavailable = True
                            continue
                    if artifact == "video":
                        _mark_downloaded_video(archives, root, request)
                    else:
                        archives.mark_complete(artifact, request.video_id)
                    produced_artifact = True
            if transcript_unavailable:
                return ItemResult("completed", "Media downloaded; transcript was unavailable.")
            return ItemResult("completed" if produced_artifact else "skipped")

        for artifact in kinds:
            with _artifact_lock(root, artifact, request.video_id):
                if _artifact_complete(archives, root, request, artifact):
                    continue
                if artifact == "video":
                    archives.set_video_quality(request.video_id, None)
                _run_yt_dlp(request, root, artifact, progress_cb)
                if artifact == "transcript":
                    if not _finalize_transcript(request, root):
                        transcript_unavailable = True
                        continue
                if artifact == "video":
                    _mark_downloaded_video(archives, root, request)
                else:
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
