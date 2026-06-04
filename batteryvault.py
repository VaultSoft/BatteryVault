#!/usr/bin/env python3
"""BatteryVault v1.0.0 — Free Portable Windows Battery Health Monitor (VaultSoft)

Reads battery health data via psutil + Windows WMI (root\\wmi battery classes).
No admin rights required. Minimises to the system tray.
"""
from __future__ import annotations
import sys, os, platform
from dataclasses import dataclass, field
from typing import Optional, Dict, List

import psutil
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QLabel, QPushButton,
    QVBoxLayout, QHBoxLayout, QGridLayout, QSystemTrayIcon, QMenu,
    QSizePolicy, QFrame,
)
from PyQt6.QtCore import Qt, QTimer, QPoint, QRectF
from PyQt6.QtGui import (
    QColor, QPainter, QPen, QBrush, QFont, QIcon, QPixmap, QAction,
    QPainterPath,
)

APP_VERSION = "1.0.0"
APP_NAME    = "BatteryVault"
PUBLISHER   = "VaultSoft"
REFRESH_MS  = 10_000   # refresh every 10 seconds

_IS_WIN = platform.system() == "Windows"

# ══════════════════════════════════════════════════════════════════
# THEME  (matches PulseMonitor / VaultSoft brand)
# ══════════════════════════════════════════════════════════════════
C = {
    "bg0":   "#060A10",
    "bg1":   "#0D1117",
    "bg2":   "#131A23",
    "bg3":   "#1B2535",
    "b0":    "#1C2B3A",
    "b1":    "#263848",
    "acc":   "#00D4AA",   # teal accent
    "acc2":  "#007A60",
    "t1":    "#E2EAF4",
    "t2":    "#a0aec0",
    "t3":    "#617080",
    "title": "#ffffff",
    "grn":   "#2ECC71",
    "amb":   "#F0A500",
    "red":   "#E74C3C",
}

# ══════════════════════════════════════════════════════════════════
# DATA MODEL
# ══════════════════════════════════════════════════════════════════
@dataclass
class BatteryData:
    has_battery:   bool             = False
    charge_pct:    Optional[float]  = None   # %
    status:        str              = "Unknown"
    design_mwh:    Optional[int]    = None
    full_mwh:      Optional[int]    = None
    cycle_count:   Optional[int]    = None
    rate_w:        Optional[float]  = None   # watts (signed: + charging, - discharging)
    secs_left:     Optional[int]    = None   # seconds remaining when discharging

    @property
    def wear_mwh(self) -> Optional[int]:
        if self.design_mwh and self.full_mwh:
            return max(0, self.design_mwh - self.full_mwh)
        return None

    @property
    def health_pct(self) -> Optional[float]:
        if self.design_mwh and self.full_mwh and self.design_mwh > 0:
            return min(100.0, self.full_mwh / self.design_mwh * 100.0)
        return None


def health_band(pct: Optional[float]) -> tuple[str, str]:
    """Return (label, colour) for a health percentage."""
    if pct is None:
        return ("Unknown", C["t2"])
    if pct > 80: return ("Excellent", C["acc"])
    if pct >= 60: return ("Good", C["grn"])
    if pct >= 40: return ("Fair", C["amb"])
    return ("Poor", C["red"])


