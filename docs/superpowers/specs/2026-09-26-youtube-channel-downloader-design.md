# YouTube Channel Downloader — Design

Date: 2026-09-26

## Goal

Build a private Chrome extension and local Windows helper that lets one user paste a public YouTube channel URL, load the channel's videos, select all or selected videos, and download permitted content as video, audio, transcripts, or all three.

The user chooses the download folder from the extension and can change it at any time. The selected folder is remembered for later sessions.

## Scope

### Included

- Paste a YouTube channel URL.
- Load the channel's public videos.
- Show a selectable video list with Select All / Clear All.
- Download selected entries as:
  - video,
  - audio only,
  - transcript/subtitles,
  - or everything.
- Per-job video quality choice:
  - 360p,
  - 720p,
  - 1080p,
  - Best available.
- User-selected download root folder through a native Windows folder picker.
- Remember the last folder and last output/quality choices.
- Progress display for queued, active, completed, skipped, and failed items.
- Retry failed downloads.
- Avoid accidental duplicate downloads with separate completion tracking for video, audio, and transcript outputs.
- Organize output by channel and video.

### Not included in v1

- YouTube account login or private/member-only content.
- DRM circumvention.
- Built-in speech-to-text when a video has no captions.
- Cloud service, remote server, accounts, sync, or multi-user access.
- Automatic scheduled downloading.
- Publishing or redistributing downloaded media.

## Approaches Considered

### 1. Chrome extension only

Simplest installation, but not reliable for bulk media extraction, FFmpeg processing, arbitrary filesystem destinations, or yt-dlp-style format selection. Rejected.

### 2. Chrome extension + local HTTP helper — selected

The extension provides the UI. A Python process bound only to `127.0.0.1` runs yt-dlp and FFmpeg, opens the Windows folder picker, performs downloads, and reports progress.

This gives the best balance of easy development, reliable downloads, progress reporting, and folder selection.

### 3. Chrome Native Messaging

Stronger browser-to-helper integration but requires a native messaging manifest and Windows registry setup tied to an extension ID. This adds installation friction without enough benefit for a private single-PC v1. Deferred.

## Architecture

### Chrome extension

Manifest V3 extension with a compact popup or extension page containing:

- Channel URL field.
- `Load Channel` button.
- Download folder row:
  - current path,
  - `Choose Folder` button,
  - `Change` button once a folder is set.
- Video results list with:
  - checkbox,
  - title,
  - thumbnail when available,
  - duration when available,
  - video ID.
- `Select All` and `Clear All`.
- Output selector: Video / Audio / Transcript / Everything.
- Quality selector: 360p / 720p / 1080p / Best.
- Start Download button.
- Progress panel with per-video state and aggregate counts.
- Retry Failed button.

Extension settings are stored with `chrome.storage.local`.

### Local helper

Python service listening only on `127.0.0.1` on a fixed local port.

Responsibilities:

- Health/status endpoint.
- Channel discovery through yt-dlp.
- Native folder selection.
- Validation and persistence of the selected download folder.
- Starting download jobs.
- Running yt-dlp / FFmpeg subprocesses.
- Converting downloaded VTT captions to readable `.txt` when captions exist.
- Tracking job progress and failures.
- Supplying job status to the extension.

The helper must not listen on a LAN/public interface.

### External tools

- `yt-dlp` for channel discovery, media selection, subtitle retrieval, and download archive support.
- `FFmpeg` for merging compatible streams, remuxing when needed, and MP3 extraction.

The setup script will verify both dependencies and report a clear error if either is missing.

## Data Flow

### Load channel

1. User pastes a channel URL.
2. Extension sends the URL to the helper.
3. Helper invokes yt-dlp in flat-playlist/metadata mode.
4. Helper returns normalized video metadata.
5. Extension renders the list and enables selection controls.

### Choose download folder

1. User clicks `Choose Folder`.
2. Extension asks the local helper to open the native Windows folder picker.
3. User chooses a directory.
4. Helper validates that the directory exists and is writable.
5. Helper returns the path.
6. Extension stores the path in local settings and displays it.

The download button stays disabled until a valid folder is selected.

### Download selected videos

1. User selects videos, output type, quality, and starts the job.
2. Extension submits only the selected video IDs/URLs plus current options.
3. Helper creates a job and processes the selection with bounded concurrency.
4. Extension polls job status at a short interval and updates the progress UI.
5. Completed, skipped, and failed items remain visible until the user clears or starts another job.

## Download Rules

### Video

