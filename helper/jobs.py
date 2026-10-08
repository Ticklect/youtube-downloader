from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from copy import deepcopy
from pathlib import Path
import threading
import uuid

from .downloader import DownloadRequest, ItemResult, download_item


ITEM_STATES = ("queued", "active", "completed", "skipped", "unavailable", "failed")
DEFAULT_MAX_WORKERS = 4


class JobManager:
    def __init__(self, max_workers: int = DEFAULT_MAX_WORKERS):
        self.max_workers = max_workers
        self._executor = ThreadPoolExecutor(max_workers=max_workers)
        self._jobs: dict[str, dict] = {}
        self._lock = threading.RLock()

    def create_job(self, items: list[DownloadRequest], root: Path) -> str:
        if not items:
            raise ValueError("Select at least one video.")
        job_id = uuid.uuid4().hex
        job = {
            "id": job_id,
            "status": "running",
            "root": Path(root).resolve(),
            "items": [
                {
                    "request": item,
                    "video_id": item.video_id,
                    "title": item.title,
                    "mode": item.mode,
                    "quality": item.quality,
                    "state": "queued",
                    "percent": 0.0,
                    "message": "",
                }
                for item in items
            ],
        }
        with self._lock:
            self._jobs[job_id] = job
        threading.Thread(target=self._run_job, args=(job_id,), daemon=True).start()
        return job_id

    def _set_progress(self, job_id: str, index: int, update: dict) -> None:
        with self._lock:
            item = self._jobs[job_id]["items"][index]
            if isinstance(update.get("percent"), (int, float)):
                item["percent"] = float(update["percent"])
            if update.get("artifact"):
                item["message"] = f"Downloading {update['artifact']}"

    def _execute_item(self, job_id: str, index: int, root: Path) -> ItemResult:
        with self._lock:
            item = self._jobs[job_id]["items"][index]
            item["state"] = "active"
            request = item["request"]
        try:
            return download_item(request, root, lambda update: self._set_progress(job_id, index, update))
        except Exception as exc:
            return ItemResult("failed", str(exc))

    def _run_job(self, job_id: str) -> None:
        with self._lock:
            job = self._jobs[job_id]
            root = job["root"]
            count = len(job["items"])
        futures = {self._executor.submit(self._execute_item, job_id, index, root): index for index in range(count)}
        for future in as_completed(futures):
            index = futures[future]
            result = future.result()
            with self._lock:
                item = self._jobs[job_id]["items"][index]
                item["state"] = result.state if result.state in ITEM_STATES else "failed"
                item["message"] = result.message
                if item["state"] in {"completed", "skipped", "unavailable"}:
                    item["percent"] = 100.0
        with self._lock:
            self._jobs[job_id]["status"] = "completed"

    def get_job(self, job_id: str) -> dict:
        with self._lock:
            if job_id not in self._jobs:
                raise KeyError(job_id)
            job = self._jobs[job_id]
            public_items = []
            for item in job["items"]:
                public_items.append({key: deepcopy(value) for key, value in item.items() if key != "request"})
            counts = {state: 0 for state in ITEM_STATES}
            for item in public_items:
                counts[item["state"]] += 1
            return {"id": job_id, "status": job["status"], "items": public_items, "counts": counts}

    def retry_failed(self, job_id: str) -> str:
        with self._lock:
            if job_id not in self._jobs:
                raise KeyError(job_id)
            job = self._jobs[job_id]
            failed = [item["request"] for item in job["items"] if item["state"] == "failed"]
            root = job["root"]
        if not failed:
            raise ValueError("This job has no failed items to retry.")
        return self.create_job(failed, root)
