use crate::engine::{channel_url, validate_id, Mode, Video, MAX_CHANNEL_VIDEOS};
use serde::{Deserialize, Serialize};
use serde_json::Value;
use std::path::{Path, PathBuf};
use std::{fs, io};

pub const SCHEMA_VERSION: u32 = 1;
pub const MAX_JOBS: usize = 1_000;
pub const MAX_CHANNEL_HISTORY: usize = 64;
pub const MAX_SAVED_CHANNELS: usize = 16;
// Accommodate a saved 1,000-video library plus bounded queue/history entries.
const MAX_FILE_BYTES: u64 = 8_000_000;

#[derive(Clone, Debug, Serialize, Deserialize, PartialEq, Eq)]
pub struct SavedChannel {
    pub name: String,
    pub url: String,
}

#[derive(Clone, Debug, Serialize, Deserialize, PartialEq, Eq)]
pub struct SavedChannelHistory {
    pub name: String,
    pub url: String,
    pub loads: u32,
    pub last_opened: u64,
}

#[derive(Clone, Debug, Serialize, Deserialize, PartialEq, Eq)]
pub struct SavedVideo {
    pub video: Video,
    pub selected: bool,
}

#[derive(Clone, Copy, Debug, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "lowercase")]
pub enum SavedJobStatus {
    Queued,
    Active,
    Completed,
    Failed,
    Cancelled,
}

#[derive(Clone, Debug, Serialize, Deserialize, PartialEq, Eq)]
pub struct SavedJob {
    pub video: Video,
    pub mode: Mode,
    pub quality: String,
    pub folder: PathBuf,
    pub state: SavedJobStatus,
    pub detail: String,
}

#[derive(Clone, Debug, Serialize, Deserialize, PartialEq, Eq)]
pub struct SavedState {
    pub schema: u32,
    #[serde(default = "default_theme")]
    pub theme: String,
    pub channel_name: String,
    pub channel_url: String,
    #[serde(default)]
    pub channel_history: Vec<SavedChannelHistory>,
    #[serde(default)]
    pub saved_channels: Vec<SavedChannel>,
    pub folder: PathBuf,
    pub videos: Vec<SavedVideo>,
    pub jobs: Vec<SavedJob>,
}

fn default_theme() -> String {
    "red".to_owned()
}

fn valid_video(video: &Video) -> bool {
    validate_id(&video.id)
        && video.title.len() <= 1_000
        && !video.title.chars().any(char::is_control)
        && video.duration.len() <= 80
        && !video.duration.chars().any(char::is_control)
        && video.uploaded.len() <= 30
        && !video.uploaded.chars().any(char::is_control)
}

fn valid_channel(name: &str, url: &str) -> bool {
    !name.trim().is_empty()
        && name.len() <= 400
        && !name.chars().any(char::is_control)
        && url.len() <= 2_048
        && channel_url(url).is_ok_and(|canonical| canonical == url)
}

fn unique_channel_urls<'a>(urls: impl Iterator<Item = &'a str>) -> bool {
    let mut seen = std::collections::HashSet::new();
    urls.into_iter().all(|url| seen.insert(url))
}

fn recover_channel_history(value: Value) -> Vec<SavedChannelHistory> {
    let Value::Array(items) = value else {
        return Vec::new();
    };
    let mut seen = std::collections::HashSet::new();
    items
        .into_iter()
        .filter_map(|item| serde_json::from_value::<SavedChannelHistory>(item).ok())
        .filter(|entry| {
            entry.loads > 0
                && entry.last_opened > 0
                && valid_channel(&entry.name, &entry.url)
                && seen.insert(entry.url.clone())
        })
        .take(MAX_CHANNEL_HISTORY)
        .collect()
}

fn recover_saved_channels(value: Value) -> Vec<SavedChannel> {
    let Value::Array(items) = value else {
        return Vec::new();
    };
    let mut seen = std::collections::HashSet::new();
    items
        .into_iter()
        .filter_map(|item| serde_json::from_value::<SavedChannel>(item).ok())
        .filter(|entry| valid_channel(&entry.name, &entry.url) && seen.insert(entry.url.clone()))
        .take(MAX_SAVED_CHANNELS)
        .collect()
}

