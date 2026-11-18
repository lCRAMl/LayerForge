# AUTOBUILD.py
#
# Builds LayerForge with PyInstaller as a program folder (decision G3: starts in about
# a second; a single-file EXE would unpack ~150 MB on every start). Writes
# build_version.py (version from git), bundles the help, the TIA templates and the icon,
# runs the built program's self-test and creates a Start-menu shortcut.
# Adapted from APIImageGenerator/AUTOBUILD.py.
#
# Usage:  python AUTOBUILD.py
# Result: output/LayerForge_<version>/LayerForge_<version>.exe (+ _internal/)

import os
import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

from layerforge import APP_NAME

# The emoji status lines must not crash a build whose output goes to a file or a
# console with a legacy code page (cp1252).
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# =========================
# CONFIG
# =========================

ICON_PATH = "layerforge/resources/icons/layerforge.ico"

# Data files PyInstaller does not find by import analysis: source -> folder in the build.
# The code locates them relative to its own package, so the folder names must match.
DATA_PATHS = {
    "layerforge/resources": "layerforge/resources",
    "layerforge/infrastructure/templates": "layerforge/infrastructure/templates",
}

# Never bundled: a second Qt binding (installed on this machine, must not be mixed with
# PyQt6) and test-only or unused packages.
EXCLUDES = ["PySide6", "shiboken6", "tkinter", "pytest", "pytestqt", "reportlab", "IPython",
            "matplotlib", "PIL"]          # PIL: openpyxl only needs it for embedded pictures

# Large files the hooks bundle but LayerForge never loads; removed after the build and
# before the self-test, so the test proves the program works without them (~47 MB).
PRUNE = [
    "_internal/cv2/opencv_videoio_ffmpeg*.dll",    # video input/output
    "_internal/PyQt6/Qt6/bin/opengl32sw.dll",      # software OpenGL; the editor uses none
]

ENTRY_SCRIPT = "run.py"
VERSION_FILE = "build_version.py"
OUTPUT_DIR = Path("output")
BUILD_DIR = Path("pyinstaller_build")


# =========================
# VERSION HELPERS
# =========================

def git(*args: str) -> str:
    return subprocess.check_output(["git", *args]).decode().strip()


def get_git_version() -> str:
    try:
        return git("describe", "--tags", "--long")
    except Exception:
        return "0.0.0-0-unknown"


def get_git_commit() -> str:
    try:
        return git("rev-parse", "--short", "HEAD")
    except Exception:
        return "unknown"


def get_git_commit_url() -> str:
    try:
        commit = git("rev-parse", "HEAD")
        remote = git("config", "--get", "remote.origin.url")
        # SSH address to HTTPS, drop a trailing ".git"
        if remote.startswith("git@github.com:"):
            remote = remote.replace("git@github.com:", "https://github.com/", 1)
        return f"{remote.removesuffix('.git')}/commit/{commit}"
    except Exception:
        return "unknown-commit-url"


def write_version_file(version: str, build_time: str, commit: str, commit_url: str) -> None:
    content = f'''# AUTO GENERATED FILE - written by AUTOBUILD.py, not committed
APP_NAME = "{APP_NAME}"
VERSION = "{version}"
BUILD_TIME = "{build_time}"
COMMIT = "{commit}"
COMMIT_URL = "{commit_url}"
'''
    Path(VERSION_FILE).write_text(content, encoding="utf-8")
    print(f"✅ Version file written: {VERSION_FILE}")


# =========================
# SHORTCUT
# =========================

def get_start_menu_programs_dir() -> str:
    """The current user's "Start Menu\\Programs" folder (also with redirected profiles)."""
    CSIDL_PROGRAMS = 0x0002
    SHGFP_TYPE_CURRENT = 0
    try:
        import ctypes
        buf = ctypes.create_unicode_buffer(260)
        if ctypes.windll.shell32.SHGetFolderPathW(0, CSIDL_PROGRAMS, 0, SHGFP_TYPE_CURRENT, buf) == 0 \
                and buf.value:
            return buf.value
    except Exception:
        pass
    appdata = os.environ.get("APPDATA") or os.path.join(
        "C:\\Users", os.environ.get("USERNAME", ""), "AppData", "Roaming")
    return os.path.join(appdata, "Microsoft", "Windows", "Start Menu", "Programs")


