from __future__ import annotations

import json
import os
from pathlib import Path
import tempfile


def _default_settings_path() -> Path:
    base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    return base / "YouTubeChannelDownloader" / "settings.json"


def pick_download_root() -> Path | None:
    import tkinter as tk
    from tkinter import filedialog

    window = tk.Tk()
    window.withdraw()
    window.attributes("-topmost", True)
    try:
        selected = filedialog.askdirectory(title="Choose YouTube download folder")
    finally:
        window.destroy()
    return Path(selected).resolve() if selected else None


def validate_download_root(path: Path) -> Path:
    resolved = Path(path).expanduser().resolve()
    if not resolved.exists() or not resolved.is_dir():
        raise ValueError("Download folder does not exist.")
    try:
        with tempfile.NamedTemporaryFile(prefix=".ycd-write-", dir=resolved, delete=True):
            pass
    except (OSError, PermissionError) as exc:
        raise ValueError("Download folder is not writable.") from exc
    return resolved


def safe_child(root: Path, *parts: str) -> Path:
    safe_root = Path(root).resolve()
    candidate = safe_root.joinpath(*parts).resolve()
    if candidate != safe_root and safe_root not in candidate.parents:
        raise ValueError("Output path resolves outside the selected download root.")
    return candidate


class SettingsStore:
    def __init__(self, path: Path | None = None):
        self.path = Path(path) if path is not None else _default_settings_path()

    def load(self) -> dict:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except (OSError, json.JSONDecodeError, TypeError, ValueError):
            return {}

    def _save(self, data: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temp = self.path.with_suffix(self.path.suffix + ".tmp")
        temp.write_text(json.dumps(data, indent=2), encoding="utf-8")
        temp.replace(self.path)

    def save_download_root(self, path: Path) -> None:
        validated = validate_download_root(path)
        data = self.load()
        data["download_root"] = str(validated)
        self._save(data)

    def get_download_root(self) -> Path | None:
        raw = self.load().get("download_root")
        if not isinstance(raw, str) or not raw:
            return None
        try:
            return validate_download_root(Path(raw))
        except ValueError:
            return None
