from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from urllib.parse import urlparse

from flask import Flask, jsonify, make_response, request

from .channel import ChannelResult, load_channel
from .dependencies import check_dependencies
from .jobs import DownloadRequest, JobManager
from .settings import SettingsStore, pick_download_root

PORT = 17865
ALLOWED_METHODS = "GET, POST, OPTIONS"
ALLOWED_HEADERS = "Content-Type, X-YCD-Client"
MODES = {"video", "audio", "transcript", "everything"}
QUALITIES = {"360", "720", "1080", "best"}


def _valid_extension_origin(origin: str | None) -> bool:
    if not origin:
        return False
    parsed = urlparse(origin)
    return parsed.scheme == "chrome-extension" and bool(parsed.netloc) and not parsed.path.strip("/")


def _error(code: str, message: str, status: int):
    return jsonify({"error": {"code": code, "message": message}}), status


def _youtube_video_url(url: object) -> bool:
    if not isinstance(url, str):
        return False
    parsed = urlparse(url)
    return parsed.scheme in {"http", "https"} and (parsed.hostname or "").lower() in {
        "youtube.com",
        "www.youtube.com",
        "m.youtube.com",
        "youtu.be",
    }


def create_app(
    *,
    settings_store: SettingsStore | None = None,
    job_manager: JobManager | None = None,
    channel_loader=load_channel,
    folder_picker=pick_download_root,
    dependency_checker=check_dependencies,
) -> Flask:
    app = Flask(__name__)
    store = settings_store or SettingsStore()
    jobs = job_manager or JobManager(max_workers=2)

    @app.before_request
    def security_gate():
        origin = request.headers.get("Origin")
        if request.method == "GET" and not origin:
            return None
        if not _valid_extension_origin(origin):
            return _error("extension_origin_required", "Requests must come from the Chrome extension.", 403)
        if request.method == "OPTIONS":
            return make_response("", 204)
        if request.method in {"POST", "PUT", "PATCH", "DELETE"} and request.headers.get("X-YCD-Client") != "1":
            return _error("client_header_required", "Missing downloader client header.", 403)
        return None

    @app.after_request
    def cors_headers(response):
        origin = request.headers.get("Origin")
        if _valid_extension_origin(origin):
            response.headers["Access-Control-Allow-Origin"] = origin
            response.headers["Vary"] = "Origin"
            response.headers["Access-Control-Allow-Methods"] = ALLOWED_METHODS
            response.headers["Access-Control-Allow-Headers"] = ALLOWED_HEADERS
            response.headers["Access-Control-Max-Age"] = "600"
        return response

    @app.get("/health")
    def health():
        status = dependency_checker()
        return jsonify({
            "service": "youtube-channel-downloader",
            "ok": status.yt_dlp and status.ffmpeg,
            "dependencies": asdict(status),
        })

    @app.post("/channel")
    def channel_route():
        payload = request.get_json(silent=True) or {}
        url = payload.get("url")
        if not isinstance(url, str) or not url.strip():
            return _error("invalid_channel_url", "Enter a YouTube channel URL.", 400)
        try:
            result: ChannelResult = channel_loader(url)
        except ValueError as exc:
            return _error("invalid_channel_url", str(exc), 400)
        except Exception as exc:
            return _error("channel_load_failed", str(exc), 502)
        if not result.videos:
            return _error("no_videos", "No public videos were found on this channel.", 404)
        return jsonify({"channel_name": result.channel_name, "videos": [asdict(video) for video in result.videos]})

    @app.post("/folder/pick")
    def folder_pick_route():
        selected = folder_picker()
        if selected is None:
            current = store.get_download_root()
            return jsonify({"cancelled": True, "path": str(current) if current else None})
        try:
            store.save_download_root(Path(selected))
        except ValueError as exc:
            return _error("folder_invalid", str(exc), 400)
        current = store.get_download_root()
        return jsonify({"cancelled": False, "path": str(current) if current else None})

    @app.get("/folder")
    def folder_get_route():
        current = store.get_download_root()
        return jsonify({"path": str(current) if current else None})

    @app.post("/jobs")
    def jobs_create_route():
        root = store.get_download_root()
        if root is None:
            return _error("folder_required", "Choose a writable download folder first.", 400)
        payload = request.get_json(silent=True) or {}
        mode = payload.get("mode")
        quality = payload.get("quality")
        videos = payload.get("videos")
        if mode not in MODES:
            return _error("invalid_mode", "Unsupported output mode.", 400)
        if quality not in QUALITIES:
            return _error("invalid_quality", "Unsupported video quality.", 400)
        if not isinstance(videos, list) or not videos:
            return _error("no_videos_selected", "Select at least one video.", 400)

        requests: list[DownloadRequest] = []
        for item in videos:
            if not isinstance(item, dict):
                return _error("invalid_video", "Invalid video entry.", 400)
            video_id = item.get("video_id")
            video_url = item.get("url")
            title = item.get("title")
            channel_name = item.get("channel_name")
            if not all(isinstance(value, str) and value.strip() for value in [video_id, title, channel_name]) or not _youtube_video_url(video_url):
                return _error("invalid_video", "Each video must contain a valid YouTube URL, ID, title, and channel name.", 400)
            requests.append(
                DownloadRequest(
                    video_id=video_id.strip(),
                    url=video_url,
                    title=title.strip(),
                    channel_name=channel_name.strip(),
                    mode=mode,
                    quality=quality,
                )
            )
        try:
            job_id = jobs.create_job(requests, root)
        except ValueError as exc:
            return _error("job_invalid", str(exc), 400)
        return jsonify({"job_id": job_id}), 202

    @app.get("/jobs/<job_id>")
    def jobs_get_route(job_id: str):
        try:
            return jsonify(jobs.get_job(job_id))
        except KeyError:
            return _error("job_not_found", "Job not found.", 404)

    @app.post("/jobs/<job_id>/retry")
    def jobs_retry_route(job_id: str):
        try:
            new_id = jobs.retry_failed(job_id)
        except KeyError:
            return _error("job_not_found", "Job not found.", 404)
        except ValueError as exc:
            return _error("nothing_to_retry", str(exc), 400)
        return jsonify({"job_id": new_id}), 202

    return app


def main() -> None:
    app = create_app()
    app.run(host="127.0.0.1", port=PORT, threaded=True)


if __name__ == "__main__":
    main()
