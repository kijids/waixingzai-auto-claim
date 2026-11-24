# -*- coding: utf-8 -*-
"""首次准备：下载 adb 和 OCR 运行库到本地（两者都不进仓库）。

    python tools/setup.py          # 全部下载
    python tools/setup.py adb      # 只下 adb
    python tools/setup.py ocr      # 只下 OCR
"""
import io
import os
import sys
import zipfile

try:
    from pip._vendor import requests          # 借用 pip 自带的 requests，免装依赖
except ImportError:                           # 没有 pip 时退回标准库
    requests = None

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "src")
VENDOR = os.path.join(ROOT, "vendor", "ocr")

ADB_URL = "https://dl.google.com/android/repository/platform-tools-latest-windows.zip"
OCR_PKGS = [
    "winrt-runtime",
    "winrt-Windows.Foundation",
    "winrt-Windows.Foundation.Collections",
    "winrt-Windows.Globalization",
    "winrt-Windows.Graphics.Imaging",
    "winrt-Windows.Media.Ocr",
    "winrt-Windows.Storage.Streams",
]
PY_TAG = f"cp{sys.version_info.major}{sys.version_info.minor}"


def http(url):
    if requests:
        r = requests.get(url, timeout=180)
        r.raise_for_status()
        return r.content
    import urllib.request
    with urllib.request.urlopen(url, timeout=180) as f:
        return f.read()


def setup_adb():
    target = os.path.join(SRC, "adb.exe")
    if os.path.exists(target):
        print("[skip] adb 已存在")
        return
    print("[get ] platform-tools …")
    blob = http(ADB_URL)
    with zipfile.ZipFile(io.BytesIO(blob)) as z:
        for name in ("platform-tools/adb.exe",
                     "platform-tools/AdbWinApi.dll",
                     "platform-tools/AdbWinUsbApi.dll"):
            data = z.read(name)
            out = os.path.join(SRC, os.path.basename(name))
            with open(out, "wb") as f:
                f.write(data)
            print("  ok", os.path.basename(name))


def setup_ocr():
    if not requests:
        print("[skip] 没有 pip.vendor.requests，OCR 请手动安装：pip install winrt-runtime 等")
        return
    os.makedirs(VENDOR, exist_ok=True)
    for name in OCR_PKGS:
        d = requests.get(f"https://pypi.org/pypi/{name}/json", timeout=60).json()
        pick = None
        for tag in (f"{PY_TAG}-{PY_TAG}-win_amd64", "py3-none-any"):
            for u in d["urls"]:
                if tag in u["filename"]:
                    pick = u
                    break
            if pick:
                break
        if not pick:
            print("[skip]", name, "没有匹配的 wheel")
            continue
        print("[get ]", pick["filename"])
        blob = requests.get(pick["url"], timeout=180).content
        with zipfile.ZipFile(io.BytesIO(blob)) as z:
            z.extractall(VENDOR)


def main():
    what = sys.argv[1] if len(sys.argv) > 1 else "all"
    if what in ("all", "adb"):
        setup_adb()
    if what in ("all", "ocr"):
        setup_ocr()
    print("\n完成。双击 setup.bat 或 run.bat 即可。")


if __name__ == "__main__":
    main()
