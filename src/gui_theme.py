# -*- coding: utf-8 -*-
"""界面配色与字体，gui.py 和 usb_guide.py 共用。"""

BG = "#F4F5F9"
CARD = "#FFFFFF"
TEXT = "#1B1F27"
MUTED = "#8B90A0"
ACCENT = "#6C5CE7"
ACCENT_DARK = "#5A4BD1"
OK = "#12B886"
ERR = "#E8590C"
DANGER = "#E8590C"
LINE = "#E7E9F0"
RAIL_BG = "#FFFFFF"

FONT = "Microsoft YaHei UI"


def ui_font(size=10, bold=False):
    return (FONT, size, "bold") if bold else (FONT, size)
