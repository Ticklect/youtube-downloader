from pathlib import Path
from unittest.mock import patch

import pytest

from helper.settings import SettingsStore, safe_child, validate_download_root


def test_settings_store_persists_download_root(tmp_path):
    root = tmp_path / "downloads"
    root.mkdir()
    settings_path = tmp_path / "settings.json"

    SettingsStore(settings_path).save_download_root(root)

    assert SettingsStore(settings_path).get_download_root() == root.resolve()


def test_missing_and_corrupt_settings_fall_back_to_empty(tmp_path):
    store = SettingsStore(tmp_path / "missing.json")
    assert store.load() == {}
    (tmp_path / "missing.json").write_text("not json", encoding="utf-8")
    assert store.load() == {}


def test_validate_download_root_rejects_nonexistent_path(tmp_path):
    with pytest.raises(ValueError, match="exist"):
        validate_download_root(tmp_path / "missing")


def test_validate_download_root_rejects_unwritable_path(tmp_path):
    with patch("helper.settings.tempfile.NamedTemporaryFile", side_effect=PermissionError):
        with pytest.raises(ValueError, match="writable"):
            validate_download_root(tmp_path)


def test_safe_child_stays_under_root_and_blocks_traversal(tmp_path):
    assert safe_child(tmp_path, "channel", "video") == (tmp_path / "channel" / "video").resolve()
    with pytest.raises(ValueError, match="outside"):
        safe_child(tmp_path, "..", "escape")


def test_deleted_persisted_root_is_not_returned(tmp_path):
    root = tmp_path / "downloads"
    root.mkdir()
    store = SettingsStore(tmp_path / "settings.json")
    store.save_download_root(root)
    root.rmdir()

    assert store.get_download_root() is None
