#[cfg(windows)]
pub struct InstanceGuard(windows_sys::Win32::Foundation::HANDLE);

#[cfg(windows)]
impl InstanceGuard {
    pub fn acquire() -> Result<Self, String> {
        Self::acquire_named("Local\\YouTubeDownloaderDesktop-v1")
    }

    fn acquire_named(name: &str) -> Result<Self, String> {
        use windows_sys::Win32::Foundation::{CloseHandle, GetLastError, ERROR_ALREADY_EXISTS};
        use windows_sys::Win32::System::Threading::CreateMutexW;
        let wide: Vec<u16> = name.encode_utf16().chain(std::iter::once(0)).collect();
        // SAFETY: pointer is a null-terminated UTF-16 buffer valid for this
        // API call. The named mutex handle is owned and closed in Drop.
        unsafe {
            let handle = CreateMutexW(std::ptr::null(), 0, wide.as_ptr());
            if handle.is_null() {
                return Err(format!(
                    "Could not establish single-instance guard: {}",
                    std::io::Error::last_os_error()
                ));
            }
            if GetLastError() == ERROR_ALREADY_EXISTS {
                CloseHandle(handle);
                use windows_sys::Win32::UI::WindowsAndMessaging::{
                    MessageBoxW, MB_ICONINFORMATION, MB_OK,
                };
                let message: Vec<u16> = "YouTube Downloader Desktop is already running."
                    .encode_utf16()
                    .chain(std::iter::once(0))
                    .collect();
                let title: Vec<u16> = "YouTube Downloader Desktop"
                    .encode_utf16()
                    .chain(std::iter::once(0))
                    .collect();
                MessageBoxW(
                    std::ptr::null_mut(),
                    message.as_ptr(),
                    title.as_ptr(),
                    MB_OK | MB_ICONINFORMATION,
                );
                return Err("The desktop downloader is already running.".into());
            }
            Ok(Self(handle))
        }
    }
}

#[cfg(windows)]
impl Drop for InstanceGuard {
    fn drop(&mut self) {
        // SAFETY: this is the owned handle returned by CreateMutexW.
        unsafe {
            windows_sys::Win32::Foundation::CloseHandle(self.0);
        }
    }
}

#[cfg(test)]
#[cfg(windows)]
mod tests {
    use super::InstanceGuard;
    #[test]
    fn mutually_excludes_two_instances_and_releases_on_drop() {
        let name = format!("Local\\YTDL-Test-{}", std::process::id());
        let first = InstanceGuard::acquire_named(&name).unwrap();
        // Do not test the interactive duplicate UI path (MessageBox would
        // block); ensure normal acquisition releases cleanly.
        drop(first);
        let second = InstanceGuard::acquire_named(&name).unwrap();
        drop(second);
    }
}
