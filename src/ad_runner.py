#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
外星仔加速器（com.etalien.booster）「点广告 领时长」—— ADB 版循环器。

每轮：冷启动 App -> 点「点广告 领时长」-> 盯焦点组件（不读屏）-> 到点杀进程 -> 清后台 -> 下一轮。

为什么不是「盲等 20 秒就杀」：
  真机实测，发奖点在【点击 CTA 后 18-20 秒】（视频中段），17 秒杀会漏奖，
  20 秒杀能到账（2/2）。所以 20 秒是下限，不是余量。

为什么不用读屏找「关闭」：
  激励视频是 Surface 渲染，屏幕文本要么没有、要么是 stale 的假死文本；
  唯一可靠的信号是 `dumpsys window` 里的 mCurrentFocus（焦点组件名）：
    焦点离开 MainActivity  = 广告起来了
    焦点回到 MainActivity  = 广告结束，奖励状态已定

vivo / OriginOS 注意：
  部分 vivo 机型在系统层禁用了 `uiautomator dump`（静默失败，rc=0 但没输出）。
  先跑 `--selftest` 确认；不可用就用 `--cta-xy` 走坐标点击。

阶段识别：
    脚本会读主页上三个阶段各自的「X/Y」或「已完成」，算出今天还剩几条，只跑剩下的。
    比如阶段一 7/9、阶段二 0/3、加油包 2/9 → 还剩 2+3+7 = 12 条，跑完 12 轮就停，
    不会傻跑 21 轮。阶段跑完解锁下一阶段，所以「跳过」是自动的。

用法：
    python ad_runner.py --devices
    python ad_runner.py --selftest            # 三项自检：adb / 焦点 / dump
    python ad_runner.py --state               # 只看今天各阶段还剩多少条
    python ad_runner.py --probe               # 打开 App，打印这一屏的文字
    python ad_runner.py                       # 按剩余数自动跑完（默认）
    python ad_runner.py --rounds 7            # 最多跑 7 轮（剩余不足时以剩余为准）
    python ad_runner.py --targets 9,3,9       # 阶段一/二/加油包每日总额，默认 9,3,9