# ══════════════════════════════════════════════════════════════════
# BATTERY READER  (psutil + WMI, fully error-tolerant)
# ══════════════════════════════════════════════════════════════════
class BatteryReader:
    """Collects battery data. Every lookup is guarded so a failing WMI
    query degrades to None ("N/A") rather than crashing the app."""

    def __init__(self):
        self._wmi_cim = None     # root\cimv2
        self._wmi_raw = None     # root\wmi
        self._wmi_failed = False

    def _ensure_wmi(self):
        if self._wmi_failed or not _IS_WIN:
            return
        if self._wmi_cim is not None:
            return
        try:
            import wmi
            self._wmi_cim = wmi.WMI()
            self._wmi_raw = wmi.WMI(namespace="root\\wmi")
        except Exception:
            self._wmi_failed = True
            self._wmi_cim = None
            self._wmi_raw = None

    # ── individual WMI lookups ────────────────────────────────────
    def _raw_query(self, cls: str):
        """Query a root\\wmi class; returns [] on any failure (e.g. no battery)."""
        try:
            return self._wmi_raw.query(f"SELECT * FROM {cls}")
        except Exception:
            return []

    def read(self) -> BatteryData:
        d = BatteryData()

        # 1. psutil — reliable for charge %, plugged state, time left
        ps = None
        try:
            ps = psutil.sensors_battery()
        except Exception:
            ps = None

        if ps is not None:
            d.has_battery = True
            try:
                d.charge_pct = float(ps.percent)
            except Exception:
                pass
            if ps.secsleft is not None and ps.secsleft >= 0 and not ps.power_plugged:
                d.secs_left = int(ps.secsleft)

        # 2. WMI raw battery classes for capacities / cycles / rate / status
        self._ensure_wmi()
        charging = discharging = power_online = None
        if self._wmi_raw is not None:
            # design capacity
            for o in self._raw_query("BatteryStaticData"):
                d.design_mwh = _int(getattr(o, "DesignedCapacity", None))
                break
            # full charge capacity
            for o in self._raw_query("BatteryFullChargedCapacity"):
                d.full_mwh = _int(getattr(o, "FullChargedCapacity", None))
                break
            # cycle count
            for o in self._raw_query("BatteryCycleCount"):
                d.cycle_count = _int(getattr(o, "CycleCount", None))
                break
            # live status: rate + charging flags
            for o in self._raw_query("BatteryStatus"):
                d.has_battery = True
                charging     = bool(getattr(o, "Charging", False))
                discharging  = bool(getattr(o, "Discharging", False))
                power_online = bool(getattr(o, "PowerOnline", False))
                cr = _int(getattr(o, "ChargeRate", None)) or 0
                dr = _int(getattr(o, "DischargeRate", None)) or 0
                rate_mw = cr if cr else -dr
                if rate_mw:
                    d.rate_w = rate_mw / 1000.0
                break

        # 3. Fallback to Win32_Battery presence/charge if psutil gave nothing
        if not d.has_battery and self._wmi_cim is not None:
            try:
                for b in self._wmi_cim.Win32_Battery():
                    d.has_battery = True
                    if d.charge_pct is None:
                        d.charge_pct = _int(getattr(b, "EstimatedChargeRemaining", None))
                    break
            except Exception:
                pass

        # 4. Derive a human status string
        d.status = self._status_text(d, ps, charging, discharging, power_online)
        return d

    @staticmethod
    def _status_text(d, ps, charging, discharging, power_online) -> str:
        if not d.has_battery:
            return "No battery"
        plugged = power_online if power_online is not None else (
            ps.power_plugged if ps is not None else None)
        pct = d.charge_pct if d.charge_pct is not None else 0

        if charging:
            return "Charging"
        if discharging:
            return "Discharging"
        # flags unavailable — infer from psutil
        if plugged:
            if pct >= 99:
                return "Full"
            return "Plugged in, not charging"
        if plugged is False:
            return "Discharging"
        return "Unknown"


def _int(v) -> Optional[int]:
    try:
        if v is None:
            return None
        return int(v)
    except Exception:
        return None


# ══════════════════════════════════════════════════════════════════
# FORMAT HELPERS
# ══════════════════════════════════════════════════════════════════
def fmt_mwh(v: Optional[int]) -> str:
    if v is None:
        return "N/A"
    if v >= 1000:
        return f"{v:,} mWh  ({v/1000:.1f} Wh)"
    return f"{v:,} mWh"


def fmt_pct(v: Optional[float]) -> str:
    return "N/A" if v is None else f"{v:.0f}%"


def fmt_time(secs: Optional[int]) -> str:
    if secs is None:
        return "N/A"
    h, rem = divmod(secs, 3600)
    m = rem // 60
    if h:
        return f"{h}h {m:02d}m"
    return f"{m}m"


