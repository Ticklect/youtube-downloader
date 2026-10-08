# YouTube Downloader

A Chrome extension for saving videos from a public YouTube channel to your Windows PC. Pick the videos you want; a local helper downloads them to your chosen folder.

**[Download the latest release](https://github.com/Ticklect/youtube-downloader/releases/latest)** · Windows 10/11 · Google Chrome

## What it does

- Browse and search the **200 newest public videos** from a channel's Videos tab.
- Download **MP4 video**, **MP3 audio**, **transcripts** or **Everything**.
- Choose video quality: **360p**, **720p**, **1080p** or **Best available**, depending on what's available.
- Choose a folder, track progress and retry failed downloads.

## Install

You need **Chrome**, **Python 3.11+** and **FFmpeg** on Windows. You can install FFmpeg with `winget install Gyan.FFmpeg` (then reopen PowerShell).

1. Download the [release ZIP](https://github.com/Ticklect/youtube-downloader/releases/latest) and **extract it to a permanent folder**. Don't run setup inside the ZIP or move the folder afterward.
2. Open PowerShell in the extracted folder and run:

   ```powershell
   powershell -ExecutionPolicy Bypass -File scripts/setup.ps1
   ```

3. In Chrome, open `chrome://extensions`, switch on **Developer mode**, click **Load unpacked** and select the extracted **`extension`** folder.

Setup installs the local helper and registers it with Chrome. This is **not** a Chrome Web Store extension or a standalone installer.

## How to use it

1. Open the extension and paste a public channel URL (such as `https://www.youtube.com/@channel`).
2. Click **Load channel**, search the list and select the videos you want.
3. Click **Choose Folder**, then select Video, **Audio (MP3)**, **Transcript** or Everything.
4. Set video quality if needed and click **Download**. Use **Retry failed** for any unsuccessful items.

**Auto-start when needed** is enabled by default. To control the helper yourself, switch to **manual mode** and use **Turn On** / **Turn Off**.

Files are saved in folders organized by channel and video. Repeated downloads can skip existing files; changing video quality downloads a fresh video.

## Things to know

- Only the **200 newest public uploads** from a channel's **Videos** tab are listed. Older uploads and Shorts-only listings aren't covered.
- Private, members-only and login-required videos aren't supported. Transcripts require available captions.
- Downloads run on your PC. The helper listens on `127.0.0.1:17865` and contacts YouTube through [yt-dlp](https://github.com/yt-dlp/yt-dlp); there is no separate project cloud service.
- Only download content you own or have **permission** to save. DRM bypass is not supported.

## Troubleshooting

- **Helper won't start:** Rerun `scripts/setup.ps1` and reload the extension. In manual mode, click **Turn On**. As a fallback, run `powershell -ExecutionPolicy Bypass -File scripts/start-helper.ps1`.
- **FFmpeg missing:** Run `ffmpeg -version`; install FFmpeg and reopen PowerShell if it isn't found.
- **No videos or captions:** Check that the link points to a public channel, and that captions exist for the video.
- **Download failed:** Check the item message and select **Retry failed** after the job finishes.

To unregister the Chrome helper (without deleting downloaded files), run:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/uninstall-helper-control.ps1
```

After moving the install folder or upgrading to a new release, run setup again and reload the extension.

## Source and license

To build a release ZIP from a source checkout with dependencies installed, run `powershell -NoProfile -ExecutionPolicy Bypass -File scripts/build-release.ps1`.

Uses [yt-dlp](https://github.com/yt-dlp/yt-dlp), [FFmpeg](https://ffmpeg.org/), Flask and PyInstaller. Licensed under **AGPL-3.0**; see [LICENSE](LICENSE).
