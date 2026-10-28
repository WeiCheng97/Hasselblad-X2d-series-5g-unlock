#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
repack_cim_adb.py — 在官方哈苏 CIM 固件中仅注入 ADB 开启载荷并重打包。

载荷注入 hbl-post-upgrade 开头，升级后首次启动以 root 执行：
  1. setprop 立即把 adb 加入 USB 配置
  2. sed 修改 setup_usb.sh，重启后仍然保留 adb

用法: repack_cim_adb.py <官方.cim> <解包目录> <输出.cim>
"""
import hashlib
import os
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
ENT_START = 0x200
ENTRY_SIZE = 0x100
ALIGN = 0x200

ADB_PAYLOAD = (
    b"\n# === adb enable ===\n"
    b"{\n"
    b"  mkdir -p /blackbox/upgrade\n"
    b"  setprop sys.usb.config none\n"
    b"  setprop sys.usb.config rndis,mass_storage,bulk,acm,adb\n"
    b"  mount -o remount,rw /system\n"
    b"  sed -i 's/rndis,mass_storage,bulk,acm$/rndis,mass_storage,bulk,acm,adb/' /system/bin/setup_usb.sh\n"
    b"  mount -o remount,ro /system\n"
    b"  sync\n"
    b"} > /data/adb_enable.log 2>&1 || true\n"
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
    date_s = next(line for line in lines if '-' in line and len(line) == 10)
    time_s = next(line for line in lines if ':' in line and len(line) == 8)
    return date_s, time_s


def md5_file(content):
    return hashlib.md5(content + HASH_SALT).digest()


def main():
    if len(sys.argv) != 4:
        raise SystemExit(f"用法: {sys.argv[0]} <官方.cim> <解包目录> <输出.cim>")
    src_path, extracted_dir, out_path = sys.argv[1:]

    data = open(src_path, 'rb').read()
    date_s, time_s = parse_header_timestamp(data[:PRIV_START])
    iv = derive_iv(date_s, time_s)
    print(f"[*] header: {date_s} {time_s}  iv={iv.hex()}")

    prologue = bytearray(aes_decrypt(data[PRIV_START:ENT_START], iv))
    probe = aes_decrypt(data[ENT_START:ENT_START + 0x80], iv)
    priv_end = struct.unpack('>I', probe[0x24:0x28])[0]
    ent_plain = bytearray(aes_decrypt(data[ENT_START:priv_end], iv))
    print(f"[*] private header end: 0x{priv_end:x}")

    entries = []
    for base in range(0, priv_end - ENT_START, ENTRY_SIZE):
        entry = ent_plain[base:base + ENTRY_SIZE]
        name = entry[0x60:0xA0].split(b'\x00')[0]
        if not name:
            continue
        off, size = struct.unpack('>II', entry[0x24:0x2C])
        entries.append({
            'name': name.decode(), 'off': off, 'size': size,
            'hash1': bytes(entry[0x00:0x10]),
            'entry_base': base,
        })
        print(f"    {name.decode():22s} off=0x{off:08x} size=0x{size:x}")

    assert 'hbl-post-upgrade' in {entry['name'] for entry in entries}

    contents = {}
    for entry in entries:
        name = entry['name']
        path = os.path.join(extracted_dir, name)
        contents[name] = open(path, 'rb').read()
        assert len(contents[name]) == entry['size'], f"size mismatch: {name}"
        assert md5_file(contents[name]) == ent_plain[
            entry['entry_base'] + 0x2C:entry['entry_base'] + 0x3C
        ], f"hash mismatch: {name}"

    post = contents['hbl-post-upgrade']
    assert b'# === adb enable ===' not in post
    assert b'force wifi region' not in post
    assert b'region readback' not in post
    first_line_end = post.find(b'\n') + 1
    assert first_line_end > 0
    contents['hbl-post-upgrade'] = post[:first_line_end] + ADB_PAYLOAD + post[first_line_end:]
    print(f"[*] hbl-post-upgrade: {len(post)} -> {len(contents['hbl-post-upgrade'])} bytes")

    layout = {entry['name']: [entry['off'], len(contents[entry['name']])] for entry in entries}
    moved = set()
    for index, entry in enumerate(entries):
        if entry['name'] != 'hbl-post-upgrade':
            continue
        for following in entries[index + 1:]:
            previous = entries[entries.index(following) - 1]
            previous_off, previous_size = layout[previous['name']]
            previous_end = previous_off + (previous_size + 15) // 16 * 16
            new_off = (previous_end + ALIGN - 1) // ALIGN * ALIGN
            if new_off != layout[following['name']][0]:
                moved.add(following['name'])
            layout[following['name']][0] = new_off
    if moved:
        print(f"[*] moved: {[(name, hex(layout[name][0])) for name in moved]}")

    last = entries[-1]
    total_end = layout[last['name']][0] + (layout[last['name']][1] + 15) // 16 * 16
    out = bytearray(data[:total_end])
    out[PRIV_START:priv_end] = b'\x00' * (priv_end - PRIV_START)

    for entry in entries:
        base = entry['entry_base']
        name = entry['name']
        off, size = layout[name]
        hash2 = md5_file(contents[name])
        hash1 = hash2 if name == 'hbl-post-upgrade' else entry['hash1']
        ent_plain[base:base + 0x10] = hash1
        ent_plain[base + 0x24:base + 0x2C] = struct.pack('>II', off, size)
        ent_plain[base + 0x2C:base + 0x3C] = hash2

    out[ENT_START:priv_end] = aes_encrypt(bytes(ent_plain), iv)[:priv_end - ENT_START]
    for entry in entries:
        name = entry['name']
        off, _ = layout[name]
        encrypted = aes_encrypt(contents[name], iv)
        need = off + len(encrypted)
        if need > len(out):
            out += b'\x00' * (need - len(out))
        out[off:off + len(encrypted)] = encrypted

    digest = hashlib.md5(bytes(out[ENT_START:]) + HASH_SALT).digest()
    checksum = hashlib.md5(digest + bytes(prologue[0x20:0x180])).digest()
    prologue[0x10:0x20] = checksum
    out[PRIV_START:ENT_START] = aes_encrypt(bytes(prologue), iv)[:ENT_START - PRIV_START]
    print(f"[*] private header checksum: {checksum.hex()}")

    for entry in entries:
        name = entry['name']
        if name in moved or name == 'hbl-post-upgrade':
            continue
        off = layout[name][0]
        comparable = entry['size'] // 16 * 16
        assert bytes(out[off:off + comparable]) == data[off:off + comparable], \
            f"encrypt mismatch: {name}"
    print("[*] 未修改且未移动文件的加密结果与原件一致 ✓")

    open(out_path, 'wb').write(bytes(out))
    print(f"[*] wrote {out_path} ({len(out)} bytes)")


if __name__ == '__main__':
    main()
