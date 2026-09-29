# YouTube Channel Downloader

A private Chrome extension plus Windows helper for downloading public YouTube content you own or have permission to download. It can load a whole public channel, let you pick all or individual videos, choose the exact download folder, and save video, MP3 audio, transcripts, or all of them.

The helper is local-only. It binds to `127.0.0.1:17865` and does not use a cloud backend.

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

The setup script creates `.venv`, installs `helper/requirements.txt`, and checks whether FFmpeg is available. If FFmpeg is missing, install it and then reopen PowerShell. One option is:

```powershell
winget install Gyan.FFmpeg
```

Start the local helper:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/start-helper.ps1
```

Keep that helper running while you use the extension.

## Load the Chrome extension

1. Open `chrome://extensions`.
2. Enable **Developer mode**.
3. Click **Load unpacked**.
4. Select this project's `extension` folder.
5. Pin **YouTube Channel Downloader** if you want it visible on the toolbar.

## Use it

1. Click the toolbar extension. The complete downloader opens directly in the popup and shows **Connected** when the local helper is reachable.
2. Paste a public YouTube channel URL such as `https://youtube.com/@channel`.
3. Click **Load**.
4. Select individual videos, or use **Select all** / **Clear**.
5. Click **Choose Folder** and pick exactly where you want the downloads stored. The helper remembers this folder until you change it.
6. Choose an output:
   - **Video**
   - **Audio (MP3)**
   - **Transcript**
   - **Everything**
7. For Video or Everything, choose **360p**, **720p**, **1080p**, or **Best available**.
8. Click **Download Selected**.
9. Watch the progress list. If an item fails, use **Retry Failed**.

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

**Offline / Local helper is not running**
Run `powershell -ExecutionPolicy Bypass -File scripts/start-helper.ps1`.

**Limited / FFmpeg missing**
Run `scripts/setup.ps1` again and install FFmpeg if it reports that FFmpeg is not on PATH.

**No public videos found**
Make sure you pasted a channel URL, not an individual watch or Shorts URL. Private and member-only videos are not supported.

**Transcript unavailable**
The video does not expose usable creator captions or automatic captions. The rest of the queue continues normally.

**Folder no longer works**
If the saved folder was moved, deleted, or became unwritable, click **Choose Folder** again.

## Permission and limits

Use this tool only for content you own or otherwise have permission to download. It does not log in to YouTube, bypass private/member-only access, or circumvent DRM.
