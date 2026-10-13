use std::{env, fs, path::PathBuf, process::Command};

fn windows_resource_compiler() -> PathBuf {
    if let Some(custom_rc) = env::var_os("RC") {
        return custom_rc.into();
    }

    // rc.exe is part of the Windows SDK installed alongside MSVC. It is often
    // absent from PATH when Cargo is launched from a normal terminal.
    let sdk_root = env::var_os("WindowsSdkDir")
        .map(PathBuf::from)
        .unwrap_or_else(|| {
            PathBuf::from(env::var_os("ProgramFiles(x86)").unwrap_or_default())
                .join("Windows Kits")
                .join("10")
        });
    let bin_dir = sdk_root.join("bin");
    let mut compilers: Vec<_> = fs::read_dir(bin_dir)
        .into_iter()
        .flatten()
        .flatten()
        .map(|item| item.path().join("x64").join("rc.exe"))
        .filter(|file| file.is_file())
        .collect();
    compilers.sort();
    compilers.pop().unwrap_or_else(|| PathBuf::from("rc.exe"))
}

fn main() {
    slint_build::compile("ui/main.slint").expect("Slint UI must compile");

    println!("cargo:rerun-if-changed=assets/windows-icon.rc");
    println!("cargo:rerun-if-changed=assets/app-icon.ico");
    println!("cargo:rerun-if-env-changed=RC");

    // The Slint Window.icon property controls the live taskbar/title-bar
    // image. The native PE icon resource also gives File Explorer, shortcuts,
    // and the EXE itself the same branding before the window is launched.
    if env::var("CARGO_CFG_TARGET_OS").as_deref() == Ok("windows")
        && env::var("CARGO_CFG_TARGET_ENV").as_deref() == Ok("msvc")
    {
        let manifest_dir = PathBuf::from(env::var_os("CARGO_MANIFEST_DIR").unwrap());
        let output = PathBuf::from(env::var_os("OUT_DIR").unwrap()).join("app-icon.res");
        let status = Command::new(windows_resource_compiler())
            .current_dir(manifest_dir.join("assets"))
            .arg("/nologo")
            .arg("/fo")
            .arg(&output)
            .arg("windows-icon.rc")
            .status()
            .expect("Windows SDK resource compiler required for EXE icon");
        assert!(status.success(), "Windows resource icon compilation failed");
        println!("cargo:rustc-link-arg-bins={}", output.display());
    }
}
