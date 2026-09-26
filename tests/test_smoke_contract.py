import json
from pathlib import Path

from helper.app import MODES, PORT, QUALITIES, create_app


ROOT = Path(__file__).resolve().parents[1]


def test_extension_and_helper_share_routes_port_modes_and_qualities():
    manifest = json.loads((ROOT / "extension" / "manifest.json").read_text(encoding="utf-8"))
    api_source = (ROOT / "extension" / "api.js").read_text(encoding="utf-8")
    state_source = (ROOT / "extension" / "state.js").read_text(encoding="utf-8")
    app = create_app()
    routes = {rule.rule for rule in app.url_map.iter_rules()}

    assert PORT == 17865
    assert "http://127.0.0.1:17865/*" in manifest["host_permissions"]
    assert "http://127.0.0.1:17865" in api_source
    assert {"/health", "/channel", "/folder/pick", "/folder", "/jobs", "/jobs/<job_id>", "/jobs/<job_id>/retry"} <= routes
    assert MODES == {"video", "audio", "transcript", "everything"}
    assert QUALITIES == {"360", "720", "1080", "best"}
    for value in MODES | QUALITIES:
        assert f'"{value}"' in state_source


def test_readme_documents_complete_setup_and_usage_path():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    required = [
        "chrome://extensions",
        "Load unpacked",
        "scripts/setup.ps1",
        "scripts/start-helper.ps1",
        "Choose Folder",
        "360p",
        "720p",
        "1080p",
        "Best available",
        "Audio (MP3)",
        "Transcript",
        "permission",
    ]
    for text in required:
        assert text in readme

    for relative in [
        "extension/manifest.json",
        "scripts/setup.ps1",
        "scripts/start-helper.ps1",
        "helper/requirements.txt",
    ]:
        assert (ROOT / relative).exists()


def test_setup_and_popup_preserve_dependency_and_job_lifecycle_contracts():
    setup = (ROOT / "scripts" / "setup.ps1").read_text(encoding="utf-8")
    popup = (ROOT / "extension" / "popup.js").read_text(encoding="utf-8")

    assert "Setup incomplete" in setup
    assert "currentJobId" in popup
    assert 'chrome.storage.local.get(["mode", "quality", "folderPath", "currentJobId"])' in popup
