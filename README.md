# 外星仔领时长（桌面助手）

[![CI](https://github.com/USER/REPO/actions/workflows/ci.yml/badge.svg)](https://github.com/USER/REPO/actions/workflows/ci.yml)

> 把上面的 `USER/REPO` 换成你的仓库地址即可显示构建状态。

Windows 上的小工具：电脑通过 USB 或无线调试控制手机，自动完成外星仔加速器
「点广告 领时长」的每日任务。

- 五步向导：连接手机 → 检测 → 选择 → 执行 → 完成
- 读屏两种方式：手机的 `uiautomator`（能用的机型优先）或 **Windows 自带 OCR**（vivo 等禁用了 uiautomator 的机型）
- 坐标实时识别，不写死机型/分辨率
- 每轮验收：跑完重开 App 截图对比计数，没涨自动补跑
- 广告跳转拦截：被 deeplink 抢走前台时自动按 BACK 拉回来

> ⚠️ 自动播放激励广告大概率违反外星仔加速器的用户协议，存在封号、追回时长的风险。
> 本项目仅供个人在自己设备上学习研究，**不要用于代领、批量账号或任何营利场景**。

## 下载（免安装）
不想装 Python 的话，直接去 [Releases](https://github.com/kijids/waixingzai-auto-claim/releases/latest)
下载 `外星仔领时长-v1.9.2-win64.zip`，解压后双击 `外星仔领时长.exe`。
内置 adb，不用额外配置；首次运行可能被 SmartScreen 拦截，右键 → 属性 → 解除锁定。


## 快速开始

在AI的帮助下我完成了这个小工具，只是这个还是会跳转广告，所以有没有大佬能告诉我，怎么才能不看广告／或者在看广告的时候让它没有任何权限，使其不会自动跳转到广告商平台，或者就是让它黑屏到时间了就退出，求大佬指点啊



1. 装 [Python 3.10+](https://www.python.org/downloads/)（安装时勾选 *Add python.exe to PATH*）
2. 双击 **setup.bat** —— 下载 adb 和 OCR 运行库（两者都不进仓库）
3. 手机：开发者选项 → 打开「USB 调试」，插线，选「传输文件(MTP)」，允许调试
4. 双击 **run.bat** 启动


也可以命令行跑：

```bash
python tools/setup.py          # 下 adb + OCR
python src/gui.py              # 启动界面
```

## 目录

```
src/
  gui.py             界面（tkinter，五步向导）
  ad_runner.py       引擎：启动/点击/焦点探针/强停/进度解析
  ocr_reader.py      Windows OCR 读屏（替代 uiautomator）
  gui_theme.py       配色与字体
  usb_guide.py       「开启 USB 调试」引导
  wireless_dialog.py 无线调试配对（adb pair）
tools/
  setup.py           下载 adb 与 OCR 运行库
docs/                界面截图
tests/
  test_core.py       进度解析 / 锁定判断 / 按钮定位的单元测试（不连手机）
.github/workflows/
  ci.yml             每次 push：语法检查 + 单元测试 + 导入冒烟
  build.yml          打 tag 或手动触发：PyInstaller 打 exe 并上传 artifact
```

运行时会在 `src/` 旁边生成 `_shot.png`、`_selftest.txt` 之类的临时文件，已在 `.gitignore` 里。

## 测试与 CI

本地跑单元测试（不需要手机、不需要界面）：

```bash
python -m unittest discover -s tests -v
```

覆盖的是纯逻辑：阶段进度解析、「待解锁」判断、剩余条数计算、按钮定位（含误标标题行的情况）。

GitHub Actions 已配好两个：

| workflow | 触发 | 做什么 |
|---|---|---|
| `ci.yml` | push / PR / 手动 | 语法检查、单元测试、下载依赖后做导入冒烟（Python 3.10 与 3.12 两档） |
| `build.yml` | 打 `v*` tag / 手动 | PyInstaller 打包，产物作为 artifact 上传（不自动发 Release） |

要自动发 Release，在 `build.yml` 末尾加一步 `softprops/action-gh-release`，把 `dist/AlienTimer` 压成 zip 传上去。

## 打包成 exe

需要 PyInstaller：

```powershell
python -m pip install pyinstaller
python tools\setup.py
python -m PyInstaller --noconfirm --windowed --name "外星仔领时长" ^
  --icon src\app.ico --add-data "src\app.ico;." --paths src ^
  --add-binary "src\adb.exe;." --add-binary "src\AdbWinApi.dll;." --add-binary "src\AdbWinUsbApi.dll;." ^
  --hidden-import uuid --hidden-import winreg --hidden-import typing_extensions ^
  --distpath dist --workpath build --specpath build src\gui.py
```

打包后把 `vendor\ocr\winrt` 复制到 `dist\外星仔领时长\_internal\ocr\winrt`，OCR 才会生效。

## 兼容性

| 项 | 说明 |
|---|---|
| 系统 | Windows 10 / 11，64 位 |
| 手机 | Android 8.0 及以上，开 USB 调试或无线调试 |
| 读屏 | 能用 uiautomator 的走原生；被 ROM 禁用的（部分 vivo/OriginOS）走 Windows OCR |
| OCR 语言包 | 需要系统装有中文 OCR（中文 Windows 默认自带）。`--selftest` 里看 `ocr available` |
| 分辨率 | 不用适配：每轮截图按当前屏幕实时算坐标 |

## 已知限制

- 程序未签名，首次运行会被 SmartScreen 拦一下：右键 → 属性 → 解除锁定
- 广告 SDK 的计数要在 App 重启后才刷新，所以「验收」那一步会重开一次 App
- 没有自动更新，换版本直接覆盖

## 许可

MIT，见 [LICENSE](LICENSE)。仓库不含 Google 的 adb 二进制与第三方 wheel，均由 `setup.bat` 在本地下载。
