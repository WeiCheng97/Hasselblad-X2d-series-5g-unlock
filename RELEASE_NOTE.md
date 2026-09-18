# Release Notes

**[English](#english)** | [中文](#中文)

---

## 中文

# v1.1.0 — 支持 907X & CFV 100C 🎉

哈苏 X2D / X2D II / 907 WiFi 地区设置工具：解除日版相机的 5GHz WiFi 限制，完全本地运行，不刷机、不改固件、随时可逆。

> **本工具完全免费开源，任何收费行为皆为倒卖。**

## 本版更新

- ✅ **新增支持 Hasselblad 907X & CFV 100C**（社区实测固件 v4.0.0；热点名形如 `CFV 100C xxxxxx`）。感谢 [@hugo00618](https://github.com/hugo00618) 实测并反馈
- ✅ Mac 版热点自动识别兼容 `CFV …` 命名（此前版本扫描过滤已兼容，本版补齐全部界面文案与文档）
- ✅ 界面标题、热点名示例、全部文档同步为三机型（X2D / X2D II / 907）
- 📦 **成品改到 GitHub Releases 分发**，源码仓库不再内置二进制

## 下载

| 文件 | 平台 | SHA256 |
|---|---|---|
| `X2D_WiFi_Region_mac.zip` | macOS 12+（Intel / Apple Silicon） | `b7ea2bb2c664b2f7fa26866ce81682b8d7776be10134e7ab30f11064505b5d3f` |
| `X2D_WiFi_Region_win.exe` | Windows 10/11 x64 | `cee2d70a2a631983acc504746b826be74e22e2c96d4776db2715a5d057c257c5` |
| `X2D_WiFi_Region_mac.command` | macOS（无需安装任何依赖） | `db111d5d64bf59be36460c33b7d69447136ab25fbfc49d02296c0121f4be00c7` |

## 快速上手

1. 相机打开 WiFi 热点（菜单 → WiFi → 热点；密码显示在相机 WiFi 界面）
2. 电脑连上该热点（GUI 会自动识别热点名；首次输密码后本机记住）
3. 点「设为 CN 解锁 5GHz」→ 相机自动重启 → 完成

## 注意

- ⚠️ **Windows 版 GUI 未经真机测试**；如遇问题请改用 Python 脚本（`python3 src/x2d_wifi_region.py --set 6 --reboot`），跨平台零依赖
- macOS 首次打开未签名 app：右键 → 打开，或「隐私与安全性」里允许
- macOS 首次运行会请求"本地网络"与"位置"权限（扫描相机热点所需），允许即可
- 实测机型：X2D 100C（v4.2.0）、X2D II 100C（v1.3.16.2）、907X & CFV 100C（v4.0.0，社区实测）

**完整文档**：[README.md](README.md)（中文）/ [README_EN.md](README_EN.md)（English）/ [使用说明与问题指南.md](使用说明与问题指南.md)

<details>
<summary>v1.0.0 — 首次发布（历史）</summary>

- 三端三形态：Mac GUI（universal 双架构）、Windows GUI（单文件）、macOS 双击极简版（系统自带 Perl）、跨平台 Python 命令行
- 完全本地：无服务器、无授权码、无配额、无遥测
- 中英双语：界面默认跟随系统语言，右上角一键切换；README 中英对照
- 自动体验：热点名自动扫描进下拉、密码输一次本机永记、写入后相机自动重启、执行后自动切回日常网络
- 协议全公开：帧格式 / 通道 / 地区值 / 重启命令全部文档化，三种实现逐字节交叉验证一致

</details>

---

## English

# v1.1.0 — 907X & CFV 100C Support 🎉

WiFi region tool for Hasselblad X2D / X2D II / 907: lift the 5GHz restriction on Japanese-region cameras. Fully local, no flashing, no firmware changes, fully reversible.

> **Free and open source — anyone charging for it is reselling.**

## What's New

- ✅ **Added support for Hasselblad 907X & CFV 100C** (community-tested on firmware v4.0.0; hotspot name looks like `CFV 100C xxxxxx`). Thanks to [@hugo00618](https://github.com/hugo00618) for testing and reporting
- ✅ Mac hotspot auto-detection works with `CFV …` names (the scan filter already matched; this release updates all UI text and docs)
- ✅ Titles, SSID examples and docs updated for all three models (X2D / X2D II / 907)
- 📦 **Binaries now ship via GitHub Releases** instead of living in the source repo

## Downloads

| File | Platform | SHA256 |
|---|---|---|
| `X2D_WiFi_Region_mac.zip` | macOS 12+ (Intel / Apple Silicon) | `b7ea2bb2c664b2f7fa26866ce81682b8d7776be10134e7ab30f11064505b5d3f` |
| `X2D_WiFi_Region_win.exe` | Windows 10/11 x64 | `cee2d70a2a631983acc504746b826be74e22e2c96d4776db2715a5d057c257c5` |
| `X2D_WiFi_Region_mac.command` | macOS (zero dependencies) | `db111d5d64bf59be36460c33b7d69447136ab25fbfc49d02296c0121f4be00c7` |

## Quick Start

1. Open the WiFi hotspot on the camera (menu → WiFi → Hotspot; password shown on the camera screen)
2. Connect your computer to it (the GUI auto-detects the hotspot name; password remembered after first entry)
3. Click "Set CN (unlock 5GHz)" → camera reboots automatically → done

## Notes

- ⚠️ **Windows GUI is untested on real hardware** — use the Python CLI if you hit issues (`python3 src/x2d_wifi_region.py --set 6 --reboot`)
- macOS unsigned app: right-click → Open, or allow in Privacy & Security
- macOS will ask for Local Network and Location permissions (needed to scan for the camera hotspot)
- Tested on: X2D 100C (v4.2.0), X2D II 100C (v1.3.16.2), 907X & CFV 100C (v4.0.0, community-tested)

**Docs**: [README.md](README.md) (中文) / [README_EN.md](README_EN.md) (English) / [使用说明与问题指南.md](使用说明与问题指南.md)

<details>
<summary>v1.0.0 — Initial release (history)</summary>

- Three platforms, three forms: Mac GUI (universal), Windows GUI (single file), double-click macOS minimal tool (stock Perl), cross-platform Python CLI
- Fully local: no servers, no accounts, no codes, no telemetry
- Bilingual 中/EN: UI follows system language with one-click toggle; README in both languages
- Smooth flow: hotspot auto-detection into dropdown, password remembered after first entry, camera auto-reboots after writing, auto-switch back to your regular network afterwards
- Fully documented protocol: frame format / channel / region values / reboot command — three independent implementations verified byte-identical

</details>
