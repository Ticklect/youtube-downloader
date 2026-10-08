"""Windows release packaging checks, using isolated output directories."""

import importlib.util
import hashlib
import json
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import uuid
from zipfile import ZipFile

import pytest


ROOT = Path(__file__).resolve().parents[1]
POWERSHELL = shutil.which("powershell") or shutil.which("pwsh")
WINDOWS_ONLY = pytest.mark.skipif(
    sys.platform != "win32" or POWERSHELL is None,
    reason="The distributable and native messaging host target Windows PowerShell",
)

STATIC_FILES = {
    "README.md", "LICENSE", "helper/requirements.txt",
    "extension/manifest.json", "extension/browser-identities.json", "extension/popup.html", "extension/popup.css",
    "extension/popup.js", "extension/api.js", "extension/helper-control.js",
    "extension/job-lifecycle.js", "extension/state.js", "extension/storage-queue.js",
    "scripts/setup.ps1", "scripts/start-helper.ps1", "scripts/install-native-host.ps1",
    "scripts/uninstall-helper-control.ps1",
    *(f"extension/icons/icon{size}.png" for size in (16, 32, 48, 128)),
}


def _expected_files():
    return STATIC_FILES | {
        path.relative_to(ROOT).as_posix()
        for directory in ("helper", "native_host")
        for path in (ROOT / directory).glob("*.py")
    }


def _release_name(version: str, browser: str) -> str:
    label = "Firefox-Windows-Temporary" if browser == "Firefox" else "Chrome-Windows"
    return f"YouTube-Downloader-v{version}-{label}.zip"


def _build_release(root: Path, output: Path):
    return subprocess.run(
        [POWERSHELL, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
         str(root / "scripts" / "build-release.ps1"), "-SkipTests", "-OutputDir", str(output)],
        cwd=root,
        capture_output=True,
        text=True,
        timeout=90,
    )


def _archive_files(archive: Path):
    with ZipFile(archive) as bundle:
        assert bundle.testzip() is None, "Release ZIP has a corrupt member"
        files = {member.filename.replace("\\", "/") for member in bundle.infolist() if not member.is_dir()}
        assert all(not name.startswith("/") and ".." not in name.split("/") for name in files)
        return files


