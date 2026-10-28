#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
extract_cim.py — 解包哈苏 CIM 固件到目录 (repack_cim.py 的逆操作)。

用法: extract_cim.py <固件.cim> <输出目录> [--list]
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
    date_s = next(l for l in lines if '-' in l and len(l) == 10)
    time_s = next(l for l in lines if ':' in l and len(l) == 8)
    return date_s, time_s


def main():
    src_path, out_dir = sys.argv[1], sys.argv[2]
    list_only = '--list' in sys.argv

    data = open(src_path, 'rb').read()
    date_s, time_s = parse_header_timestamp(data[:PRIV_START])
    iv = derive_iv(date_s, time_s)
    print(f"[*] header: {date_s} {time_s}  iv={iv.hex()}")

    probe = aes_decrypt(data[ENT_START:ENT_START + 0x80], iv)
    priv_end = struct.unpack('>I', probe[0x24:0x28])[0]
    ent_plain = aes_decrypt(data[ENT_START:priv_end], iv)
    print(f"[*] private header end: 0x{priv_end:x}")

    entries = []
    for base in range(0, priv_end - ENT_START, ENTRY_SIZE):
        e = ent_plain[base:base + ENTRY_SIZE]
        name = e[0x60:0xA0].split(b'\x00')[0]
        if not name:
            continue
        off, size = struct.unpack('>II', e[0x24:0x2C])
        entries.append({'name': name.decode(), 'off': off, 'size': size,
                        'hash2': bytes(e[0x2C:0x3C])})
        print(f"    {name.decode():24s} off=0x{off:08x} size={size:>11,}")

    if list_only:
        return

    os.makedirs(out_dir, exist_ok=True)
    for e in entries:
        enc_size = (e['size'] + 15) // 16 * 16
        plain = aes_decrypt(data[e['off']:e['off'] + enc_size], iv)[:e['size']]
        h = hashlib.md5(plain + HASH_SALT).digest()
        ok = 'OK' if h == e['hash2'] else '** HASH2 MISMATCH **'
        path = os.path.join(out_dir, e['name'])
        with open(path, 'wb') as f:
            f.write(plain)
        print(f"    {e['name']:24s} -> {path}  {ok}")


if __name__ == '__main__':
    main()
