# -*- coding: utf-8 -*-
"""开启 USB 调试的引导窗口。"""

import tkinter as tk
from tkinter import ttk

import gui_theme as T

BRANDS = [
    "vivo / iQOO",
    "小米 / Redmi / POCO",
    "OPPO / 一加 / realme",
    "荣耀 / 华为（老机型）",
    "三星",
]

STEPS = {
    "vivo / iQOO": [
        ("打开开发者模式",
         "设置 → 关于手机 → 版本信息 → 连点「软件版本号」7 次，中途要输锁屏密码。"),
        ("进开发者选项",
         "回到设置首页 → 系统管理 → 开发者选项。"),
        ("打开 USB 调试",
         "找到「调试」一栏，把「USB 调试」打开。"),
        ("插线授权",
         "插上数据线 → 下拉通知栏 → USB 用途改成「传输文件(MTP)」→ "
         "手机弹「允许 USB 调试吗」勾「一律允许」再点允许。"),
    ],
    "小米 / Redmi / POCO": [
        ("打开开发者模式",
         "设置 → 我的设备 → 全部参数与信息 → 连点「OS 版本」7 次。"),
        ("进开发者选项",
         "设置 → 更多设置 → 开发者选项。"),
        ("打开 USB 调试",
         "打开「USB 调试」，如果这一页还有「USB 调试（安全设置）」，也一起打开"
         "（需要插 SIM 卡并登录小米账号，否则部分点击会失效）。"),
        ("插线授权",
         "插上数据线 → 通知栏 USB 用途选「传输文件」→ 手机上点「允许」。"),
    ],
    "OPPO / 一加 / realme": [
        ("打开开发者模式",
         "设置 → 关于本机 → 版本信息 → 连点「版本号」7 次。"),
        ("进开发者选项",
         "设置 → 系统设置 → 开发者选项。"),
        ("打开 USB 调试",
         "把「USB 调试」打开。"),
        ("插线授权",
         "插上数据线 → 通知栏 USB 用途选「传输文件」→ 手机上点「允许」。"),
    ],
    "荣耀 / 华为（老机型）": [
        ("打开开发者模式",
         "设置 → 关于手机 → 连点「版本号」7 次。"),
        ("进开发者选项",
         "设置 → 系统和更新 → 开发者选项。"),
        ("打开 USB 调试",
         "把「USB 调试」打开。"),
        ("插线授权",
         "插上数据线 → 通知栏 USB 用途选「传输文件」→ 手机上点「允许」。"),
    ],
    "三星": [
        ("打开开发者模式",
         "设置 → 关于手机 → 软件信息 → 连点「版本号」7 次。"),
        ("进开发者选项",
         "设置 → 开发者选项（在设置最下面）。"),
        ("打开 USB 调试",
         "把「USB 调试」打开。"),
        ("插线授权",
         "插上数据线 → 通知栏 USB 用途选「文件传输」→ 手机上点「允许」。"),
    ],
}