def create_shortcut(app_name: str, target_exe: Path, working_dir: Path) -> None:
    try:
        import pythoncom
        from win32com.shell import shell

        pythoncom.CoInitialize()          # required before creating the shell link
        target = os.path.realpath(target_exe)
        for _ in range(50):
            if os.path.exists(target) and os.path.getsize(target) > 0:
                break
            time.sleep(0.1)
        else:
            raise FileNotFoundError("EXE not ready yet: " + target)

        shortcut_dir = get_start_menu_programs_dir()
        os.makedirs(shortcut_dir, exist_ok=True)
        shortcut_path = os.path.join(shortcut_dir, f"{app_name}.lnk")
        link = pythoncom.CoCreateInstance(shell.CLSID_ShellLink, None,
                                          pythoncom.CLSCTX_INPROC_SERVER, shell.IID_IShellLinkW)
        link.SetPath(target)
        link.SetWorkingDirectory(os.path.realpath(working_dir))
        link.SetDescription(app_name)
        link.SetIconLocation(target, 0)
        link.QueryInterface(pythoncom.IID_IPersistFile).Save(shortcut_path, 0)
        print(f"🔗 Start-menu shortcut created: {shortcut_path}")
    except Exception as exc:
        print(f"⚠ Shortcut creation failed: {exc}")


# =========================
# PYINSTALLER BUILD
# =========================

def build_pyinstaller(name: str) -> Path:
    """Build straight into OUTPUT_DIR/<name>/ and return that folder.

    Built in place on purpose: moving a fresh build on the network drive fails while
    the virus scanner still holds the new DLLs open.
    """
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--noconfirm",
        "--clean",
        "--windowed",
        f"--name={name}",
        f"--distpath={OUTPUT_DIR}",
        f"--workpath={BUILD_DIR / 'work'}",
        f"--specpath={BUILD_DIR}",
        f"--icon={Path(ICON_PATH).resolve()}",
    ]
    for source, target in DATA_PATHS.items():
        cmd.append(f"--add-data={Path(source).resolve()}{os.pathsep}{target}")
    for module in EXCLUDES:
        cmd.append(f"--exclude-module={module}")
    cmd.append(ENTRY_SCRIPT)

    print("\n🚀 Running build:\n")
    print(" ".join(cmd), "\n")
    subprocess.run(cmd, check=True)
    return OUTPUT_DIR / name


def prune(folder: Path) -> None:
    freed = 0
    for pattern in PRUNE:
        for path in folder.glob(pattern):
            freed += path.stat().st_size
            path.unlink()
    print(f"🧹 Pruned {freed / 1048576:.0f} MB of unused files")


def selftest(exe: Path) -> bool:
    """Start the built program in self-test mode; it checks DLLs, data files and the window."""
    report = BUILD_DIR / "selftest.txt"
    result = subprocess.run([str(exe), "--selftest", str(report.resolve())], timeout=180)
    if report.exists():
        print(report.read_text(encoding="utf-8"))
    return result.returncode == 0


def clean() -> None:
    shutil.rmtree(BUILD_DIR, ignore_errors=True)


# =========================
# MAIN
# =========================

def main() -> int:
    print("🔧 Build started...")
    version = get_git_version()
    build_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    commit = get_git_commit()
    commit_url = get_git_commit_url()
    print(f"📦 Git Version: {version}")
    print(f"⏱ Build Time: {build_time}")
    print(f"🔗 Commit: {commit}")
    print(f"🌐 Commit URL: {commit_url}")
    write_version_file(version, build_time, commit, commit_url)

    safe_app = APP_NAME.replace(" ", "")
    safe_version = version.replace("+", "_").replace(" ", "_")
    name = f"{safe_app}_{safe_version}"
    target = build_pyinstaller(name)
    prune(target)
    exe = (target / f"{name}.exe").resolve()

    ok = selftest(exe)
    print("🧪 Self-test", "passed" if ok else "FAILED")
    if ok:
        create_shortcut(safe_app, exe, target)
    clean()
    print(f"\n{'✅ DONE' if ok else '❌ BUILD UNUSABLE'}: {exe}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
