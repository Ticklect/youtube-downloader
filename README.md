# YouTube Downloader

Pick the videos you want from a YouTube channel and save them to a folder on your Windows PC. The Chrome extension gives you a channel browser, selections and download progress; a local Python helper handles the files.

**Windows 10/11 · Google Chrome · Python 3.11+ · FFmpeg**

- Browse the **200 newest public videos** from a channel's Videos tab.
- Search the loaded list, select specific uploads or select all matching results.
- Save **MP4 video**, **MP3 audio**, **transcripts**, or **Everything**.
- Choose a destination, watch individual downloads and retry failed items.
- Reopen the popup with your channel, selected videos and settings still there.

The extension runs in Chrome; downloading happens on your computer. There is no YouTube Downloader account or hosted processing service.

## Install on Windows

Get the ZIP from [GitHub Releases](https://github.com/Ticklect/youtube-downloader/releases), or download the repository source. Extract it to a folder you intend to keep. **Don't run setup from inside the ZIP or move the extracted folder afterward**: Chrome's native helper registration points to that installation path. If you relocate it, run setup again.

You'll need:

- **Google Chrome.** Native helper registration currently targets Chrome; other Chromium browsers are not supported by this installer.
- **Python 3.11 or newer**, with `python` available on PATH.
- **FFmpeg**, with `ffmpeg` available on PATH, for merging video and creating MP3 files.

To install FFmpeg with Windows Package Manager:

```powershell
winget install Gyan.FFmpeg
```

Open a new PowerShell window after installation so it picks up the updated PATH. In the extracted YouTube Downloader folder, run:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/setup.ps1
```

Setup creates a private `.venv`, installs the helper's Python dependencies, checks FFmpeg, builds the Windows Native Messaging control program and registers it for your Windows user. It may take a few minutes the first time. You do **not** need to keep PowerShell open afterward.

Then load the extension:

1. Open `chrome://extensions` in Google Chrome.
2. Turn on **Developer mode** (top right).
3. Click **Load unpacked** and select the extracted `extension` folder.
4. Pin **YouTube Downloader** to the toolbar if you use it often.

This is an unpacked extension, not a Chrome Web Store install. If you extract a newer release to a different location, rerun `scripts/setup.ps1` from that location and reload the extension in Chrome.

## Download a channel's videos

1. Open the extension and paste a public channel URL, for example `https://www.youtube.com/@channel`. Channel home and `/videos` links are supported.
2. Click **Load channel**. The popup shows the channel's most recent public video listings and thumbnails.
3. Use **Search video titles** to filter the list. Choose individual videos, **Select all** / **Select matches**, or **Clear** / **Clear matches**. Selection stays intact when you change the search.
4. Click **Choose Folder** to select a writable destination.
5. Select **Output** and, for video downloads, the desired **Quality**.
6. Click **Download**. Each item reports its state and progress. When a job finishes, **Retry failed** is available for failed items.

**Auto-start when needed** is enabled by default. The extension starts its local helper when an action needs it. You can use the **Turn On** and **Turn Off** controls yourself; disable auto-start for **manual mode**. The header shows whether the helper is connected.

The popup also remembers your chosen **Red** or **Mono** appearance.

### Output choices

| Output | Saved files | Notes |
| --- | --- | --- |
| Video | `video.mp4` | H.264 video with AAC audio when the source provides a compatible format |
| Audio (MP3) | `audio.mp3` | Audio extracted with FFmpeg |
| Transcript | `transcript.vtt` and `transcript.txt` | Creator captions preferred; automatic captions used when available |
| Everything | Video, audio and available transcript files | Missing captions do not stop the media download |

Video quality options are **360p**, **720p**, **1080p** and **Best available**. The numbered options are maximum resolutions, subject to formats the source provides. Quality has no effect on transcript-only or audio-only downloads.

Your chosen folder contains one subfolder per channel and one per video. Files appear only for the outputs you requested:

```text
Chosen folder/
  Channel name/
    Video title [video-id]/
      video.mp4
      audio.mp3
      transcript.vtt
      transcript.txt
  .youtube-channel-downloader/
    archive-video-h264.txt
    archive-video-quality.json
    archive-audio.txt
    archive-transcript.txt
```

The small archive files track downloads by format and remember the selected video quality. Repeating the same request can skip output already present; changing video quality downloads the video again. You can add a new format later without restarting the whole channel.

### Current limits

- Channel loading reads **up to the 200 newest public videos** from the channel's Videos tab. Older entries aren't shown if the channel has more than 200. This is not a full-channel archive tool for larger channels.
- Paste a channel URL, not a single watch page, Shorts link or playlist URL. Private, members-only and age-restricted content requiring login aren't supported.
- YouTube's available formats and captions vary. Some videos may not offer the requested quality or any transcript.
- The helper needs a network connection to reach YouTube. The files themselves are written to your selected local folder.

## Troubleshooting

**“Helper control not installed” or the helper stays off**

Run `powershell -ExecutionPolicy Bypass -File scripts/setup.ps1` again, then reload the extension at `chrome://extensions`. If you moved the folder, this also updates the registered path. In manual mode, press **Turn On** before loading a channel.

For troubleshooting only, you can start the Python service yourself:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/start-helper.ps1
```

**“Limited” or setup cannot find FFmpeg**

Run `ffmpeg -version` in a new PowerShell window. If it isn't found, install FFmpeg, reopen PowerShell and rerun setup. Video and MP3 downloads need FFmpeg.

**A channel loads no videos**

Use a public YouTube channel's home or Videos URL (`/@handle` or `/channel/ID`). A watch URL or channel with no public uploads will not produce a list.

**A transcript is unavailable**

The video has no usable captions in the formats the downloader handles. Select Video or Audio (MP3) if you only need the media; the rest of a batch continues.

**The save folder fails**

Use **Choose Folder** again. A moved, deleted or read-only destination can stop downloads.

**An item failed**

Check its message in the progress list and use **Retry failed** after the current job has finished. YouTube sometimes changes its download formats; an updated release or newer yt-dlp dependency may be needed.

## Privacy and permissions

The extension requests Chrome's `storage` and `nativeMessaging` permissions and access to `http://127.0.0.1:17865/*`. Chrome stores your channel selection and popup preferences locally. Native Messaging lets the extension start or stop the Windows helper; the HTTP service listens on the loopback address `127.0.0.1:17865` and checks the extension origin for operations.

There is **no separate cloud backend** for this project. The helper contacts YouTube through [yt-dlp](https://github.com/yt-dlp/yt-dlp) to list and download requested media. YouTube's own network services and policies still apply. You can review the extension and helper source in this repository.

Only download content you own or have **permission** to save. The project does not log in to YouTube, bypass members-only access or provide DRM circumvention. You are responsible for the rights and terms that apply to what you download.

## Remove or update

To unregister the Chrome helper control and remove its generated native-host files, run this from the installed project folder:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/uninstall-helper-control.ps1
```

The command does not delete your downloaded videos, the project folder or `.venv`. Remove those yourself if you no longer need them.

For a newer release, replace the installed source files, run `scripts/setup.ps1` again and reload the unpacked extension in Chrome. Keep downloaded media outside the application folder.

## Building a release

From a **source checkout** with dependencies installed, Node.js available and `.venv` set up, run:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/build-release.ps1
```

The build checks the JavaScript and Python tests and writes a versioned ZIP in `release/`, using the version from `extension/manifest.json`. The ZIP contains the extension, helper source and Windows setup scripts. It excludes your virtual environment and local settings. The build will refuse to overwrite an existing ZIP of the same version; move or rename the old one first. People installing the ZIP still need to run setup on their own computers.

## Credits and license

The local downloader uses [yt-dlp](https://github.com/yt-dlp/yt-dlp) for YouTube extraction, [FFmpeg](https://ffmpeg.org/) for media processing, [Flask](https://flask.palletsprojects.com/) for the local service and [PyInstaller](https://pyinstaller.org/) for the Windows helper-control executable.

Released under the **GNU Affero General Public License v3.0 (AGPL-3.0)**. See [LICENSE](LICENSE).
