#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

mod engine;
#[cfg(windows)]
mod single_instance;
mod store;
mod thumbnails;

use engine::{Mode, Video};
use slint::{ComponentHandle, Model, ModelRc, VecModel};
use std::path::PathBuf;
use std::rc::Rc;
use std::sync::{
    atomic::{AtomicBool, AtomicU64, Ordering},
    Arc, Mutex,
};

slint::include_modules!();

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
enum JobState {
    Queued,
    Active,
    Completed,
    Failed,
    Cancelled,
}

struct Job {
    video: Video,
    mode: Mode,
    quality: String,
    folder: PathBuf,
    status: JobState,
    percent: i32,
    detail: String,
    cancel: Arc<AtomicBool>,
}

// A request for the same video in a different destination is a distinct job.
// Only identical in-flight destinations are duplicates.
fn is_pending_duplicate(
    job: &Job,
    video: &Video,
    mode: Mode,
    quality: &str,
    folder: &PathBuf,
) -> bool {
    job.video.id == video.id
        && job.mode == mode
        && job.quality == quality
        && job.folder == *folder
        && matches!(job.status, JobState::Queued | JobState::Active)
}

fn begin_channel_request(generation: &AtomicU64) -> u64 {
    generation.fetch_add(1, Ordering::SeqCst) + 1
}

#[derive(Default)]
struct State {
    theme: String,
    videos: Vec<(Video, bool)>,
    jobs: Vec<Job>,
    active: usize,
    channel_name: String,
    channel_url: String,
    folder: PathBuf,
}

impl State {
    fn persist(&self) {
        let snapshot = store::SavedState {
            schema: store::SCHEMA_VERSION,
            theme: self.theme.clone(),
            channel_name: self.channel_name.clone(),
            channel_url: self.channel_url.clone(),
            folder: self.folder.clone(),
            videos: self
                .videos
                .iter()
                .map(|(video, selected)| store::SavedVideo {
                    video: video.clone(),
                    selected: *selected,
                })
                .collect(),
            jobs: self
                .jobs
                .iter()
                .map(|job| store::SavedJob {
                    video: job.video.clone(),
                    mode: job.mode,
                    quality: job.quality.clone(),
                    folder: job.folder.clone(),
                    state: match job.status {
                        JobState::Queued => store::SavedJobStatus::Queued,
                        JobState::Active => store::SavedJobStatus::Active,
                        JobState::Completed => store::SavedJobStatus::Completed,
                        JobState::Failed => store::SavedJobStatus::Failed,
                        JobState::Cancelled => store::SavedJobStatus::Cancelled,
                    },
                    detail: job.detail.chars().take(300).collect(),
                })
                .collect(),
        };
        if let Err(error) = store::save(&store::session_path(), &snapshot) {
            eprintln!("Unable to persist queue: {error}");
        }
    }
}

fn restore_state() -> (State, Option<String>) {
    match store::load(&store::session_path()) {
        Ok(Some(saved)) => {
            let had_previous_content = !saved.videos.is_empty() || !saved.jobs.is_empty();
            let jobs = saved
                .jobs
                .into_iter()
                .map(|job| {
                    let status = match job.state {
                        store::SavedJobStatus::Queued | store::SavedJobStatus::Active => {
                            JobState::Queued
                        }
                        store::SavedJobStatus::Completed => JobState::Completed,
                        store::SavedJobStatus::Failed => JobState::Failed,
                        store::SavedJobStatus::Cancelled => JobState::Cancelled,
                    };
                    Job {
                        video: job.video,
                        mode: job.mode,
                        quality: job.quality,
                        folder: job.folder,
                        status,
                        percent: if status == JobState::Completed {
                            100
                        } else {
                            0
                        },
                        detail: job.detail,
                        cancel: Arc::new(AtomicBool::new(false)),
                    }
                })
                .collect::<Vec<_>>();
            let pending = jobs
                .iter()
                .filter(|job| job.status == JobState::Queued)
                .count();
            (
                State {
                    theme: saved.theme,
                    videos: saved
                        .videos
                        .into_iter()
                        .map(|item| (item.video, item.selected))
                        .collect(),
                    jobs,
                    active: 0,
                    channel_name: saved.channel_name,
                    channel_url: saved.channel_url,
                    folder: saved.folder,
                },
                if pending > 0 {
                    Some(format!(
                        "Resuming {pending} queued downloads from the saved session."
                    ))
                } else if had_previous_content {
                    Some("Saved library and download history restored.".into())
                } else {
                    None
                },
            )
        }
        Ok(None) => (
            State {
                theme: "red".into(),
                folder: default_folder(),
                ..State::default()
            },
            None,
        ),
        Err(error) => (
            State {
                theme: "red".into(),
                folder: default_folder(),
                ..State::default()
            },
            Some(format!("Saved queue could not be recovered: {error}")),
        ),
    }
}

fn reconcile_videos(
    previous: &[(Video, bool)],
    incoming: Vec<Video>,
    same_channel: bool,
) -> Vec<(Video, bool)> {
    incoming
        .into_iter()
        .map(|video| {
            let retained = same_channel
                && previous
                    .iter()
                    .any(|(old, selected)| old.id == video.id && *selected);
            (video, retained)
        })
        .collect()
}

