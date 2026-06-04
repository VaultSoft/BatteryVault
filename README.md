# BatteryVault

**Free portable Windows battery health monitor — by VaultSoft.**

A clean, lightweight tray app that reports your laptop's battery health, wear,
and charge cycles. Portable, no installer, no admin rights required.

> ## ⚠️ Beta Release — v1.0.0-beta
> BatteryVault has been built and tested on desktop hardware. We are looking for
> feedback from **laptop users** to verify battery detection and stats display.
>
> If you find any issues please [open an issue](https://github.com/VaultSoft/BatteryVault/issues)
> or contact us at **vaultwall@proton.me**.
>
> Once confirmed working on laptop hardware this will move to a stable v1.0.0 release.

## Features

- **Battery health %** — full charge capacity vs. original design capacity
- **Design / full charge capacity** and **capacity wear** (mWh)
- **Charge cycle count**
- **Live status** — Charging / Discharging / Full / Plugged in, not charging
- **Current charge %**, estimated **time remaining**, and **charge/discharge rate** (W)
- **Health band** — Excellent / Good / Fair / Poor, colour-coded
- **System tray** — live battery icon and tooltip; minimises to tray instead of closing
- Desktop PCs (no battery) show a clean "No battery detected" message

## Install

1. Download `BatteryVault_v1.0.0_Portable.zip` from the
   [Releases](https://github.com/VaultSoft/BatteryVault/releases) page.
2. Unzip anywhere.
3. Double-click `BatteryVault.exe`.

No installation, no registry entries. To uninstall, delete the folder.

**Requirements:** Windows 10/11 64-bit.

## Build from source

```bat
pip install -r requirements.txt
build_installer.bat
```

This produces `dist\BatteryVault\BatteryVault.exe` and a portable ZIP.

## Tech

PyQt6 UI · battery data via `psutil` and Windows WMI (`root\wmi` battery classes) ·
packaged with PyInstaller.

---

© VaultSoft · https://ko-fi.com/vaultsoft
