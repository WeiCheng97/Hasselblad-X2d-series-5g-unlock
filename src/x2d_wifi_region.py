#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
x2d_wifi_region.py — 通过相机 WiFi 热点读/写哈苏 X2D / X2D II / 907X & CFV 100C 的 WiFi 地区

通道（固件逆向实证，X2D v4.2.0 与 X2D II v1.3.16.2 逐字节一致）：
  TCP 30303（msg2dbus NetIO，裸 hblm 帧，无封帧无鉴权）
  → signal 0x05 tcphost_testrx_event（origin=9 tcphost, dest=5 eagle）
  → D-Bus com.hasselblad.tcphost testrx → camera-test（testd，常驻 root 工厂测试守护）
  → TestExecutor 命令 49 ProdConfig → 属性 13 = wifiRegion
  → ProdInfo::setWifiRegion → /factory_data/settings.ini 的 Identity/WifiRegion

帧格式（257 字节，一次 write 发完）：
  [05 00] signal=5  [09] origin  [05] dest  [fc] type=252
  sutest_cmd 252B: +00 u32le cmd=49 | +04 u32le func(0=print 1=set 2=get 3=init)
                   +08 u32le cookie(应答回显) | +0C u32le CRC16-XMODEM(cmd[0x10:0xFC])
                   +10 u32le 保留 | +14 u32le field=13 | +18 u32le 值
应答：[09 00][05][09][fc] + 252B 结果（signal=9 testtx）

地区值：EU=0 US=1 CN=6 JP=8 KR=9 RadioOff=12
  注意：JP(8) 会被双层禁 5G（GUI 隐藏菜单 + dji_network 强制 2.4G-only）
  写入后必须【完全重启相机】才生效（WmsCtrl 只在开机时读一次 settings.ini）

用法：
  Mac 连接相机热点（如 X2D II 100C 012343 / CFV 100C xxxxxx；热点休眠时先用手机 Phocus 蓝牙唤醒）
  python3 x2d_wifi_region.py              # 只读当前地区（安全）
  python3 x2d_wifi_region.py --set 6      # 设为 CN（解锁 5G）
  python3 x2d_wifi_region.py --set 8      # 设为 JP（验证用：5G 会消失）
"""
import socket
import struct
import sys
import time

HOST, PORT = "192.168.2.1", 30303
SIG_TESTRX, SIG_TESTTX = 0x05, 0x09
NODE_TCPHOST, NODE_EAGLE = 9, 5
CMD_PRODCONFIG, FIELD_WIFIREGION = 49, 13
FUNC_PRINT, FUNC_SET, FUNC_GET = 0, 1, 2
REGIONS = {0: "EU", 1: "US", 2: "2gOnly", 3: "None", 4: "AU", 5: "CA",
           6: "CN", 7: "IN", 8: "JP", 9: "KR", 10: "SG", 11: "AE", 12: "RadioOff"}


def crc16_xmodem(data, crc=0):
    for b in data:
        crc ^= b << 8
        for _ in range(8):
            crc = ((crc << 1) ^ 0x1021) & 0xFFFF if crc & 0x8000 else (crc << 1) & 0xFFFF
    return crc


assert crc16_xmodem(b"123456789") == 0x31C3  # XMODEM 校验值自证


def build_cmd(func, field=FIELD_WIFIREGION, value=0, cookie=0x4842):
    cmd = bytearray(252)
    struct.pack_into("<I", cmd, 0x00, CMD_PRODCONFIG)
    struct.pack_into("<I", cmd, 0x04, func)
    struct.pack_into("<I", cmd, 0x08, cookie)
    struct.pack_into("<I", cmd, 0x14, field)
    struct.pack_into("<I", cmd, 0x18, value)
    struct.pack_into("<I", cmd, 0x0C, crc16_xmodem(cmd[0x10:0xFC]))
    return bytes([SIG_TESTRX & 0xFF, SIG_TESTRX >> 8, NODE_TCPHOST, NODE_EAGLE, 0xFC]) + bytes(cmd)


def transact(payload, timeout=6.0):
    """发一帧，收 1.5s 内所有应答帧，返回 [(sig, origin, dest, body)]。"""
    try:
        sock = socket.create_connection((HOST, PORT), timeout=timeout)
    except OSError as e:
        sys.exit(f"""[x] 连不上相机 {HOST}:{PORT}（{e.strerror or e}）