@WINDOWS_ONLY
@pytest.mark.parametrize("browser", ["Chrome", "Firefox"])
def test_release_archive_is_complete_and_runs_from_clean_extraction(tmp_path, browser):
    output = tmp_path / "output"
    built = _build_release(ROOT, output)
    assert built.returncode == 0, built.stdout + built.stderr

    version = json.loads((ROOT / "extension" / "manifest.json").read_text(encoding="utf-8"))["version"]
    archive = output / _release_name(version, browser)
    other_browser = "Firefox" if browser == "Chrome" else "Chrome"
    assert (output / _release_name(version, other_browser)).is_file()
    assert archive.is_file(), built.stdout
    assert f"SHA256: {hashlib.sha256(archive.read_bytes()).hexdigest().upper()}" in built.stdout
    assert _archive_files(archive) == _expected_files()

    extracted = tmp_path / "extracted"
    with ZipFile(archive) as bundle:
        bundle.extractall(extracted)

    # -I ignores the developer's PYTHONPATH and current-directory imports. The
    # test inserts only the extracted package, then verifies where imports came from.
    smoke = """
import json, pathlib, sys
root = pathlib.Path(sys.argv[1]).resolve()
sys.path.insert(0, str(root))
from helper import app
assert pathlib.Path(app.__file__).resolve().is_relative_to(root), app.__file__
service = app.create_app().test_client()
assert service.get('/health').status_code == 200
assert service.get('/folder').status_code == 403
manifest = json.loads((root / 'extension/manifest.json').read_text(encoding='utf-8'))
assert manifest['action']['default_popup'] == 'popup.html'
ids = json.loads((root / 'extension/browser-identities.json').read_text(encoding='utf-8'))
assert len(ids['key']) > 40 and ids['firefox_id']
"""
    subprocess.run(
        [sys.executable, "-I", "-c", smoke, str(extracted)],
        cwd=extracted, check=True, capture_output=True, text=True, timeout=20,
    )

    with ZipFile(archive) as bundle:
        manifest = json.loads(bundle.read("extension/manifest.json"))
        identities = json.loads(bundle.read("extension/browser-identities.json"))
        assert identities["firefox_id"] == "youtube-downloader@ticklect.local"
        if browser == "Firefox":
            assert "key" not in manifest
            assert manifest["browser_specific_settings"]["gecko"]["id"] == identities["firefox_id"]
        else:
            assert manifest["key"] == identities["key"]
            assert "browser_specific_settings" not in manifest

    # The release must not include its own generated ZIP or local build files.
    assert all(
        not any(part in {".venv", ".git", "__pycache__", "build", "dist", "install", "node_modules", "release"}
                for part in name.split("/"))
        for name in _archive_files(archive)
    )

    # A second attempt at the same path must preserve the published bytes.
    original = archive.read_bytes()
    duplicate = _build_release(ROOT, output)
    assert duplicate.returncode != 0
    assert "already exists" in duplicate.stdout + duplicate.stderr
    assert archive.read_bytes() == original

    # A version bump must work in an independent extracted package, including
    # when its output directory sits below the package root.
    shutil.copy2(ROOT / "scripts" / "build-release.ps1", extracted / "scripts" / "build-release.ps1")
    manifest_path = extracted / "extension" / "manifest.json"
    changed = json.loads(manifest_path.read_text(encoding="utf-8"))
    bumped_version = f"{int(version.split('.')[0]) + 1}.0.0"
    changed["version"] = bumped_version
    manifest_path.write_text(json.dumps(changed), encoding="utf-8")
    rebuilt_output = extracted / "release"
    rebuilt = _build_release(extracted, rebuilt_output)
    assert rebuilt.returncode == 0, rebuilt.stdout + rebuilt.stderr
    for target_browser in ("Chrome", "Firefox"):
        bumped_archive = rebuilt_output / _release_name(bumped_version, target_browser)
        assert _archive_files(bumped_archive) == _expected_files()
        with ZipFile(bumped_archive) as bundle:
            assert json.loads(bundle.read("extension/manifest.json"))["version"] == bumped_version


@WINDOWS_ONLY
@pytest.mark.skipif(importlib.util.find_spec("PyInstaller") is None, reason="PyInstaller not installed")
def test_isolated_native_host_executable_speaks_native_messaging():
    # Never touch the registered native host or its existing build directory.
    release_dir = ROOT / "release"
    release_dir.mkdir(exist_ok=True)
    artifact_root = release_dir / f".native-host-smoke-{uuid.uuid4().hex}"
    try:
        result = subprocess.run(
            [POWERSHELL, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
             str(ROOT / "scripts" / "install-native-host.ps1"),
             "-SkipRegistry", "-ArtifactRoot", str(artifact_root)],
            cwd=ROOT, capture_output=True, text=True, timeout=240,
        )
        assert result.returncode == 0, result.stdout + result.stderr
        executable = artifact_root / "dist" / "ycd-helper-control.exe"
        assert executable.is_file()
        message = json.dumps({"command": "status"}).encode("utf-8")
        reply = subprocess.run(
            [str(executable)], input=struct.pack("=I", len(message)) + message,
            capture_output=True, cwd=ROOT, timeout=30, check=True,
        ).stdout
        assert len(reply) >= 4
        size = struct.unpack("=I", reply[:4])[0]
        assert len(reply) == size + 4
        response = json.loads(reply[4:].decode("utf-8"))
        assert response["ok"] is True, response
        assert isinstance(response["healthy"], bool)
        assert isinstance(response["owned"], bool)
    finally:
        if artifact_root.is_dir():
            assert artifact_root.resolve().parent == release_dir.resolve()
            shutil.rmtree(artifact_root)