风险提示：自动播放激励广告可能违反该 App 用户协议，有封号/追回时长风险，仅限本人设备自用。
"""

import argparse
import os
import re
import subprocess
import sys
import time
import xml.etree.ElementTree as ET

ADB = "adb"

# GUI 打包成无控制台程序时，每次调 adb 都不能弹黑框
_NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0

# ---- 外星仔加速器的已知常量 ----
PKG = "com.etalien.booster"
CTA_TEXTS = ("点广告", "观看广告", "看广告")          # 主按钮文案「点广告 领时长」
MAIN_HINTS = ("MainActivity", "SplashActivity")      # 这两个算「在 App 主页/启动页」
DONE_TEXTS = ("明日再来", "已看完", "次数已用完", "已达上限")   # 当天领完的标志

BOUNDS_RE = re.compile(r"\[(-?\d+),(-?\d+)\]\[(-?\d+),(-?\d+)\]")
FOCUS_RE = re.compile(r"mCurrentFocus=Window\{[^}]*?([A-Za-z0-9_.]+)/([A-Za-z0-9_.$]+)\}")
FOCUS_APP_RE = re.compile(r"mFocusedApp=.*?([A-Za-z0-9_.]+)/([A-Za-z0-9_.$]+)")

# 最近任务里「清空」按钮的常见文案
CLEAR_WORDS = (
    "全部清除", "清除全部", "清除所有", "全部关闭", "关闭所有",
    "清理全部", "一键清理", "Clear all", "Clear All", "清除",
)

# ---- 三个阶段 & 各自的每日总额 ----
# 顺序就是 App 里的执行顺序：阶段一跑完才解锁阶段二，最后是加油包。
PHASE_NAMES = ("阶段一", "阶段二", "加油包")
DEFAULT_TARGETS = {"阶段一": 9, "阶段二": 3, "加油包": 9}
COUNT_RE = re.compile(r"(\d+)\s*/\s*(\d+)")

# GUI 可以注入：返回 (x, y) 的定位器 / 返回进度表的读取器（用于 OCR）
CTA_FINDER = None
PROGRESS_FINDER = None


# ---------------------------------------------------------------- adb
def adb(serial, *args, timeout=30):
    cmd = [ADB] + (["-s", serial] if serial else []) + list(args)
    try:
        p = subprocess.run(cmd, capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=timeout,
                           creationflags=_NO_WINDOW)
    except FileNotFoundError:
        sys.exit("找不到 adb：把 platform-tools 加进 PATH，或用 --adb 指定完整路径。")
    except subprocess.TimeoutExpired:
        return "", 124
    return (p.stdout or "").strip(), p.returncode


def list_devices():
    out, _ = adb(None, "devices")
    found = []
    for line in out.splitlines()[1:]:
        parts = line.split("\t")
        if len(parts) == 2 and parts[1].strip() == "device":
            found.append(parts[0].strip())
    return found


def screencap(serial, path):
    """截屏存成 PNG。不依赖 uiautomator，vivo 禁用读屏时也能用。

    adb 有时会在 PNG 前面多打一行警告（[Warning] Multiple displays...），
    所以落地后把 PNG 签名之前的内容剪掉，否则图片库读不出来。
    """
    cmd = [ADB] + (["-s", serial] if serial else []) + ["exec-out", "screencap", "-p"]
    try:
        with open(path, "wb") as f:
            p = subprocess.run(cmd, stdout=f, stderr=subprocess.DEVNULL,
                               creationflags=_NO_WINDOW, timeout=30)
        if p.returncode != 0:
            return False
        with open(path, "rb") as f:
            data = f.read()
        i = data.find(b"\x89PNG\r\n\x1a\n")
        if i < 0:
            return False
        if i > 0:
            with open(path, "wb") as f:
                f.write(data[i:])
            data = data[i:]
        return len(data) > 2000
    except Exception:
        return False


# ---------------------------------------------------------------- 无线调试
def mdns_services():
    """从 adb mdns services 里找配对端口和连接端口。返回 {"pair": ip:port, "connect": ip:port}"""
    out, _ = adb(None, "mdns", "services", timeout=20)
    found = {}
    for line in out.splitlines():
        low = line.lower()
        if "_adb-tls-pairing" in low and "pair" not in found:
            parts = line.split()
            if parts:
                found["pair"] = parts[-1]
        elif "_adb-tls-connect" in low and "connect" not in found:
            parts = line.split()
            if parts:
                found["connect"] = parts[-1]
    return found


def pair(addr, code):
    """adb pair <地址> <配对码>，返回 (是否成功, 输出)。"""
    out, rc = adb(None, "pair", addr, str(code), timeout=60)
    return ("Successfully paired" in out) or ("already paired" in out.lower()), out or ""


def connect(addr):
    """adb connect <地址>:<端口>，返回 (是否成功, 输出)。"""
    out, rc = adb(None, "connect", addr, timeout=30)
    low = out.lower()
    return ("connected to" in low or "already connected" in low), out or ""


def disconnect(addr):
    adb(None, "disconnect", addr, timeout=20)




# ---------------------------------------------------------------- 焦点探针
def short_activity(pkg, act):
    """com.etalien.booster/com.etalien.booster.ui.MainActivity -> ui.MainActivity"""
    act = act.split("/")[-1]
    if act.startswith("."):
        act = pkg + act
    if act.startswith(pkg + "."):
        act = act[len(pkg) + 1:]
    return act


def focus(serial):
    """返回 (包名, 短 Activity 名)。广告的 Activity 归本包，但名字不是 MainActivity。"""
    out, _ = adb(serial, "shell", "dumpsys", "window", timeout=15)
    m = FOCUS_RE.search(out) or FOCUS_APP_RE.search(out)
    if not m:
        return "", ""
    pkg, act = m.group(1), m.group(2)
    return pkg, short_activity(pkg, act)


def is_main(pkg, act):
    return pkg == PKG and act.endswith(MAIN_HINTS)


# ---------------------------------------------------------------- 读屏（可能不可用）
def dump(serial):
    for _ in range(2):
        adb(serial, "shell", "uiautomator", "dump", "--compressed",
            "/sdcard/ad_runner_ui.xml", timeout=25)
        xml, _ = adb(serial, "shell", "cat", "/sdcard/ad_runner_ui.xml", timeout=25)
        if "<hierarchy" in xml:
            adb(serial, "shell", "rm", "-f", "/sdcard/ad_runner_ui.xml")
            return xml
        time.sleep(0.6)
    return ""


def parse(xml):
    if not xml:
        return []
    try:
        root = ET.fromstring(xml)
    except ET.ParseError:
        return []
    rows = []
    for node in root.iter("node"):
        m = BOUNDS_RE.match(node.get("bounds") or "")
        if not m:
            continue
        x1, y1, x2, y2 = map(int, m.groups())
        rows.append({
            "text": (node.get("text") or "").strip(),
            "desc": (node.get("content-desc") or "").strip(),
            "clickable": node.get("clickable") == "true",
            "cx": (x1 + x2) // 2,
            "cy": (y1 + y2) // 2,
        })
    return rows


def find(rows, *words):
    for row in rows:
        for w in words:
            if w and (w in row["text"] or w in row["desc"]):
                return row
    return None


# ---------------------------------------------------------------- 进度识别
def parse_progress(xml):
    """从主页 dump 里读出三个阶段各自领了几条。

    返回 {阶段名: {"done": bool, "locked": bool, "cur": int|None, "total": int|None}}。
    归属按相邻标题的中点切分；「待解锁」表示本轮还不能领。
    """
    rows = [r for r in parse(xml) if (r["text"] or r["desc"])]
    if not rows:
        return {}

    marks = []
    for r in rows:
        t = (r["text"] or r["desc"]).strip()
        for name in PHASE_NAMES:
            if (t == name or t.startswith(name)) and not any(m[1] == name for m in marks):
                marks.append((r["cy"], name))
                break
    if not marks:
        return {}
    marks.sort()

    out = {}
    for i, (y, name) in enumerate(marks):
        lo = (marks[i - 1][0] + y) // 2 if i > 0 else -1
        hi = (y + marks[i + 1][0]) // 2 if i + 1 < len(marks) else 10 ** 9
        info = {"done": False, "locked": False, "cur": None, "total": None}
        for r in rows:
            if not (lo <= r["cy"] < hi):
                continue
            t = r["text"] or r["desc"]
            if "已完成" in t:
                info["done"] = True
            if "待解锁" in t or "未解锁" in t:
                info["locked"] = True
            m = COUNT_RE.search(t)
            if m and info["cur"] is None:
                info["cur"], info["total"] = int(m.group(1)), int(m.group(2))
        out[name] = info
    return out


def remaining_now(prog, targets):
    """本轮还能领几条。

    三个阶段是顺序解锁的，所以只看「第一个没完成的阶段」还剩多少；
    已完成的跳过，返回 0 表示今天确实没得领了。
    """
    for name in PHASE_NAMES:
        info = prog.get(name)
        if not info:
            continue
        if info.get("done"):
            continue
        total = info.get("total") or targets.get(name, 0)
        if info.get("cur") is not None:
            return max(0, total - info["cur"])
        if info.get("locked"):
            return 0
        return None
    return 0


def progress_line(prog, targets):
    """一行摘要 + 本轮还能领几条（读不出时返回 None）。"""
    parts = []
    for name in PHASE_NAMES:
        info = prog.get(name)
        if not info:
            parts.append(f"{name} ?")
            continue
        total = info["total"] or targets.get(name, 0)
        if info["done"]:
            cur = info["cur"] if info["cur"] is not None else total
            parts.append(f"{name} {cur}/{total}✓")
        elif info.get("locked"):
            parts.append(f"{name} 待解锁")
        elif info["cur"] is not None:
            parts.append(f"{name} {info['cur']}/{total}(剩{total - info['cur']})")
        else:
            parts.append(f"{name} ?")
    return " | ".join(parts), remaining_now(prog, targets)


def progress_table(prog, targets):
    lines = []
    for name in PHASE_NAMES:
        info = prog.get(name)
        if not info:
            lines.append(f"  {name}  页面上没找到")
            continue
        total = info["total"] or targets.get(name, 0)
        if info["done"]:
            cur = info["cur"] if info["cur"] is not None else total
            lines.append(f"  {name}  {cur}/{total}  已完成")
        elif info.get("locked"):
            lines.append(f"  {name}  待解锁")
        elif info["cur"] is not None:
            lines.append(f"  {name}  {info['cur']}/{total}  还剩 {total - info['cur']}")
        else:
            lines.append(f"  {name}  读不出进度")
    return "\n".join(lines), remaining_now(prog, targets)


def read_progress(serial):
    xml = dump(serial)
    return parse_progress(xml) if xml else {}


def counts_of(prog):
    return {n: (prog.get(n) or {}).get("cur") for n in PHASE_NAMES}


# ---------------------------------------------------------------- 动作
def tap(serial, x, y):
    adb(serial, "shell", "input", "tap", str(int(x)), str(int(y)))


def keyevent(serial, code):
    adb(serial, "shell", "input", "keyevent", str(code))


def launch(serial):
    """冷启动：先 force-stop，再起。热启动会留下卡死的广告 Activity。"""
    adb(serial, "shell", "am", "force-stop", PKG)
    time.sleep(0.5)
    out, rc = adb(serial, "shell", "monkey", "-p", PKG,
                  "-c", "android.intent.category.LAUNCHER", "1", timeout=60)
    if rc == 0 and "No activities found" not in out:
        return True
    out2, _ = adb(serial, "shell", "cmd", "package", "resolve-activity",
                  "--brief", "-c", "android.intent.category.LAUNCHER", PKG)
    for line in out2.splitlines():
        line = line.strip()
        if "/" in line and not line.startswith("priority"):
            adb(serial, "shell", "am", "start", "-n", line)
            return True
    return False


def clear_recents(serial):
    keyevent(serial, 187)          # KEYCODE_APP_SWITCH
    time.sleep(1.2)
    hit = find(parse(dump(serial)), *CLEAR_WORDS)
    if hit:
        tap(serial, hit["cx"], hit["cy"])
        time.sleep(0.6)
        print("  已清空最近任务")
    else:
        print("  没找到「全部清除」，只回到桌面")
    keyevent(serial, 3)            # KEYCODE_HOME


# ---------------------------------------------------------------- 主流程
def wait_main(serial, timeout=25):
    """等 App 回到主页；顺带处理「广告加载失败，点击重试」和登录页。"""
    deadline = time.time() + timeout
    while time.time() < deadline:
        pkg, act = focus(serial)
        if is_main(pkg, act):
            return True
        time.sleep(0.5)
    return False


def tap_cta(serial, cta_xy):
    """优先按文字找「点广告」，找不到就用坐标兜底（vivo 禁 dump 时）。"""
    rows = parse(dump(serial))
    hit = find(rows, *CTA_TEXTS)
    if hit:
        tap(serial, hit["cx"], hit["cy"])
        print(f"  点了「{hit['text']}」({hit['cx']},{hit['cy']})")
        return True
    if CTA_FINDER is not None:
        pos = CTA_FINDER(serial)
        if pos:
            tap(serial, *pos)
            print(f"  OCR 定位到「点广告」({pos[0]},{pos[1]})")
            return True
    if cta_xy:
        tap(serial, *cta_xy)
        print(f"  文字没找到，按坐标点 ({cta_xy[0]},{cta_xy[1]})")
        return True
    print("  找不到「点广告」按钮：dump 可能被 ROM 禁用，或页面还没加载好。")
    return False


def watch(serial, seconds, early_min=15.0, poll=0.3, stop=None):
    """点完 CTA 后调用：等到发奖点。返回 (广告是否真的起来过, 用时)。"""
    t0 = time.time()
    ad_start = None
    jumped = set()
    while True:
        if stop is not None and stop.is_set():
            break
        now = time.time()
        elapsed = now - t0
        if elapsed >= seconds:
            break
        pkg, act = focus(serial)

        # 广告 deeplink：前台被别的 App 抢走 → 立刻退回去，别让广告中断
        if pkg and pkg not in (PKG, "com.android.systemui"):
            if pkg not in jumped:
                print(f"  拦截跳转：{pkg}")
                jumped.add(pkg)
            keyevent(serial, 4)
            time.sleep(0.8)
            pkg2, _ = focus(serial)
            if pkg2 == pkg and len(jumped) <= 6:
                adb(serial, "shell", "am", "force-stop", pkg)
                time.sleep(0.5)
            continue
        if pkg == PKG and not act.endswith(MAIN_HINTS):
            if ad_start is None:
                ad_start = now
                print(f"  广告已起来：{act}（+{elapsed:.1f}s）")
        else:
            # 广告自己关了：只要已经过了 early_min，就认为发奖点已过
            if ad_start and elapsed >= early_min:
                print(f"  广告自己关了（+{elapsed:.1f}s），提前收工")
                break
        time.sleep(poll)
    return ad_start is not None, time.time() - t0


def one_round(serial, seconds, cta_xy, clear, settle, targets, stop=None,
              cold_start=True, keep=False):
    """跑一条广告。返回 (状态, 进度, 剩余)，状态是 ok / done / fail。"""
    keyevent(serial, 224)          # KEYCODE_WAKEUP
    if cold_start:
        if not launch(serial):
            print("  启动失败：包名/安装对吗？")
            return "fail", {}, None
        if not wait_main(serial, 25):
            pkg, act = focus(serial)
            print(f"  25 秒还没回到主页（当前 {pkg}/{act}），这轮跳过")
            return "fail", {}, None
    else:
        pkg, act = focus(serial)
        if pkg and pkg not in (PKG, "com.android.systemui"):
            print(f"  前台是 {pkg}，先清掉再回到外星仔")
            adb(serial, "shell", "am", "force-stop", pkg)
            time.sleep(0.5)
            adb(serial, "shell", "am", "start", "-n",
                f"{PKG}/com.etalien.booster.ui.MainActivity")
            time.sleep(2.0)
        elif pkg == PKG and not act.endswith(MAIN_HINTS):
            keyevent(serial, 4)
            time.sleep(1.0)
        print("  复用当前页面（不重启 App）")

    xml = dump(serial)
    rows = parse(xml)
    prog = parse_progress(xml)
    if not prog and PROGRESS_FINDER is not None:
        prog = PROGRESS_FINDER(serial) or {}
    remain = None
    if prog:
        line, remain = progress_line(prog, targets)
        print(f"  进度：{line}")

    # 三条路都判「今天领完了」：页面写「明日再来」、或三个阶段都没剩余了
    page = find(rows, *DONE_TEXTS)
    if page or remain == 0:
        why = f"页面显示「{page['text']}」" if page else "三个阶段都没有剩余"
        print(f"  今天领完了（{why}）。")
        return "done", prog, 0

    if not tap_cta(serial, cta_xy):
        return "fail", prog, remain

    seen, used = watch(serial, seconds, stop=stop)
    if not seen:
        if stop is not None and stop.is_set():
            print("  已停止。")
            return "fail", prog, remain
        print(f"  等了 {used:.1f}s 没看到广告 Activity —— CTA 可能没点中，这轮不算。")
        return "fail", prog, remain

    time.sleep(settle)             # 发奖后落账
    if keep:
        keyevent(serial, 4)
        time.sleep(1.2)
        pkg, act = focus(serial)
        if pkg == PKG and not act.endswith(MAIN_HINTS):
            keyevent(serial, 4)
            time.sleep(0.8)
            pkg, act = focus(serial)
        if pkg == PKG and act.endswith(MAIN_HINTS):
            print(f"  已退出广告，回到主页（约 {used + settle:.1f}s）")
        else:
            adb(serial, "shell", "am", "force-stop", PKG)
            print("  退不回主页，强停兜底")
    else:
        adb(serial, "shell", "am", "force-stop", PKG)
        print(f"  已强停（点击后约 {used + settle:.1f}s）")
        if clear:
            clear_recents(serial)
    return "ok", prog, remain


def probe(serial):
    launch(serial)
    time.sleep(5)
    rows = parse(dump(serial))
    if not rows:
        print("读不到界面：uiautomator dump 不可用（vivo/OriginOS 常见）。")
        print("→ 改用 --cta-xy 坐标点击，或装 mobilecli 当读屏后端。")
        return
    print(f"这一屏 {len(rows)} 个节点，带文字的有：")
    for row in rows:
        t = row["text"] or row["desc"]
        if t:
            mark = "★可点" if row["clickable"] else "    "
            print(f"  {mark} ({row['cx']:4d},{row['cy']:4d})  {t}")


def selftest(serial):
    print("[1/3] adb 连接")
    out, _ = adb(serial, "shell", "echo", "ok")
    print("    ", out or "无输出 —— 检查 USB 调试授权")

    print("[2/3] 焦点探针")
    pkg, act = focus(serial)
    print(f"     {pkg or '?'} / {act or '?'}")
    if not pkg:
        print("     读不到 mCurrentFocus —— 解锁屏幕后再试")

    print("[3/3] uiautomator dump")
    xml = dump(serial)
    if xml:
        print(f"     可用：{len(parse(xml))} 个节点")
    else:
        print("     不可用。vivo/OriginOS 有机型在系统层禁用它（rc=0 但没输出）。")
        print("     → 走 --cta-xy 坐标模式，或换 mobilecli 后端。")


def main():
    global ADB, PKG

    ap = argparse.ArgumentParser(description="外星仔加速器「点广告领时长」循环器")
    ap.add_argument("-p", "--package", default=PKG, help=f"包名，默认 {PKG}")
    ap.add_argument("-s", "--serial", help="设备序列号（只连一台可省略）")
    ap.add_argument("--adb", default="adb", help="adb 可执行文件路径")
    ap.add_argument("--devices", action="store_true", help="列出已连接设备")
    ap.add_argument("--selftest", action="store_true", help="三项自检：adb / 焦点 / dump")
    ap.add_argument("--probe", action="store_true", help="打开 App 并打印屏幕文字")
    ap.add_argument("--seconds", type=float, default=20.0,
                    help="点击 CTA 后等多少秒再杀，默认 20（实测发奖点 18-20s，别更低）")
    ap.add_argument("--settle", type=float, default=2.0, help="发奖后落账等待，默认 2s")
    ap.add_argument("--rounds", type=int, default=0,
                    help="最多跑几轮；0（默认）= 按页面上剩余的条数自动跑")
    ap.add_argument("--targets", default="9,3,9",
                    help="阶段一/阶段二/加油包的每日总额，默认 9,3,9")
    ap.add_argument("--state", action="store_true", help="只打印当前各阶段进度，不点广告")
    ap.add_argument("--interval", type=float, default=2.0, help="两轮间隔秒数")
    ap.add_argument("--cta-xy", default="", help="dump 不可用时「点广告」按钮坐标，如 630,2204")
    ap.add_argument("--no-clear", action="store_true", help="不清最近任务")
    args = ap.parse_args()

    ADB = args.adb

    if args.devices:
        devs = list_devices()
        print("已连接设备：" if devs else "没有设备：检查数据线、USB 调试授权弹窗。")
        for d in devs:
            print(" ", d)
        return

    serial = args.serial
    if not serial:
        devs = list_devices()
        if not devs:
            sys.exit("没有设备：检查数据线、USB 调试授权弹窗。")
        if len(devs) > 1:
            sys.exit(f"连了多台设备，用 -s 指定一台：{', '.join(devs)}")
        serial = devs[0]

    PKG = args.package
    print(f"设备 {serial}，目标 {PKG}")

    if args.selftest:
        selftest(serial)
        return
    if args.probe:
        probe(serial)
        return

    parts = [int(x) for x in args.targets.split(",") if x.strip()]
    if len(parts) != 3:
        sys.exit("--targets 要三个数，例如 9,3,9")
    targets = dict(zip(PHASE_NAMES, parts))

    if args.state:
        launch(serial)
        if not wait_main(serial, 25):
            sys.exit("打不开 App 主页：确认已登录、没停在别的页面。")
        prog = read_progress(serial)
        if not prog:
            sys.exit("读不到页面（uiautomator dump 不可用），进度只能自己数。")
        table, remain = progress_table(prog, targets)
        print(table)
        print(f"合计还剩 {remain} 条")
        return

    cta_xy = None
    if args.cta_xy:
        x, y = args.cta_xy.split(",")
        cta_xy = (int(x), int(y))

    done = 0
    prev_counts = None

    # 开工前先读一次进度：今天还剩几条，就只跑几条
    launch(serial)
    plan = None
    if wait_main(serial, 25):
        prog0 = read_progress(serial)
        if prog0:
            table, plan = progress_table(prog0, targets)
            print(table)
            if plan:
                print(f"今天还剩 {plan} 条，开始。")
    if plan is None:
        if not args.rounds:
            sys.exit("读不出剩余条数（dump 不可用或页面不在主页），请用 --rounds N 指定跑几条。")
        plan = args.rounds
    if args.rounds:
        plan = min(plan, args.rounds)
    if plan <= 0:
        print("今天已经领完了，不用跑。")
        return

    try:
        while done < plan:
            done += 1
            print(f"第 {done}/{plan} 轮")
            t0 = time.time()
            status, prog, remain = one_round(
                serial, args.seconds, cta_xy, not args.no_clear, args.settle, targets)
            print(f"  用时 {time.time() - t0:.1f}s")

            if status == "done":
                print("今天领完了，停。")
                break
            if status == "fail":
                print(f"第 {done} 轮失败，先停。已领的不会重复算，处理完再重跑。")
                break

            # 阶段计数涨没涨，是这条有没有真到账最直接的证据
            if prog:
                cur = counts_of(prog)
                if prev_counts is not None and cur == prev_counts:
                    print("  注意：阶段计数没变，上一条可能没到账。")
                prev_counts = cur

            if remain is not None and remain <= 1:
                print("  这是最后一条，下一轮会确认收尾。")
            time.sleep(args.interval)
    except KeyboardInterrupt:
        print("\n手动停止。")
    print(f"跑了 {done} 轮。")

    # 收尾再读一次页面，确认是不是真的领完
    launch(serial)
    if wait_main(serial, 20):
        prog = read_progress(serial)
        if prog:
            table, remain = progress_table(prog, targets)
            print("收尾确认：")
            print(table)
            print("全部完成。" if remain == 0 else f"还剩 {remain} 条，再跑一次接着领。")


if __name__ == "__main__":
    main()