fn set_visible_selection(items: &mut [(Video, bool)], search: &str, checked: bool) {
    let term = search.trim().to_lowercase();
    for (video, selected) in items {
        if video.title.to_lowercase().contains(&term) {
            *selected = checked;
        }
    }
}

fn visible_selected_count(items: &[(Video, bool)], search: &str) -> usize {
    let term = search.trim().to_lowercase();
    items
        .iter()
        .filter(|(video, selected)| *selected && video.title.to_lowercase().contains(&term))
        .count()
}

fn publish_videos(ui: &MainWindow, state: &State) {
    let filter = ui.get_video_search().to_string().trim().to_lowercase();
    let visible_selected = visible_selected_count(&state.videos, &filter);
    ui.set_visible_selected_items(visible_selected as i32);
    let selected = state
        .videos
        .iter()
        .filter(|(_, selected)| *selected)
        .count();
    ui.set_selected_items(selected as i32);
    ui.set_selected_count(
        format!(
            "{selected} video{} selected",
            if selected == 1 { "" } else { "s" }
        )
        .into(),
    );
    let visible_rows = state
        .videos
        .iter()
        .filter(|(video, _)| video.title.to_lowercase().contains(&filter))
        .map(|(video, selected)| VideoRow {
            id: video.id.clone().into(),
            title: video.title.clone().into(),
            title_long: video.title.chars().count() > 55,
            detail: video.duration.clone().into(),
            secondary: if video.uploaded.is_empty() {
                state.channel_name.clone()
            } else {
                format!("Published {}", video.uploaded)
            }
            .into(),
            thumbnail: thumbnails::cached(&video.id)
                .and_then(|path| slint::Image::load_from_path(&path).ok())
                .unwrap_or_default(),
            selected: *selected,
        })
        .collect::<Vec<_>>();
    // Preserve the live Slint repeater and focused row during selection
    // changes. Replacing the entire model on each toggle dropped keyboard
    // focus, so Space could not toggle the same video twice in succession.
    let previous = ui.get_videos();
    let same_identity = previous.row_count() == visible_rows.len()
        && visible_rows.iter().enumerate().all(|(index, row)| {
            previous
                .row_data(index)
                .is_some_and(|existing| existing.id == row.id)
        });
    if same_identity {
        for (index, row) in visible_rows.into_iter().enumerate() {
            previous.set_row_data(index, row);
        }
    } else {
        ui.set_videos(ModelRc::from(Rc::new(VecModel::from(visible_rows))));
    }
    // The review screen must show the complete selection, even when Library
    // search filters the visible list. Otherwise saved selections look lost.
    ui.set_selected_videos(ModelRc::from(Rc::new(VecModel::from(
        state
            .videos
            .iter()
            .filter(|(_, selected)| *selected)
            .map(|(video, selected)| VideoRow {
                id: video.id.clone().into(),
                title: video.title.clone().into(),
                title_long: video.title.chars().count() > 55,
                detail: video.duration.clone().into(),
                secondary: if video.uploaded.is_empty() {
                    state.channel_name.clone()
                } else {
                    format!("Published {}", video.uploaded)
                }
                .into(),
                thumbnail: thumbnails::cached(&video.id)
                    .and_then(|path| slint::Image::load_from_path(&path).ok())
                    .unwrap_or_default(),
                selected: *selected,
            })
            .collect::<Vec<_>>(),
    ))));
}

fn update_thumbnails(ui: &MainWindow, state: &Arc<Mutex<State>>) {
    let videos = {
        let value = state.lock().unwrap();
        value
            .videos
            .iter()
            .map(|(v, _)| v.clone())
            .collect::<Vec<_>>()
    };
    let weak_ui = ui.as_weak();
    let weak_state = Arc::downgrade(state);
    thumbnails::update_in_background(videos, move || {
        let ui = weak_ui.clone();
        let state = weak_state.clone();
        let _ = slint::invoke_from_event_loop(move || {
            if let (Some(ui), Some(state)) = (ui.upgrade(), state.upgrade()) {
                publish_videos(&ui, &state.lock().unwrap());
            }
        });
    });
}

