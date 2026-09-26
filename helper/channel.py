from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlparse

try:
    from yt_dlp import YoutubeDL
except ImportError:  # dependency health endpoint reports this more cleanly
    YoutubeDL = None  # type: ignore[assignment]


@dataclass(frozen=True)
class VideoInfo:
    video_id: str
    title: str
    url: str
    thumbnail: str | None
    duration: int | None


@dataclass(frozen=True)
class ChannelResult:
    channel_name: str
    videos: list[VideoInfo]


def normalize_channel_url(url: str) -> str:
    raw = url.strip()
    if not raw:
        raise ValueError("Enter a YouTube channel URL.")
    parsed = urlparse(raw)
    if parsed.scheme not in {"http", "https"}:
        raise ValueError("Channel URL must use http or https.")
    host = (parsed.hostname or "").lower()
    if host not in {"youtube.com", "www.youtube.com", "m.youtube.com"}:
        raise ValueError("Only youtube.com channel URLs are supported.")

    parts = [part for part in parsed.path.split("/") if part]
    if not parts:
        raise ValueError("This is not a YouTube channel URL.")

    first = parts[0]
    valid = first.startswith("@") or first in {"channel", "c", "user"}
    if not valid:
        raise ValueError("This is not a supported YouTube channel URL.")
    if first in {"channel", "c", "user"} and len(parts) < 2:
        raise ValueError("Channel URL is incomplete.")

    if len(parts) > 1 and first.startswith("@") and parts[1] not in {"videos"}:
        raise ValueError("Use the channel home or videos URL.")
    if len(parts) > 2 and first in {"channel", "c", "user"} and parts[2] not in {"videos"}:
        raise ValueError("Use the channel home or videos URL.")

    base_parts = parts[:1] if first.startswith("@") else parts[:2]
    path = "/" + "/".join(base_parts) + "/videos"
    return f"https://www.youtube.com{path}"


def _thumbnail(entry: dict) -> str | None:
    direct = entry.get("thumbnail")
    if isinstance(direct, str) and direct:
        return direct
    thumbnails = entry.get("thumbnails")
    if isinstance(thumbnails, list):
        for item in reversed(thumbnails):
            if isinstance(item, dict) and isinstance(item.get("url"), str):
                return item["url"]
    return None


def load_channel(url: str) -> ChannelResult:
    normalized = normalize_channel_url(url)
    if YoutubeDL is None:
        raise RuntimeError("yt-dlp is not installed.")

    options = {
        "extract_flat": True,
        "skip_download": True,
        "quiet": True,
        "no_warnings": True,
        "ignoreerrors": True,
    }
    with YoutubeDL(options) as ydl:
        info = ydl.extract_info(normalized, download=False) or {}

    channel_name = (
        info.get("channel")
        or info.get("uploader")
        or info.get("title")
        or "YouTube Channel"
    )
    videos: list[VideoInfo] = []
    for entry in info.get("entries") or []:
        if not isinstance(entry, dict):
            continue
        video_id = entry.get("id")
        title = entry.get("title")
        if not isinstance(video_id, str) or not video_id or not isinstance(title, str) or not title:
            continue
        webpage_url = entry.get("webpage_url")
        if not isinstance(webpage_url, str) or not webpage_url.startswith(("http://", "https://")):
            webpage_url = f"https://www.youtube.com/watch?v={video_id}"
        duration_raw = entry.get("duration")
        duration = int(duration_raw) if isinstance(duration_raw, (int, float)) else None
        videos.append(
            VideoInfo(
                video_id=video_id,
                title=title,
                url=webpage_url,
                thumbnail=_thumbnail(entry),
                duration=duration,
            )
        )

    return ChannelResult(channel_name=str(channel_name), videos=videos)