class UsbGuide(tk.Toplevel):
    """品牌 → 点击路径 → 重新检测。"""

    def __init__(self, app):
        super().__init__(app)
        self.app = app
        self.title("开启 USB 调试")
        self.configure(bg=T.BG)
        self.resizable(False, False)
        self.update_idletasks()
        w, h = 680, 600
        px, py = app.winfo_rootx(), app.winfo_rooty()
        cx = px + max(0, (app.winfo_width() - w) // 2)
        cy = py + max(0, (app.winfo_height() - h) // 2)
        self.geometry("%dx%d+%d+%d" % (w, h, cx, cy))
        self.transient(app)
        self.grab_set()

        head = tk.Frame(self, bg=T.BG)
        head.pack(fill="x", padx=26, pady=(22, 0))
        tk.Label(head, text="开启 USB 调试", bg=T.BG, fg=T.TEXT,
                 font=T.ui_font(17, True), anchor="w").pack(anchor="w")
        tk.Label(head, text="跟着做，做完点「重新检测」，连上就自动继续。",
                 bg=T.BG, fg=T.MUTED, font=T.ui_font(9), anchor="w").pack(anchor="w", pady=(4, 0))

        card = tk.Frame(self, bg=T.CARD)
        card.pack(fill="both", expand=True, padx=26, pady=(14, 0))

        row = tk.Frame(card, bg=T.CARD)
        row.pack(fill="x", padx=20, pady=(18, 0))
        tk.Label(row, text="手机品牌", bg=T.CARD, fg=T.TEXT, font=T.ui_font(10)).pack(side="left")
        self.var_brand = tk.StringVar(value=BRANDS[0])
        box = ttk.Combobox(row, values=BRANDS, textvariable=self.var_brand,
                           state="readonly", width=22, font=T.ui_font(9))
        box.pack(side="left", padx=10)
        box.bind("<<ComboboxSelected>>", lambda e: self._render())

        self.body = tk.Frame(card, bg=T.CARD)
        self.body.pack(fill="both", expand=True, padx=20, pady=(14, 0))
        self._render()

        bar = tk.Frame(card, bg=T.CARD)
        bar.pack(fill="x", padx=20, pady=(6, 16))
        self.btn_check = tk.Button(bar, text="重新检测", command=self._check,
                                   bg=T.ACCENT, fg="#FFFFFF", relief="flat", bd=0,
                                   font=T.ui_font(10, True), padx=20, pady=8,
                                   activebackground=T.ACCENT_DARK, activeforeground="#FFFFFF",
                                   cursor="hand2")
        self.btn_check.pack(side="left")
        self.lbl_state = tk.Label(bar, text="", bg=T.CARD, fg=T.MUTED, font=T.ui_font(9))
        self.lbl_state.pack(side="left", padx=12)
        tk.Button(bar, text="关闭", command=self.destroy, bg=T.CARD, fg=T.MUTED,
                  relief="flat", bd=0, font=T.ui_font(9), padx=16, pady=7,
                  activebackground="#F0F1F7", cursor="hand2",
                  highlightthickness=1, highlightbackground=T.LINE).pack(side="right")

    def _render(self):
        for w in self.body.winfo_children():
            w.destroy()
        brand = self.var_brand.get()
        for i, (title, detail) in enumerate(STEPS[brand], 1):
            row = tk.Frame(self.body, bg=T.CARD)
            row.pack(fill="x", pady=6)
            tk.Label(row, text=str(i), bg=T.ACCENT, fg="#FFFFFF", width=2,
                     font=T.ui_font(9, True)).pack(side="left", anchor="n", pady=2)
            box = tk.Frame(row, bg=T.CARD)
            box.pack(side="left", fill="x", expand=True, padx=10)
            tk.Label(box, text=title, bg=T.CARD, fg=T.TEXT, font=T.ui_font(10, True),
                     anchor="w").pack(fill="x")
            tk.Label(box, text=detail, bg=T.CARD, fg=T.MUTED, font=T.ui_font(9),
                     anchor="w", justify="left", wraplength=540).pack(fill="x", pady=(2, 0))
        tk.Label(self.body, text="开启后手机可能会提示「是否允许 USB 调试」，一定要点允许。",
                 bg=T.CARD, fg=T.DANGER, font=T.ui_font(9), anchor="w",
                 justify="left", wraplength=580).pack(fill="x", pady=(12, 0))

    def _check(self):
        self.btn_check.configure(state="disabled", text="检测中…")
        self.lbl_state.configure(text="")

        def work():
            import ad_runner
            ad_runner.ADB = self.app.adb_path
            try:
                devs = ad_runner.list_devices()
            except SystemExit:
                devs = []
            self.app.q.put(("guide_check", devs))

        import threading
        threading.Thread(target=work, daemon=True).start()

    def show_result(self, devs):
        self.btn_check.configure(state="normal", text="重新检测")
        if devs:
            self.lbl_state.configure(text=f"已连上 {devs[0]}", fg=T.OK)
            self.app.after(600, self.destroy)
            self.app.q.put(("guide_connected", devs[0]))
        else:
            self.lbl_state.configure(text="还没检测到，检查线 / USB 用途 / 允许弹窗", fg=T.DANGER)