fn publish_tasks(ui: &MainWindow, state: &State) {
    let filter = ui.get_queue_filter().to_string();
    ui.set_tasks(ModelRc::from(Rc::new(VecModel::from(
        state
            .jobs
            .iter()
            .enumerate()
            .rev()
            .filter(|(_, job)| match filter.as_str() {
                "active" => matches!(job.status, JobState::Active | JobState::Queued),
                "completed" => job.status == JobState::Completed,
                "failed" => job.status == JobState::Failed,
                _ => true,
            })
            .map(|(index, job)| TaskRow {
                job_index: index as i32,
                title: job.video.title.clone().into(),
                title_long: job.video.title.chars().count() > 40,
                thumbnail: thumbnails::cached(&job.video.id)
                    .and_then(|path| slint::Image::load_from_path(&path).ok())
                    .unwrap_or_default(),
                detail: format!("{}  ·  {}", job.detail, job.video.duration).into(),
                metadata: format!(
                    "{}  ·  {}",
                    match job.mode {
                        Mode::Video => "Video",
                        Mode::Audio => "MP3",
                        Mode::Captions => "Captions",
                    },
                    if job.mode == Mode::Video {
                        if job.quality == "best" {
                            "Best quality"
                        } else {
                            &job.quality
                        }
                    } else {
                        "Original"
                    },
                )
                .into(),
                progress: job.percent,
                state: match job.status {
                    JobState::Queued => "Queued",
                    JobState::Active => "Downloading",
                    JobState::Completed => "Completed",
                    JobState::Failed => "Failed",
                    JobState::Cancelled => "Cancelled",
                }
                .into(),
            })
            .collect::<Vec<_>>(),
    ))));
    let done = state
        .jobs
        .iter()
        .filter(|j| j.status == JobState::Completed)
        .count();
    let failed = state
        .jobs
        .iter()
        .filter(|j| j.status == JobState::Failed)
        .count();
    ui.set_failed_items(failed as i32);
    ui.set_pending_items(
        state
            .jobs
            .iter()
            .filter(|j| matches!(j.status, JobState::Active | JobState::Queued))
            .count() as i32,
    );
    ui.set_finished_items(
        state
            .jobs
            .iter()
            .filter(|j| {
                matches!(
                    j.status,
                    JobState::Completed | JobState::Failed | JobState::Cancelled
                )
            })
            .count() as i32,
    );
    ui.set_queue_count(
        format!(
            "{} total  •  {} active  •  {} completed  •  {} failed",
            state.jobs.len(),
            state.active,
            done,
            failed
        )
        .into(),
    );
}

fn cancel_job(job: &mut Job) -> bool {
    match job.status {
        JobState::Queued => {
            job.status = JobState::Cancelled;
            job.detail = "Cancelled before starting.".into();
            true
        }
        JobState::Active => {
            job.cancel.store(true, Ordering::Relaxed);
            job.detail = "Cancelling download...".into();
            true
        }
        _ => false,
    }
}

fn retry_job(job: &mut Job) -> bool {
    if job.status != JobState::Failed {
        return false;
    }
    job.status = JobState::Queued;
    job.detail = "Retry queued...".into();
    job.percent = 0;
    job.cancel = Arc::new(AtomicBool::new(false));
    true
}

fn publish(ui: &MainWindow, state: &State) {
    publish_videos(ui, state);
    publish_tasks(ui, state);
}

fn schedule(ui: &MainWindow, state: &Arc<Mutex<State>>, yt_dlp: PathBuf, ffmpeg: PathBuf) {
    let mut to_start = Vec::new();
    {
        let mut state = state.lock().unwrap();
        for index in 0..state.jobs.len() {
            if state.active >= engine::MAX_PARALLEL {
                break;
            }
            if state.jobs[index].status != JobState::Queued {
                continue;
            }
            state.jobs[index].status = JobState::Active;
            state.jobs[index].detail = "Preparing download…".into();
            state.active += 1;
            let job = &state.jobs[index];
            to_start.push((
                index,
                job.video.clone(),
                job.mode,
                job.quality.clone(),
                job.folder.clone(),
                job.cancel.clone(),
            ));
        }
    }
    {
        let state = state.lock().unwrap();
        state.persist();
        publish_tasks(ui, &state);
    }
    for (index, video, mode, quality, folder, cancel) in to_start {
        let weak = ui.as_weak();
        let state_for_progress = Arc::downgrade(state);
        let yt_dlp = yt_dlp.clone();
        let ffmpeg = ffmpeg.clone();
        std::thread::spawn(move || {
            let progress_ui = weak.clone();
            let progress_state = state_for_progress.clone();
            let result = engine::download_video(
                engine::DownloadSpec {
                    executable: &yt_dlp,
                    ffmpeg: &ffmpeg,
                    video: &video,
                    mode,
                    quality: &quality,
                    folder: &folder,
                },
                cancel.clone(),
                move |percent, detail| {
                    let weak = progress_ui.clone();
                    let state = progress_state.clone();
                    let _ = slint::invoke_from_event_loop(move || {
                        if let (Some(ui), Some(state)) = (weak.upgrade(), state.upgrade()) {
                            let mut value = state.lock().unwrap();
                            if let Some(job) = value.jobs.get_mut(index) {
                                if job.status != JobState::Active {
                                    return;
                                }
                                job.percent = percent;
                                job.detail = detail;
                            }
                            publish_tasks(&ui, &value);
                        }
                    });
                },
            );
            let _ = slint::invoke_from_event_loop(move || {
                let (Some(ui), Some(state)) = (weak.upgrade(), state_for_progress.upgrade()) else {
                    return;
                };
                {
                    let mut value = state.lock().unwrap();
                    if let Some(job) = value.jobs.get_mut(index) {
                        job.status = match &result {
                            Ok(()) => JobState::Completed,
                            Err(_) if cancel.load(Ordering::Relaxed) => JobState::Cancelled,
                            Err(_) => JobState::Failed,
                        };
                        job.percent = if job.status == JobState::Completed {
                            100
                        } else {
                            job.percent
                        };
                        job.detail = match result {
                            Ok(()) => "Saved successfully".to_owned(),
                            Err(message) => message,
                        };
                    }
                    value.active = value.active.saturating_sub(1);
                    value.persist();
                }
                schedule(&ui, &state, yt_dlp, ffmpeg);
            });
        });
    }
}

