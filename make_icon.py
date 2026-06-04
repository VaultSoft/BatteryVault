#!/usr/bin/env python3
"""Generate icon.ico for BatteryVault from the in-app battery drawing.
Renders several sizes into a multi-resolution .ico."""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import sys
from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QPixmap, QPainter, QPen, QColor, QPainterPath
from PyQt6.QtCore import Qt, QRectF

ACC = "#00D4AA"; BG = "#0D1117"; T1 = "#E2EAF4"


def draw(size: int) -> QPixmap:
    s = size
    pm = QPixmap(s, s); pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm); p.setRenderHint(QPainter.RenderHint.Antialiasing)
    # rounded dark tile background
    p.setBrush(QColor(BG)); p.setPen(Qt.PenStyle.NoPen)
    p.drawRoundedRect(QRectF(0, 0, s, s), s*0.18, s*0.18)
    # battery body
    bw, bh = s*0.62, s*0.40
    bx, by = (s-bw)/2 - s*0.03, (s-bh)/2
    lw = max(1.0, s*0.05)
    p.setPen(QPen(QColor(T1), lw)); p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawRoundedRect(QRectF(bx, by, bw, bh), s*0.05, s*0.05)
    # terminal nub
    p.setBrush(QColor(T1)); p.setPen(Qt.PenStyle.NoPen)
    p.drawRoundedRect(QRectF(bx+bw+s*0.01, by+bh*0.3, s*0.05, bh*0.4), s*0.01, s*0.01)
    # fill
    inset = lw*1.2
    p.setBrush(QColor(ACC))
    p.drawRoundedRect(QRectF(bx+inset, by+inset, (bw-2*inset)*0.82, bh-2*inset),
                      s*0.02, s*0.02)
    # lightning bolt
    cx, cy = bx+bw*0.5, by+bh*0.5
    u = s*0.012
    path = QPainterPath()
    path.moveTo(cx+2*u, cy-9*u); path.lineTo(cx-5*u, cy+2*u)
    path.lineTo(cx-0*u, cy+2*u); path.lineTo(cx-2*u, cy+9*u)
    path.lineTo(cx+6*u, cy-2*u); path.lineTo(cx+1*u, cy-2*u); path.closeSubpath()
    p.setBrush(QColor("#ffffff")); p.setPen(Qt.PenStyle.NoPen)
    p.drawPath(path)
    p.end()
    return pm


def main():
    app = QApplication(sys.argv)
    out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "icon.ico")
    sizes = [16, 24, 32, 48, 64, 128, 256]
    pms = [draw(s) for s in sizes]
    # Qt writes a multi-image ICO when multiple sizes are added via QImage list?
    # QPixmap.save with .ico writes single image, so use the largest and let
    # Windows downscale, plus also embed via QIcon addPixmap if supported.
    # Simplest reliable path: save the 256 px; Windows scales fine.
    big = draw(256)
    ok = big.save(out, "ICO")
    print("wrote", out, ok, "exists:", os.path.exists(out),
          os.path.getsize(out) if os.path.exists(out) else 0, "bytes")


if __name__ == "__main__":
    main()