impl SavedState {
    fn validate(&self) -> Result<(), String> {
        if self.schema != SCHEMA_VERSION
            || !matches!(self.theme.as_str(), "red" | "mono")
            || self.channel_name.len() > 400
            || self.channel_url.len() > 2_048
            || self.channel_history.len() > MAX_CHANNEL_HISTORY
            || self.saved_channels.len() > MAX_SAVED_CHANNELS
            || self.videos.len() > MAX_CHANNEL_VIDEOS
            || self.jobs.len() > MAX_JOBS
            || !self.folder.is_absolute()
        {
            return Err("Saved download session has invalid bounds or version.".into());
        }
        if !self.channel_url.is_empty() {
            channel_url(&self.channel_url)?;
        }
        if !unique_channel_urls(
            self.channel_history
                .iter()
                .map(|channel| channel.url.as_str()),
        ) || !unique_channel_urls(
            self.saved_channels
                .iter()
                .map(|channel| channel.url.as_str()),
        ) || self.channel_history.iter().any(|entry| {
            !valid_channel(&entry.name, &entry.url) || entry.loads == 0 || entry.last_opened == 0
        }) || self
            .saved_channels
            .iter()
            .any(|entry| !valid_channel(&entry.name, &entry.url))
        {
            return Err("Saved session contains invalid channel history.".into());
        }
        if self.videos.iter().any(|item| !valid_video(&item.video))
            || self.jobs.iter().any(|item| {
                !valid_video(&item.video)
                    || !item.folder.is_absolute()
                    || item.detail.len() > 500
                    || !matches!(item.quality.as_str(), "best" | "1080" | "720" | "360")
            })
        {
            return Err("Saved session contained invalid video or job data.".into());
        }
        Ok(())
    }
}

pub fn session_path() -> PathBuf {
    let base = std::env::var_os("LOCALAPPDATA")
        .map(PathBuf::from)
        .or_else(|| {
            std::env::var_os("USERPROFILE").map(|v| PathBuf::from(v).join("AppData").join("Local"))
        })
        .unwrap_or_else(std::env::temp_dir);
    base.join("YouTube Downloader Desktop").join("session.json")
}

pub fn load(path: &Path) -> Result<Option<SavedState>, String> {
    let metadata = match fs::metadata(path) {
        Ok(metadata) => metadata,
        Err(error) if error.kind() == io::ErrorKind::NotFound => return Ok(None),
        Err(error) => return Err(format!("Unable to access saved session: {error}")),
    };
    if metadata.len() > MAX_FILE_BYTES {
        return Err("Saved session is larger than permitted.".into());
    }
    let contents =
        fs::read(path).map_err(|error| format!("Unable to read saved session: {error}"))?;
    if contents.len() as u64 > MAX_FILE_BYTES {
        return Err("Saved session is larger than permitted.".into());
    }
    let mut document: Value = serde_json::from_slice(&contents)
        .map_err(|_| "Saved session file has invalid JSON.".to_owned())?;
    // Optional channel suggestions must never make an otherwise healthy
    // download queue unrecoverable. A damaged entry is discarded locally;
    // the core videos, jobs and configuration retain their strict validation.
    let (history, saved_channels) = if let Some(fields) = document.as_object_mut() {
        (
            fields.remove("channel_history").unwrap_or(Value::Null),
            fields.remove("saved_channels").unwrap_or(Value::Null),
        )
    } else {
        (Value::Null, Value::Null)
    };
    let mut state: SavedState = serde_json::from_value(document)
        .map_err(|_| "Saved session file has invalid JSON.".to_owned())?;
    state.channel_history = recover_channel_history(history);
    state.saved_channels = recover_saved_channels(saved_channels);
    state.validate()?;
    for job in &mut state.jobs {
        if job.state == SavedJobStatus::Active {
            job.state = SavedJobStatus::Queued;
            job.detail = "Resuming after application restart…".into();
        }
    }
    Ok(Some(state))
}