排查清单：
  1. Mac 是否已连接相机热点 WiFi？（系统设置 → Wi-Fi，如 X2D II 100C 012343 / CFV 100C xxxxxx）
  2. 相机热点是否处于唤醒状态？——相机菜单里开启 WiFi；
     热点休眠时先用手机 Phocus 通过蓝牙唤醒
  3. 相机是否 ping 得通：ping -c 2 {HOST}
  4. 相机 IP 不是 {HOST} 的话，用 --host <ip> 指定""")
    with sock as s:
        s.settimeout(1.5)
        s.sendall(payload)
        buf, frames = b"", []
        deadline = time.time() + 1.5
        while time.time() < deadline:
            try:
                chunk = s.recv(4096)
            except socket.timeout:
                break
            if not chunk:
                break
            buf += chunk
        while len(buf) >= 257:
            sig, origin, dest = struct.unpack_from("<HBB", buf, 0)
            frames.append((sig, origin, dest, buf[5:257]))  # buf[4]=type 0xfc, 之后 252B 为结果 cmd
            buf = buf[257:]
        if len(buf) >= 5:  # 不足一帧的尾部（异步事件等），原样展示
            sig, origin, dest = struct.unpack_from("<HBB", buf, 0)
            frames.append((sig, origin, dest, buf[5:]))
        return frames


def show_frames(frames, label):
    print(f"--- {label}: 收到 {len(frames)} 帧 ---")
    if not frames:
        print("  [!] 连接成功但 1.5s 内无应答。可能原因：相机刚切换地区正在重启 WiFi、")
        print("      30303 被其它客户端占用、或固件版本不一致。可稍等片刻重试。")
    for sig, origin, dest, body in frames:
        print(f"  signal=0x{sig:04x} origin={origin} dest={dest} body={len(body)}B")
        if sig == SIG_TESTTX and len(body) >= 0x20:
            r = body[:252]  # body 即 sutest 结果 cmd（type 字节已在切片时跳过）
            crc_ok = crc16_xmodem(r[0x10:0xFC]) == struct.unpack_from("<I", r, 0x0C)[0]
            cmd_id, func = struct.unpack_from("<II", r, 0x00)
            cookie = struct.unpack_from("<I", r, 0x08)[0]
            field, value = struct.unpack_from("<II", r, 0x14)
            print(f"    cmdId={cmd_id} func={func} cookie=0x{cookie:08x} crc={'OK' if crc_ok else 'BAD'}")
            print(f"    field={field} value={value} ({REGIONS.get(value, '?')})")
            print("    全部 u32: " + " ".join(
                f"+{o:02x}={struct.unpack_from('<I', r, o)[0]}" for o in range(0x10, 0x24, 4)))
            print("    hex[0:64]: " + r[:64].hex())
        else:
            print("    hex: " + body[:64].hex())


def build_reboot_cmd(cookie=0x4842):
    """cmd 52 OsSystemCommand(func=1)：/system/bin/reboot，走 init 有序关机（干净重启）。"""
    cmd = bytearray(252)
    struct.pack_into("<I", cmd, 0x00, 52)
    struct.pack_into("<I", cmd, 0x04, 1)
    struct.pack_into("<I", cmd, 0x08, cookie)
    s = b"/system/bin/reboot\x00"
    cmd[0x14:0x14 + len(s)] = s
    struct.pack_into("<I", cmd, 0x0C, crc16_xmodem(cmd[0x10:0xFC]))
    return bytes([SIG_TESTRX & 0xFF, SIG_TESTRX >> 8, NODE_TCPHOST, NODE_EAGLE, 0xFC]) + bytes(cmd)


def reboot_camera():
    return transact(build_reboot_cmd())


def get_region():
    return transact(build_cmd(FUNC_GET))


def set_region(v):
    return transact(build_cmd(FUNC_SET, value=v))


def main():
    args = sys.argv[1:]
    set_val = None
    if "--set" in args:
        i = args.index("--set")
        set_val = int(args[i + 1], 0)
        if not 0 <= set_val <= 12:
            sys.exit("地区值须为 0..12（EU=0 US=1 CN=6 JP=8 KR=9 RadioOff=12）")
    if "--host" in args:
        global HOST
        HOST = args[args.index("--host") + 1]

    print(f"[*] 连接 {HOST}:{PORT} ...")
    print("[*] 步骤一：读取当前 wifiRegion（ProdConfig get）")
    show_frames(get_region(), "GET 应答")

    if set_val is None:
        print("\n[*] 只读模式结束。加 --set 6 可设为 CN（解锁 5G）。")
        return

    print(f"\n[*] 步骤二：写入 wifiRegion = {set_val} ({REGIONS.get(set_val,'?')})，发送一次，不重试")
    show_frames(set_region(set_val), "SET 应答")
    time.sleep(0.5)
    print("\n[*] 步骤三：独立回读校验")
    show_frames(get_region(), "GET 应答")
    if "--reboot" in args:
        print("\n[*] 步骤四：触发相机自动重启（cmd 52 /system/bin/reboot）")
        show_frames(reboot_camera(), "REBOOT 应答")
        print("[√] 相机正在重启，新地区随之生效（热点会断开，重启后按新地区拉起）。")
    else:
        print("\n[!] 若上面 value 已变为目标值：请【完全重启相机】使新地区生效（或加 --reboot 自动重启）。")


if __name__ == "__main__":
    main()
