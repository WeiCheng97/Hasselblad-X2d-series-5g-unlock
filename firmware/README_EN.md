# X2D / X2D II Firmware Unlock Module

**[中文](README.md)** | English

> **Free and open source — anyone charging for it is reselling.** These are not official Hasselblad firmware packages. Use them only on cameras you own and are authorized to modify.
>
> **The no-flash tool in the repository root remains the recommended way to change WiFi region.** Use this module only if you specifically need prebuilt firmware or ADB. Flashing modified firmware can fail, damage the installation, or brick the camera.

This module provides two kinds of modified firmware for the X2D 100C and X2D II 100C, plus reproducible CIM extraction, repacking, and verification tools:

- **ADB packages**: enable USB ADB only; they do not change WiFi region.
- **CN / 5GHz packages**: write `WifiRegion=6 (CN)` after the upgrade; they do not enable ADB.
- Both leave `ota.zip`, MCU/CPLD images, and other payloads unchanged. Only `hbl-post-upgrade` and the required file-table, offset, and checksum fields change.

## Support and verification

| Camera | Official baseline | ADB package | CN / 5GHz package |
|---|---|---|---|
| X2D 100C | v4.2.0 | Full offline verification passed; **ADB and root shell confirmed on hardware on 2026-10-28** | Full offline verification passed; not reflashed for this release |
| X2D II 100C | v1.3.16.2 | Full offline verification passed; not tested on hardware | Full offline verification passed; not reflashed for this release |

**Do not flash a package onto a different camera model or baseline version.** Offline verification covers package structure, the global checksum, every entry MD5, and payload isolation; it cannot guarantee a successful flash on every camera.

## Downloads (v1.2.0)