fn default_folder() -> PathBuf {
    let home = std::env::var_os("USERPROFILE")
        .map(PathBuf::from)
        .unwrap_or_else(|| PathBuf::from("."));
    home.join("Downloads").join("YouTube Downloader")
}

fn show_error(ui: &MainWindow, text: impl Into<String>) {
    ui.set_status_text(text.into().into());
}

fn show_channel_error(ui: &MainWindow, text: impl Into<String>) {
    let message = text.into();
    ui.set_channel_error(message.clone().into());
    show_error(ui, message);
}

fn show_download_error(ui: &MainWindow, text: impl Into<String>) {
    let message = text.into();
    ui.set_download_error(message.clone().into());
    show_error(ui, message);
}

fn show_queue_error(ui: &MainWindow, text: impl Into<String>) {
    let message = text.into();
    ui.set_queue_error(message.clone().into());
    show_error(ui, message);
}

fn main() -> Result<(), Box<dyn std::error::Error>> {
    #[cfg(windows)]
    let _instance = if std::env::var("YTD_UI_SMOKE_PREVIEW").as_deref() == Ok("1") {
        // Synthetic screenshot sessions use a separate app-data directory and
        // must not interrupt a running user's desktop downloader.
        None
    } else {
        Some(single_instance::InstanceGuard::acquire()?)
    };
    let ui = MainWindow::new()?;
    let (loaded_state, restore_notice) = restore_state();
    let folder = loaded_state.folder.clone();
    ui.set_channel_url(loaded_state.channel_url.clone().into());
    if !loaded_state.channel_name.is_empty() {
        ui.set_channel_name(loaded_state.channel_name.clone().into());
    }
    let state = Arc::new(Mutex::new(loaded_state));
    ui.set_download_folder(folder.display().to_string().into());
    ui.set_theme(state.lock().unwrap().theme.clone().into());
    // Visual smoke tests override only the displayed palette, without
    // modifying the user's persisted preference.
    if let Ok(theme) = std::env::var("YTD_UI_SMOKE_THEME") {
        if matches!(theme.as_str(), "red" | "mono") {
            ui.set_theme(theme.into());
        }
    }
    if let Ok(page) = std::env::var("YTD_UI_SMOKE_PAGE") {
        if matches!(page.as_str(), "discover" | "setup" | "queue" | "legal") {
            ui.set_page(page.into());
        }
    }
    // Deterministic UI snapshots for error layouts. Only the explicitly
    // isolated smoke-preview process accepts these test-only values.
    if std::env::var("YTD_UI_SMOKE_PREVIEW").as_deref() == Ok("1") {
        match std::env::var("YTD_UI_SMOKE_ERROR").as_deref() {
            Ok("channel") => ui.set_channel_error(
                "Enter a valid YouTube channel URL, then try loading again.".into(),
            ),
            Ok("download") => ui.set_download_error(
                "Choose an accessible destination folder and try again.".into(),
            ),
            Ok("queue") => ui.set_queue_error("The download folder is no longer available.".into()),
            _ => {}
        }
    }
    ui.on_toggle_maximize({
        let weak = ui.as_weak();
        move || {
            if let Some(ui) = weak.upgrade() {
                let window = ui.window();
                let maximized = !window.is_maximized();
                window.set_fullscreen(false);
                window.set_maximized(maximized);
                ui.set_fullscreen_active(false);
                ui.set_maximized_active(maximized);
            }
        }
    });
    ui.on_toggle_fullscreen({
        let weak = ui.as_weak();
        move || {
            if let Some(ui) = weak.upgrade() {
                let window = ui.window();
                let fullscreen = !window.is_fullscreen();
                window.set_fullscreen(fullscreen);
                ui.set_fullscreen_active(fullscreen);
                ui.set_maximized_active(window.is_maximized());
            }
        }
    });
    ui.on_change_theme({
        let state = state.clone();
        let weak = ui.as_weak();
        move |theme| {
            let theme = theme.to_string();
            if !matches!(theme.as_str(), "red" | "mono") {
                return;
            }
            if let Some(ui) = weak.upgrade() {
                ui.set_theme(theme.clone().into());
                let mut value = state.lock().unwrap();
                value.theme = theme;
                value.persist();
            }
        }
    });

    match (
        engine::find_dependency("yt-dlp.exe"),
        engine::find_dependency("ffmpeg.exe"),
        engine::find_dependency("deno.exe"),
    ) {
        (Ok(_), Ok(_), Ok(_)) => {
            show_error(&ui, "Ready — bundled yt-dlp, FFmpeg and Deno detected.")
        }
        _ => show_error(
            &ui,
            "Dependencies not found. Install the complete package with its bin folder.",
        ),
    }
    if let Some(notice) = restore_notice {
        show_error(&ui, notice);
    }

    let channel_request_generation = Arc::new(AtomicU64::new(0));
    ui.on_load_channel({
        let weak = ui.as_weak();
        let state = state.clone();
        let channel_request_generation = channel_request_generation.clone();
        move || {
            let Some(ui) = weak.upgrade() else {
                return;
            };
            // Even an invalid newer attempt supersedes an earlier in-flight
            // request. Otherwise the older response can replace its error.
            let generation = begin_channel_request(&channel_request_generation);
            let input = ui.get_channel_url().to_string();
            let canonical = match engine::channel_url(&input) {
                Ok(url) => url,
                Err(error) => {
                    ui.set_loading(false);
                    let previous = state.lock().unwrap();
                    if !previous.videos.is_empty() {
                        ui.set_channel_name(
                            format!("Previously loaded: {}", previous.channel_name).into(),
                        );
                        show_channel_error(
                            &ui,
                            format!("{error} Previous channel videos are still shown below."),
                        );
                    } else {
                        show_channel_error(&ui, error);
                    }
                    return;
                }
            };
            let exe = match engine::find_dependency("yt-dlp.exe") {
                Ok(exe) => exe,
                Err(error) => {
                    ui.set_loading(false);
                    show_channel_error(&ui, error);
                    return;
                }
            };
            ui.set_channel_error("".into());
            let same_channel = {
                let mut value = state.lock().unwrap();
                let same = value.channel_url == canonical;
                if !same {
                    value.channel_url = canonical.clone();
                    value.channel_name = String::new();
                    value.videos.clear();
                    value.persist();
                }
                same
            };
            if !same_channel {
                ui.set_channel_name("Loading channel...".into());
                ui.set_video_search("".into());
                publish(&ui, &state.lock().unwrap());
            }
            ui.set_loading(true);
            show_error(&ui, "Scanning channel with yt-dlp…");
            let state = Arc::downgrade(&state);
            let weak = weak.clone();
            let channel_request_generation = channel_request_generation.clone();
            std::thread::spawn(move || {
                let result = engine::load_channel(&exe, &input);
                let _ = slint::invoke_from_event_loop(move || {
                    if channel_request_generation.load(Ordering::SeqCst) != generation {
                        return;
                    }
                    let (Some(ui), Some(state)) = (weak.upgrade(), state.upgrade()) else {
                        return;
                    };
                    ui.set_loading(false);
                    match result {
                        Ok((name, videos)) => {
                            ui.set_channel_name(name.clone().into());
                            show_error(
                                &ui,
                                format!(
                                    "Loaded {} videos. Select which to download.",
                                    videos.len()
                                ),
                            );
                            {
                                let mut value = state.lock().unwrap();
                                value.channel_name = name;
                                value.channel_url = canonical;
                                value.videos =
                                    reconcile_videos(&value.videos, videos, same_channel);
                                value.persist();
                            }
                            publish(&ui, &state.lock().unwrap());
                            update_thumbnails(&ui, &state);
                        }
                        Err(error) => {
                            if !same_channel {
                                ui.set_channel_name("Channel could not be loaded".into());
                            }
                            show_channel_error(&ui, error);
                        }
                    }
                });
            });
        }
    });

    ui.on_toggle_video({
        let weak = ui.as_weak();
        let state = state.clone();
        move |id| {
            let Some(ui) = weak.upgrade() else { return };
            if let Some((_, selected)) = state
                .lock()
                .unwrap()
                .videos
                .iter_mut()
                .find(|(video, _)| video.id == id.as_str())
            {
                *selected = !*selected;
            }
            state.lock().unwrap().persist();
            publish(&ui, &state.lock().unwrap());
        }
    });
    ui.on_search_videos({
        let weak = ui.as_weak();
        let state = state.clone();
        move || {
            if let Some(ui) = weak.upgrade() {
                publish(&ui, &state.lock().unwrap());
            }
        }
    });
    ui.on_filter_tasks({
        let weak = ui.as_weak();
        let state = state.clone();
        move || {
            if let Some(ui) = weak.upgrade() {
                publish_tasks(&ui, &state.lock().unwrap());
            }
        }
    });
    ui.on_select_all({
        let weak = ui.as_weak();
        let state = state.clone();
        move || {
            let Some(ui) = weak.upgrade() else { return };
            let search = ui.get_video_search().to_string();
            set_visible_selection(&mut state.lock().unwrap().videos, &search, true);
            state.lock().unwrap().persist();
            publish(&ui, &state.lock().unwrap());
        }
    });
    ui.on_clear_selection({
        let weak = ui.as_weak();
        let state = state.clone();
        move || {
            let Some(ui) = weak.upgrade() else { return };
            let search = ui.get_video_search().to_string();
            set_visible_selection(&mut state.lock().unwrap().videos, &search, false);
            state.lock().unwrap().persist();
            publish(&ui, &state.lock().unwrap());
        }
    });
    ui.on_choose_folder({
        let weak = ui.as_weak();
        let state = state.clone();
        move || {
            let Some(ui) = weak.upgrade() else { return };
            if let Some(path) = rfd::FileDialog::new()
                .set_title("Choose download folder")
                .pick_folder()
            {
                ui.set_download_folder(path.display().to_string().into());
                {
                    let mut value = state.lock().unwrap();
                    value.folder = path;
                    value.persist();
                }
                ui.set_download_error("".into());
                show_error(&ui, "Download location updated.");
            }
        }
    });
    ui.on_start_download({
        let weak = ui.as_weak();
        let state = state.clone();
        move || {
            let Some(ui) = weak.upgrade() else { return };
            let folder = PathBuf::from(ui.get_download_folder().to_string());
            if !folder.is_absolute() {
                show_download_error(&ui, "Choose a valid absolute download directory.");
                return;
            }
            if let Err(error) = std::fs::create_dir_all(&folder) {
                show_download_error(&ui, format!("Cannot create download directory: {error}"));
                return;
            }
            let yt_dlp = match engine::find_dependency("yt-dlp.exe") {
                Ok(path) => path,
                Err(e) => {
                    show_download_error(&ui, e);
                    return;
                }
            };
            let ffmpeg = match engine::find_dependency("ffmpeg.exe") {
                Ok(path) => path,
                Err(e) => {
                    show_download_error(&ui, e);
                    return;
                }
            };
            if let Err(error) = engine::find_dependency("deno.exe") {
                show_download_error(&ui, error);
                return;
            }
            let mode = match Mode::parse(&ui.get_mode()) {
                Ok(mode) => mode,
                Err(e) => {
                    show_download_error(&ui, e);
                    return;
                }
            };
            let quality = ui.get_quality().to_string();
            let selected = state
                .lock()
                .unwrap()
                .videos
                .iter()
                .filter(|(_, selected)| *selected)
                .map(|(v, _)| v.clone())
                .collect::<Vec<_>>();
            if selected.is_empty() {
                show_download_error(&ui, "Select at least one real video before downloading.");
                return;
            }
            if selected.len() > engine::MAX_SELECTED {
                show_download_error(&ui, "Too many downloads selected.");
                return;
            }
            if state.lock().unwrap().jobs.len() + selected.len() > store::MAX_JOBS {
                show_download_error(
                    &ui,
                    "Queue history is full. Finish current downloads and clear history first.",
                );
                return;
            }
            let added = {
                let mut value = state.lock().unwrap();
                value.folder = folder.clone();
                let mut added = 0;
                for video in selected {
                    if value
                        .jobs
                        .iter()
                        .any(|job| is_pending_duplicate(job, &video, mode, &quality, &folder))
                    {
                        continue;
                    }
                    value.jobs.push(Job {
                        video,
                        mode,
                        quality: quality.clone(),
                        folder: folder.clone(),
                        status: JobState::Queued,
                        percent: 0,
                        detail: "Waiting for download slot…".into(),
                        cancel: Arc::new(AtomicBool::new(false)),
                    });
                    added += 1;
                }
                value.persist();
                added
            };
            if added == 0 {
                show_download_error(&ui, "These videos are already queued or downloading.");
                return;
            }
            ui.set_download_error("".into());
            ui.set_page("queue".into());
            show_error(
                &ui,
                format!(
                    "Queued up to {added} items. Running {} simultaneously.",
                    engine::MAX_PARALLEL
                ),
            );
            schedule(&ui, &state, yt_dlp, ffmpeg);
        }
    });
    ui.on_cancel_downloads({
        let weak = ui.as_weak();
        let state = state.clone();
        move || {
            let Some(ui) = weak.upgrade() else { return };
            for job in &mut state.lock().unwrap().jobs {
                cancel_job(job);
            }
            state.lock().unwrap().persist();
            publish(&ui, &state.lock().unwrap());
            ui.set_queue_error("".into());
        }
    });
    ui.on_retry_failed({
        let weak = ui.as_weak();
        let state = state.clone();
        move || {
            let Some(ui) = weak.upgrade() else { return };
            let yt_dlp = match engine::find_dependency("yt-dlp.exe") {
                Ok(path) => path,
                Err(e) => {
                    show_queue_error(&ui, e);
                    return;
                }
            };
            let ffmpeg = match engine::find_dependency("ffmpeg.exe") {
                Ok(path) => path,
                Err(e) => {
                    show_queue_error(&ui, e);
                    return;
                }
            };
            let mut count = 0;
            for job in &mut state.lock().unwrap().jobs {
                if retry_job(job) {
                    count += 1;
                }
            }
            state.lock().unwrap().persist();
            ui.set_queue_error("".into());
            show_error(&ui, format!("Retrying {count} failed download(s)."));
            schedule(&ui, &state, yt_dlp, ffmpeg);
        }
    });
    ui.on_clear_finished({
        let weak = ui.as_weak();
        let state = state.clone();
        move || {
            let Some(ui) = weak.upgrade() else { return };
            let mut value = state.lock().unwrap();
            if value.active > 0 || value.jobs.iter().any(|job| job.status == JobState::Queued) {
                show_queue_error(
                    &ui,
                    "Wait until the download queue is idle before clearing history.",
                );
                return;
            }
            let count = value.jobs.len();
            value
                .jobs
                .retain(|job| matches!(job.status, JobState::Queued | JobState::Active));
            let removed = count - value.jobs.len();
            value.persist();
            publish(&ui, &value);
            ui.set_queue_error("".into());
            show_error(&ui, format!("Cleared {removed} finished download records."));
        }
    });
    ui.on_cancel_job({
        let weak = ui.as_weak();
        let state = state.clone();
        move |index| {
            let Some(ui) = weak.upgrade() else { return };
            let mut value = state.lock().unwrap();
            if let Some(job) = usize::try_from(index)
                .ok()
                .and_then(|i| value.jobs.get_mut(i))
            {
                if cancel_job(job) {
                    value.persist();
                    publish_tasks(&ui, &value);
                    ui.set_queue_error("".into());
                }
            }
        }
    });
    ui.on_retry_job({
        let weak = ui.as_weak();
        let state = state.clone();
        move |index| {
            let Some(ui) = weak.upgrade() else { return };
            let yt = match engine::find_dependency("yt-dlp.exe") {
                Ok(path) => path,
                Err(error) => {
                    show_queue_error(&ui, error);
                    return;
                }
            };
            let ffmpeg = match engine::find_dependency("ffmpeg.exe") {
                Ok(path) => path,
                Err(error) => {
                    show_queue_error(&ui, error);
                    return;
                }
            };
            {
                let mut value = state.lock().unwrap();
                if !usize::try_from(index)
                    .ok()
                    .and_then(|i| value.jobs.get_mut(i))
                    .is_some_and(retry_job)
                {
                    return;
                }
                value.persist();
            }
            ui.set_queue_error("".into());
            schedule(&ui, &state, yt, ffmpeg);
        }
    });
    ui.on_open_job_folder({
        let weak = ui.as_weak();
        let state = state.clone();
        move |index| {
            let Some(ui) = weak.upgrade() else { return };
            let folder = {
                let value = state.lock().unwrap();
                usize::try_from(index)
                    .ok()
                    .and_then(|i| value.jobs.get(i))
                    .filter(|job| job.status == JobState::Completed)
                    .map(|job| job.folder.clone())
            };
            let Some(folder) = folder else { return };
            if !folder.is_dir() {
                show_queue_error(&ui, "The download folder is no longer available.");
                return;
            }
            if let Err(error) = std::process::Command::new("explorer.exe")
                .arg(folder)
                .spawn()
            {
                show_queue_error(&ui, format!("Could not open folder: {error}"));
            } else {
                ui.set_queue_error("".into());
            }
        }
    });

    publish(&ui, &state.lock().unwrap());
    update_thumbnails(&ui, &state);
    // A deterministic active-transfer UI fixture has no network or filesystem
    // effects. It exists only for screenshot review in isolated smoke sessions.
    if std::env::var("YTD_UI_SMOKE_PREVIEW").as_deref() == Ok("1")
        && std::env::var("YTD_UI_SMOKE_ACTIVE").as_deref() == Ok("1")
    {
        let tasks = ui.get_tasks();
        if let Some(mut row) = tasks.row_data(0) {
            row.state = "Downloading".into();
            row.progress = 47;
            row.detail = "2.8 MiB/s · 00:22 remaining".into();
            tasks.set_row_data(0, row);
            ui.set_pending_items(1);
            ui.set_queue_count("3 total · 1 active · 1 completed · 1 failed".into());
        }
    }
    if std::env::var("YTD_UI_SMOKE_PREVIEW").as_deref() != Ok("1")
        && state
            .lock()
            .unwrap()
            .jobs
            .iter()
            .any(|job| job.status == JobState::Queued)
    {
        if let (Ok(yt_dlp), Ok(ffmpeg), Ok(_deno)) = (
            engine::find_dependency("yt-dlp.exe"),
            engine::find_dependency("ffmpeg.exe"),
            engine::find_dependency("deno.exe"),
        ) {
            schedule(&ui, &state, yt_dlp, ffmpeg);
        }
    }
    // On Windows, requesting a native size before show() can be overwritten
    // during the first winit layout pass. Apply the size after creating the
    // OS window, before entering the Slint event loop.
    ui.show()?;
    // Fit the initial window to smaller laptop displays; resizing, maximize
    // and true fullscreen remain available afterwards.
    #[cfg(windows)]
    let start_size = {
        use windows_sys::Win32::UI::WindowsAndMessaging::{
            GetSystemMetrics, SM_CXSCREEN, SM_CYSCREEN,
        };
        // SAFETY: GetSystemMetrics is read-only with valid predefined indices.
        let (screen_w, screen_h) =
            unsafe { (GetSystemMetrics(SM_CXSCREEN), GetSystemMetrics(SM_CYSCREEN)) };
        slint::PhysicalSize::new(
            1180u32.min((screen_w - 40).max(880) as u32),
            800u32.min((screen_h - 100).max(625) as u32),
        )
    };
    #[cfg(not(windows))]
    let start_size = slint::PhysicalSize::new(1180, 800);
    ui.window().set_size(start_size);
    match std::env::var("YTD_UI_SMOKE_WINDOW_MODE").as_deref() {
        Ok("maximized") => {
            ui.window().set_maximized(true);
            ui.set_maximized_active(true);
        }
        Ok("fullscreen") => {
            ui.window().set_fullscreen(true);
            ui.set_fullscreen_active(true);
        }
        Ok("compact") => {
            ui.window().set_size(slint::PhysicalSize::new(930, 660));
        }
        Ok("minimum") => {
            ui.window().set_size(slint::PhysicalSize::new(880, 625));
        }
        _ => {}
    }
    ui.run()?;
    Ok(())
}

