# -*- coding: utf-8 -*-
"""外星仔领时长 —— Windows 桌面客户端（tkinter，无第三方依赖）。

五步向导：连接手机 → 检测 → 选择 → 执行 → 完成。
执行逻辑全部来自 ad_runner.py，这里只负责界面、线程和日志。
"""

import os
import queue
import sys
import threading
import time
import traceback

import tkinter as tk
from tkinter import messagebox, ttk

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import ad_runner  # noqa: E402
import ocr_reader  # noqa: E402
import usb_guide  # noqa: E402
import wireless_dialog  # noqa: E402

APP_NAME = "外星仔领时长"
APP_VERSION = "1.9.2"


def _log_dir():
    return os.path.dirname(sys.executable) if getattr(sys, "frozen", False) else HERE


def _install_crash_log():
    """打包后没有控制台，出错就写到 exe 旁边的 _error.txt。"""

    def hook(exc_type, exc, tb):
        try:
            with open(os.path.join(_log_dir(), "_error.txt"), "w", encoding="utf-8") as f:
                f.write("".join(traceback.format_exception(exc_type, exc, tb)))
        except Exception:
            pass

    sys.excepthook = hook
    if sys.stdout is None:
        sys.stdout = open(os.devnull, "w", encoding="utf-8")
    if sys.stderr is None:
        sys.stderr = open(os.devnull, "w", encoding="utf-8")


_install_crash_log()


from gui_theme import (BG, CARD, TEXT, MUTED, ACCENT, ACCENT_DARK, OK, ERR,
                      LINE, RAIL_BG, ui_font)


def adb_path():
    base = getattr(sys, "_MEIPASS", HERE)
    p = os.path.join(base, "adb.exe")
    return p if os.path.exists(p) else "adb"


class QueueWriter:
    """把 print 的输出转成界面日志。"""

    def __init__(self, q):
        self.q = q

    def write(self, s):
        if s:
            self.q.put(("log", s))

    def flush(self):
        pass