| Camera | Purpose | File | SHA256 |
|---|---|---|---|
| X2D 100C | ADB only | [X2D_100C_v4_2_0_adb.cim](https://github.com/WeiCheng97/Hasselblad-X2d-series-5g-unlock/releases/download/v1.2.0/X2D_100C_v4_2_0_adb.cim) | `51ecadd29e93f304e4386bc86cc73bf89e55f4f545c0c09fac9d583e68007b07` |
| X2D 100C | CN / 5GHz only | [X2D_100C_v4_2_0_regionCN_v2.cim](https://github.com/WeiCheng97/Hasselblad-X2d-series-5g-unlock/releases/download/v1.2.0/X2D_100C_v4_2_0_regionCN_v2.cim) | `6360ebf33685b2e02cd76815103bfe8948164c7592f93f7b5368cc5a10d69f45` |
| X2D II 100C | ADB only | [X2DII_100C_v1_3_16_2_adb.cim](https://github.com/WeiCheng97/Hasselblad-X2d-series-5g-unlock/releases/download/v1.2.0/X2DII_100C_v1_3_16_2_adb.cim) | `f917578a71876ae54a234001bdefa378c6ee4daca32b72312b0c39f4e17696ec` |
| X2D II 100C | CN / 5GHz only | [X2DII_100C_v1_3_16_2_regionCN_v2.cim](https://github.com/WeiCheng97/Hasselblad-X2d-series-5g-unlock/releases/download/v1.2.0/X2DII_100C_v1_3_16_2_regionCN_v2.cim) | `30ca98ff0c7726e5f98274030366e4c9e0b2ae0b4ff5f18be076625f2655240f` |

A machine-readable [SHA256SUMS](https://github.com/WeiCheng97/Hasselblad-X2d-series-5g-unlock/releases/download/v1.2.0/SHA256SUMS) file is also attached to the release.

## Before flashing

1. Back up photos and settings, charge the camera, and never interrupt power during the upgrade.
2. Verify the **camera model, baseline version, filename, and SHA256**. X2D and X2D II packages are not interchangeable.
3. ADB packages retain the official internal version. A same-version or downgrade installation may require confirmation or be rejected. Do not change versions blindly to bypass this check.
4. CN packages retain the earlier v2 policy of raising the internal build suffix to `.96`; the payload still changes only the WiFi region. This internal field is separate from the version shown in the camera menu.
5. If you are not comfortable with these risks, use the no-flash tool instead.

## Flash and verify

1. Copy the selected `.cim` file to the **root directory** of a CFexpress card or the internal SSD.
2. On the camera, open Settings → Firmware Update, select the file, and confirm.
3. Let every upgrade and reboot finish without interrupting power.
4. After a CN-package upgrade, perform one more full reboot so the camera reloads the region.

For ADB, connect a data-capable USB-C cable and run `adb devices`, then `adb shell id`. The device state should be `device`; the tested X2D returned `uid=0(root)`. The on-camera log is `/data/adb_enable.log`.

For X2D II, the hotspot password is shown through the phone workflow: connect a phone to the camera first, then look in the phone's WiFi interface. If you cannot find the password or prefer not to use that workflow, flash the CN / 5GHz package directly from a memory card instead.

The CN payload runs `prodconfig-tool --wifi-region 6`. The `--` is required: the older `prodconfig-tool wifi-region 6` form is silently ignored. If the write fails, the payload attempts a direct `/factory_data/settings.ini` fallback and records diagnostics in `/data/region_force.log` and `wifi_region_6.txt` on writable storage.

## Rollback

- **ADB**: reflashing the matching official full firmware restores the modified `/system` script.
- **WiFi region**: region is stored in factory data, so **flashing official firmware does not necessarily restore JP**. Set `JP=8` with the no-flash tool, or build a region-8 package.
- Keep your own copy of the matching official firmware before flashing.

## Reproduce a package

Install Python 3.10+ and the pinned dependency, then extract an official package into a new empty directory:

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r firmware/tools/requirements.txt
mkdir -p work/x2d
python firmware/tools/extract_cim.py /path/to/X2D_100C_v4_2_0.cim work/x2d
```

On Windows, activate with `.venv\Scripts\activate`.

Build an ADB-only package:

```bash
python firmware/tools/repack_cim_adb.py /path/to/X2D_100C_v4_2_0.cim work/x2d X2D_100C_v4_2_0_adb.cim
```

Or build a CN package:

```bash
python firmware/tools/repack_cim_region.py /path/to/X2D_100C_v4_2_0.cim work/x2d X2D_100C_v4_2_0_regionCN_v2.cim 6
```

Region values `0-12` are accepted; `99` builds a read-only diagnostic payload. Value `12` disables radio and should not be used casually.

Verify the result:

```bash
python firmware/tools/verify_cim.py X2D_100C_v4_2_0_adb.cim
```

The verifier decrypts the package again, checks the global checksum and every entry MD5, prints SHA256, and exits nonzero on any failure.

## Repacking format

The implementation documents the format recovered from the camera's `camera-upgrade` validation and extraction paths:

1. The plaintext header supplies the build date/time used to derive the IV as `MD5(IV_SALT + binary timestamp)`.
2. Encryption is AES-128-CBC. The prologue and entry area reset IV separately; each file payload is encrypted independently with IV reset every 4096 bytes and zero padding to 16 bytes.
3. File-table entries are `0x100` bytes, offsets and sizes are big-endian, and following payloads are aligned to `0x200`.
4. Entry hash2 is `MD5(plaintext + HASH_SALT)`.
5. The global checksum is `MD5(MD5(cim[0x200:EOF] + HASH_SALT) || prologue[0x20:0x180])`.
6. Payloads are inserted after the `hbl-post-upgrade` shebang and run as root on the first boot after upgrading.
7. `ota.zip` is not repacked, preserving its internal DJI signature. Unmodified MCU/CPLD and other payloads remain plaintext-identical.

The extractor reads the complete final cipher block before truncating plaintext; this avoids corrupting files whose size is not 16-byte aligned.

## Disclaimer

For security research and devices you are authorized to modify only. Comply with local radio regulations. Modified firmware can cause data loss, warranty loss, or an unbootable camera; the authors and contributors accept no liability. This project is not affiliated with Hasselblad, and all trademarks belong to their respective owners.
