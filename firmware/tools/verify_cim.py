#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""verify_cim.py — 校验哈苏 CIM 的全局 Checksum、条目 MD5 与 SHA256。"""
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


def parse_header_timestamp(header):
    end = header.find(b'\x1a')
    text = header[:end].decode('utf-8', 'replace')
    lines = text.split('\r\n')
    date_s = next(line for line in lines if '-' in line and len(line) == 10)
    time_s = next(line for line in lines if ':' in line and len(line) == 8)
    return date_s, time_s


def main():
    if len(sys.argv) != 2:
        raise SystemExit(f"用法: {sys.argv[0]} <固件.cim>")

    path = sys.argv[1]
    data = open(path, 'rb').read()
    date_s, time_s = parse_header_timestamp(data[:PRIV_START])
    iv = derive_iv(date_s, time_s)
    prologue = aes_decrypt(data[PRIV_START:ENT_START], iv)
    probe = aes_decrypt(data[ENT_START:ENT_START + 0x80], iv)
    priv_end = struct.unpack('>I', probe[0x24:0x28])[0]
    if priv_end > len(data):
        raise SystemExit("[FAIL] 文件表末尾超出文件大小")
    ent_plain = aes_decrypt(data[ENT_START:priv_end], iv)

    errors = []
    digest = hashlib.md5(data[ENT_START:] + HASH_SALT).digest()
    expected = hashlib.md5(digest + prologue[0x20:0x180]).digest()
    stored = prologue[0x10:0x20]
    if stored != expected:
        errors.append("全局 Checksum 不匹配")
    print(f"[*] {os.path.basename(path)}")
    print(f"[*] header: {date_s} {time_s}")
    print(f"[{'OK' if stored == expected else 'FAIL'}] global checksum: {stored.hex()}")

    count = 0
    for base in range(0, priv_end - ENT_START, ENTRY_SIZE):
        entry = ent_plain[base:base + ENTRY_SIZE]
        name_raw = entry[0x60:0xA0].split(b'\x00')[0]
        if not name_raw:
            continue
        name = name_raw.decode()
        off, size = struct.unpack('>II', entry[0x24:0x2C])
        enc_size = (size + 15) // 16 * 16
        if off + enc_size > len(data):
            errors.append(f"{name}: 条目数据超出文件大小")
            print(f"[FAIL] {name}: truncated")
            continue
        encrypted = data[off:off + enc_size]
        plain = aes_decrypt(encrypted, iv)[:size]
        expected_hash = entry[0x2C:0x3C]
        actual_hash = hashlib.md5(plain + HASH_SALT).digest()
        ok = actual_hash == expected_hash
        if not ok:
            errors.append(f"{name}: 条目 MD5 不匹配")
        print(f"[{'OK' if ok else 'FAIL'}] {name:24s} size={size}")
        count += 1

    print(f"[*] SHA256: {hashlib.sha256(data).hexdigest()}")
    if errors:
        for error in errors:
            print(f"[FAIL] {error}", file=sys.stderr)
        raise SystemExit(1)
    print(f"[*] 全部通过：global checksum + {count} 个条目 MD5")


if __name__ == '__main__':
    main()