class App(tk.Tk):
    def __init__(self, demo=None):
        super().__init__()
        self.title(f"{APP_NAME} v{APP_VERSION}")
        try:
            ico = os.path.join(getattr(sys, "_MEIPASS", HERE), "app.ico")
            if not os.path.exists(ico):
                ico = os.path.join(HERE, "app.ico")
            if os.path.exists(ico):
                self.iconbitmap(default=ico)
                self.wm_iconbitmap(ico)
        except Exception:
            pass
        self.geometry("980x700")
        self.minsize(900, 640)
        self.configure(bg=BG)

        self.serial = None
        self.adb_path = adb_path()
        self.model = ""
        self.checks = {}
        self.prog = {}
        self.remaining = None
        self.cta_xy = None
        self.preview_locked = True
        self._preview_scale = 1
        self.use_ocr = ocr_reader.available()
        if self.use_ocr:
            ad_runner.CTA_FINDER = self._ocr_find_cta
            ad_runner.PROGRESS_FINDER = self._ocr_progress
        self.targets = dict(ad_runner.DEFAULT_TARGETS)
        self.stop_evt = threading.Event()
        self.q = queue.Queue()
        self.worker = None
        self.done_count = 0
        self.plan = 0

        self._build_rail()
        self._build_pages()
        self._show(0)
        if demo:
            self._demo(int(demo))
        self.after(100, self._pump)

    def _demo_locked(self):
        """--demo locked：渲染「阶段一 7/9、后两个待解锁」这一屏，验收文案用。"""
        self.serial = "V2301A"
        self.model = "V2301A"
        self.status_dot.configure(text="● 已连接 V2301A", fg=OK)
        self.prog = {
            "阶段一": {"done": False, "locked": False, "cur": 7, "total": 9},
            "阶段二": {"done": False, "locked": True, "cur": None, "total": None},
            "加油包": {"done": False, "locked": True, "cur": None, "total": None},
        }
        self.remaining = 2
        self._refresh_choose()
        self._show(2)

    def _demo(self, step):
        """--demo N：跳过真机，用假数据把第 N 步画出来（截图验收用）。"""
        self.serial = "ABC123456789"
        self.model = "iQOO Neo8"
        self.status_dot.configure(text="● 已连接 iQOO Neo8", fg=OK)
        self.prog = {
            "阶段一": {"done": True, "cur": None, "total": None},
            "阶段二": {"done": False, "cur": 1, "total": 3},
            "加油包": {"done": False, "cur": 2, "total": 9},
        }
        self.remaining = 9
        if step >= 1:
            self._write(self.txt_connect, "\n已连接：ABC123456789\n  型号：iQOO Neo8\n  Android：16\n")
        if step >= 2:
            self._write(self.txt_detect,
                        "  [✓] 调试通道\n  [✓] 焦点探针  com.etalien.booster/ui.MainActivity\n"
                        "  [✓] 读屏（uiautomator），58 个节点\n  [✓] 启动外星仔\n"
                        "  [✓] 今日进度  阶段一 9/9✓ | 阶段二 1/3(剩2) | 加油包 2/9(剩7)\n")
        self._refresh_choose()
        if step >= 3:
            self._show(3)
            self.progress["maximum"] = 9
            self.progress["value"] = 3
            self.lbl_run.configure(text="3 / 9 轮")
            self._write(self.txt_run,
                        "第 1/9 轮\n  进度：阶段一 9/9✓ | 阶段二 1/3(剩2) | 加油包 2/9(剩7)\n"
                        "  点了「点广告 领时长」(628,2205)\n"
                        "  广告已起来：com.qq.e.ads.PortraitADActivity（+1.2s）\n"
                        "  已强停（点击后约 22.0s）\n  已清空最近任务\n  用时 27.4s\n")
        self._show(max(0, min(step - 1, 4)))
        if step >= 5:
            self.prog = {n: {"done": True, "cur": None, "total": None}
                         for n in ad_runner.PHASE_NAMES}
            self.lbl_done.configure(text="这一轮跑了 9 条，成功 9")
            table, _ = ad_runner.progress_table(self.prog, self.targets)
            self.lbl_done_table.configure(text=table)
            self.lbl_done_hint.configure(
                text="还剩 0 条，今天全部领完。\n时长以 App 内「可暂停时长」为准，重启 App 后刷新。")


    # ------------------------------------------------------------ 左侧步骤栏
    def _build_rail(self):
        rail = tk.Frame(self, bg=RAIL_BG, width=214)
        rail.pack(side="left", fill="y")
        rail.pack_propagate(False)

        tk.Label(rail, text="外星仔领时长", bg=RAIL_BG, fg=TEXT,
                 font=ui_font(16, True), anchor="w").pack(fill="x", padx=22, pady=(26, 2))
        tk.Label(rail, text="自动看广告 · 领可暂停时长", bg=RAIL_BG, fg=MUTED,
                 font=ui_font(9), anchor="w").pack(fill="x", padx=22, pady=(0, 26))

        self.rail_items = []
        for i, title in enumerate(["连接手机", "检测", "选择", "执行", "完成"]):
            row = tk.Frame(rail, bg=RAIL_BG)
            row.pack(fill="x", padx=14, pady=2)
            dot = tk.Label(row, text=str(i + 1), bg=LINE, fg=MUTED, width=3,
                           font=ui_font(9, True), pady=3)
            dot.pack(side="left")
            lab = tk.Label(row, text=title, bg=RAIL_BG, fg=MUTED,
                           font=ui_font(10), anchor="w", padx=12)
            lab.pack(side="left", fill="x", expand=True, pady=4)
            self.rail_items.append((row, dot, lab))

        tk.Frame(rail, bg=RAIL_BG).pack(fill="both", expand=True)
        self.status_dot = tk.Label(rail, text="● 未连接", bg=RAIL_BG, fg=ERR,
                                   font=ui_font(9), anchor="w")
        self.status_dot.pack(fill="x", padx=22, pady=(0, 6))
        tk.Label(rail, text="不 root · 只做正常点击", bg=RAIL_BG, fg=MUTED,
                 font=ui_font(8), anchor="w").pack(fill="x", padx=22, pady=(0, 22))

    def _show(self, idx):
        self.step = idx
        for i, (row, dot, lab) in enumerate(self.rail_items):
            if i == idx:
                dot.configure(bg=ACCENT, fg="#FFFFFF")
                lab.configure(fg=TEXT, font=ui_font(10, True))
            elif i < idx:
                dot.configure(bg=OK, fg="#FFFFFF")
                lab.configure(fg=MUTED, font=ui_font(10))
            else:
                dot.configure(bg=LINE, fg=MUTED)
                lab.configure(fg=MUTED, font=ui_font(10))
        for i, f in enumerate(self.pages):
            f.pack_forget()
        self.pages[idx].pack(side="left", fill="both", expand=True)

    # ------------------------------------------------------------ 右侧页面
    def _page(self, title, subtitle):
        f = tk.Frame(self, bg=BG)
        head = tk.Frame(f, bg=BG)
        head.pack(fill="x", padx=34, pady=(28, 0))
        tk.Label(head, text=title, bg=BG, fg=TEXT, font=ui_font(18, True),
                 anchor="w").pack(anchor="w")
        tk.Label(head, text=subtitle, bg=BG, fg=MUTED, font=ui_font(9),
                 anchor="w", justify="left").pack(anchor="w", pady=(4, 0))
        card = tk.Frame(f, bg=CARD)
        card.pack(fill="both", expand=True, padx=34, pady=(16, 26))
        inner = tk.Frame(card, bg=CARD)
        inner.pack(fill="both", expand=True, padx=24, pady=20)
        return f, inner

    def _build_pages(self):
        self.pages = []
        self.pages.append(self._page_connect())
        self.pages.append(self._page_detect())
        self.pages.append(self._page_choose())
        self.pages.append(self._page_run())
        self.pages.append(self._page_done())

    # ---- 第 1 步
    def _page_connect(self):
        f, body = self._page("连接手机", "用数据线把手机连到电脑，打开「USB 调试」。")

        hints = tk.Frame(body, bg="#F7F7FC", highlightthickness=1, highlightbackground=LINE)
        hints.pack(fill="x", pady=(0, 14))
        for i, (t, d) in enumerate([
            ("① 打开 USB 调试", "设置 → 关于手机 → 版本信息 → 连点「软件版本号」7 次 → 开发者选项 → USB 调试"),
            ("② 选对 USB 用途", "插线后下拉通知栏，把 USB 用途改成「传输文件(MTP)」，别用「仅充电」"),
            ("③ 允许调试", "手机弹「允许 USB 调试吗」→ 勾「一律允许」→ 允许"),
        ]):
            row = tk.Frame(hints, bg="#F7F7FC")
            row.pack(fill="x", padx=14, pady=(10 if i == 0 else 4, 0))
            tk.Label(row, text=t, bg="#F7F7FC", fg=TEXT, font=ui_font(9, True),
                     anchor="w", width=14).pack(side="left")
            tk.Label(row, text=d, bg="#F7F7FC", fg=MUTED, font=ui_font(9),
                     anchor="w", justify="left").pack(side="left", fill="x", expand=True)
        tk.Frame(hints, bg="#F7F7FC", height=10).pack()

        self.txt_connect = tk.Text(body, height=9, bg="#FAFAFD", fg=TEXT, relief="flat",
                                   font=("Microsoft YaHei UI", 10), wrap="word", padx=12, pady=10,
                                   highlightthickness=1, highlightbackground=LINE)
        self.txt_connect.pack(fill="both", expand=True)
        self._write(self.txt_connect, "点下面的按钮开始。\n")

        bar = tk.Frame(body, bg=CARD)
        bar.pack(side="bottom", fill="x", pady=(16, 0))
        self.btn_connect = self._primary(bar, "连接手机", self.on_connect)
        self.btn_connect.pack(side="left")
        self.btn_usb = self._ghost(bar, "开启 USB 调试", self.on_usb_guide)
        self.btn_usb.pack(side="left", padx=(10, 0))
        self.btn_wifi = self._ghost(bar, "无线连接", self.on_wireless)
        self.btn_wifi.pack(side="left", padx=(8, 0))
        self.btn_next1 = self._ghost(bar, "下一步", lambda: self._show(1))
        self.btn_next1.pack(side="right")
        self.btn_next1.configure(state="disabled")
        return f

    def on_connect(self):
        self.btn_connect.configure(state="disabled", text="连接中…")

        def work():
            ad_runner.ADB = adb_path()
            try:
                devs = ad_runner.list_devices()
            except SystemExit:
                devs = []
            if not devs:
                self.q.put(("log", "\n没有找到设备。检查：\n"
                                   "  1. 数据线是不是只能充电的线\n"
                                   "  2. 手机「USB 用途」选「传输文件(MTP)」\n"
                                   "  3. 手机弹出的「允许 USB 调试」有没有点允许\n"))
                self.q.put(("connect_fail", None))
                return
            self.serial = devs[0]
            model, _ = ad_runner.adb(self.serial, "shell", "getprop", "ro.product.model")
            rel, _ = ad_runner.adb(self.serial, "shell", "getprop", "ro.build.version.release")
            self.model = (model or "").strip()
            self.q.put(("log", f"\n已连接：{self.serial}\n  型号：{self.model or '未知'}\n"
                               f"  Android：{rel or '未知'}\n"))
            if len(devs) > 1:
                self.q.put(("log", f"  检测到 {len(devs)} 台设备，默认用第一台。\n"))
            self.q.put(("connect_ok", None))

        threading.Thread(target=work, daemon=True).start()

    def on_usb_guide(self):
        """打开「开启 USB 调试」引导窗口。"""
        self.guide = usb_guide.UsbGuide(self)

    def on_wireless(self):
        """打开无线配对窗口（adb pair）。"""
        self.wifi = wireless_dialog.WirelessDialog(self)

    # ------------------------------------------------------------ OCR 读屏
    def _shot_rows(self, serial):
        path = os.path.join(_log_dir(), "_shot.png")
        if not ad_runner.screencap(serial, path):
            return []
        return ocr_reader.read_png(path)

    def _ocr_find_cta(self, serial):
        rows = self._shot_rows(serial)
        self._last_ocr = rows
        hit = ocr_reader.find_cta(rows)
        return (hit["cx"], hit["cy"]) if hit else None

    def _ocr_progress(self, serial):
        rows = getattr(self, "_last_ocr", None) or self._shot_rows(serial)
        return ocr_reader.progress(rows) if rows else {}

    # ---- 第 2 步
    def _page_detect(self):
        f, body = self._page("检测", "点「开始检测」：自动截屏、识别进度，并把按钮框出来。")

        bar = tk.Frame(body, bg=CARD)
        bar.pack(side="bottom", fill="x", pady=(14, 0))
        self.btn_detect = self._primary(bar, "开始检测", self.on_detect)
        self.btn_detect.pack(side="left")
        self.btn_calib = self._ghost(bar, "重新截图", self.on_calibrate)
        self.btn_calib.pack(side="left", padx=(10, 0))
        self.lbl_calib = tk.Label(bar, text="", bg=CARD, fg=MUTED, font=ui_font(9))
        self.lbl_calib.pack(side="left", padx=10)
        self.btn_next2 = self._ghost(bar, "下一步", lambda: self._show(2))
        self.btn_next2.pack(side="right")
        self.btn_next2.configure(state="disabled")

        split = tk.Frame(body, bg=CARD)
        split.pack(fill="both", expand=True)

        # 右侧先占位，左侧才能把剩下的空间吃满（Tk 的打包顺序很重要）
        right = tk.Frame(split, bg=CARD, width=290)
        right.pack(side="right", fill="y", padx=(14, 0))
        right.pack_propagate(False)

        left = tk.Frame(split, bg=CARD)
        left.pack(side="left", fill="both", expand=True)

        box = tk.Frame(left, bg=LINE, padx=1, pady=1)
        box.pack(fill="both", expand=True)
        inner = tk.Frame(box, bg="#FBFBFE")
        inner.pack(fill="both", expand=True)
        self.txt_detect = tk.Text(inner, bg="#FBFBFE", fg=TEXT, relief="flat", bd=0,
                                  font=("Microsoft YaHei UI", 10), wrap="word",
                                  padx=10, pady=8, highlightthickness=0,
                                  spacing1=1, spacing3=2, cursor="arrow", takefocus=0,
                                  state="disabled")
        sb = tk.Scrollbar(inner, command=self.txt_detect.yview, width=10,
                          troughcolor="#F1F1F7", bd=0, relief="flat")
        self.txt_detect.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        self.txt_detect.pack(side="left", fill="both", expand=True)
        self._write(self.txt_detect, "点「开始检测」。检测不会点广告、不会改任何东西。\n")

        tk.Label(right, text="手机屏幕", bg=CARD, fg=MUTED, font=ui_font(9),
                 anchor="w").pack(fill="x")

        # 先占住底部的锁和说明，再让画布吃剩下的空间
        self.lock_btn = tk.Button(right, text="🔒 已锁定（点一下解锁）", command=self._toggle_lock,
                                  bg="#F0F1F7", fg=MUTED, relief="flat", bd=0,
                                  font=ui_font(9), pady=6, cursor="hand2",
                                  activebackground="#E7E9F0")
        self.lock_btn.pack(side="bottom", fill="x")
        self.preview_hint = tk.Label(right, text="检测后这里显示截图", bg=CARD, fg=MUTED,
                                     font=ui_font(8), anchor="w", wraplength=286,
                                     justify="left")
        self.preview_hint.pack(side="bottom", fill="x", pady=(4, 4))

        self.preview = tk.Canvas(right, bg="#101216", width=290, height=470,
                                 highlightthickness=0)
        self.preview.pack(fill="both", expand=True)
        self.preview.bind("<Button-1>", self._on_preview_click)
        self.preview.bind("<Configure>", self._on_preview_resize)
        self.preview.bind("<Double-Button-1>", lambda e: self._open_shot())
        return f

    def _open_shot(self):
        path = getattr(self, "_shot_path", None)
        if path and os.path.exists(path):
            try:
                os.startfile(path)
            except Exception as e:
                self._write(self.txt_detect, f"\n打不开图片：{e}\n")
        else:
            self._write(self.txt_detect, "\n还没有截图。\n")

    def _toggle_lock(self):
        self.preview_locked = not self.preview_locked
        if self.preview_locked:
            self.lock_btn.configure(text="🔒 已锁定（点一下解锁）", bg="#F0F1F7", fg=MUTED)
            self.preview.configure(cursor="")
        else:
            self.lock_btn.configure(text="🔓 已解锁，点图片取坐标", bg="#FFF4E6", fg=ERR)
            self.preview.configure(cursor="crosshair")

    def _on_preview_click(self, e):
        if self.preview_locked:
            self._write(self.txt_detect, "预览是锁着的：先点下面的「已锁定」解锁，再点图片。\n")
            return
        if not self._preview_scale:
            return
        x, y = int(e.x * self._preview_scale), int(e.y * self._preview_scale)
        self.cta_xy = (x, y)
        self._draw_preview_marker(e.x, e.y, color=OK)
        self.lbl_calib.configure(text=f"按钮坐标：{x}, {y}", fg=OK)
        self._write(self.txt_detect, f"手动设置「点广告」坐标：{x}, {y}\n")
        self.btn_next2.configure(state="normal")

    def _draw_preview_marker(self, x, y, color=OK, r=11):
        self.preview.delete("mark")
        self.preview.create_oval(x - r, y - r, x + r, y + r, outline=color, width=3, tags="mark")

    def _show_preview(self, path, hit=None):
        self._shot_path = path
        self._shot_hit = hit
        self._render_preview()

    def _on_preview_resize(self, _e=None):
        if not getattr(self, "_shot_path", None):
            return
        if getattr(self, "_resize_job", None):
            self.after_cancel(self._resize_job)
        self._resize_job = self.after(180, self._render_preview)

    def _render_preview(self):
        path = getattr(self, "_shot_path", None)
        if not path:
            return
        try:
            img = tk.PhotoImage(file=path)
        except Exception as e:
            self._write(self.txt_detect, f"\n截图读不出来：{e}\n")
            return
        cw = max(200, self.preview.winfo_width() or 340)
        ch = max(200, self.preview.winfo_height() or 520)
        w, h = img.width(), img.height()
        factor = max(1, int(max(w / float(cw), h / float(ch)) + 0.999))
        self._preview_scale = factor
        small = img.subsample(factor) if factor > 1 else img
        self.preview.delete("all")
        self.preview.create_image(cw // 2, 8, anchor="n", image=small)
        self.preview.image = small
        self.preview_hint.configure(text=f"{w}×{h}（缩略 {small.width()}×{small.height()}）\n双击图片看大图；解锁后可点图取坐标")
        hit = getattr(self, "_shot_hit", None)
        if hit:
            self._draw_preview_marker(hit["cx"] // factor, hit["cy"] // factor)

    def on_detect(self):
        if not self.serial:
            messagebox.showwarning(APP_NAME, "先连接手机。")
            return
        self.btn_detect.configure(state="disabled", text="检测中…")
        self._write(self.txt_detect, "\n开始检测…\n")
        threading.Thread(target=self._detect_worker, daemon=True).start()

    def on_calibrate(self):
        self._refresh_shot()

    def _refresh_shot(self):
        """截图 + OCR，把进度和按钮位置刷新一遍（检测和「重新截图」都走这里）。"""
        if not self.serial:
            messagebox.showwarning(APP_NAME, "先连接手机。")
            return
        self.btn_calib.configure(state="disabled", text="截屏中…")

        def work():
            path = os.path.join(_log_dir(), "_shot.png")
            ok = ad_runner.screencap(self.serial, path)
            prog, hit, line = {}, None, ""
            if ok and ocr_reader.available():
                rows = ocr_reader.read_png(path)
                if rows:
                    prog = ocr_reader.progress(rows)
                    hit = ocr_reader.find_cta(rows)
                    line, _ = ad_runner.progress_line(prog, self.targets)
            self.q.put(("shot", (ok, path, prog, hit, line)))

        threading.Thread(target=work, daemon=True).start()

    def _detect_worker(self):
        ad_runner.ADB = self.adb_path
        log = lambda x: self.q.put(("log_detect", x))
        ok_all = True
        try:
            out, _ = ad_runner.adb(self.serial, "shell", "echo", "ok")
            ok_all &= out == "ok"
            log(f"  [{'✓' if out == 'ok' else '✗'}] 调试通道\n")

            started = ad_runner.launch(self.serial)
            at_main = started and ad_runner.wait_main(self.serial, 25)
            log(f"  [{'✓' if at_main else '✗'}] 启动外星仔"
                f"{'（没进主页，确认已登录）' if not at_main else ''}\n")
            ok_all &= at_main

            pkg, act = ad_runner.focus(self.serial)
            log(f"  [{'✓' if pkg else '✗'}] 焦点探针  {pkg or '读不到'}/{act or ''}\n")

            prog = {}
            if at_main:
                xml = ad_runner.dump(self.serial)
                if xml:
                    prog = ad_runner.parse_progress(xml)
                    log(f"  [✓] 读屏（uiautomator），{len(ad_runner.parse(xml))} 个节点\n")

            # 不论能不能 dump，都截一张图：预览 + OCR 兜底
            path = os.path.join(_log_dir(), "_shot.png")
            ok_shot = ad_runner.screencap(self.serial, path)
            rows, hit = [], None
            if ok_shot and ocr_reader.available():
                rows = ocr_reader.read_png(path)
                if rows:
                    hit = ocr_reader.find_cta(rows)
                    if not prog:
                        prog = ocr_reader.progress(rows)
                        log(f"  [✓] 读屏（OCR·Windows 本地），识别 {len(rows)} 行\n")
            self.q.put(("shot", (ok_shot, path, prog, hit, "")))

            if at_main and prog:
                self.prog = prog
                line, self.remaining = ad_runner.progress_line(prog, self.targets)
                log(f"  [✓] 今日进度  {line}\n")
            else:
                self.prog = {}
                self.remaining = None
                if at_main:
                    log("  [!] 读不到进度，下一步手动填轮数即可。\n")
            self.q.put(("detect_done", ok_all))
        except Exception:
            log("\n检测出错：\n" + traceback.format_exc())
            self.q.put(("detect_done", False))

    def _on_shot(self, ok, path, prog, hit, line):
        self.btn_calib.configure(state="normal", text="重新截图")
        if not ok:
            self._write(self.txt_detect, "\n截图失败：确认手机已解锁、线连着。\n")
            return
        self._show_preview(path, hit)
        if prog:
            self.prog = prog
            text, self.remaining = ad_runner.progress_line(prog, self.targets)
            self._write(self.txt_detect, f"OCR 识别图片：{text}\n")
            self._refresh_choose()
        all_done = bool(self.prog) and all(
            (self.prog.get(n) or {}).get("done") for n in ad_runner.PHASE_NAMES)
        if all_done:
            self._write(self.txt_detect, "今天已经全部领完，不需要按钮坐标。\n")
            self.lbl_calib.configure(text="今日已领完", fg=OK)
        elif hit:
            if self.cta_xy is None:
                self.cta_xy = (hit["cx"], hit["cy"])
            self.lbl_calib.configure(text=f"按钮坐标：{hit['cx']}, {hit['cy']}", fg=OK)
            self._write(self.txt_detect, f"OCR 找到「点广告」按钮：{hit['cx']}, {hit['cy']}\n")
        self.btn_next2.configure(state="normal")

    # ---- 第 3 步
    def _page_choose(self):
        f, body = self._page("选择", "脚本会自动跳过已完成的阶段，只跑剩下的。")
        self.lbl_summary = tk.Label(body, text="先做检测。", bg=CARD, fg=TEXT,
                                    font=ui_font(12, True), anchor="w", justify="left")
        self.lbl_summary.pack(fill="x")

        self.lbl_table = tk.Label(body, text="", bg=CARD, fg=MUTED, font=("Microsoft YaHei UI", 10),
                                  anchor="w", justify="left")
        self.lbl_table.pack(fill="x", pady=(10, 0))

        row = tk.Frame(body, bg=CARD)
        row.pack(fill="x", pady=(20, 0))
        tk.Label(row, text="本次最多跑", bg=CARD, fg=TEXT, font=ui_font(10)).pack(side="left")
        self.var_rounds = tk.StringVar(value="0")
        self.spin_rounds = tk.Spinbox(row, from_=0, to=99, width=6, textvariable=self.var_rounds,
                                      font=ui_font(10), relief="flat", bg="#FAFAFD",
                                      highlightthickness=1, highlightbackground=LINE)
        self.spin_rounds.pack(side="left", padx=8)
        tk.Label(row, text="轮（0 = 按剩余数跑完）", bg=CARD, fg=MUTED, font=ui_font(9)).pack(side="left")

        self.var_keep = tk.BooleanVar(value=True)
        tk.Checkbutton(body, text="连点模式（不重启 App，跑完一批再统一确认；失败会自动改回重启）",
                       variable=self.var_keep, bg=CARD, fg=TEXT, activebackground=CARD,
                       font=ui_font(9), anchor="w").pack(fill="x", pady=(10, 0))

        self.var_clear = tk.BooleanVar(value=True)
        tk.Checkbutton(body, text="每轮结束后清空后台（更稳，但每轮多 3 秒）",
                       variable=self.var_clear, bg=CARD, fg=TEXT, activebackground=CARD,
                       font=ui_font(9), anchor="w").pack(fill="x", pady=(14, 0))

        self.var_seconds = tk.StringVar(value="25")
        row2 = tk.Frame(body, bg=CARD)
        row2.pack(fill="x", pady=(10, 0))
        tk.Label(row2, text="每轮等待", bg=CARD, fg=TEXT, font=ui_font(10)).pack(side="left")
        tk.Spinbox(row2, from_=20, to=45, width=5, textvariable=self.var_seconds,
                   font=ui_font(10), relief="flat", bg="#FAFAFD",
                   highlightthickness=1, highlightbackground=LINE).pack(side="left", padx=8)
        tk.Label(row2, text="秒（实测发奖点 18–20 秒，但 22 秒仍偶发漏奖，建议 25）",
                 bg=CARD, fg=MUTED, font=ui_font(9)).pack(side="left")

        bar = tk.Frame(body, bg=CARD)
        bar.pack(side="bottom", fill="x", pady=(18, 0))
        self.btn_start = self._primary(bar, "开始执行", self.on_start)
        self.btn_start.pack(side="left")
        self._ghost(bar, "上一步", lambda: self._show(1)).pack(side="right")
        return f

    def _refresh_choose(self):
        if not self.prog:
            self.lbl_summary.configure(
                text="读不到进度。到第 2 步点「截图标按钮」识别一次，或在下面直接填轮数。", fg=TEXT)
            self.lbl_table.configure(text="")
            return

        table, remain = ad_runner.progress_table(self.prog, self.targets)
        self.lbl_table.configure(text=table)

        names = ad_runner.PHASE_NAMES
        info = {n: (self.prog.get(n) or {}) for n in names}
        all_done = all(info[n].get("done") for n in names)
        locked = [n for n in names if info[n].get("locked")]
        unknown = [n for n in names
                   if info[n].get("cur") is None
                   and not info[n].get("done") and not info[n].get("locked")]

        if all_done:
            self.lbl_summary.configure(text="今天已经全部领完了，不用跑。", fg=OK)
            return
        if remain is None:
            self.lbl_summary.configure(
                text=f"「{'、'.join(unknown)}」读不出次数，请在下面填要跑几轮。", fg=TEXT)
            return
        if remain == 0:
            self.lbl_summary.configure(
                text="现在没有可领的（后面的阶段还没解锁），过一会儿再检测。", fg=TEXT)
            return

        tail = f"（{'、'.join(locked)} 待解锁，不占这一轮）" if locked else ""
        self.lbl_summary.configure(
            text=f"这一轮能领 {remain} 条，预计 {self._eta(remain)} 分钟{tail}。", fg=TEXT)
        if self.var_rounds.get().strip() in ("", "0"):
            self.var_rounds.set(str(remain))

    @staticmethod
    def _eta(n):
        return max(1, round(n * 27 / 60))

    def on_start(self):
        if self.worker and self.worker.is_alive():
            return
        try:
            cap = int(self.var_rounds.get() or 0)
        except ValueError:
            cap = 0
        try:
            seconds = max(10.0, float(self.var_seconds.get() or 20))
        except ValueError:
            seconds = 20.0

        remain = self.remaining if self.remaining is not None else cap
        plan = remain if not cap else min(remain, cap)
        if plan <= 0:
            if self.remaining is None:
                messagebox.showinfo(
                    APP_NAME,
                    "读不到进度（这台手机的读屏被系统禁用了）。\n\n"
                    "请在第 3 步的「本次最多跑」里填要跑几轮，\n"
                    "并在第 2 步点「截图标按钮」标出「点广告」的位置。")
            else:
                messagebox.showinfo(APP_NAME, "今天没有剩余的轮数了。")
            return

        self.plan = plan
        self.done_count = 0
        self.stop_evt.clear()
        self._clear(self.txt_run)
        self._show(3)
        self.progress["maximum"] = plan
        self.progress["value"] = 0
        self.lbl_run.configure(text=f"0 / {plan} 轮")
        self.btn_stop.configure(state="normal", text="停止")

        self.worker = threading.Thread(
            target=self._run_worker,
            args=(plan, seconds, self.var_clear.get()),
            daemon=True)
        self.worker.start()

    # ---- 第 4 步
    def _page_run(self):
        f, body = self._page("执行", "连点模式：看完一条按 BACK 回主页接着点；只在验收/失败时才重启 App。手机别锁屏。")
        head = tk.Frame(body, bg=CARD)
        head.pack(fill="x")
        self.lbl_run = tk.Label(head, text="0 / 0 轮", bg=CARD, fg=TEXT, font=ui_font(12, True))
        self.lbl_run.pack(side="left")
        self.lbl_run_hint = tk.Label(head, text="", bg=CARD, fg=MUTED, font=ui_font(9))
        self.lbl_run_hint.pack(side="right")

        style = ttk.Style(self)
        style.theme_use("default")
        style.configure("A.Horizontal.TProgressbar", troughcolor="#EFEFF6", background=ACCENT,
                        borderwidth=0, thickness=8)
        self.progress = ttk.Progressbar(body, style="A.Horizontal.TProgressbar",
                                        orient="horizontal", mode="determinate")
        self.progress.pack(fill="x", pady=(10, 14))

        box = tk.Frame(body, bg=LINE, padx=1, pady=1)
        box.pack(fill="both", expand=True)
        inner = tk.Frame(box, bg="#FBFBFE")
        inner.pack(fill="both", expand=True)
        self.txt_run = tk.Text(inner, bg="#FBFBFE", fg=TEXT, relief="flat", bd=0,
                               font=("Microsoft YaHei UI", 9), wrap="word",
                               padx=10, pady=8, highlightthickness=0,
                               spacing1=1, spacing3=2, cursor="arrow", takefocus=0,
                               state="disabled")
        sb = tk.Scrollbar(inner, command=self.txt_run.yview, width=10,
                          troughcolor="#F1F1F7", bd=0, relief="flat")
        self.txt_run.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        self.txt_run.pack(side="left", fill="both", expand=True)

        bar = tk.Frame(body, bg=CARD)
        bar.pack(fill="x", pady=(14, 0))
        self.btn_stop = self._danger(bar, "停止", self.on_stop)
        self.btn_stop.pack(side="left")
        self.btn_skip = self._ghost(bar, "看结果", lambda: self._show(4))
        self.btn_skip.pack(side="right")
        self.btn_skip.configure(state="disabled")
        return f

    def _run_worker(self, plan, seconds, clear):
        ad_runner.ADB = adb_path()
        old = sys.stdout
        sys.stdout = QueueWriter(self.q)
        statuses = []
        try:
            prev = None
            for i in range(plan):
                if self.stop_evt.is_set():
                    break
                self.q.put(("progress", (i, plan)))
                print(f"\n第 {i + 1}/{plan} 轮")
                keep = bool(self.var_keep.get())
                reuse = keep and i > 0
                if i == 0:
                    pkg, act = ad_runner.focus(self.serial)
                    reuse = bool(pkg) and act.endswith(("MainActivity", "SplashActivity"))
                try:
                    status, prog, remain = ad_runner.one_round(
                        self.serial, seconds, self.cta_xy, clear, 2.0, self.targets,
                        stop=self.stop_evt, cold_start=not reuse,
                        keep=keep)
                    if reuse and status == "fail":
                        print("  复用页面失败，改成冷启动重试")
                        status, prog, remain = ad_runner.one_round(
                            self.serial, seconds, self.cta_xy, clear, 2.0, self.targets,
                            stop=self.stop_evt)

                    # —— 每轮验收：重开 App 截图识别，对比计数涨了没 ——
                    last_round = (i == plan - 1)
                    if status == "ok" and keep and not last_round:
                        print("  连点模式：本条先不重启确认，跑完一批统一验收")
                    elif status == "ok":
                        before = self._counts(prog)
                        after_prog = self._verify_state(before, relaunch=not keep)
                        if after_prog:
                            after = self._counts(after_prog)
                            if self._gained(before, after):
                                print(f"  ✓ 验收通过：{self._delta(prog, after_prog)}")
                                prog = after_prog
                                self.prog = after_prog
                            else:
                                print("  ✗ 这一轮没到账，补跑一次")
                                st2, pg2, rm2 = ad_runner.one_round(
                                    self.serial, seconds, self.cta_xy, clear, 2.0,
                                    self.targets, stop=self.stop_evt)
                                if st2 == "ok":
                                    prog3 = self._verify_state(before)
                                    if prog3:
                                        prog = prog3
                                        self.prog = prog3
                                        if self._gained(before, self._counts(prog3)):
                                            print(f"  ✓ 补跑后到账：{self._delta(after_prog or prog, prog3)}")
                                        else:
                                            print("  ✗ 补跑仍未到账，先停")
                                            status = "fail"
                                        after_prog = prog3
                                else:
                                    status = st2
                except Exception:
                    print("出错：\n" + traceback.format_exc())
                    status, prog, remain = "fail", {}, None
                if prog:
                    self.prog = prog
                    line, _ = ad_runner.progress_line(prog, self.targets)
                    if prev is not None:
                        print(f"  上一轮结果：{line}（对比上一轮：{self._delta(prev, prog)}）")
                    prev = dict(prog)
                statuses.append(status)
                if status == "done":
                    print("\n今天领完了。")
                    break
                if status == "fail":
                    print("\n这一轮失败，先停。处理完再点开始。")
                    break
                if remain is not None and remain <= 1:
                    print("  这是最后一条，下一轮会确认收尾。")
                self.q.put(("progress", (i + 1, plan)))
                time.sleep(1.5)

            # 收尾：不再重启 App，直接对着当前屏幕多读几次
            try:
                deadline = time.time() + 20
                while True:
                    p2 = self._read_once()
                    if p2:
                        self.prog = p2
                        line, _ = ad_runner.progress_line(p2, self.targets)
                        print(f"收尾确认（不重启）：{line}")
                        break
                    if time.time() >= deadline:
                        print("收尾确认：暂时读不到，重启 App 后以实际数字为准")
                        break
                    time.sleep(2)
            except Exception:
                pass
        finally:
            sys.stdout = old
            self.q.put(("run_done", statuses))

    def _read_once(self):
        """截屏 + 读屏，读回当前进度。"""
        path = os.path.join(_log_dir(), "_shot.png")
        if not ad_runner.screencap(self.serial, path):
            return None
        xml = ad_runner.dump(self.serial)
        if xml:
            prog = ad_runner.parse_progress(xml)
            if prog:
                return prog
        if ocr_reader.available():
            rows = ocr_reader.read_png(path)
            if rows:
                prog = ocr_reader.progress(rows)
                if prog:
                    return prog
        return None

    def _verify_state(self, before=None, timeout=14.0, relaunch=True):
        """重开 App 后轮询读数：服务端同步有延迟，不能只读一次。

        只要看到计数比 before 涨了就立刻返回；超时则返回最后一次读到的值。
        """
        try:
            if relaunch:
                ad_runner.launch(self.serial)
                if not ad_runner.wait_main(self.serial, 20):
                    return None
            deadline = time.time() + timeout
            last = None
            while True:
                prog = self._read_once()
                if prog:
                    last = prog
                    if before is None or self._gained(before, self._counts(prog)):
                        return prog
                    print("  …计数还没同步，2 秒后再读")
                if time.time() >= deadline:
                    return last
                time.sleep(2)
        except Exception:
            return None

    @staticmethod
    def _counts(prog):
        out = {}
        for n in ad_runner.PHASE_NAMES:
            info = prog.get(n) or {}
            cur = info.get("cur")
            if cur is None and info.get("done"):
                cur = info.get("total")
            out[n] = cur
        return out

    @staticmethod
    def _gained(before, after):
        for n in ad_runner.PHASE_NAMES:
            b, a = before.get(n), after.get(n)
            if a is not None and (b is None or a > b):
                return True
        return False

    @staticmethod
    def _delta(before, after):
        """两个进度快照比一比，返回「阶段二 +1」这种描述。"""
        parts = []
        for name in ad_runner.PHASE_NAMES:
            b = (before.get(name) or {}).get("cur")
            a = (after.get(name) or {}).get("cur")
            if a is None and (after.get(name) or {}).get("done"):
                a = (after.get(name) or {}).get("total")
            if b is not None and a is not None and a != b:
                parts.append(f"{name} {b}→{a}")
            elif b is not None and a is None and not (after.get(name) or {}).get("done"):
                parts.append(f"{name} 读数丢失")
        return "，".join(parts) if parts else "计数没变"

    def on_stop(self):
        self.stop_evt.set()
        self.btn_stop.configure(state="disabled", text="正在停…")

    # ---- 第 5 步
    def _page_done(self):
        f, body = self._page("完成", "结果以 App 里的阶段计数为准。")
        self.lbl_done = tk.Label(body, text="", bg=CARD, fg=TEXT, font=ui_font(13, True),
                                 anchor="w", justify="left")
        self.lbl_done.pack(fill="x")
        self.lbl_done_table = tk.Label(body, text="", bg=CARD, fg=MUTED, font=("Microsoft YaHei UI", 10),
                                       anchor="w", justify="left")
        self.lbl_done_table.pack(fill="x", pady=(12, 0))
        self.lbl_done_hint = tk.Label(body, text="", bg=CARD, fg=MUTED, font=ui_font(9),
                                      anchor="w", justify="left", wraplength=560)
        self.lbl_done_hint.pack(fill="x", pady=(16, 0))

        bar = tk.Frame(body, bg=CARD)
        bar.pack(side="bottom", fill="x", pady=(18, 0))
        self._primary(bar, "再跑一次", self.on_again).pack(side="left")
        self._ghost(bar, "退出", self.destroy).pack(side="right")
        return f

    def on_again(self):
        self.remaining = None
        self._show(1)

    # ------------------------------------------------------------ 控件
    def _primary(self, parent, text, cmd):
        b = tk.Button(parent, text=text, command=cmd, bg=ACCENT, fg="#FFFFFF",
                      activebackground=ACCENT_DARK, activeforeground="#FFFFFF",
                      disabledforeground="#EDEAFF", font=ui_font(10, True),
                      relief="flat", padx=24, pady=8, cursor="hand2", bd=0,
                      highlightthickness=0)
        b.bind("<Enter>", lambda e: b.configure(bg=ACCENT_DARK) if str(b["state"]) == "normal" else None)
        b.bind("<Leave>", lambda e: b.configure(bg=ACCENT) if str(b["state"]) == "normal" else None)
        return b

    def _ghost(self, parent, text, cmd):
        b = tk.Button(parent, text=text, command=cmd, bg=CARD, fg="#4A4F5C",
                      activebackground="#EEF0F6", activeforeground=TEXT,
                      disabledforeground="#B9BECD", font=ui_font(9),
                      relief="flat", bd=0, padx=16, pady=7, cursor="hand2",
                      highlightthickness=1, highlightbackground=LINE,
                      highlightcolor=LINE)
        b.bind("<Enter>", lambda e: b.configure(bg="#F4F5FA") if str(b["state"]) == "normal" else None)
        b.bind("<Leave>", lambda e: b.configure(bg=CARD) if str(b["state"]) == "normal" else None)
        return b

    def _danger(self, parent, text, cmd):
        return tk.Button(parent, text=text, command=cmd, bg=ERR, fg="#FFFFFF",
                         activebackground="#D9480F", activeforeground="#FFFFFF",
                         font=ui_font(10, True), relief="flat", padx=22, pady=8,
                         cursor="hand2", bd=0)

    @staticmethod
    def _write(widget, s):
        widget.configure(state="normal")
        widget.insert("end", s)
        widget.see("end")
        widget.configure(state="disabled")

    @staticmethod
    def _clear(widget):
        widget.configure(state="normal")
        widget.delete("1.0", "end")
        widget.configure(state="disabled")

    # ------------------------------------------------------------ 消息泵
    def _pump(self):
        try:
            while True:
                kind, payload = self.q.get_nowait()
                if kind == "log":
                    self._write(self.txt_run, payload)
                elif kind == "log_detect":
                    self._write(self.txt_detect, payload)
                elif kind == "connect_ok":
                    self.btn_connect.configure(state="normal", text="重新连接")
                    self.btn_next1.configure(state="normal")
                    self.status_dot.configure(text=f"● 已连接 {self.model or self.serial}", fg=OK)
                    self._show(1)
                elif kind == "connect_fail":
                    self.btn_connect.configure(state="normal", text="重新连接")
                elif kind == "detect_done":
                    self.btn_detect.configure(state="normal", text="重新检测")
                    self.btn_next2.configure(state="normal")
                    self._refresh_choose()
                elif kind == "shot":
                    self._on_shot(*payload)
                elif kind == "guide_check":
                    if getattr(self, "guide", None) and self.guide.winfo_exists():
                        self.guide.show_result(payload)
                elif kind == "wireless_ok":
                    self.serial = payload
                    self.on_connect()
                elif kind == "guide_connected":
                    self.serial = payload
                    self.on_connect()
                elif kind == "progress":
                    done, total = payload
                    self.done_count = done
                    self.progress["value"] = done
                    self.lbl_run.configure(text=f"{done} / {total} 轮")
                elif kind == "run_done":
                    self.btn_stop.configure(state="disabled")
                    self.btn_skip.configure(state="normal")
                    self._finish(payload)
        except queue.Empty:
            pass
        self.after(100, self._pump)

    def _finish(self, statuses):
        ok = sum(1 for s in statuses if s == "ok")
        fail = sum(1 for s in statuses if s == "fail")
        done = sum(1 for s in statuses if s == "done")
        self.lbl_done.configure(text=f"这一轮跑了 {len(statuses)} 条，成功 {ok}" +
                                     (f"，失败 {fail}" if fail else "") +
                                     ("（已领完）" if done else ""))
        if self.prog:
            table, remain = ad_runner.progress_table(self.prog, self.targets)
            self.lbl_done_table.configure(text=table)
            if remain == 0:
                self.lbl_done_hint.configure(
                    text="三个阶段都已完成，今天不用再跑了。\n"
                         "时长以 App 内「可暂停时长」为准，重启 App 后刷新。")
            else:
                self.lbl_done_hint.configure(
                    text=f"还剩 {remain} 条。直接点「再跑一次」会接着领。")
        else:
            self.lbl_done_table.configure(text="")
            self.lbl_done_hint.configure(text="读不到进度，去 App 里看一眼。")
        self._show(4)


def _selftest():
    """打包自检：确认 tkinter / ad_runner / adb 都在，结果写到 exe 旁边的 _selftest.txt。"""
    lines = []
    ok = True
    try:
        lines.append(f"tkinter {tk.TkVersion}")
    except Exception as e:  # pragma: no cover
        ok = False
        lines.append(f"tkinter 失败: {e}")
    try:
        lines.append(f"ad_runner {getattr(ad_runner, '__file__', '?')}")
    except Exception as e:  # pragma: no cover
        ok = False
        lines.append(f"ad_runner 失败: {e}")
    try:
        import ocr_reader
        lines.append(f"ocr available: {ocr_reader.available()} {getattr(ocr_reader, '_last_error', '')}")
    except Exception as e:
        lines.append(f"ocr 导入失败: {e}")

    ap = adb_path()
    if os.path.exists(ap):
        lines.append(f"adb {ap}")
    else:
        lines.append(f"adb 未找到: {ap}")
    ad_runner.ADB = ap
    try:
        out, rc = ad_runner.adb(None, "version", timeout=15)
        first = (out or "").splitlines()[0] if out else "(无输出)"
        lines.append(f"adb version: {first} rc={rc}")
        ok = ok and bool(out)
    except Exception as e:
        ok = False
        lines.append(f"adb 执行失败: {e}")
    lines.append("OK" if ok else "FAIL")
    target = os.path.join(_log_dir(), "_selftest.txt")
    try:
        with open(target, "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
    except Exception:
        pass
    print("\n".join(lines))
    return 0 if ok else 1


def main():
    if "--selftest" in sys.argv:
        return _selftest()
    demo = None
    if "--demo" in sys.argv:
        i = sys.argv.index("--demo")
        if i + 1 < len(sys.argv):
            demo = sys.argv[i + 1]
    try:
        import ctypes
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass
    app = App(None if demo in ("guide", "wifi", "locked", "shot") else demo)
    if demo == "guide":
        app.on_usb_guide()
    elif demo == "wifi":
        app.on_wireless()
    elif demo == "locked":
        app._demo_locked()
    elif demo == "shot":
        app._show(1)
        app._show_preview(os.path.join(_log_dir(), "demo_shot.png"))
    app.mainloop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
