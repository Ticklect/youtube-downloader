# YouTube Downloader Desktop

**Beta · Windows x64 · Rust + Slint**

A native Windows app for browsing a public YouTube channel, choosing uploads, and saving videos, audio or available captions to your PC. No browser extension or Python service is needed.

![YouTube Downloader Desktop Library with sample videos](docs/screenshots/library.png)

[Download the desktop Beta](https://github.com/Ticklect/youtube-downloader-desktop/releases/tag/desktop-beta) · [Download options screenshot](docs/screenshots/options.png) · [Downloads screenshot](docs/screenshots/downloads.png)

## Install on Windows

1. Download the **Windows x64 ZIP** from the [desktop Beta release](https://github.com/Ticklect/youtube-downloader-desktop/releases/tag/desktop-beta).
2. Extract the whole ZIP. Keep the `bin` folder next to `YouTube Downloader Desktop.exe`.
3. Run `YouTube Downloader Desktop.exe`. Paste a public channel URL, load the videos, select the ones you want, then choose the output format and destination.

The portable build bundles **yt-dlp, FFmpeg and Deno**. There is no separate server, login or Python installation. It is **not code-signed** and has no Windows installer yet.

## What it currently does

- Browse and search up to **200 recent public videos** from a channel.
- Choose **Best, 1080p, 720p or 360p** video quality where available; save MP3 audio or English captions when available.
- Pick a destination folder, monitor progress, cancel jobs, retry failures, and see completed downloads.
- Switch between YouTube Red and Mono themes; restore the previous library, queue and settings on restart.

Downloads are performed locally through the bundled tools. App state is saved under `%LOCALAPPDATA%\YouTube Downloader Desktop\`.

## Building from source

Requires Windows x64, stable Rust with the MSVC toolchain, Windows SDK/C++ build tools and PowerShell. The `bin` tools are downloaded and checksum-verified by the packaging script. You do not need Python unless you want to regenerate the icon.

```powershell
cargo fmt --all -- --check
cargo test --locked
cargo clippy --locked --all-targets -- -D warnings
cargo build --release --locked
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/package-windows.ps1 -Tag Local-Build
```

The output is `dist\YouTube Downloader Desktop Beta Local-Build\` and a matching ZIP. Use a new tag for each packaging run; the script deliberately refuses to overwrite existing builds. The UI test suite is Windows-specific:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/smoke-beta-acceptance.ps1 -Executable 'dist\YouTube Downloader Desktop Beta Local-Build\YouTube Downloader Desktop.exe' -CaptureMatrix
```

These smoke tests use isolated synthetic session data rather than your real library or downloads. The screenshots above also use sample content.

## Desktop versus the extension-only alternative

The **desktop Beta is the main application in this repository**. A separate **browser-only extension experiment** is in development for people who prefer not to install a desktop app. It is not bundled here or published as an equivalent replacement yet. Direct browser downloads have different format and conversion limitations; the desktop app uses yt-dlp and FFmpeg to support more outputs.

The old Chrome/Firefox extension plus Python helper is **not** the current desktop application. Historical extension releases and their source remain available in the Git history and older GitHub Releases; do not use their setup instructions for this Beta.

## Limitations and license

- Windows x64 only; no signed installer and no macOS/Linux build tested.
- Channel browsing shows up to 200 recent public uploads, not the entire archive. Shorts and captions can be limited by YouTube availability.
- No private, members-only, DRM-protected or login-restricted video bypass. yt-dlp and YouTube can change, so some public downloads will fail.
- Beta software; test before relying on it for large queues. Download only content you own or have permission to save.

Source licensed under [AGPL-3.0](LICENSE). The UI uses [Slint](https://slint.dev/), with its required attribution accessible under **About & legal**. Portable builds also contain upstream FFmpeg notices; yt-dlp and Deno have their own upstream licenses.
