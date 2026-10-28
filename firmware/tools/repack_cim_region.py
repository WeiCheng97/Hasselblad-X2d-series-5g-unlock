#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
repack_cim_region.py — 在官方哈苏 CIM 固件中注入 WiFi 地区载荷并重打包。

载荷注入 hbl-post-upgrade 开头，升级后首次启动以 root 执行：
  prodconfig-tool --wifi-region N (必须带 --，否则会被静默忽略)，
  失败则 remount+sed 直写兜底；诊断信息写到卡根目录 wifi_region_<N>.txt。

加密/校验链(全部从相机 camera-upgrade 二进制逆向并实证):
  AES-128-CBC 静态 key, IV = MD5(IV_SALT + 头部日期时间)
  分段加密: 文件表头(prologue 0x80..0x200) 与 条目区(0x200..priv_end) 分别重置 IV;
           每个文件载荷独立加密, 每 4096 字节重置 IV
  文件表 hash2 = MD5(明文 + MAGIC_HASH_SALT)           — extractFile 校验
  Checksum 字段 = MD5( MD5(cim[0x200:EOF] + HASH_SALT) || prologue[0x20:0x180] )
                                                    — verifyChecksum 必检
  hash1 语义未知(疑似签名), 非提取/校验项: 未修改文件保留原值, 修改文件填 md5(content+salt)
  首个条目 hash1 固定为 16 个 0

