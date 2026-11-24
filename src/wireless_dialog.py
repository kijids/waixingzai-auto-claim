# -*- coding: utf-8 -*-
"""无线调试配对窗口：用电脑执行 adb pair，之后拔线也能跑。"""

import threading
import tkinter as tk
from tkinter import messagebox, ttk

import ad_runner
import gui_theme as T


class WirelessDialog(tk.Toplevel):
    def __init__(self, app):
        super().__init__(app)
        self.app = app
        self.title("无线连接（免数据线）")
        self.configure(bg=T.BG)
        self.resizable(False, False)
        self.transient(app)
        self.grab_set()

        self.update_idletasks()
        w, h = 700, 470
        px, py = app.winfo_rootx(), app.winfo_rooty()
        cx = px + max(0, (app.winfo_width() - w) // 2)
        cy = py + max(0, (app.winfo_height() - h) // 2)
        self.geometry("%dx%d+%d+%d" % (w, h, cx, cy))

        head = tk.Frame(self, bg=T.BG)
        head.pack(fill="x", padx=24, pady=(20, 0))
        tk.Label(head, text="无线连接", bg=T.BG, fg=T.TEXT, font=T.ui_font(17, True),
                 anchor="w").pack(anchor="w")
        tk.Label(head, text="电脑代替你完成 adb 配对，配好就能拔线。不用装 Shizuku。",
                 bg=T.BG, fg=T.MUTED, font=T.ui_font(9), anchor="w").pack(anchor="w", pady=(4, 0))

        card = tk.Frame(self, bg=T.CARD)
        card.pack(fill="both", expand=True, padx=24, pady=(12, 0))

        steps = [
            ("手机先开无线调试",
             "设置 → 系统管理 → 开发者选项 → 无线调试（打开）"),
            ("点「使用配对码配对设备」",
             "手机会弹窗显示 6 位配对码，下面还写着「IP 地址和端口」"),
            ("把配对码填到这里",
             "配对端口和连接端口一般能自动发现；发现不了就手填"),
        ]
        for i, (t1, t2) in enumerate(steps, 1):
            row = tk.Frame(card, bg=T.CARD)
            row.pack(fill="x", padx=18, pady=(12 if i == 1 else 6, 0))
            tk.Label(row, text=str(i), bg=T.ACCENT, fg="#FFFFFF", width=2,
                     font=T.ui_font(9, True)).pack(side="left", anchor="n", pady=2)
            box = tk.Frame(row, bg=T.CARD)
            box.pack(side="left", fill="x", expand=True, padx=10)
            tk.Label(box, text=t1, bg=T.CARD, fg=T.TEXT, font=T.ui_font(10, True),
                     anchor="w").pack(fill="x")
            tk.Label(box, text=t2, bg=T.CARD, fg=T.MUTED, font=T.ui_font(9),
                     anchor="w", justify="left", wraplength=540).pack(fill="x")

        form = tk.Frame(card, bg=T.CARD)
        form.pack(fill="x", padx=18, pady=(16, 0))

        tk.Label(form, text="配对码", bg=T.CARD, fg=T.TEXT, font=T.ui_font(9)).grid(
            row=0, column=0, sticky="w")
        self.var_code = tk.StringVar()
        tk.Entry(form, textvariable=self.var_code, width=10, font=T.ui_font(11),
                 relief="flat", bg="#FAFAFD", highlightthickness=1,
                 highlightbackground=T.LINE).grid(row=1, column=0, sticky="w", pady=(2, 10))

        tk.Label(form, text="配对端口/地址（可留空自动发现）", bg=T.CARD, fg=T.TEXT,
                 font=T.ui_font(9)).grid(row=0, column=1, sticky="w", padx=(18, 0))
        self.var_pair = tk.StringVar()
        tk.Entry(form, textvariable=self.var_pair, width=26, font=T.ui_font(10),
                 relief="flat", bg="#FAFAFD", highlightthickness=1,
                 highlightbackground=T.LINE).grid(row=1, column=1, sticky="w",
                                                  padx=(18, 0), pady=(2, 10))

        tk.Label(form, text="连接端口/地址（可留空自动发现）", bg=T.CARD, fg=T.TEXT,
                 font=T.ui_font(9)).grid(row=2, column=0, columnspan=2, sticky="w")
        self.var_conn = tk.StringVar()
        tk.Entry(form, textvariable=self.var_conn, width=26, font=T.ui_font(10),
                 relief="flat", bg="#FAFAFD", highlightthickness=1,
                 highlightbackground=T.LINE).grid(row=3, column=0, columnspan=2,
                                                  sticky="w", pady=(2, 6))

        bar = tk.Frame(card, bg=T.CARD)
        bar.pack(side="bottom", fill="x", padx=18, pady=(8, 16))
        self.btn_go = tk.Button(bar, text="配对并连接", command=self.start,
                                bg=T.ACCENT, fg="#FFFFFF", relief="flat", bd=0,
                                font=T.ui_font(10, True), padx=20, pady=8,
                                activebackground=T.ACCENT_DARK, activeforeground="#FFFFFF",
                                cursor="hand2")
        self.btn_go.pack(side="left")
        self.lbl = tk.Label(bar, text="", bg=T.CARD, fg=T.MUTED, font=T.ui_font(9),
                            anchor="w", justify="left", wraplength=420)
        self.lbl.pack(side="left", padx=12)
        tk.Button(bar, text="关闭", command=self.destroy, bg=T.CARD, fg=T.MUTED,
                  relief="flat", bd=0, font=T.ui_font(9), padx=16, pady=7,
                  activebackground="#F0F1F7", cursor="hand2",
                  highlightthickness=1, highlightbackground=T.LINE).pack(side="right")

    # ------------------------------------------------------------ 流程
    def start(self):
        code = self.var_code.get().strip()
        if not code:
            messagebox.showwarning("无线连接", "先填 6 位配对码。")
            return
        self.btn_go.configure(state="disabled", text="连接中…")
        self.set("正在执行 adb pair…")
        threading.Thread(target=self.work, args=(code,), daemon=True).start()

    def work(self, code):
        ad_runner.ADB = self.app.adb_path
        pair_addr = self.var_pair.get().strip()
        conn_addr = self.var_conn.get().strip()

        if not pair_addr or not conn_addr:
            found = ad_runner.mdns_services()
            pair_addr = pair_addr or found.get("pair", "")
            conn_addr = conn_addr or found.get("connect", "")

        if not pair_addr:
            self.done(False, "没自动发现配对端口。到手机「无线调试」页看一下\n"
                             "弹窗上写的 IP:端口，填到「配对端口」里再试。")
            return

        ok, out = ad_runner.pair(pair_addr, code)
        if not ok:
            self.done(False, "配对失败：" + (out.strip() or "没有输出") +
                      "\n配对码过期就重新点一次「使用配对码配对设备」。")
            return

        if not conn_addr:
            found = ad_runner.mdns_services()
            conn_addr = found.get("connect", "")
        if not conn_addr:
            self.done(False, "配对成功，但没发现连接端口。\n"
                             "把手机「无线调试」页上那个 IP:端口 填到「连接端口」再点一次。")
            return

        ok, out = ad_runner.connect(conn_addr)
        if not ok or "connected" not in out.lower():
            self.done(False, "配对成功，连接失败：" + (out.strip() or "没有输出"))
            return

        devs = ad_runner.list_devices()
        if not devs:
            self.done(False, "已连接但设备列表还是空，稍等两秒重试。")
            return
        self.done(True, f"已连上 {conn_addr}", devs[0])

    def done(self, ok, msg, serial=None):
        def apply():
            self.btn_go.configure(state="normal", text="配对并连接")
            self.set(msg, ok)
            if ok and serial:
                self.app.q.put(("wireless_ok", serial))
                self.after(700, self.destroy)
        self.after(0, apply)

    def set(self, text, ok=False):
        self.lbl.configure(text=text, fg=T.OK if ok else T.DANGER)
