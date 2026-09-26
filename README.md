# YouTube Channel Downloader

Private local Chrome extension + Windows helper for downloading public YouTube content you are permitted to download.

## Bootstrap

1. Run `powershell -ExecutionPolicy Bypass -File scripts/setup.ps1`.
2. Install FFmpeg if the setup script reports it missing.
3. Run `powershell -ExecutionPolicy Bypass -File scripts/start-helper.ps1`.
4. Load the `extension` directory as an unpacked Chrome extension once it exists.

The helper listens only on `127.0.0.1`.