pub fn save(path: &Path, snapshot: &SavedState) -> Result<(), String> {
    snapshot.validate()?;
    let content = serde_json::to_vec(snapshot).map_err(|_| "Unable to encode saved session.")?;
    if content.len() as u64 > MAX_FILE_BYTES {
        return Err("Session contains too much data to save.".into());
    }
    let parent = path.parent().ok_or("No session parent directory.")?;
    fs::create_dir_all(parent)
        .map_err(|error| format!("Unable to create session directory: {error}"))?;
    let file_name = path
        .file_name()
        .and_then(|n| n.to_str())
        .ok_or("Invalid session filename.")?;
    let temp = parent.join(format!(".{file_name}.{}.tmp", std::process::id()));
    fs::write(&temp, content).map_err(|error| format!("Unable to write session: {error}"))?;
    if let Err(error) = fs::rename(&temp, path) {
        let _ = fs::remove_file(&temp);
        return Err(format!("Unable to atomically save session: {error}"));
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    fn sample() -> SavedState {
        let video = Video {
            id: "abcdefghijk".into(),
            title: "A test upload".into(),
            duration: "1:03".into(),
            uploaded: String::new(),
        };
        SavedState {
            schema: SCHEMA_VERSION,
            theme: "red".into(),
            channel_name: "Test creator".into(),
            channel_url: "https://www.youtube.com/@TestCreator/videos".into(),
            channel_history: Vec::new(),
            saved_channels: Vec::new(),
            folder: PathBuf::from(r"C:\Downloads"),
            videos: vec![SavedVideo {
                video: video.clone(),
                selected: true,
            }],
            jobs: vec![SavedJob {
                video,
                mode: Mode::Video,
                quality: "720".into(),
                folder: PathBuf::from(r"C:\Downloads"),
                state: SavedJobStatus::Active,
                detail: "Downloading…".into(),
            }],
        }
    }

    #[test]
    fn roundtrip_recovers_active_job_without_losing_selection() {
        let dir = std::env::temp_dir().join(format!("ycd-session-test-{}", std::process::id()));
        let path = dir.join("session.json");
        let sample = sample();
        save(&path, &sample).unwrap();
        let loaded = load(&path).unwrap().unwrap();
        assert_eq!(loaded.channel_name, sample.channel_name);
        assert!(loaded.videos[0].selected);
        assert_eq!(loaded.jobs[0].state, SavedJobStatus::Queued);
        assert_eq!(loaded.jobs[0].mode, Mode::Video);
        std::fs::remove_file(&path).unwrap();
        std::fs::remove_dir(&dir).unwrap();
    }

    #[test]
    fn repeated_saves_replace_previous_snapshot_without_corrupting_it() {
        let dir = std::env::temp_dir().join(format!("ycd-save-replace-{}", std::process::id()));
        let path = dir.join("session.json");
        let first = sample();
        save(&path, &first).unwrap();
        let mut second = first.clone();
        second.channel_name = "Updated creator".into();
        second.jobs[0].state = SavedJobStatus::Completed;
        second.jobs[0].detail = "Download is complete".into();
        save(&path, &second).unwrap();
        let loaded = load(&path).unwrap().unwrap();
        assert_eq!(loaded.channel_name, "Updated creator");
        assert_eq!(loaded.jobs[0].detail, "Download is complete");
        std::fs::remove_file(&path).unwrap();
        std::fs::remove_dir(&dir).unwrap();
    }

    #[test]
    fn theme_is_validated_and_old_sessions_default_to_youtube_red() {
        let mut state = sample();
        state.theme = "mono".into();
        let encoded = serde_json::to_string(&state).unwrap();
        let decoded: SavedState = serde_json::from_str(&encoded).unwrap();
        assert_eq!(decoded.theme, "mono");
        state.theme = "bad-theme".into();
        assert!(state.validate().is_err());
        let mut old: serde_json::Value = serde_json::from_str(&encoded).unwrap();
        old.as_object_mut().unwrap().remove("theme");
        let restored: SavedState = serde_json::from_value(old).unwrap();
        assert_eq!(restored.theme, "red");
        assert!(restored.channel_history.is_empty());
        assert!(restored.saved_channels.is_empty());
        // Older desktop builds did not store an upload date in Video.
        let mut old_video: serde_json::Value =
            serde_json::to_value(&state.videos[0].video).unwrap();
        old_video.as_object_mut().unwrap().remove("uploaded");
        let parsed: Video = serde_json::from_value(old_video).unwrap();
        assert!(parsed.uploaded.is_empty());
    }

    #[test]
    fn channel_history_and_saved_bar_roundtrip_without_schema_bump() {
        let mut state = sample();
        state.channel_history.push(SavedChannelHistory {
            name: "Real creator".into(),
            url: "https://www.youtube.com/@realcreator/videos".into(),
            loads: 3,
            last_opened: 5,
        });
        state.saved_channels.push(SavedChannel {
            name: "Real creator".into(),
            url: "https://www.youtube.com/@realcreator/videos".into(),
        });
        let json = serde_json::to_vec(&state).unwrap();
        let decoded: SavedState = serde_json::from_slice(&json).unwrap();
        decoded.validate().unwrap();
        assert_eq!(decoded.channel_history[0].loads, 3);
        assert_eq!(decoded.saved_channels[0].name, "Real creator");
        let mut prior: serde_json::Value = serde_json::from_slice(&json).unwrap();
        prior.as_object_mut().unwrap().remove("channel_history");
        prior.as_object_mut().unwrap().remove("saved_channels");
        let decoded_legacy: SavedState = serde_json::from_value(prior).unwrap();
        decoded_legacy.validate().unwrap();
    }

    #[test]
    fn history_rejects_external_urls_duplicates_and_invalid_counts() {
        let mut state = sample();
        let entry = SavedChannelHistory {
            name: "Known creator".into(),
            url: "https://www.youtube.com/@knowncreator/videos".into(),
            loads: 1,
            last_opened: 1,
        };
        state.channel_history.push(entry.clone());
        state.validate().unwrap();
        state.channel_history.push(entry.clone());
        assert!(state.validate().is_err());
        state.channel_history.pop();
        state.channel_history[0].url = "https://evil.invalid/@knowncreator".into();
        assert!(state.validate().is_err());
        state.channel_history[0] = entry;
        state.channel_history[0].loads = 0;
        assert!(state.validate().is_err());
        state.channel_history[0].loads = 1;
        state.saved_channels.push(SavedChannel {
            name: "Hidden\nlabel".into(),
            url: state.channel_history[0].url.clone(),
        });
        assert!(state.validate().is_err());
    }

    #[test]
    fn corrupt_optional_channel_entries_do_not_erase_valid_video_and_queue() {
        let dir = std::env::temp_dir().join(format!("ycd-recover-channels-{}", std::process::id()));
        std::fs::create_dir_all(&dir).unwrap();
        let path = dir.join("session.json");
        let mut document = serde_json::to_value(sample()).unwrap();
        document["channel_history"] = serde_json::json!([
            {"name": "Wrong host", "url": "https://evil.invalid/@creator", "loads": 9, "last_opened": 4},
            {"name": "Good channel", "url": "https://www.youtube.com/@goodchannel/videos", "loads": 3, "last_opened": 10},
            {"name": "Missing count", "url": "https://www.youtube.com/@broken/videos"},
            {"name": "Good channel again", "url": "https://www.youtube.com/@goodchannel/videos", "loads": 8, "last_opened": 11}
        ]);
        document["saved_channels"] = serde_json::json!([
            {"name": "Saved good channel", "url": "https://www.youtube.com/@goodchannel/videos"},
            {"name": "Bad control\n", "url": "https://www.youtube.com/@badchannel/videos"},
            {"name": 404, "url": "https://www.youtube.com/@badchannel/videos"}
        ]);
        std::fs::write(&path, serde_json::to_vec(&document).unwrap()).unwrap();
        let loaded = load(&path).unwrap().unwrap();
        assert_eq!(loaded.videos.len(), 1);
        assert!(loaded.videos[0].selected);
        assert_eq!(loaded.jobs[0].state, SavedJobStatus::Queued);
        assert_eq!(loaded.channel_history.len(), 1);
        assert_eq!(loaded.channel_history[0].loads, 3);
        assert_eq!(loaded.saved_channels.len(), 1);
        assert_eq!(loaded.saved_channels[0].name, "Saved good channel");
        std::fs::remove_file(&path).unwrap();
        std::fs::remove_dir(&dir).unwrap();
    }

    #[test]
    fn invalid_stored_jobs_and_external_urls_are_rejected() {
        let mut state = sample();
        state.jobs[0].video.id = ";rm -rf /".into();
        assert!(state.validate().is_err());
        state = sample();
        state.channel_url = "https://evil.invalid/@creator".into();
        assert!(state.validate().is_err());
        state = sample();
        state.jobs[0].folder = PathBuf::from("relative-path");
        assert!(state.validate().is_err());
    }

    #[test]
    fn oversized_session_and_corrupt_json_fail_safely() {
        let dir =
            std::env::temp_dir().join(format!("ycd-large-session-test-{}", std::process::id()));
        std::fs::create_dir_all(&dir).unwrap();
        let path = dir.join("session.json");
        std::fs::write(&path, vec![b'x'; (MAX_FILE_BYTES + 10) as usize]).unwrap();
        assert!(load(&path).unwrap_err().contains("larger"));
        std::fs::write(&path, b"{ bad json").unwrap();
        assert!(load(&path).unwrap_err().contains("JSON"));
        std::fs::remove_file(&path).unwrap();
        std::fs::remove_dir(&dir).unwrap();
    }

    #[test]
    fn thousand_video_library_roundtrips_without_losing_selections() {
        let dir = std::env::temp_dir().join(format!("ycd-paged-library-{}", std::process::id()));
        let path = dir.join("session.json");
        let mut state = sample();
        state.videos = (0..MAX_CHANNEL_VIDEOS)
            .map(|index| SavedVideo {
                video: Video {
                    id: format!("{index:011}"),
                    title: format!("Upload {index}: {}", "description ".repeat(15)),
                    duration: "12:34".into(),
                    uploaded: String::new(),
                },
                selected: index % 200 == 0,
            })
            .collect();
        save(&path, &state).unwrap();
        let restored = load(&path).unwrap().unwrap();
        assert_eq!(restored.videos.len(), MAX_CHANNEL_VIDEOS);
        assert_eq!(
            restored
                .videos
                .iter()
                .filter(|video| video.selected)
                .count(),
            5
        );
        std::fs::remove_file(path).unwrap();
        std::fs::remove_dir(dir).unwrap();
    }
}
