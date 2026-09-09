#!/usr/bin/env python3
"""Shared BatteryVault application metadata."""
from __future__ import annotations

import re
import sys
from pathlib import Path

APP_NAME = "BatteryVault"
PUBLISHER = "VaultSoft"
_SEMVER = re.compile(r"^\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?$")


def app_base_dir() -> Path:
    """Return the directory containing bundled app resources."""
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        return Path(meipass)
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def read_version() -> str:
    version_file = app_base_dir() / "VERSION"
    try:
        version = version_file.read_text(encoding="utf-8").strip()
    except OSError as exc:
        raise RuntimeError(f"Missing {APP_NAME} VERSION file: {version_file}") from exc
    if not _SEMVER.fullmatch(version):
        raise RuntimeError(f"Invalid {APP_NAME} version: {version!r}")
    return version


APP_VERSION = read_version()
