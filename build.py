#!/usr/bin/env python3
"""Build and validate the BatteryVault portable package."""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

from app_metadata import APP_NAME, APP_VERSION

ROOT = Path(__file__).resolve().parent
BUILD_DIR = ROOT / "build"
DIST_DIR = ROOT / "dist"
APP_DIR = DIST_DIR / APP_NAME
EXE_PATH = APP_DIR / f"{APP_NAME}.exe"
ZIP_PATH = DIST_DIR / f"{APP_NAME}_v{APP_VERSION}_Portable.zip"
SPEC_PATH = ROOT / f"{APP_NAME}.spec"
README_PATH = ROOT / "README.txt"
VERSION_PATH = ROOT / "VERSION"
ICON_PATH = ROOT / "icon.ico"

_BLOCKED_PATH_MARKERS = (
    "\\.cache\\codex-runtimes\\",
    "\\codex-runtimes\\",
    "\\poppler\\",
    "\\libheif\\",
)


def _assert_within_repo(path: Path) -> Path:
    resolved = path.resolve()
    if resolved == ROOT:
        raise RuntimeError("Refusing to clean repository root")
    try:
        resolved.relative_to(ROOT)
    except ValueError as exc:
        raise RuntimeError(f"Refusing to clean outside repository: {resolved}") from exc
    return resolved


def assert_python_311() -> None:
    if sys.version_info[:2] != (3, 11):
        raise RuntimeError(
            f"{APP_NAME} packaging requires Python 3.11; "
            f"found {sys.version_info.major}.{sys.version_info.minor}"
        )


def _is_path_entry_allowed(entry: str, python_root: Path) -> bool:
    if not entry:
        return False
    normalized = str(Path(entry)).lower().replace("/", "\\")
    if any(marker in normalized for marker in _BLOCKED_PATH_MARKERS):
        return False

    system_root = Path(os.environ.get("SystemRoot", r"C:\Windows"))
    allowed_roots = [
        python_root,
        python_root / "Scripts",
        system_root,
        system_root / "System32",
        system_root / "System32" / "Wbem",
        system_root / "System32" / "WindowsPowerShell" / "v1.0",
    ]
    entry_path = Path(entry)
    for root in allowed_roots:
        try:
            entry_path.resolve().relative_to(root.resolve())
            return True
        except (OSError, ValueError):
            continue
    return False


def sanitized_env() -> dict[str, str]:
    env = os.environ.copy()
    python_root = Path(sys.executable).resolve().parent
    path_entries = env.get("PATH", "").split(os.pathsep)
    kept = [entry for entry in path_entries if _is_path_entry_allowed(entry, python_root)]
    env["PATH"] = os.pathsep.join(dict.fromkeys(kept))
    env["PYTHONPATH"] = str(ROOT)
    return env


def clean_build_outputs() -> None:
    for path in (BUILD_DIR, DIST_DIR):
        resolved = _assert_within_repo(path)
        if resolved.exists():
            shutil.rmtree(resolved)


def validate_inputs() -> None:
    required = [SPEC_PATH, README_PATH, VERSION_PATH, ICON_PATH, ROOT / "batteryvault.py"]
    missing = [str(path) for path in required if not path.exists()]
    if missing:
        raise RuntimeError("Missing required build inputs: " + ", ".join(missing))


def run_pyinstaller() -> None:
    cmd = [sys.executable, "-B", "-m", "PyInstaller", str(SPEC_PATH), "--noconfirm", "--clean"]
    subprocess.run(cmd, cwd=ROOT, env=sanitized_env(), check=True)


def validate_bundle() -> None:
    if not EXE_PATH.exists():
        raise RuntimeError(f"Missing packaged executable: {EXE_PATH}")
    internal_dir = APP_DIR / "_internal"
    if not internal_dir.exists():
        raise RuntimeError(f"Missing PyInstaller internal directory: {internal_dir}")
    for resource in ("README.txt", "VERSION"):
        if not (APP_DIR / resource).exists():
            raise RuntimeError(f"Missing packaged resource: {resource}")

    root_dlls = sorted(path.name for path in APP_DIR.glob("*.dll"))
    if root_dlls:
        raise RuntimeError("Unexpected root-level DLL leakage: " + ", ".join(root_dlls))

    forbidden_names = {
        "__pycache__",
        "build.py",
        "make_icon.py",
        "tests",
        "docs",
        "stdlib_pyc",
        "encodings_pyc",
    }
    forbidden = []
    for path in APP_DIR.rglob("*"):
        if path.name in forbidden_names or path.suffix == ".pyc":
            forbidden.append(str(path.relative_to(APP_DIR)))
    if forbidden:
        raise RuntimeError("Unexpected development/stale files in bundle: " + ", ".join(forbidden))


def copy_resources() -> None:
    shutil.copy2(README_PATH, APP_DIR / "README.txt")
    shutil.copy2(VERSION_PATH, APP_DIR / "VERSION")


def create_portable_zip() -> None:
    if ZIP_PATH.exists():
        ZIP_PATH.unlink()
    with zipfile.ZipFile(ZIP_PATH, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for path in sorted(APP_DIR.rglob("*")):
            if path.is_file():
                zf.write(path, Path(APP_NAME) / path.relative_to(APP_DIR))
    if not ZIP_PATH.exists():
        raise RuntimeError(f"Portable ZIP was not created: {ZIP_PATH}")


def main() -> int:
    assert_python_311()
    validate_inputs()
    clean_build_outputs()
    run_pyinstaller()
    copy_resources()
    validate_bundle()
    create_portable_zip()
    print(f"Portable ZIP: {ZIP_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
