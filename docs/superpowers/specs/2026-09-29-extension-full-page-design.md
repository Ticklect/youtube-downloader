# Extension Full-Page Downloader Design

## Goal

Keep the existing workflow the user likes: paste a YouTube channel URL, load its videos, choose individual videos, choose output/quality/folder, and download through the local helper.

The change is primarily about presentation and usability. The current popup is too cramped once a channel contains many videos. The extension should open a full extension page for the complete downloader while keeping a small toolbar popup as a launcher/status surface.

## Product Shape

### Toolbar popup

The toolbar popup becomes intentionally small. It should show:

- Product name.
- Local helper state: Connected, Limited, or Offline.
- A primary **Open Downloader** button that opens or focuses the full extension page.
- A short helper action/message when the helper is unavailable.

The popup will no longer contain the full channel loading, video selection, folder, output, quality, queue, or progress UI.

### Full extension page

The full page keeps the existing feature set and interaction model:

1. Paste a supported YouTube channel URL.
2. Press **Load**.
3. See all returned public videos in a spacious list.
4. Select individual videos, **Select all**, or **Clear**.
5. Choose a download folder.
6. Choose output: Video, Audio (MP3), Transcript, or Everything.
7. Choose video quality when relevant: 360p, 720p, 1080p, or Best available.
8. Press **Download Selected**.
9. Watch per-item progress and retry failed items.

The page should preserve the dark visual language the user already likes rather than replacing it with a different design system.

## Layout

The page uses a centered responsive app shell with enough width for large channel lists.

### Header

- Product title and short description on the left.
- Helper status pill on the right.

### Source panel

- Wide URL field.
- Load button.
- Inline loading/error/status message.

### Main content

On desktop widths, use a two-column layout:

- **Left / primary column:** loaded channel and video list.
- **Right / controls column:** folder, output mode, quality, selection summary, and primary download action.

On narrower windows, collapse to one column.

### Video list

The list should be optimized for dozens or hundreds of videos:

- Larger thumbnails than the popup.
- Full title with sensible wrapping/truncation.
- Duration and video ID metadata.
- Checkbox per video.
- Sticky/select controls near the list header.
- Scroll the page naturally instead of trapping the user in a tiny 260px list.

Search/filter is not part of this first conversion unless implementation shows it is trivial and isolated; the priority is preserving the working flow while giving it space.

### Progress

The existing job polling behavior remains. Progress moves into a proper page section with more room for titles, states, percentages, and retry controls.

## Architecture

The local helper API remains unchanged.

The extension is split into three UI layers:

1. `popup.html` / `popup.js` / `popup.css`: launcher and helper status only.
2. New full-page files such as `downloader.html`, `downloader.js`, and `downloader.css`: complete downloader experience.
3. Existing shared modules `api.js` and `state.js`: reused by both surfaces where appropriate.

The manifest continues to use Manifest V3. The toolbar action keeps `popup.html` as its popup. The launcher opens the full page with `chrome.runtime.getURL("downloader.html")` and should focus an already-open downloader tab rather than creating duplicates when practical.

No content-script page detection is added. The user remains in control by pasting the channel URL manually.

## State and Data Flow

- Persistent preferences continue to use `chrome.storage.local`.
- Mode, quality, folder path, and current job ID remain persistent.
- Loaded video lists and current checkbox selection stay in page memory rather than being written to storage.
- The full page performs the same helper health check, folder retrieval, channel loading, job creation, polling, and retry calls the popup performs today.
- Helper restart behavior remains: a stale job ID is cleared when the helper reports `job_not_found`.

## Error Handling

- Offline helper state must not make the whole extension look broken. The full page remains usable enough to explain what is unavailable and how to start the helper.
- Dependency problems such as missing FFmpeg remain shown as **Limited**, not **Offline**.
- Load, folder, download, polling, and retry errors are shown inline without replacing the whole page.
- The primary download button stays disabled until the existing `canStartDownload` conditions are satisfied.

## Visual Direction

Preserve the current design language:

- Dark background.
- Slightly raised charcoal panels.
- Indigo/purple primary actions.
- Rounded controls and status pills.
- Small muted metadata.
- Green / amber / red helper states.

The page version should feel like the same product with more room, not a redesign into a different app.

## Testing

Implementation will use TDD for the structural behavior introduced by the split.

Tests should cover at minimum:

- Manifest still points the toolbar action at the launcher popup.
- Popup launcher opens the full downloader page.
- Reopening from the popup focuses/reuses an existing downloader tab where supported by the chosen implementation.
- Full page contains the existing required controls and imports the downloader logic.
- Existing state helper tests continue to pass.
- Existing Python helper tests continue to pass unchanged.
- Full project test suite remains green.

Manual verification should additionally confirm:

- The popup is compact and visually polished.
- Clicking **Open Downloader** opens the full page.
- A real channel can be loaded and individual videos selected.
- Folder selection, output selection, quality selection, download creation, progress polling, and retry behavior still work through the local helper.

## Non-Goals

This change does not add:

- Current-tab YouTube detection.
- Content scripts on youtube.com.
- A mandatory standalone desktop app.
- New download formats.
- Authentication/private/member-only access.
- DRM bypassing.
- A replacement helper protocol.

Those can be considered separately after the full-page extension experience is stable.
