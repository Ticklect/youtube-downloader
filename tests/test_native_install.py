import json
from pathlib import Path
import subprocess


ROOT = Path(__file__).resolve().parents[1]
INSTALLER = ROOT / "scripts" / "install-native-host.ps1"
UNINSTALLER = ROOT / "scripts" / "uninstall-helper-control.ps1"
HOST_NAME = "com.ycd.helper_control"


def run_installer(artifact_root: Path):
    return subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(INSTALLER),
            "-SkipBuild",
            "-SkipRegistry",
            "-ArtifactRoot",
            str(artifact_root),
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=True,
    )


def test_installer_generates_deterministic_native_manifest_and_config(tmp_path):
    assert INSTALLER.exists()
    artifact_root = tmp_path / "native"
    run_installer(artifact_root)
    manifest_path = artifact_root / "install" / f"{HOST_NAME}.json"
    config_path = artifact_root / "install" / "config.json"
    first_manifest = manifest_path.read_text(encoding="utf-8")
    first_config = config_path.read_text(encoding="utf-8")

    run_installer(artifact_root)

    assert manifest_path.read_text(encoding="utf-8") == first_manifest
    assert config_path.read_text(encoding="utf-8") == first_config
    manifest = json.loads(first_manifest)
    config = json.loads(first_config)
    assert manifest["name"] == HOST_NAME
    assert manifest["description"] == "YouTube Downloader helper control"
    assert manifest["type"] == "stdio"
    assert Path(manifest["path"]).is_absolute()
    assert manifest["path"] == str((artifact_root / "dist" / "ycd-helper-control.exe").resolve())
    assert len(manifest["allowed_origins"]) == 1
    assert manifest["allowed_origins"][0].startswith("chrome-extension://")
    assert manifest["allowed_origins"][0].endswith("/")
    extension_id = manifest["allowed_origins"][0].removeprefix("chrome-extension://").removesuffix("/")
    assert len(extension_id) == 32
    assert set(extension_id) <= set("abcdefghijklmnop")
    assert config == {"repo_root": str(ROOT.resolve())}


def test_installer_registers_only_current_user_chrome_native_host_path():
    source = INSTALLER.read_text(encoding="utf-8")
    assert "HKCU:\\Software\\Google\\Chrome\\NativeMessagingHosts\\com.ycd.helper_control" in source
    assert "HKLM:" not in source
    assert "Set-Item" in source
    assert "allowed_origins" in source


def test_uninstaller_is_scoped_to_owned_registration_and_native_host_artifacts():
    assert UNINSTALLER.exists()
    source = UNINSTALLER.read_text(encoding="utf-8")
    assert "HKCU:\\Software\\Google\\Chrome\\NativeMessagingHosts\\com.ycd.helper_control" in source
    assert "native_host" in source
    assert "Get-ItemPropertyValue" in source
    assert "RegisteredManifest" in source
    assert "ManifestPath" in source
    assert "OrdinalIgnoreCase" in source
    assert ".venv\\Scripts\\python.exe" in source
    assert "HKLM:" not in source
    assert "Remove-Item" in source


def test_uninstaller_stops_verified_helper_before_removing_registration_or_artifacts():
    source = UNINSTALLER.read_text(encoding="utf-8")
    guard = source.index("--prepare-uninstall")
    registry_remove = source.index("Remove-Item -LiteralPath $RegistryPath")
    artifact_loop = source.index('foreach ($name in @("install", "dist", "build"))')

    assert guard < registry_remove < artifact_loop
    assert "$LASTEXITCODE -ne 0" in source
    assert "Refusing to uninstall" in source


def test_uninstaller_allows_broken_install_cleanup_only_when_expected_helper_is_not_healthy():
    source = UNINSTALLER.read_text(encoding="utf-8")
    missing_venv_fallback = source.index("Invoke-RestMethod")
    expected_service_check = source.index('$Health.service -eq "youtube-channel-downloader"')
    refusal = source.index("Helper environment is missing while the downloader helper is still running")
    registry_remove = source.index("Remove-Item -LiteralPath $RegistryPath")

    assert "if (Test-Path -LiteralPath $Python)" in source
    assert missing_venv_fallback < expected_service_check < refusal < registry_remove
    assert '$ExpectedHelperHealthy = $false' in source


def test_setup_invokes_native_host_installer_after_dependencies():
    setup = (ROOT / "scripts" / "setup.ps1").read_text(encoding="utf-8")
    assert "install-native-host.ps1" in setup
    assert setup.index("pip install -r") < setup.index("install-native-host.ps1")