用法: repack_cim_region.py <官方.cim> <解包目录> <输出.cim> <地区0-12|99>
"""
import hashlib
import os
import re
import struct
import sys

from Crypto.Cipher import AES

STATIC_KEY = bytes([0x93, 0xF8, 0x2C, 0xA2, 0x44, 0xAB, 0x29, 0xE0,
                    0x36, 0x69, 0x34, 0xD5, 0x67, 0x13, 0xEE, 0xA2])
IV_SALT = bytes([0xE6, 0x36, 0xFA, 0xDC, 0x3D, 0x99, 0x2D, 0x07,
                 0x05, 0xFD, 0x95, 0x8E, 0x82, 0xE3, 0x14, 0x7A])
HASH_SALT = bytes([0xCD, 0x87, 0xD7, 0x27, 0xFA, 0x5E, 0xE7, 0xF9,
                   0x5D, 0x43, 0xE2, 0xC4, 0x9E, 0x90, 0xD7, 0x0B])
CHUNK = 4096
PRIV_START = 0x80
ENT_START = 0x200          # 条目区起点 (文件偏移)
ENTRY_SIZE = 0x100
ALIGN = 0x200

# 强制+回读合并载荷 v2: 修正语法 (--wifi-region), 全程留证, 写不进则 sed 兜底
# 注意: prodconfig-tool 用 QCommandLineParser, 子命令必须带 --; 其输出走 qDebug->logcat
PAYLOAD_TMPL = (
    b"\n# === force wifi region __REGION__ + readback (v2, fixed syntax) ===\n"
    b"{\n"
    b"  echo '-- before --'\n"
    b"  grep -i wifiregion /factory_data/settings.ini 2>&1\n"
    b"  getenforce 2>&1\n"
    b"  cat /proc/mounts | grep -i factory 2>&1\n"
    b"  prodconfig-tool --wifi-region __REGION__\n"
    b"  echo \"prodconfig-tool exit=$?\"\n"
    b"  sync\n"
    b"  echo '-- after --'\n"
    b"  grep -i wifiregion /factory_data/settings.ini 2>&1\n"
    b"} > /data/region_force.log 2>&1 || true\n"
    b"if ! grep -q \"WifiRegion=__REGION__\" /factory_data/settings.ini 2>/dev/null; then\n"
    b"  {\n"
    b"    echo '-- prodconfig-tool failed, fallback: direct sed write --'\n"
    b"    mount -o remount,rw /factory_data 2>&1\n"
    b"    sed -i 's/^WifiRegion=.*/WifiRegion=__REGION__/' /factory_data/settings.ini 2>&1\n"
    b"    sync\n"
    b"    mount -o remount,ro /factory_data 2>&1\n"
    b"    echo '-- after fallback --'\n"
    b"    grep -i wifiregion /factory_data/settings.ini 2>&1\n"
    b"  } >> /data/region_force.log 2>&1 || true\n"
    b"fi\n"
    b"tmp=/tmp/region_readback.txt\n"
    b"{\n"
    b"  echo \"== force --wifi-region __REGION__, readback v2 ==\"\n"
    b"  date\n"
    b"  echo '-- region_force.log --'\n"
    b"  cat /data/region_force.log 2>&1\n"
    b"  echo '-- settings.ini --'\n"
    b"  cat /factory_data/settings.ini 2>/dev/null\n"
    b"  echo '-- mounts|factory --'\n"
    b"  cat /proc/mounts | grep -i factory 2>&1\n"
    b"  echo '-- product_info --'\n"
    b"  product_info all 2>&1\n"
    b"  echo '-- prodconfig-tool --print (via logcat) --'\n"
    b"  prodconfig-tool --print >/dev/null 2>&1\n"
    b"  sleep 1\n"
    b"  /system/bin/logcat -d 2>/dev/null | grep -iE 'wifi ?region|prodinfo|prodconfig|failed to mount' | tail -30\n"
    b"  echo '-- factory partition strings --'\n"
    b"  strings /dev/block/by-name/factory 2>/dev/null | grep -iE 'region|wifi' | head -10\n"
    b"} > $tmp 2>&1\n"
    b"for d in /mnt/media_rw/cfe /mnt/media_rw/ssd /mnt/media_rw/sdcard /mnt/media_rw/emulated; do\n"
    b"  if [ -d \"$d\" ] && [ -w \"$d\" ]; then cp $tmp \"$d/wifi_region___REGION__.txt\"; fi\n"
    b"done\n"
    b"sync\n"
    b"# === end ===\n"
)

# 回读载荷: 把当前地区/诊断信息写到存储卡根目录 wifi_region.txt (USB 大容量存储可读)
PAYLOAD_READBACK = (
    b"\n# === wifi region readback ===\n"
    b"tmp=/tmp/region_readback.txt\n"
    b"{\n"
    b"  echo \"== wifi region readback ==\"\n"
    b"  date\n"
    b"  echo '-- product_info --'\n"
    b"  product_info all 2>&1\n"
    b"  echo '-- settings.ini --'\n"
    b"  cat /factory_data/settings.ini 2>/dev/null\n"
    b"  echo '-- prodconfig-tool --print (from logcat) --'\n"
    b"  prodconfig-tool --print >/dev/null 2>&1\n"
    b"  sleep 1\n"
    b"  /system/bin/logcat -d 2>/dev/null | grep -iE 'wifi ?region|usbpower|dutstatus|prodinfo|failed to mount' | tail -15\n"
    b"  echo '-- factory partition strings --'\n"
    b"  strings /dev/block/by-name/factory 2>/dev/null | grep -iE 'region|wifi' | head -10\n"
    b"} > $tmp 2>&1\n"
    b"for d in /mnt/media_rw/cfe /mnt/media_rw/ssd /mnt/media_rw/sdcard /mnt/media_rw/emulated; do\n"
    b"  if [ -d \"$d\" ] && [ -w \"$d\" ]; then cp $tmp \"$d/wifi_region.txt\"; fi\n"
    b"done\n"
    b"sync\n"
    b"# === end ===\n"
)


def derive_iv(date_str, time_str):
    y, mo, da = map(int, date_str.split('-'))
    h, mi, s = map(int, time_str.split(':'))
    tb = bytearray(16)
    tb[0], tb[1], tb[2], tb[3] = y // 100, y % 100, mo, da
    tb[4], tb[5], tb[6] = h, mi, s
    return hashlib.md5(IV_SALT + bytes(tb)).digest()


def aes_decrypt(buf, iv):
    out = bytearray()
    for i in range(0, len(buf), CHUNK):
        chunk = bytes(buf[i:i + CHUNK])
        chunk += b'\x00' * ((-len(chunk)) % 16)
        out += AES.new(STATIC_KEY, AES.MODE_CBC, iv).decrypt(chunk)
    return bytes(out)


def aes_encrypt(buf, iv):
    out = bytearray()
    for i in range(0, len(buf), CHUNK):
        chunk = bytes(buf[i:i + CHUNK])
        chunk += b'\x00' * ((-len(chunk)) % 16)
        out += AES.new(STATIC_KEY, AES.MODE_CBC, iv).encrypt(chunk)
    return bytes(out)


def parse_header_timestamp(header):
    end = header.find(b'\x1a')
    text = header[:end].decode('utf-8', 'replace')
    lines = text.split('\r\n')
    date_s = next(l for l in lines if '-' in l and len(l) == 10)
    time_s = next(l for l in lines if ':' in l and len(l) == 8)
    return date_s, time_s


def md5_file(content):
    return hashlib.md5(content + HASH_SALT).digest()


def main():
    if len(sys.argv) != 5:
        raise SystemExit(f"用法: {sys.argv[0]} <官方.cim> <解包目录> <输出.cim> <地区0-12|99>")
    src_path, extracted_dir, out_path = sys.argv[1], sys.argv[2], sys.argv[3]
    region = int(sys.argv[4])
    if region not in range(13) and region != 99:
        raise SystemExit("地区值必须为 0-12，或 99（只读诊断）")
    if region == 99:
        payload = PAYLOAD_READBACK
        print("[*] mode: readback (region -> 卡上 wifi_region.txt)")
    else:
        payload = PAYLOAD_TMPL.replace(b'__REGION__', str(region).encode())
        print(f"[*] mode: force wifi region = {region}")

    data = open(src_path, 'rb').read()
    date_s, time_s = parse_header_timestamp(data[:PRIV_START])
    iv = derive_iv(date_s, time_s)
    print(f"[*] header: {date_s} {time_s}  iv={iv.hex()}")

    # ---- 两段解密: prologue (0x80..0x200) 与 entries (0x200..priv_end) ----
    prologue = bytearray(aes_decrypt(data[PRIV_START:ENT_START], iv))
    probe = aes_decrypt(data[ENT_START:ENT_START + 0x80], iv)
    priv_end = struct.unpack('>I', probe[0x24:0x28])[0]
    ent_plain = bytearray(aes_decrypt(data[ENT_START:priv_end], iv))
    print(f"[*] private header end: 0x{priv_end:x}")

    entries = []
    for base in range(0, priv_end - ENT_START, ENTRY_SIZE):
        e = ent_plain[base:base + ENTRY_SIZE]
        name = e[0x60:0xA0].split(b'\x00')[0]
        if not name:
            continue
        off, size = struct.unpack('>II', e[0x24:0x2C])
        entries.append({
            'name': name.decode(), 'off': off, 'size': size,
            'hash1': bytes(e[0x00:0x10]), 'hash2': bytes(e[0x2C:0x3C]),
            'entry_base': base,
        })
        print(f"    {name.decode():22s} off=0x{off:08x} size=0x{size:x} hash1={'0'*32 if e[0:16]==b'\x00'*16 else e[0:16].hex()[:16]+'...'}")

    names = [e['name'] for e in entries]
    assert 'hbl-post-upgrade' in names, "no hbl-post-upgrade in cim!"

    # ---- 注入载荷 ----
    post = open(os.path.join(extracted_dir, 'hbl-post-upgrade'), 'rb').read()
    assert b'force wifi region' not in post
    assert b'region readback' not in post
    nl = post.find(b'\n') + 1
    new_post = post[:nl] + payload + post[nl:]
    print(f"[*] hbl-post-upgrade: {len(post)} -> {len(new_post)} bytes")

    contents = {}
    for e in entries:
        contents[e['name']] = new_post if e['name'] == 'hbl-post-upgrade' else \
            open(os.path.join(extracted_dir, e['name']), 'rb').read()
        assert len(contents[e['name']]) == e['size'] or e['name'] == 'hbl-post-upgrade'

    # ---- 布局: post 之后的文件顺移 ----
    layout = {e['name']: [e['off'], len(contents[e['name']])] for e in entries}
    moved = set()
    for idx, e in enumerate(entries):
        if e['name'] == 'hbl-post-upgrade':
            for e2 in entries[idx + 1:]:
                prev = entries[entries.index(e2) - 1]
                prev_end = layout[prev['name']][0] + ((layout[prev['name']][1] + 15) // 16) * 16
                new_off = (prev_end + ALIGN - 1) // ALIGN * ALIGN
                if new_off != layout[e2['name']][0]:
                    moved.add(e2['name'])
                layout[e2['name']][0] = new_off
    if moved:
        print(f"[*] moved: {[(n, hex(layout[n][0])) for n in moved]}")

    last = entries[-1]
    total_end = layout[last['name']][0] + ((layout[last['name']][1] + 15) // 16) * 16
    out = bytearray(data[:total_end])
    out[PRIV_START:priv_end] = b'\x00' * (priv_end - PRIV_START)

    # ---- 更新条目 (entries 明文) ----
    for e in entries:
        base = e['entry_base']
        off, size = layout[e['name']]
        content = contents[e['name']]
        hash2 = md5_file(content)
        hash1 = e['hash1'] if e['name'] != 'hbl-post-upgrade' else hash2
        ent_plain[base + 0x00:base + 0x10] = hash1
        ent_plain[base + 0x24:base + 0x2C] = struct.pack('>II', off, size)
        ent_plain[base + 0x2C:base + 0x3C] = hash2

    # ---- 先加密条目区 + 载荷 (与 prologue 无关) ----
    out[ENT_START:priv_end] = aes_encrypt(bytes(ent_plain), iv)[:priv_end - ENT_START]
    for e in entries:
        name = e['name']
        off, size = layout[name]
        enc = aes_encrypt(contents[name], iv)
        need = off + len(enc)
        if need > len(out):
            out += b'\x00' * (need - len(out))
        out[off:off + len(enc)] = enc

    # ---- 计算 Checksum 并写入 prologue, 加密 prologue ----
    #   checksum = MD5( MD5(cim[0x200:EOF] + HASH_SALT) || prologue[0x20:0x180] )
    d0 = hashlib.md5(bytes(out[ENT_START:]) + HASH_SALT).digest()
    checksum = hashlib.md5(d0 + bytes(prologue[0x20:0x180])).digest()
    prologue[0x10:0x20] = checksum
    out[PRIV_START:ENT_START] = aes_encrypt(bytes(prologue), iv)[:ENT_START - PRIV_START]
    print(f"[*] private header checksum: {checksum.hex()}")

    # ---- 校验: 未修改/未移动文件与原件一致 (忽略末尾填充块) ----
    for e in entries:
        if e['name'] in moved or e['name'] == 'hbl-post-upgrade':
            continue
        off = layout[e['name']][0]
        comparable = e['size'] // 16 * 16
        assert bytes(out[off:off + comparable]) == data[off:off + comparable], \
            f"encrypt mismatch: {e['name']}"
    print("[*] 未修改文件加密结果与原件一致 ✓")

    # ---- 抬高包头 build 版本号 (明文, 不影响校验/IV), 保证同内容也能作为"新版本"被接受 ----
    # 版本字符串等长替换: 最后一位组件 -> 90+region (CN=6->96, JP=8->98, readback->97)
    # (v1 包用过 86/88/89, 必须更高以通过同版本检查)
    vbump = min(90 + region, 99) if region != 99 else 97
    hdr = bytes(out[:PRIV_START])
    m = re.search(rb'\d+\.\d+\.\d+\.(\d+)\x00', hdr)
    if m:
        old_ver = m.group(0)
        new_ver = hdr[:m.start(1)] + str(vbump).encode() + hdr[m.end(1):]
        assert len(new_ver) == len(hdr)
        out[:PRIV_START] = new_ver
        print(f"[*] header version: {old_ver[:-1].decode()} -> ...{vbump}")
    else:
        print("[!] 未找到包头版本号, 跳过抬高 (同版本可能弹确认框)")

    open(out_path, 'wb').write(bytes(out))
    print(f"[*] wrote {out_path} ({len(out)} bytes)")


if __name__ == '__main__':
    main()
