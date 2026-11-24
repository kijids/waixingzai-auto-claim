# -*- coding: utf-8 -*-
"""用 Windows 自带 OCR 读手机截图，替代被 ROM 禁掉的 uiautomator。

不装任何手机端 App：电脑截屏（adb screencap）→ 本地 OCR → 得到文字和坐标。
"""

import asyncio
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
FROZEN = getattr(sys, "frozen", False)
BASE = getattr(sys, "_MEIPASS", HERE)

_ready = None
_last_error = ""


def _ensure_path():
    """把 PyWinRT 目录挂进 sys.path。打包后在 _internal/ocr，开发时在 ../build_tools/ocr。"""
    cands = [
        os.path.join(BASE, "ocr"),
        os.path.join(HERE, "..", "vendor", "ocr"),
        os.path.join(HERE, "..", "build_tools", "ocr"),
        os.path.join(HERE, "ocr"),
    ]
    for c in cands:
        c = os.path.abspath(c)
        if os.path.isdir(os.path.join(c, "winrt")) and c not in sys.path:
            sys.path.insert(0, c)
            return True
    return False


def available():
    global _ready
    if _ready is not None:
        return _ready
    try:
        _ensure_path()
        from winrt.windows.media.ocr import OcrEngine  # noqa: F401
        _ready = bool(OcrEngine.available_recognizer_languages)
    except Exception as e:
        globals()["_last_error"] = f"{type(e).__name__}: {e}"
        _ready = False
    return _ready


def _engine():
    from winrt.windows.globalization import Language
    from winrt.windows.media.ocr import OcrEngine

    for tag in ("zh-Hans-CN", "zh-Hans", "zh-CN"):
        e = OcrEngine.try_create_from_language(Language(tag))
        if e:
            return e
    return OcrEngine.try_create_from_user_profile_languages()


async def _ocr_png(path):
    from winrt.windows.graphics.imaging import BitmapDecoder
    from winrt.windows.storage.streams import DataWriter, InMemoryRandomAccessStream

    with open(path, "rb") as f:
        data = f.read()
    i = data.find(b"\x89PNG\r\n\x1a\n")
    if i > 0:
        data = data[i:]

    stream = InMemoryRandomAccessStream()
    writer = DataWriter(stream)
    writer.write_bytes(data)
    await writer.store_async()
    await writer.flush_async()
    stream.seek(0)

    decoder = await BitmapDecoder.create_async(stream)
    bitmap = await decoder.get_software_bitmap_async()
    result = await _engine().recognize_async(bitmap)

    rows = []
    for line in result.lines:
        words = list(line.words)
        if not words:
            continue
        left = min(w.bounding_rect.x for w in words)
        top = min(w.bounding_rect.y for w in words)
        right = max(w.bounding_rect.x + w.bounding_rect.width for w in words)
        bottom = max(w.bounding_rect.y + w.bounding_rect.height for w in words)
        rows.append({
            "text": line.text,
            "norm": re.sub(r"\s+", "", line.text),
            "x1": int(left), "y1": int(top),
            "x2": int(right), "y2": int(bottom),
            "cx": int((left + right) / 2), "cy": int((top + bottom) / 2),
        })
    return rows


def read_png(path):
    """返回 [{text, norm, x1, y1, x2, y2, cx, cy}]，失败返回 []。"""
    if not available():
        return []
    try:
        return asyncio.run(_ocr_png(path))
    except Exception:
        return []


# ------------------------------------------------------------ 语义
def merge_lines(rows, dy=26, gap=240):
    """把同一行被切碎的几段拼回去（按钮文字常被 OCR 拆成两段）。"""
    merged = []
    for r in sorted(rows, key=lambda x: (x["cy"], x["x1"])):
        if merged:
            last = merged[-1]
            if abs(r["cy"] - last["cy"]) <= dy and (r["x1"] - last["x2"]) < gap:
                last["norm"] += r["norm"]
                last["text"] += " " + r["text"]
                last["x1"] = min(last["x1"], r["x1"])
                last["x2"] = max(last["x2"], r["x2"])
                last["y1"] = min(last["y1"], r["y1"])
                last["y2"] = max(last["y2"], r["y2"])
                last["cx"] = (last["x1"] + last["x2"]) // 2
                last["cy"] = (last["y1"] + last["y2"]) // 2
                continue
        merged.append(dict(r))
    return merged


def find_line(rows, *keywords):
    """按去掉空格后的子串找行，返回该行（带中心坐标）。"""
    for kw in keywords:
        for row in rows:
            if kw and kw in row["norm"]:
                return row
    return None


BAD_WORDS = ("免费玩", "每日刷新", "待解锁", "已完成")


def find_cta(rows):
    """找「点广告 领时长」按钮。

    OCR 会把「点广告」认成「点广土亽」，所以用「领时长」优先；
    同时排掉标题行（点广告 免费玩）和状态行，避免领完后误标到标题上。
    """
    merged = merge_lines(rows)
    for kw in ("领时长", "点广告", "点广"):
        for row in merged:
            n = row["norm"]
            if kw not in n:
                continue
            if any(bad in n for bad in BAD_WORDS):
                continue
            if len(n) > 14:          # 按钮文字很短，标题通常更长
                continue
            return row
    return None


COUNT_RE = re.compile(r"(\d+)/(\d+)")
PHASE_NAMES = ("阶段一", "阶段二", "加油包")


def progress(rows):
    """从 OCR 行里还原三个阶段进度。

    用相邻标题的「中点」切分归属，避免卡片右上角的徽标被算到隔壁阶段。
    出现「待解锁」标记为 locked：这个阶段本轮还不能领，不算「读不出」。
    """
    anchors = []
    for row in rows:
        for name in PHASE_NAMES:
            if row["norm"].startswith(name) and not any(a[1] == name for a in anchors):
                anchors.append((row["y1"], name))
    if not anchors:
        return {}
    anchors.sort()

    out = {}
    for i, (y, name) in enumerate(anchors):
        lo = (anchors[i - 1][0] + y) // 2 if i > 0 else -1
        hi = (y + anchors[i + 1][0]) // 2 if i + 1 < len(anchors) else 10 ** 9
        info = {"done": False, "locked": False, "cur": None, "total": None}
        for row in rows:
            if not (lo <= row["y1"] < hi):
                continue
            n = row["norm"]
            if "已完成" in n:
                info["done"] = True
            if "待解锁" in n or "未解锁" in n:
                info["locked"] = True
            m = COUNT_RE.search(n)
            if m and info["cur"] is None:
                info["cur"], info["total"] = int(m.group(1)), int(m.group(2))
        out[name] = info
    return out