def fmt_rate(w: Optional[float]) -> str:
    if w is None or w == 0:
        return "N/A"
    return f"{abs(w):.1f} W"


# ══════════════════════════════════════════════════════════════════
# WIDGETS
# ══════════════════════════════════════════════════════════════════
class HealthRing(QWidget):
    """Circular health gauge with centred percentage + band label."""
    def __init__(self):
        super().__init__()
        self.setFixedSize(220, 220)
        self._pct: Optional[float] = None
        self._color = C["t3"]
        self._label = "—"

    def set_value(self, pct: Optional[float]):
        self._pct = pct
        self._label, self._color = health_band(pct)
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        side = min(self.width(), self.height())
        m = 16
        rect = QRectF(m, m, side - 2*m, side - 2*m)
        # track
        p.setPen(QPen(QColor(C["b0"]), 14, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        p.drawArc(rect, 0, 360 * 16)
        # value arc
        frac = (self._pct or 0) / 100.0
        if frac > 0:
            p.setPen(QPen(QColor(self._color), 14, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            p.drawArc(rect, 90 * 16, -int(360 * 16 * frac))
        # centre text
        p.setPen(QColor(C["title"]))
        f = QFont("Segoe UI"); f.setPointSize(40); f.setWeight(QFont.Weight.Bold)
        p.setFont(f)
        txt = f"{self._pct:.0f}%" if self._pct is not None else "N/A"
        p.drawText(rect, Qt.AlignmentFlag.AlignCenter, txt)
        # band label below number
        p.setPen(QColor(self._color))
        f2 = QFont("Segoe UI"); f2.setPointSize(12); f2.setWeight(QFont.Weight.DemiBold)
        p.setFont(f2)
        lr = QRectF(rect.x(), rect.center().y() + 30, rect.width(), 30)
        p.drawText(lr, Qt.AlignmentFlag.AlignCenter, self._label)
        p.end()


class Stat(QFrame):
    """A small card showing a label + value."""
    def __init__(self, title: str, accent: str = None):
        super().__init__()
        self.setObjectName("card")
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        lay = QVBoxLayout(self); lay.setContentsMargins(16, 13, 16, 13); lay.setSpacing(6)
        self._title = QLabel(title.upper())
        self._title.setStyleSheet(
            f"color:{C['t2']}; font-size:10px; font-weight:700; letter-spacing:1.3px;"
            "background:transparent; border:none;")
        self._val = QLabel("N/A")
        self._accent = accent or C["t1"]
        self._val.setStyleSheet(
            f"color:{self._accent}; font-size:19px; font-weight:700;"
            "background:transparent; border:none;")
        lay.addWidget(self._title); lay.addWidget(self._val)

    def set_value(self, text: str, color: str = None):
        self._val.setText(text)
        self._val.setStyleSheet(
            f"color:{color or self._accent}; font-size:19px; font-weight:700;"
            "background:transparent; border:none;")


# ══════════════════════════════════════════════════════════════════
# TITLE BAR  (frameless, draggable, brand)
# ══════════════════════════════════════════════════════════════════
class TitleBar(QWidget):
    def __init__(self, win: "MainWindow"):
        super().__init__()
        self._win = win
        self._drag: Optional[QPoint] = None
        self.setFixedHeight(46)
        self.setStyleSheet(f"background:{C['bg0']}; border-bottom:1px solid {C['b0']};")
        lay = QHBoxLayout(self); lay.setContentsMargins(16, 0, 8, 0); lay.setSpacing(8)

        dot = QLabel("⬢")
        dot.setStyleSheet(f"color:{C['acc']}; font-size:16px; background:transparent;")
        brand = QLabel("BATTERY<span style='color:%s'>VAULT</span>" % C["acc"])
        brand.setTextFormat(Qt.TextFormat.RichText)
        brand.setStyleSheet(
            f"color:{C['title']}; font-size:14px; font-weight:900;"
            "letter-spacing:2px; background:transparent;")
        ver = QLabel(f"v{APP_VERSION}")
        ver.setStyleSheet(f"color:{C['t3']}; font-size:11px; margin-left:4px; background:transparent;")
        lay.addWidget(dot); lay.addWidget(brand); lay.addWidget(ver)
        lay.addStretch(1)

        for txt, cb, hover in (("—", win.showMinimized, C["bg3"]),
                               ("✕", win.close, C["red"])):
            b = QPushButton(txt)
            b.setFixedSize(34, 30)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.clicked.connect(cb)
            b.setStyleSheet(
                f"QPushButton{{color:{C['t2']}; background:transparent; border:none;"
                f"font-size:13px; border-radius:6px;}}"
                f"QPushButton:hover{{background:{hover}; color:#fff;}}")
            lay.addWidget(b)

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self._drag = e.globalPosition().toPoint() - self._win.frameGeometry().topLeft()

    def mouseMoveEvent(self, e):
        if self._drag is not None and e.buttons() & Qt.MouseButton.LeftButton:
            self._win.move(e.globalPosition().toPoint() - self._drag)

    def mouseReleaseEvent(self, e):
        self._drag = None


# ══════════════════════════════════════════════════════════════════
# MAIN WINDOW
# ══════════════════════════════════════════════════════════════════
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(APP_NAME)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Window)
        self.setMinimumSize(520, 640)
        self.resize(560, 680)
        self._reader = BatteryReader()
        self._allow_exit = False

        central = QWidget(); self.setCentralWidget(central)
        central.setStyleSheet(f"background:{C['bg1']};")
        root = QVBoxLayout(central); root.setContentsMargins(0, 0, 0, 0); root.setSpacing(0)

        root.addWidget(TitleBar(self))

        # body
        self._body = QWidget()
        body = QVBoxLayout(self._body)
        body.setContentsMargins(24, 20, 24, 20); body.setSpacing(16)
        root.addWidget(self._body, 1)

        # --- battery present UI ---
        self._ring = HealthRing()
        ring_row = QHBoxLayout(); ring_row.addStretch(1)
        ring_row.addWidget(self._ring); ring_row.addStretch(1)
        body.addLayout(ring_row)

        self._status_lbl = QLabel("—")
        self._status_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._status_lbl.setStyleSheet(
            f"color:{C['t1']}; font-size:15px; font-weight:600; background:transparent;")
        body.addWidget(self._status_lbl)

        grid = QGridLayout(); grid.setHorizontalSpacing(12); grid.setVerticalSpacing(12)
        self._cards: Dict[str, Stat] = {
            "charge":  Stat("Current Charge", C["acc"]),
            "rate":    Stat("Charge / Discharge Rate"),
            "time":    Stat("Time Remaining"),
            "design":  Stat("Design Capacity"),
            "full":    Stat("Full Charge Capacity"),
            "wear":    Stat("Capacity Wear", C["amb"]),
            "cycles":  Stat("Charge Cycles"),
            "health":  Stat("Health Capacity", C["acc"]),
        }
        order = ["charge", "rate", "time", "cycles",
                 "design", "full", "wear", "health"]
        for i, key in enumerate(order):
            grid.addWidget(self._cards[key], i // 2, i % 2)
        body.addLayout(grid)
        body.addStretch(1)

        footer = QLabel(f"by {PUBLISHER}  ·  refreshes every {REFRESH_MS//1000}s")
        footer.setAlignment(Qt.AlignmentFlag.AlignCenter)
        footer.setStyleSheet(f"color:{C['t3']}; font-size:10px; background:transparent;")
        body.addWidget(footer)

        # --- no-battery overlay (hidden unless needed) ---
        self._no_batt = QWidget()
        self._no_batt.setStyleSheet(f"background:{C['bg1']};")
        nb = QVBoxLayout(self._no_batt); nb.setContentsMargins(40, 40, 40, 40)
        nb.addStretch(1)
        icon = QLabel("🔋")
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon.setStyleSheet("font-size:54px; background:transparent;")
        title = QLabel("No battery detected")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet(
            f"color:{C['t1']}; font-size:20px; font-weight:700; background:transparent;")
        sub = QLabel("BatteryVault is designed for laptops.")
        sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        sub.setStyleSheet(f"color:{C['t2']}; font-size:13px; background:transparent;")
        nb.addWidget(icon); nb.addSpacing(10); nb.addWidget(title)
        nb.addSpacing(4); nb.addWidget(sub); nb.addStretch(1)
        root.addWidget(self._no_batt, 1)
        self._no_batt.hide()

        # tray
        self._build_tray()

        # data refresh
        self._timer = QTimer(self)
        self._timer.timeout.connect(self.refresh)
        self._timer.start(REFRESH_MS)
        self.refresh()

    # ── tray ──────────────────────────────────────────────────────
    def _build_tray(self):
        self._tray = QSystemTrayIcon(make_battery_icon(100, C["acc"]), self)
        self._tray.setToolTip(f"{APP_NAME} — starting…")
        menu = QMenu()
        menu.setStyleSheet(
            f"QMenu{{background:{C['bg2']}; color:{C['t1']}; border:1px solid {C['b1']};"
            f"padding:6px;}}"
            f"QMenu::item{{padding:7px 22px; border-radius:5px;}}"
            f"QMenu::item:selected{{background:{C['bg3']};}}")
        open_act = QAction(f"Open {APP_NAME}", self)
        open_act.triggered.connect(self._show_from_tray)
        exit_act = QAction("Exit", self)
        exit_act.triggered.connect(self._exit_app)
        menu.addAction(open_act); menu.addSeparator(); menu.addAction(exit_act)
        self._tray.setContextMenu(menu)
        self._tray.activated.connect(self._tray_activated)
        self._tray.show()

    def _tray_activated(self, reason):
        if reason in (QSystemTrayIcon.ActivationReason.DoubleClick,
                      QSystemTrayIcon.ActivationReason.Trigger):
            self._show_from_tray()

    def _show_from_tray(self):
        self.showNormal(); self.raise_(); self.activateWindow()

    def _exit_app(self):
        self._allow_exit = True
        self._tray.hide()
        QApplication.quit()

    # ── data refresh ──────────────────────────────────────────────
    def refresh(self):
        try:
            d = self._reader.read()
        except Exception:
            d = BatteryData()

        if not d.has_battery:
            self._body.hide()
            self._no_batt.show()
            self._tray.setToolTip(f"{APP_NAME} — no battery detected")
            self._tray.setIcon(make_battery_icon(0, C["t3"], cross=True))
            return

        self._no_batt.hide()
        self._body.show()

        # ring + health
        self._ring.set_value(d.health_pct)
        band, bcol = health_band(d.health_pct)

        # status line
        extra = ""
        if d.status == "Discharging" and d.secs_left:
            extra = f"  ·  {fmt_time(d.secs_left)} left"
        self._status_lbl.setText(f"{d.status}{extra}")

        # cards
        self._cards["charge"].set_value(fmt_pct(d.charge_pct), C["acc"])
        self._cards["rate"].set_value(fmt_rate(d.rate_w))
        self._cards["time"].set_value(
            fmt_time(d.secs_left) if d.status == "Discharging" else "—")
        self._cards["cycles"].set_value(
            str(d.cycle_count) if d.cycle_count is not None else "N/A")
        self._cards["design"].set_value(fmt_mwh(d.design_mwh))
        self._cards["full"].set_value(fmt_mwh(d.full_mwh))
        self._cards["wear"].set_value(fmt_mwh(d.wear_mwh), C["amb"])
        self._cards["health"].set_value(
            f"{d.health_pct:.1f}%  ({band})" if d.health_pct is not None else "N/A",
            bcol)

        # tray
        cp = f"{d.charge_pct:.0f}%" if d.charge_pct is not None else "?"
        hp = f"{d.health_pct:.0f}%" if d.health_pct is not None else "?"
        self._tray.setToolTip(
            f"{APP_NAME}\nCharge: {cp}   Health: {hp}\n{d.status}")
        col = C["acc"] if d.status in ("Charging", "Full") else bcol
        self._tray.setIcon(make_battery_icon(
            d.charge_pct or 0, col, charging=(d.status == "Charging")))

    # ── minimise to tray instead of closing ───────────────────────
    def closeEvent(self, e):
        if self._allow_exit:
            e.accept()
            return
        e.ignore()
        self.hide()
        if self._tray.supportsMessages():
            self._tray.showMessage(
                APP_NAME,
                "Still running in the tray. Double-click the icon to reopen.",
                QSystemTrayIcon.MessageIcon.Information, 2500)


# ══════════════════════════════════════════════════════════════════
# ICON
# ══════════════════════════════════════════════════════════════════
def make_battery_icon(pct: float, color: str, charging: bool = False,
                      cross: bool = False) -> QIcon:
    pm = QPixmap(32, 32); pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm); p.setRenderHint(QPainter.RenderHint.Antialiasing)
    # battery body (horizontal)
    body = QRectF(4, 9, 22, 14)
    p.setPen(QPen(QColor(C["t1"]), 2))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawRoundedRect(body, 3, 3)
    # terminal nub
    p.setBrush(QColor(C["t1"]))
    p.setPen(Qt.PenStyle.NoPen)
    p.drawRoundedRect(QRectF(26, 13, 3, 6), 1, 1)
    # fill level
    frac = max(0.0, min(1.0, pct / 100.0))
    if frac > 0 and not cross:
        fw = (body.width() - 4) * frac
        p.setBrush(QColor(color))
        p.drawRoundedRect(QRectF(body.x() + 2, body.y() + 2, fw, body.height() - 4), 1.5, 1.5)
    if charging:
        # lightning bolt
        path = QPainterPath()
        path.moveTo(16, 10); path.lineTo(11, 17); path.lineTo(15, 17)
        path.lineTo(13, 23); path.lineTo(20, 15); path.lineTo(16, 15); path.closeSubpath()
        p.setBrush(QColor("#ffffff")); p.setPen(Qt.PenStyle.NoPen)
        p.drawPath(path)
    if cross:
        p.setPen(QPen(QColor(C["red"]), 2.5, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        p.drawLine(8, 12, 22, 20)
    p.end()
    return QIcon(pm)


# ══════════════════════════════════════════════════════════════════
# GLOBAL STYLE
# ══════════════════════════════════════════════════════════════════
def global_style() -> str:
    return f"""
QMainWindow, QWidget {{
    background-color:{C['bg1']}; color:{C['t1']};
    font-family:"Segoe UI","SF Pro Display",sans-serif; font-size:13px;
}}
QFrame#card {{
    background-color:{C['bg2']}; border:1px solid {C['b0']}; border-radius:10px;
}}
QToolTip {{
    background:{C['bg3']}; color:{C['t1']}; border:1px solid {C['b1']};
    padding:4px 8px; border-radius:4px;
}}
"""


# ══════════════════════════════════════════════════════════════════
# ENTRY POINT
# ══════════════════════════════════════════════════════════════════
def main():
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setApplicationVersion(APP_VERSION)
    app.setQuitOnLastWindowClosed(False)
    app.setStyle("Fusion")
    app.setStyleSheet(global_style())
    app.setWindowIcon(make_battery_icon(100, C["acc"]))

    if not QSystemTrayIcon.isSystemTrayAvailable():
        # still run; tray simply won't appear
        pass

    win = MainWindow()
    win.show()
    # centre on primary screen
    geo = app.primaryScreen().availableGeometry()
    win.move(geo.center() - win.rect().center())
    win.raise_(); win.activateWindow()

    # DWM rounded corners (Windows 11)
    if _IS_WIN:
        try:
            import ctypes
            ctypes.windll.dwmapi.DwmSetWindowAttribute(
                int(win.winId()), 33, ctypes.byref(ctypes.c_int(2)), 4)
        except Exception:
            pass

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
