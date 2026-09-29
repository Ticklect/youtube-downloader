# YouTube Downloader

A Chrome extension plus Windows helper for downloading public YouTube content you own or have permission to download. It can load a whole public channel, let you pick all or individual videos, choose the exact download folder, and save video, MP3 audio, transcripts, or all of them.

The helper is local-only. It binds to `127.0.0.1:17865` and does not use a cloud backend.

**Usage notice:** Use this tool only to download videos or channels that you own or have explicit permission to download. You are responsible for ensuring you have the rights or authorization to save any content you download.

## Requirements

- Windows 10 or 11.
- Google Chrome or another Chromium browser that can load unpacked extensions.
- Python 3.11 or newer.
- FFmpeg for video merging and MP3 extraction.

## Install

Open PowerShell in this project folder and run:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/setup.ps1
```

The setup script creates `.venv`, installs `helper/requirements.txt`, checks whether FFmpeg is available, builds the Windows Native Messaging helper-control host, and registers it for the current user. This is the one-time setup that lets the browser extension turn the local helper on and off without opening PowerShell.

If FFmpeg is missing, install it and then rerun setup. One option is:

```powershell
winget install Gyan.FFmpeg
```

## Load the Chrome extension

1. Open `chrome://extensions`.
2. Enable **Developer mode**.
3. Click **Load unpacked**.
4. Select this project's `extension` folder.
5. Pin **YouTube Downloader** if you want it visible on the toolbar.

## Use it

1. Click the toolbar extension. The complete downloader opens directly in the popup.
2. **Auto-start when needed** is enabled by default. If the helper is off, pressing **Load**, **Choose Folder**, **Download Selected**, or **Retry Failed** starts it automatically and continues the action.
3. The **Local helper** row also has manual **Turn On** / **Turn Off** control. Disable **Auto-start when needed** to use manual mode, where the helper stays off until you press **Turn On**.
4. Use **Red** or **Mono** in the header to switch the popup appearance. The extension remembers your choice.
5. Paste a public YouTube channel URL such as `https://youtube.com/@channel`.
6. Click **Load channel**.
7. Select individual videos, or use **Select all** / **Clear**.
8. Click **Choose folder** and pick exactly where you want the downloads stored. The helper remembers this folder until you change it.
9. Choose an output:
   - **Video**
   - **Audio (MP3)**
   - **Transcript**
   - **Everything**
10. For Video or Everything, choose **360p**, **720p**, **1080p**, or **Best available**.
11. Click the download button, which shows the current selection count (for example, **Download 1 video**).
12. Watch the progress list. If an item fails, use **Retry failed**.

If a video has creator-provided captions, those are preferred. Automatic captions are used when available as a fallback. Transcript downloads create both `transcript.vtt` and a cleaned `transcript.txt`. A missing transcript does not cancel the rest of a bulk job.

## Output layout

Downloads are organized underneath the folder you chose:

```text
Chosen Folder/
  Channel Name/
    Video title [video-id]/
      video.mp4
      audio.mp3
      transcript.vtt
      transcript.txt
  .youtube-channel-downloader/
    archive-video.txt
    archive-audio.txt
    archive-transcript.txt
```

The exact video container can differ when YouTube does not provide a compatible MP4 combination. The downloader keeps separate duplicate records for video, audio, and transcript outputs, so downloading a video does not prevent you from downloading its MP3 or transcript later.

## Troubleshooting

**Helper control not installed**
Run `powershell -ExecutionPolicy Bypass -File scripts/setup.ps1` again, then reload the unpacked extension.

**Manual fallback / Local helper is not running**
If Native Messaging is unavailable and you need a fallback, run `powershell -ExecutionPolicy Bypass -File scripts/start-helper.ps1`. Normal use does not require this command.

**Limited / FFmpeg missing**
Run `scripts/setup.ps1` again and install FFmpeg if it reports that FFmpeg is not on PATH.

**No public videos found**
Make sure you pasted a channel URL, not an individual watch or Shorts URL. Private and member-only videos are not supported.

**Transcript unavailable**
The video does not expose usable creator captions or automatic captions. The rest of the queue continues normally.

**Folder no longer works**
If the saved folder was moved, deleted, or became unwritable, click **Choose Folder** again.

## Remove helper control

To remove only the browser helper-control registration and generated native-host artifacts, run:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/uninstall-helper-control.ps1
```

This leaves the downloader project, `.venv`, and your downloaded files in place.

## Permission and limits

Use this tool only for content you own or otherwise have permission to download. It does not log in to YouTube, bypass private/member-only access, or circumvent DRM.

**Legal notice:** This software is provided for lawful use only. Users are solely responsible for ensuring they have the necessary rights and permissions to download, store, or use any content. The developer does not authorize copyright infringement or circumvention of access controls and is not responsible for misuse of the software.

## License

Licensed under the GNU Affero General Public License v3.0. See `LICENSE`.