#[cfg(test)]
mod ui_state_tests {
    use super::*;
    fn video(id: &str, title: &str) -> Video {
        Video {
            id: id.to_string(),
            title: title.to_string(),
            duration: "1:30".to_string(),
            uploaded: String::new(),
        }
    }
    #[test]
    fn reloading_same_channel_retains_only_matching_selected_ids() {
        let old = vec![
            (video("abcdefghijk", "One"), true),
            (video("defghijklmn", "Two"), false),
        ];
        let fresh = vec![
            video("defghijklmn", "Two changed"),
            video("abcdefghijk", "One changed"),
        ];
        let restored = reconcile_videos(&old, fresh.clone(), true);
        assert!(!restored[0].1);
        assert!(restored[1].1);
        assert!(reconcile_videos(&old, fresh, false)
            .iter()
            .all(|(_, selected)| !selected));
    }
    #[test]
    fn bulk_selection_only_affects_visible_filtered_titles() {
        let mut rows = vec![
            (video("abcdefghijk", "Rust gameplay"), false),
            (video("defghijklmn", "Unrelated music"), true),
            (video("pqrstuvwxyz", "Rust highlights"), false),
        ];
        set_visible_selection(&mut rows, "RUST", true);
        assert!(rows.iter().all(|(_, selected)| *selected));
        set_visible_selection(&mut rows, "rust", false);
        assert!(!rows[0].1);
        assert!(rows[1].1);
        assert!(!rows[2].1);
        assert_eq!(visible_selected_count(&rows, "rust"), 0);
        assert_eq!(visible_selected_count(&rows, "music"), 1);
        assert_eq!(visible_selected_count(&rows, ""), 1);
        assert_eq!(visible_selected_count(&rows, "does not exist"), 0);
    }
    #[test]
    fn cancel_and_retry_operate_on_only_the_selected_job() {
        let mut a = Job {
            video: video("abcdefghijk", "One"),
            mode: Mode::Video,
            quality: "best".into(),
            folder: PathBuf::from(r"C:\Downloads"),
            status: JobState::Active,
            percent: 47,
            detail: "Downloading".into(),
            cancel: Arc::new(AtomicBool::new(false)),
        };
        let mut b = Job {
            video: video("defghijklmn", "Two"),
            mode: Mode::Video,
            quality: "720".into(),
            folder: PathBuf::from(r"C:\Downloads"),
            status: JobState::Failed,
            percent: 40,
            detail: "Failure".into(),
            cancel: Arc::new(AtomicBool::new(false)),
        };
        assert!(cancel_job(&mut a));
        assert!(a.cancel.load(Ordering::Relaxed));
        assert_eq!(a.status, JobState::Active);
        assert!(!retry_job(&mut a));
        assert!(retry_job(&mut b));
        assert_eq!(b.status, JobState::Queued);
        assert_eq!(b.percent, 0);
        assert!(!b.cancel.load(Ordering::Relaxed));
        assert!(!retry_job(&mut b));
    }

