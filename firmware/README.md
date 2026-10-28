# X2D / X2D II 固件解锁模块

中文 | **[English](README_EN.md)**

> **免费开源，任何收费行为皆为倒卖。** 本模块不是哈苏官方固件，仅用于你自己有权修改的相机。
>
> **默认仍推荐使用仓库根目录的免刷机工具修改地区。** 只有确需预解锁固件或 ADB 时，才使用本模块。刷写修改固件存在升级失败、系统异常甚至变砖风险。

本模块提供 X2D 100C 与 X2D II 100C 的两类修改固件，以及完整、可复现的 CIM 解包、重打包和校验脚本：

- **ADB 包**：只开启 USB ADB，不修改 WiFi 地区。
- **CN / 5GHz 包**：只在升级后写入 `WifiRegion=6 (CN)`，不包含 ADB 修改。
- 两种包均保持 `ota.zip`、MCU/CPLD 等内容不变，只修改 `hbl-post-upgrade` 及必要的文件表、偏移和校验值。

## 支持范围与验证状态

| 机型 | 官方基线固件 | ADB 包 | CN / 5GHz 包 |
|---|---|---|---|
| X2D 100C | v4.2.0 | 全量离线校验通过；**2026-10-28 已真机确认 ADB 可用且 shell 为 root** | 全量离线校验通过；本次未重新实机刷写 |
| X2D II 100C | v1.3.16.2 | 全量离线校验通过；未实机刷写 | 全量离线校验通过；本次未重新实机刷写 |

**不要混刷机型，也不要把这些包用于其他固件版本。** “离线校验通过”表示包结构、全局 Checksum、全部条目 MD5 和载荷检查通过，不等于保证每台相机都能刷写成功。

## 下载成品（v1.2.0）

