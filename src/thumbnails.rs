//! Bounded, cached thumbnail fetches for *validated* public YouTube video IDs.
//! The downloader engine remains yt-dlp; thumbnails are purely presentation.
use crate::engine::{validate_id, Video};
use std::path::{Path, PathBuf};

pub fn cache_dir() -> PathBuf {
    crate::store::session_path()
        .parent()
        .unwrap_or_else(|| Path::new("."))
        .join("thumbnails")
}

pub fn cache_path(video_id: &str) -> Option<PathBuf> {
    validate_id(video_id).then(|| cache_dir().join(format!("{video_id}.jpg")))
}

pub fn cached(video_id: &str) -> Option<PathBuf> {
    let path = cache_path(video_id)?;
    let len = std::fs::metadata(&path).ok()?.len();
    (len > 200 && len <= 350_000).then_some(path)
}

#[cfg(windows)]
fn download(video_id: &str, path: &Path) -> bool {
    use std::os::windows::ffi::OsStrExt;
    #[link(name = "urlmon")]
    extern "system" {
        fn URLDownloadToFileW(
            caller: *mut std::ffi::c_void,
            url: *const u16,
            file_name: *const u16,
            reserved: u32,
            callback: *mut std::ffi::c_void,
        ) -> i32;
    }
    // Only the fixed HTTPS image host and a previously validated 11-byte ID.
    let remote = format!("https://i.ytimg.com/vi/{video_id}/mqdefault.jpg");
    let tmp = path.with_extension(format!("{}.tmp", std::process::id()));
    let url = std::ffi::OsStr::new(&remote)
        .encode_wide()
        .chain(std::iter::once(0))
        .collect::<Vec<u16>>();
    let destination = tmp
        .as_os_str()
        .encode_wide()
        .chain(std::iter::once(0))
        .collect::<Vec<u16>>();
    // SAFETY: parameters are valid null-terminated UTF-16 strings and URLMon
    // writes only the explicitly chosen cache file. No callback is supplied.
    let result = unsafe {
        URLDownloadToFileW(
            std::ptr::null_mut(),
            url.as_ptr(),
            destination.as_ptr(),
            0,
            std::ptr::null_mut(),
        )
    };
    let len = std::fs::metadata(&tmp).map(|m| m.len()).unwrap_or(0);
    if result != 0 || !(200..=350_000).contains(&len) {
        let _ = std::fs::remove_file(&tmp);
        return false;
    }
    if std::fs::rename(&tmp, path).is_err() {
        let _ = std::fs::remove_file(&tmp);
        return false;
    }
    true
}

#[cfg(not(windows))]
fn download(_video_id: &str, _path: &Path) -> bool {
    false
}

pub fn fetch(video_id: &str) -> Option<PathBuf> {
    let path = cache_path(video_id)?;
    if let Some(path) = cached(video_id) {
        return Some(path);
    }
    std::fs::create_dir_all(cache_dir()).ok()?;
    download(video_id, &path).then_some(path)
}

/// Small groups provide progressive thumbnails without flooding the network.
pub fn update_in_background(videos: Vec<Video>, update: impl Fn() + Send + Sync + 'static) {
    std::thread::spawn(move || {
        let mut changed = 0;
        for video in videos.iter().take(200) {
            if cached(&video.id).is_none() && fetch(&video.id).is_some() {
                changed += 1;
                if changed % 6 == 0 {
                    update();
                }
            }
        }
        if changed > 0 {
            update();
        }
    });
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn thumbnail_paths_are_bound_to_validated_ids() {
        let path = cache_path("abcdefghijk").unwrap();
        assert_eq!(path.extension().and_then(|x| x.to_str()), Some("jpg"));
        assert!(cache_path("../escape").is_none());
        assert!(cache_path("url?bad.png").is_none());
    }
}