    #[test]
    fn queued_duplicate_detection_includes_destination_folder() {
        let video = video("abcdefghijk", "One");
        let source = PathBuf::from(r"C:\Downloads\One");
        let other = PathBuf::from(r"C:\Downloads\Two");
        let mut job = Job {
            video: video.clone(),
            mode: Mode::Video,
            quality: "720".into(),
            folder: source.clone(),
            status: JobState::Queued,
            percent: 0,
            detail: String::new(),
            cancel: Arc::new(AtomicBool::new(false)),
        };
        assert!(is_pending_duplicate(
            &job,
            &video,
            Mode::Video,
            "720",
            &source
        ));
        assert!(!is_pending_duplicate(
            &job,
            &video,
            Mode::Video,
            "720",
            &other
        ));
        assert!(!is_pending_duplicate(
            &job,
            &video,
            Mode::Video,
            "1080",
            &source
        ));
        job.status = JobState::Completed;
        assert!(!is_pending_duplicate(
            &job,
            &video,
            Mode::Video,
            "720",
            &source
        ));
    }

    #[test]
    fn newer_channel_attempt_invalidates_older_generation() {
        let current = AtomicU64::new(0);
        let first = begin_channel_request(&current);
        assert_eq!(first, 1);
        // A validation failure still consumes a generation, so the prior
        // worker cannot publish an outdated result after this second click.
        let invalid_second = begin_channel_request(&current);
        assert_eq!(invalid_second, 2);
        assert_ne!(current.load(Ordering::SeqCst), first);
        assert_eq!(current.load(Ordering::SeqCst), invalid_second);
    }
}