- `Best`: best available video + audio.
- `1080p`: best video at or below 1080p + best audio.
- `720p`: best video at or below 720p + best audio.
- `360p`: best video at or below 360p + best audio.
- Prefer MP4/M4A-compatible streams when they do not materially reduce the requested quality.
- Merge/remux to MP4 where supported; otherwise retain a working source container rather than fail solely because MP4 is unavailable.

### Audio

- Extract to MP3 using FFmpeg.
- Use a sensible high-quality VBR setting rather than inflating files with unnecessary bitrate.

### Transcript

- Prefer creator-provided subtitles/captions when available.
- Fall back to YouTube automatic captions when available.
- Save original `.vtt` plus a cleaned readable `.txt` version.
- If no captions are available, mark transcript as unavailable for that video rather than failing the whole job.

### Everything

- Apply video rules.
- Produce MP3 audio.
- Produce transcript files when captions exist.

## Output Layout

Under the user-selected root folder:

```text
<chosen folder>/
  <channel name>/
    <video title> [<video id>]/
      video.mp4
      audio.mp3
      transcript.vtt
      transcript.txt
  .youtube-channel-downloader/
    archive-video.txt
    archive-audio.txt
    archive-transcript.txt
```

Only files relevant to the selected output mode are created.

The video ID in the folder name prevents collisions when titles are duplicated or renamed.

## Duplicate Handling

The helper keeps independent completion records inside `.youtube-channel-downloader` under the chosen root:

- `archive-video.txt`
- `archive-audio.txt`
- `archive-transcript.txt`

This is intentionally separated by artifact type. Downloading a video must not prevent a later audio-only or transcript download of the same video.

- Previously completed artifacts of the requested type are skipped by default.
- Failed/incomplete artifacts are retryable.
- Transcript entries are marked complete only when transcript files were actually produced; "unavailable" remains a visible status rather than a fake completion.
- A future force-redownload control is intentionally excluded from v1 unless needed during testing.

## Error Handling

The UI must distinguish at least:

- Helper is not running.
- Invalid or unsupported URL.
- Channel could not be loaded.
- No public videos found.
- Folder was not selected.
- Folder is not writable.
- yt-dlp missing.
- FFmpeg missing.
- Video unavailable/private/deleted.
- Requested transcript unavailable.
- Network/download failure.
- FFmpeg processing failure.

One failed video must not cancel the remaining queue.

## Security and Locality

- Helper binds to `127.0.0.1` only.
- No remote API or cloud backend.
- No arbitrary command endpoint.
- Browser requests must come from a Chrome-extension origin; ordinary web-page origins are rejected.
- State-changing requests use a custom request header so normal cross-origin form submissions cannot trigger downloads silently.
- Requests are schema-validated and only predefined yt-dlp operations are allowed.
- Video/channel URLs are passed as process arguments, never concatenated into shell command strings.
- Output paths are generated beneath the chosen root.
- The folder picker is the source of the chosen root; download requests cannot supply arbitrary per-file filesystem paths.

## Project Structure

```text
youtube-channel-downloader/
  extension/
    manifest.json
    popup.html
    popup.css
    popup.js
    api.js
  helper/
    app.py
    downloader.py
    channel.py
    transcripts.py
    jobs.py
    settings.py
    requirements.txt
  scripts/
    setup.ps1
    start-helper.ps1
  tests/
    test_channel.py
    test_downloader.py
    test_transcripts.py
    test_jobs.py
  docs/
    superpowers/
      specs/
        2026-09-26-youtube-channel-downloader-design.md
  README.md
```

Exact module boundaries may be adjusted during planning if tests show a simpler split, but the extension UI and local helper remain separate components.

## Testing

### Automated

- Unit tests for URL validation and normalization.
- Unit tests for yt-dlp command construction at every quality/output combination.
- Unit tests for safe output-path construction.
- Unit tests for subtitle-to-text conversion.
- Unit tests for job state transitions and failure isolation.
- API tests using mocked yt-dlp/FFmpeg execution so tests do not bulk-download real media.

### Manual smoke test

Using content the user is permitted to download:

1. Start helper.
2. Load unpacked extension in Chrome.
3. Paste a channel URL.
4. Confirm videos populate.
5. Choose a custom download folder.
6. Download one short video at 360p.
7. Download its audio.
8. Download its transcript where captions exist.
9. Confirm progress/error states.
10. Repeat the same download and confirm duplicate skipping.
11. Restart extension/helper and confirm the chosen folder and last options are remembered.

## Success Criteria

The v1 is complete when the user can load a public channel, choose exactly where downloads are stored, select all or individual videos, choose video/audio/transcript/everything and video quality, run the downloads locally, see progress/failures, retry failures, and avoid unintended duplicate downloads.