| 机型 | 用途 | 文件 | SHA256 |
|---|---|---|---|
| X2D 100C | 仅开启 ADB | [X2D_100C_v4_2_0_adb.cim](https://github.com/WeiCheng97/Hasselblad-X2d-series-5g-unlock/releases/download/v1.2.0/X2D_100C_v4_2_0_adb.cim) | `51ecadd29e93f304e4386bc86cc73bf89e55f4f545c0c09fac9d583e68007b07` |
| X2D 100C | 仅写入 CN，解除日版 5GHz 限制 | [X2D_100C_v4_2_0_regionCN_v2.cim](https://github.com/WeiCheng97/Hasselblad-X2d-series-5g-unlock/releases/download/v1.2.0/X2D_100C_v4_2_0_regionCN_v2.cim) | `6360ebf33685b2e02cd76815103bfe8948164c7592f93f7b5368cc5a10d69f45` |
| X2D II 100C | 仅开启 ADB | [X2DII_100C_v1_3_16_2_adb.cim](https://github.com/WeiCheng97/Hasselblad-X2d-series-5g-unlock/releases/download/v1.2.0/X2DII_100C_v1_3_16_2_adb.cim) | `f917578a71876ae54a234001bdefa378c6ee4daca32b72312b0c39f4e17696ec` |
| X2D II 100C | 仅写入 CN，解除日版 5GHz 限制 | [X2DII_100C_v1_3_16_2_regionCN_v2.cim](https://github.com/WeiCheng97/Hasselblad-X2d-series-5g-unlock/releases/download/v1.2.0/X2DII_100C_v1_3_16_2_regionCN_v2.cim) | `30ca98ff0c7726e5f98274030366e4c9e0b2ae0b4ff5f18be076625f2655240f` |

也可以下载 [SHA256SUMS](https://github.com/WeiCheng97/Hasselblad-X2d-series-5g-unlock/releases/download/v1.2.0/SHA256SUMS) 批量核对。macOS 可在文件所在目录执行 `shasum -a 256 -c SHA256SUMS`；Windows 可用 `Get-FileHash` 逐项核对。

## 刷写前必读

1. 备份照片和配置，确保相机电量充足，升级过程中不要断电或拔卡。
2. 核对**机型、官方基线版本、文件名和 SHA256**。X2D 与 X2D II 的包不能互换。
3. ADB 包保持官方内部版本号；同版本或降级安装时，相机可能弹确认框，也可能拒绝安装。**不要为了绕过版本检查而随意改版本号。**
4. CN 包沿用 v2 构建策略，将内部构建序号调整为 `.96`，载荷仍只写地区。它与相机菜单显示的固件版本不是同一个字段。
5. 修改固件不是官方升级包。无法确认风险时，请改用仓库根目录的免刷机工具。

## 刷写与验证

1. 将选定的 `.cim` 文件放到 CFexpress 卡或内置 SSD 的**根目录**。
2. 在相机菜单中选择“设置 → 固件升级”，选择对应文件并确认。
3. 等待升级和重启全部完成，期间不要中断供电。
4. CN 包升级完成后，再手动完全重启一次，确保相机重新读取地区。

### ADB 包

使用支持数据传输的 USB-C 线连接电脑，然后执行：

```bash
adb devices
adb shell id
```

设备状态应为 `device`。在本次 X2D 真机验证中，`adb shell id` 返回 `uid=0(root)`。机内日志位于 `/data/adb_enable.log`。

ADB 载荷做两件事：

- 通过 `setprop sys.usb.config rndis,mass_storage,bulk,acm,adb` 立即启用 ADB。
- 修改 `/system/bin/setup_usb.sh`，让后续启动保留 ADB。

### CN / 5GHz 包

如果 X2D II 的热点密码不容易找到，可以直接使用这里的 CN 包通过存储卡刷入，无需先完成电脑热点连接。密码的查看方式是：先用手机连接相机，再在手机的 WiFi 界面查找；找不到或操作不方便时，直接刷包即可。

载荷在升级后首次启动时执行：

```bash
prodconfig-tool --wifi-region 6
```

必须保留 `--`；旧写法 `prodconfig-tool wifi-region 6` 会被当作位置参数并静默忽略。写入失败时，载荷会尝试重新挂载并直写 `/factory_data/settings.ini`，同时留下诊断信息：

- 机内：`/data/region_force.log`
- 可写存储根目录：`wifi_region_6.txt`

升级后可用仓库根目录的免刷机工具只读查询地区，或检查相机是否恢复 5GHz 选项。

## 回退

- **ADB 修改**：重新刷入对应机型的官方完整固件，可恢复被修改的 `/system` 脚本。
- **WiFi 地区**：地区保存在工厂数据中，**刷回官方固件不一定会恢复原地区**。需要恢复日版时，使用免刷机工具设回 `JP=8`，或自行重打包 `region=8` 的固件。
- 刷机前请自行保存对应官方固件；本仓库的脚本和 Release 不替代官方备份。

## 从官方 CIM 复现

### 1. 准备环境

需要 Python 3.10+ 和 PyCryptodome。官方固件需自行准备，不要从解包目录运行脚本。

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r firmware/tools/requirements.txt
```

Windows 激活命令为 `.venv\Scripts\activate`。

### 2. 解包官方固件

输出目录应为新的空目录，避免混入其他版本的旧文件：

```bash
mkdir -p work/x2d
python firmware/tools/extract_cim.py /path/to/X2D_100C_v4_2_0.cim work/x2d
```

每个条目应显示 `OK`。解包器会读取完整的最后一个密文块再截取明文，避免非 16 字节对齐文件的尾部被错误解密。

### 3A. 生成纯 ADB 包

```bash
python firmware/tools/repack_cim_adb.py /path/to/X2D_100C_v4_2_0.cim work/x2d X2D_100C_v4_2_0_adb.cim
```

### 3B. 生成 CN / 5GHz 包

```bash
python firmware/tools/repack_cim_region.py /path/to/X2D_100C_v4_2_0.cim work/x2d X2D_100C_v4_2_0_regionCN_v2.cim 6
```

地区参数支持 `0-12`；`99` 为只读诊断载荷。`12` 会关闭射频，不要在不了解后果时使用。

### 4. 独立校验输出

```bash
python firmware/tools/verify_cim.py X2D_100C_v4_2_0_adb.cim
```

校验器会重新解密并检查全局 Checksum 和每个条目的 MD5，同时输出文件 SHA256；任何一项失败都会以非零状态退出。

## CIM 重打包原理

以下格式来自对相机 `camera-upgrade` 校验与提取路径的逆向分析：

1. **明文头部**：包含产品、内部版本、构建日期和时间。IV 由 `MD5(IV_SALT + 日期时间二进制)` 得出。
2. **加密**：AES-128-CBC。`prologue (0x80..0x200)` 与条目区分别重置 IV；每个文件载荷独立加密，并每 4096 字节重置 IV；末尾按 16 字节补零。
3. **文件表**：每条 `0x100` 字节，文件偏移和大小使用大端序，后续文件按 `0x200` 对齐。
4. **条目 hash2**：`MD5(文件明文 + HASH_SALT)`。
5. **全局 Checksum**：`MD5(MD5(cim[0x200:EOF] + HASH_SALT) || prologue[0x20:0x180])`，重新加密 prologue 前写回。
6. **载荷位置**：在 `hbl-post-upgrade` 的 shebang 后注入。该脚本在升级后首次启动以 root 执行。
7. **保持内容不变**：不重打包 `ota.zip`，避免影响其内部 DJI 签名；未修改的 MCU/CPLD 等文件保持明文一致。

工具保留未修改条目的 `hash1`；被修改的 `hbl-post-upgrade` 按现有工具策略写入 `hash2`。详细实现和常量均公开在 `tools/` 中。

## 工具文件

| 文件 | 作用 |
|---|---|
| `tools/extract_cim.py` | 解包并逐条目校验 MD5 |
| `tools/repack_cim_adb.py` | 生成纯 ADB 包，不改地区和内部版本号 |
| `tools/repack_cim_region.py` | 生成地区写入包或只读诊断包 |
| `tools/verify_cim.py` | 独立检查全局 Checksum、全部条目 MD5 和 SHA256 |
| `SHA256SUMS` | 本次四个发布固件的 SHA256 |

## 免责声明

仅用于安全研究和你自己有权修改的设备。请遵守当地无线电法规。刷写修改固件可能导致数据丢失、保修失效或设备无法启动；作者与贡献者不承担由此产生的损失。本项目与 Hasselblad 无关联，相关商标归各自权利人所有。
