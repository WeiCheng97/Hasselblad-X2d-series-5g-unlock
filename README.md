# X2D / X2D II WiFi 地区设置

中文 | **[English README](README_EN.md)**

> **本工具完全免费开源，任何收费行为皆为倒卖。**

通过相机 WiFi 热点直连哈苏 X2D / X2D II 的工厂诊断通道，读取/修改相机的 **WiFi 地区**（wifiRegion），用于解除日版等地区的 **5GHz WiFi 限制**，并可随时恢复。

- **完全本地运行**：不连任何服务器、无授权码、无遥测。
- **不刷机、不改固件**：只通过相机自带的产测命令改一个参数，可随时改回。
- 支持：查询当前地区、设为 CN（解锁 5GHz）、设为 JP（恢复日版），写入后**自动触发相机有序重启**使新地区生效。

![主界面](docs/images/ui-main.png)

---

## 快速使用

### 方式一：Windows / Mac 图形界面

| 文件 | 平台 |
|---|---|
| `release/X2D_WiFi地区设置_win.exe` | Windows 10/11 x64，单文件直接运行 |
| `release/X2D_WiFi地区设置_mac.zip` | macOS 12+（Intel / Apple Silicon），解压双击运行（首次需在「隐私与安全性」允许） |
| `release/X2D_WiFi地区一键设置.command` | macOS 双击运行的极简替代（系统自带 Perl，无需安装任何东西） |

> ⚠️ **Windows 版 GUI 目前未经真机测试**（自动连热点走 `netsh` 临时 profile，不同系统/网卡驱动行为可能有差异）。
> 如果 Windows 版遇到问题，建议改用 **Python 命令行脚本**（方式二，跨平台、无第三方依赖）——或在 Windows 系统设置里手动连上相机热点后，再运行 Python 脚本即可。

步骤：

1. **在相机上打开 WiFi 热点**（相机菜单 → WiFi → 热点；热点名/密码显示在相机 WiFi 界面）。
2. 电脑连接该热点（GUI 会自动扫描并填入热点名，密码输一次本机永久记住；或在系统设置里手动连好后点「我已手动连好」）。
3. 点要执行的操作：
   - **查看当前地区**（只读，安全）
   - **设为 CN 解锁 5GHz**
   - **设为 JP 恢复**（回滚）
4. 写入后相机**自动重启**，新地区生效。

执行成功的样子（写入 → 回读一致 → 自动触发相机重启）：

![设为 CN 成功](docs/images/success-cn.png)

> 💡 **首次运行 macOS 会弹"允许查找本地网络中的设备"**——点「允许」（扫描相机热点需要；本工具不收集任何网络数据）：
>
> ![本地网络权限](docs/images/permission-local-network.png)

### 方式二：命令行（跨平台 Python，无第三方依赖）

```bash
# 先连上相机热点，然后：
python3 src/x2d_wifi_region.py              # 只读当前地区
python3 src/x2d_wifi_region.py --set 6      # 设为 CN（解锁 5G）
python3 src/x2d_wifi_region.py --set 8      # 设为 JP（恢复日版）
python3 src/x2d_wifi_region.py --set 6 --reboot   # 写入并自动重启相机
python3 src/x2d_wifi_region.py --host 192.168.2.1 # 指定相机 IP
```

---

## 原理（协议全部公开）

通道（X2D v4.2.0 与 X2D II v1.3.16.2 逐字节一致，固件逆向实证）：

```
电脑 ──TCP 30303(裸帧,无封帧无鉴权)──> msg2dbus(NetIO)
    ──signal 0x05 tcphost_testrx_event(origin=9, dest=5)──> D-Bus
    ──> camera-test(testd,常驻 root 工厂测试守护)
    ──命令 49 ProdConfig ──> 属性 13 = wifiRegion
    ──> /factory_data/settings.ini 的 [Identity] WifiRegion
```

**帧格式（257 字节，一次 write 发完）**：

```
[05 00] signal=5 | [09] origin=tcphost | [05] dest=eagle | [fc] type=252
sutest_cmd 252B:
  +00 u32le cmd=49 | +04 u32le func(0=print 1=set 2=get 3=init)
  +08 u32le cookie(应答回显) | +0C u32le CRC16-XMODEM(cmd[0x10:0xFC])
  +10 u32le 保留 | +14 u32le field=13 | +18 u32le 值
应答：[09 00][05][09][fc] + 252B 结果
```

**地区值**：`EU=0 US=1 CN=6 JP=8 KR=9 RadioOff=12`（其余值见源码表）。
注意：**JP(8) 会被双层禁 5G**（相机 GUI 隐藏 5G 菜单 + `dji_network` 强制 2.4G-only）。
解锁目标值 = **6 (CN)**。

**重启（写入必须完全重启才生效）**：同通道 `cmd=52 OsSystemCommand`，func=1，命令串放 `+0x14` 起 NUL 结尾（`/system/bin/reboot`），走 init 有序关机（干净重启，wifi_power 持久化，开机按新地区拉起热点）。

## 常见问题

- **连不上相机 30303**：确认①电脑已连相机热点；②相机热点处于开启状态（休眠时先用手机 Phocus 蓝牙唤醒）；③ `ping 192.168.2.1` 通不通；④ IP 不对用 `--host` 指定。
- **Windows 版打不开/连不上/闪退**：Windows GUI 未经真机测试（见上方警告）。请改用 Python 脚本完成同样操作：`python3 src/x2d_wifi_region.py --set 6 --reboot`。
- **写入后没变化**：地区参数只在相机**完全重启**时重新读取一次——本工具已自动触发重启；如被中断，手动完全重启相机一次即可。
- **会不会变砖**：不会。这是相机原生工厂诊断命令，参数合法值范围内随时可改回；最坏情况手动在相机菜单/恢复出厂里重设。
- **支持机型**：Hasselblad X2D 100C（固件 v4.2.0 实测）、X2D II 100C（v1.3.16.2 实测）、CFV 100C（v4.0.0）。其它固件版本理论一致，未逐一实测。

## 构建

- Windows GUI：`cd src/client_local && CGO_ENABLED=0 GOOS=windows GOARCH=amd64 go build -ldflags "-H=windowsgui -s -w" -o X2D_WiFi地区设置.exe .`
- Mac GUI：`cd src/gui_local && swiftc -O -target arm64-apple-macosx12 -o x2d-region-local main.swift`（再按常规 .app 结构打包；x86_64 换 `-target x86_64-apple-macosx12`，`lipo` 合并即通用包）
- `.command` / Python 工具为源码即产物，无需构建。

## 免责声明

本工具仅用于恢复/调整你自己相机的合法射频配置。请遵守所在地区的无线电法规。
与 Hasselblad 无任何关联；Hasselblad、X2D 为各自权利人商标。

## License

MIT（见 LICENSE）
