// X2D / X2D II WiFi 地区设置 —— 开源本地版（无任何服务器，帧信息全部本地构造）
// 通过相机 WiFi 热点（TCP 30303 → testd 产测通道）读/写 wifiRegion，并触发相机重启。
// 编译：swiftc -O -target arm64-apple-macosx12 -o x2d-region-local main.swift
import AppKit
import CoreWLAN
import CoreLocation
import Darwin

var cameraIP = "192.168.2.1"

// ———— 双语（默认跟随系统：中文系统→中文，其它→English；右上角可切换并记住选择）————
enum Lang: String { case zh, en }
var appLang: Lang = {
    if let saved = UserDefaults.standard.string(forKey: "ui.lang"), let l = Lang(rawValue: saved) { return l }
    return Locale.preferredLanguages.first?.hasPrefix("zh") == true ? .zh : .en
}()
func L(_ zh: String, _ en: String) -> String { appLang == .zh ? zh : en }

// ———— 相机协议（帧信息全部本地，无任何网络服务）————
// 帧 257B：[05 00][09][05][fc] + 252B sutest_cmd：
//   +00 u32le cmd | +04 u32le func(1=set 2=get) | +08 u32le cookie
//   +0C u32le CRC16-XMODEM(body[0x10:0xFC]) | +14 u32le field=13 | +18 u32le value
// 重启：cmd=52 OsSystemCommand(func=1)，命令串放 +0x14 起 NUL 结尾。

let REGION_NAME = [0:"EU",1:"US",2:"2gOnly",3:"None",4:"AU",5:"CA",6:"CN",7:"IN",8:"JP",9:"KR",10:"SG",11:"AE",12:"RadioOff"]

func crc16XModem(_ b: [UInt8]) -> UInt16 {
    var crc: UInt16 = 0
    for x in b {
        crc ^= UInt16(x) << 8
        for _ in 0..<8 { crc = (crc & 0x8000) != 0 ? (crc << 1) ^ 0x1021 : crc << 1 }
    }
    return crc
}

func putU32(_ b: inout [UInt8], _ off: Int, _ v: UInt32) {
    // 注意：Swift 的 UInt8(x) 是带检转换，x>255 直接 trap——必须显式掩码
    b[off] = UInt8(v & 0xFF); b[off+1] = UInt8((v >> 8) & 0xFF); b[off+2] = UInt8((v >> 16) & 0xFF); b[off+3] = UInt8((v >> 24) & 0xFF)
}

func buildFrame(fn: UInt32, value: UInt32) -> Data {
    var body = [UInt8](repeating: 0, count: 252)
    putU32(&body, 0x00, 49)                 // ProdConfig
    putU32(&body, 0x04, fn)
    putU32(&body, 0x08, UInt32.random(in: 0x10000...0x7fffffff))
    putU32(&body, 0x14, 13)                 // wifiRegion
    putU32(&body, 0x18, value)
    let crc = crc16XModem(Array(body[0x10..<0xFC]))
    putU32(&body, 0x0C, UInt32(crc))
    return Data([0x05, 0x00, 0x09, 0x05, 0xFC] + body)
}

func buildRebootFrame() -> Data {
    var body = [UInt8](repeating: 0, count: 252)
    putU32(&body, 0x00, 52)                 // OsSystemCommand
    putU32(&body, 0x04, 1)
    putU32(&body, 0x08, UInt32.random(in: 0x10000...0x7fffffff))
    let s = Array("/system/bin/reboot\0".utf8)
    body.replaceSubrange(0x14..<(0x14 + s.count), with: s)
    let crc = crc16XModem(Array(body[0x10..<0xFC]))
    putU32(&body, 0x0C, UInt32(crc))
    return Data([0x05, 0x00, 0x09, 0x05, 0xFC] + body)
}

func probeCamera(_ host: String, port: UInt16 = 30303) -> Bool {
    let fd = socket(AF_INET, SOCK_STREAM, 0)
    guard fd >= 0 else { return false }
    defer { close(fd) }
    var addr = sockaddr_in(); addr.sin_family = sa_family_t(AF_INET); addr.sin_port = port.bigEndian
    guard inet_pton(AF_INET, host, &addr.sin_addr) == 1 else { return false }
    _ = fcntl(fd, F_SETFL, O_NONBLOCK)
    _ = withUnsafePointer(to: &addr) { $0.withMemoryRebound(to: sockaddr.self, capacity: 1) { connect(fd, $0, socklen_t(MemoryLayout<sockaddr_in>.size)) } }
    var pfd = pollfd(fd: fd, events: Int16(POLLOUT), revents: 0)
    guard poll(&pfd, 1, 3000) > 0 else { return false }
    var soerr: Int32 = 0; var slen = socklen_t(MemoryLayout<Int32>.size)
    getsockopt(fd, SOL_SOCKET, SO_ERROR, &soerr, &slen)
    return soerr == 0
}

// 发一帧收应答（1.5s 读 idle 截止）
func cameraRoundTrip(host: String, payload: Data) throws -> Data {
    let fd = socket(AF_INET, SOCK_STREAM, 0)
    guard fd >= 0 else { throw NSError(domain: "cam", code: 1) }
    defer { close(fd) }
    var addr = sockaddr_in(); addr.sin_family = sa_family_t(AF_INET); addr.sin_port = UInt16(30303).bigEndian
    guard inet_pton(AF_INET, host, &addr.sin_addr) == 1 else { throw NSError(domain: "cam", code: 2) }
    _ = fcntl(fd, F_SETFL, O_NONBLOCK)
    _ = withUnsafePointer(to: &addr) { $0.withMemoryRebound(to: sockaddr.self, capacity: 1) { connect(fd, $0, socklen_t(MemoryLayout<sockaddr_in>.size)) } }
    var pfd = pollfd(fd: fd, events: Int16(POLLOUT), revents: 0)
    guard poll(&pfd, 1, 6000) > 0 else { throw NSError(domain: "cam", code: 3, userInfo: [NSLocalizedDescriptionKey: L("连接相机超时", "camera connection timed out")]) }
    var soerr: Int32 = 0; var slen = socklen_t(MemoryLayout<Int32>.size)
    getsockopt(fd, SOL_SOCKET, SO_ERROR, &soerr, &slen)
    guard soerr == 0 else { throw NSError(domain: "cam", code: 4, userInfo: [NSLocalizedDescriptionKey: String(cString: strerror(soerr))]) }
    _ = fcntl(fd, F_SETFL, 0)
    var tv = timeval(tv_sec: 1, tv_usec: 500000)
    setsockopt(fd, SOL_SOCKET, SO_RCVTIMEO, &tv, socklen_t(MemoryLayout<timeval>.size))
    let sent = payload.withUnsafeBytes { send(fd, $0.baseAddress!, payload.count, 0) }
    guard sent == payload.count else { throw NSError(domain: "cam", code: 5) }
    var out = Data(); var chunk = [UInt8](repeating: 0, count: 4096)
    while true { let n = recv(fd, &chunk, chunk.count, 0); if n <= 0 { break }; out.append(contentsOf: chunk[0..<n]) }
    if out.isEmpty { throw NSError(domain: "cam", code: 6, userInfo: [NSLocalizedDescriptionKey: L("相机无应答", "no reply from camera")]) }
    return out
}

func parseRegionFromReply(_ buf: Data) -> Int? {
    var off = 0
    while off + 257 <= buf.count {
        let f = buf[off..<off + 257]
        if f[f.startIndex] == 0x09 && f[f.startIndex+1] == 0x00 && f[f.startIndex+2] == 0x05 && f[f.startIndex+3] == 0x09 {
            let body = f[(f.startIndex+5)...]
            let cmdId = UInt32(body[body.startIndex]) | UInt32(body[body.startIndex+1])<<8 | UInt32(body[body.startIndex+2])<<16 | UInt32(body[body.startIndex+3])<<24
            if cmdId == 49 {
                return Int(UInt32(body[body.startIndex+0x18]) | UInt32(body[body.startIndex+0x19])<<8)
            }
        }
        off += 257
    }
    return nil
}

class AppDelegate: NSObject, NSApplicationDelegate, NSWindowDelegate, CLLocationManagerDelegate, NSTextFieldDelegate, NSComboBoxDelegate {
    var window: NSWindow!
    var topStateLabel: NSTextField!
    var statusLabel: NSTextField!
    var regionLabel: NSTextField!
    var ssidField: NSComboBox!
    var pwdField: NSSecureTextField!
    var joinBtn: NSButton!
    var manualBtn: NSButton!
    var buttons: [NSButton] = []
    var logView: NSTextView!
    var langBtn: NSButton!
    var logFileHandle: FileHandle?
    let locManager = CLLocationManager()
    var statusTimer: Timer?
    var busy = false
    var wifiConnected = false
    var prevSSID: String? = nil
    var scanTick = 0

    let cInfo = NSColor.labelColor, cDim = NSColor.secondaryLabelColor
    let cOK = NSColor.systemGreen, cWarn = NSColor.systemOrange, cErr = NSColor.systemRed

    func applicationDidFinishLaunching(_ notification: Notification) {
        let w = NSWindow(contentRect: NSRect(x: 0, y: 0, width: 620, height: 440),
                         styleMask: [.titled, .closable, .miniaturizable, .resizable], backing: .buffered, defer: false)
        w.title = L("X2D / X2D II WiFi 地区设置", "X2D / X2D II WiFi Region Tool"); w.center(); w.delegate = self; w.minSize = NSSize(width: 560, height: 420)
        let cv = w.contentView!

        topStateLabel = NSTextField(labelWithString: L("相机：未连", "Camera: not connected"))
        topStateLabel.frame = NSRect(x: 20, y: 404, width: 580, height: 18)
        topStateLabel.autoresizingMask = [.width, .minYMargin]; topStateLabel.font = .systemFont(ofSize: 11); topStateLabel.textColor = cDim
        cv.addSubview(topStateLabel)

        regionLabel = NSTextField(labelWithString: L("当前地区：—", "Region: —"))
        regionLabel.frame = NSRect(x: 20, y: 372, width: 400, height: 26)
        regionLabel.font = .boldSystemFont(ofSize: 15); regionLabel.autoresizingMask = [.minYMargin]
        cv.addSubview(regionLabel)

        let step = NSTextField(labelWithString: L("① 连接相机热点（热点名自动识别；密码在相机 WiFi 界面查看）：", "① Connect to camera hotspot (SSID auto-detected; password is shown on the camera WiFi screen):"))
        step.frame = NSRect(x: 20, y: 342, width: 500, height: 20); step.autoresizingMask = [.minYMargin]
        step.textColor = cDim; step.font = .systemFont(ofSize: 12)
        cv.addSubview(step)

        let combo = NSComboBox(frame: NSRect(x: 20, y: 310, width: 200, height: 24))
        combo.placeholderString = L("热点名（扫描自动识别，可选可输）", "Hotspot SSID (auto-detected, pick or type)")
        combo.autoresizingMask = [.minYMargin]
        combo.delegate = self
        ssidField = combo
        cv.addSubview(ssidField)
        pwdField = NSSecureTextField(frame: NSRect(x: 228, y: 310, width: 180, height: 24))
        pwdField.maximumNumberOfLines = 1
        pwdField.placeholderString = L("密码（相机 WiFi 界面查看）", "Password (see camera WiFi screen)")
        pwdField.autoresizingMask = [.minYMargin]
        cv.addSubview(pwdField)
        joinBtn = NSButton(title: L("连接", "Connect"), target: self, action: #selector(onJoin(_:)))
        joinBtn.bezelStyle = .rounded
        joinBtn.frame = NSRect(x: 416, y: 308, width: 56, height: 28)
        joinBtn.autoresizingMask = [.minYMargin]
        cv.addSubview(joinBtn)
        manualBtn = NSButton(title: L("我已手动连好", "I'm connected"), target: self, action: #selector(onManual(_:)))
        manualBtn.bezelStyle = .rounded
        manualBtn.frame = NSRect(x: 480, y: 308, width: 120, height: 28)
        manualBtn.autoresizingMask = [.minYMargin]
        cv.addSubview(manualBtn)

        let step2 = NSTextField(labelWithString: L("② 选择操作（设为 CN/JP 后相机自动重启生效）：", "② Choose an action (camera reboots automatically after setting CN/JP):"))
        step2.frame = NSRect(x: 20, y: 272, width: 500, height: 20); step2.autoresizingMask = [.minYMargin]
        step2.textColor = cDim; step2.font = .systemFont(ofSize: 12)
        cv.addSubview(step2)
        let titles = [L("查看当前地区（只读）", "Query region (read-only)"), L("设为 CN 解锁 5GHz", "Set CN (unlock 5GHz)"), L("设为 JP 恢复日版", "Set JP (restore)")]
        for (i, t) in titles.enumerated() {
            let b = NSButton(title: t, target: self, action: #selector(onAction(_:)))
            b.bezelStyle = .rounded; b.tag = i
            b.frame = NSRect(x: 20 + i * 196, y: 238, width: 188, height: 32)
            b.autoresizingMask = [.minYMargin]
            cv.addSubview(b); buttons.append(b)
        }

        statusLabel = NSTextField(wrappingLabelWithString: L("先在相机上打开 WiFi 热点", "Open the WiFi hotspot on your camera first"))
        statusLabel.frame = NSRect(x: 20, y: 176, width: 580, height: 52)
        statusLabel.autoresizingMask = [.width, .minYMargin]; statusLabel.font = .systemFont(ofSize: 13)
        cv.addSubview(statusLabel)

        let scroll = NSScrollView(frame: NSRect(x: 20, y: 46, width: 580, height: 118))
        scroll.autoresizingMask = [.width, .height]; scroll.hasVerticalScroller = true; scroll.borderType = .lineBorder
        logView = NSTextView(frame: scroll.bounds)
        logView.isEditable = false; logView.drawsBackground = true
        logView.backgroundColor = .textBackgroundColor; logView.textContainerInset = NSSize(width: 6, height: 6)
        logView.autoresizingMask = [.width, .height]
        scroll.documentView = logView; cv.addSubview(scroll)

        let foot = NSTextField(wrappingLabelWithString: "https://github.com/WeiCheng97/Hasselblad-X2d-series-5g-unlock\n" + L("本工具完全免费开源，任何收费行为皆为倒卖。", "Free and open source — anyone charging for it is reselling."))
        foot.frame = NSRect(x: 20, y: 12, width: 580, height: 30)
        foot.autoresizingMask = [.width, .maxYMargin]; foot.font = .systemFont(ofSize: 11); foot.textColor = cDim
        cv.addSubview(foot)

        langBtn = NSButton(title: appLang == .zh ? "EN" : "中文", target: self, action: #selector(onLangToggle(_:)))
        langBtn.bezelStyle = .rounded
        langBtn.frame = NSRect(x: 552, y: 400, width: 48, height: 22)
        langBtn.autoresizingMask = [.minXMargin, .minYMargin]
        langBtn.font = .systemFont(ofSize: 11)
        cv.addSubview(langBtn)

        locManager.delegate = self
        openLogFile()
        log(L("[i] 已启动，完全本地运行", "[i] Started, fully local") + "\n", cDim)
        window = w; w.makeKeyAndOrderFront(nil); NSApp.activate(ignoringOtherApps: true)
        DispatchQueue.main.asyncAfter(deadline: .now() + 1) {
            if self.locManager.authorizationStatus == .notDetermined { self.locManager.requestWhenInUseAuthorization() }
        }
        scanAndReportHotspots(autofill: true)
        refreshStatus()
        statusTimer = Timer.scheduledTimer(withTimeInterval: 3, repeats: true) { [weak self] _ in self?.refreshStatus() }
    }

    @objc func onLangToggle(_ sender: NSButton) {
        appLang = (appLang == .zh) ? .en : .zh
        UserDefaults.standard.set(appLang.rawValue, forKey: "ui.lang")
        sender.title = appLang == .zh ? "EN" : "中文"
        relocalize()
    }

    // 切换语言后重设所有静态文案（日志区历史不动）
    func relocalize() {
        window?.title = L("X2D / X2D II WiFi 地区设置", "X2D / X2D II WiFi Region Tool")
        for v in window?.contentView?.subviews ?? [] {
            guard let f = v as? NSTextField else { continue }
            if f === topStateLabel { applyStatus(camera: wifiConnected, ssid: nil); continue }
            if f === regionLabel && regionLabel.stringValue == L("当前地区：—", "Region: —") || regionLabel.stringValue.hasPrefix("当前地区") || regionLabel.stringValue.hasPrefix("Region") {
                if regionLabel.stringValue == "当前地区：—" || regionLabel.stringValue == "Region: —" { regionLabel.stringValue = L("当前地区：—", "Region: —") }
                else { regionLabel.stringValue = regionLabel.stringValue.replacingOccurrences(of: "当前地区：", with: L("当前地区：", "Region: ")).replacingOccurrences(of: "Region: ", with: L("当前地区：", "Region: ")) }
                continue
            }
        }
        // 步骤标签与按钮直接重建文案
        for v in window?.contentView?.subviews ?? [] {
            if let f = v as? NSTextField, f.font == .systemFont(ofSize: 12), f.textColor == cDim {
                if f.stringValue.contains("连接相机热点") || f.stringValue.contains("Connect to camera hotspot") {
                    f.stringValue = L("① 连接相机热点（热点名自动识别；密码在相机 WiFi 界面查看）：", "① Connect to camera hotspot (SSID auto-detected; password is shown on the camera WiFi screen):")
                } else if f.stringValue.contains("选择操作") || f.stringValue.contains("Choose an action") {
                    f.stringValue = L("② 选择操作（设为 CN/JP 后相机自动重启生效）：", "② Choose an action (camera reboots automatically after setting CN/JP):")
                }
            }
        }
        ssidField.placeholderString = L("热点名（扫描自动识别，可选可输）", "Hotspot SSID (auto-detected, pick or type)")
        pwdField.placeholderString = L("密码（相机 WiFi 界面查看）", "Password (see camera WiFi screen)")
        joinBtn.title = L("连接", "Connect")
        manualBtn.title = L("我已手动连好", "I'm connected")
        let titles = [L("查看当前地区（只读）", "Query region (read-only)"), L("设为 CN 解锁 5GHz", "Set CN (unlock 5GHz)"), L("设为 JP 恢复日版", "Set JP (restore)")]
        for (i, b) in buttons.enumerated() { b.title = titles[i] }
        for v in window?.contentView?.subviews ?? [] {
            if let f = v as? NSTextField, f.font == .systemFont(ofSize: 11), f.textColor == cDim, f !== topStateLabel, f.stringValue.contains("github.com") {
                f.stringValue = "https://github.com/WeiCheng97/Hasselblad-X2d-series-5g-unlock\n" + L("本工具完全免费开源，任何收费行为皆为倒卖。", "Free and open source — anyone charging for it is reselling.")
            }
        }
    }

    func windowWillClose(_ notification: Notification) { NSApp.terminate(nil) }
    func locationManagerDidChangeAuthorization(_ manager: CLLocationManager) { refreshStatus() }

    @available(macOS, deprecated: 15.0, message: "use with Location permission")
    private func legacySSID() -> String? { CWWiFiClient.shared().interface()?.ssid() }
    func currentSSID() -> String? {
        guard locManager.authorizationStatus == .authorizedAlways else { return nil }
        return legacySSID()
    }

    func ssidLooksCamera(_ s: String) -> Bool {
        let u = s.uppercased()
        return u.contains("X2D") || u.contains("CFV") || u.contains("HASSELBLAD")
    }

    @available(macOS, deprecated: 15.0, message: "use with Location permission")
    func scanCameraHotspots() -> [String] {
        guard let iface = CWWiFiClient.shared().interface() else { return [] }
        let nets = (try? iface.scanForNetworks(withSSID: nil)) ?? []
        return nets.compactMap { $0.ssid }.filter { ssidLooksCamera($0) }
    }

    func scanAndReportHotspots(autofill: Bool) {
        DispatchQueue.global().async {
            let found = self.scanCameraHotspots()
            DispatchQueue.main.async {
                let cur = self.ssidField.stringValue
                self.ssidField.removeAllItems()
                if !found.isEmpty { self.ssidField.addItems(withObjectValues: found) }
                self.ssidField.stringValue = cur
                if found.isEmpty { return }
                let curTrim = cur.trimmingCharacters(in: .whitespaces)
                if found.contains(curTrim) {
                    if let saved = UserDefaults.standard.string(forKey: "wifiPwd.\(curTrim)"), self.pwdField.stringValue.isEmpty {
                        self.pwdField.stringValue = saved
                    }
                } else if autofill {
                    let withSaved = found.first { UserDefaults.standard.string(forKey: "wifiPwd.\($0)") != nil }
                    let pick = withSaved ?? (found.count == 1 ? found[0] : nil)
                    if let s = pick {
                        self.ssidField.stringValue = s
                        self.pwdField.stringValue = UserDefaults.standard.string(forKey: "wifiPwd.\(s)") ?? ""
                        self.log(L("[i] 已自动选中热点：", "[i] Auto-selected hotspot: ") + s + (withSaved != nil ? L("（密码已记住）", " (password saved)") : "") + "\n", self.cDim)
                    } else {
                        self.log(L("[i] 扫到多个相机热点，请在下拉里选一个", "[i] Multiple camera hotspots found — pick one in the dropdown") + "\n", self.cWarn)
                    }
                }
            }
        }
    }

    func comboBoxSelectionDidChange(_ notification: Notification) {
        let s = ssidField.stringValue.trimmingCharacters(in: .whitespaces)
        pwdField.stringValue = UserDefaults.standard.string(forKey: "wifiPwd.\(s)") ?? ""
    }

    func refreshStatus() {
        guard !busy else { return }
        let ssid = currentSSID()
        scanTick += 1
        if !wifiConnected && scanTick % 5 == 0 { scanAndReportHotspots(autofill: ssidField.stringValue.trimmingCharacters(in: .whitespaces).isEmpty) }
        DispatchQueue.global().async {
            let cam = probeCamera(cameraIP) && (ssid == nil || self.ssidLooksCamera(ssid!))
            DispatchQueue.main.async { self.applyStatus(camera: cam, ssid: ssid) }
        }
    }

    func applyStatus(camera cam: Bool, ssid: String?) {
        wifiConnected = cam
        topStateLabel.stringValue = (cam ? L("相机：已连接 ✓", "Camera: connected ✓") : L("相机：未连", "Camera: not connected")) + (ssid.map { "    WiFi：\($0)" } ?? "")
        topStateLabel.textColor = cam ? cOK : cDim
        if cam && wifiConnected { scanTick = 0 }
    }

    @objc func onJoin(_ sender: NSButton) {
        let ssid = ssidField.stringValue.trimmingCharacters(in: .whitespaces)
        guard !ssid.isEmpty else { status(L("请填热点名", "Please enter the hotspot SSID"), cWarn); return }
        prevSSID = currentSSID()
        joinWifi(ssid: ssid, pwd: pwdField.stringValue)
    }

    @objc func onManual(_ sender: NSButton) {
        log(L("[*] 好的，请在系统设置里连上相机热点，连上会自动检测", "[*] OK — connect to the camera hotspot in System Settings; detection is automatic") + "\n", cInfo)
        scanAndReportHotspots(autofill: true)
        refreshStatus()
    }

    func joinWifi(ssid: String, pwd: String) {
        log(L("[*] 连接 ", "[*] Connecting to ") + ssid + "…\n")
        DispatchQueue.global().async {
            var ok = false; var msg = ""
            for attempt in 1...6 {
                if attempt == 1 {
                    let rm = Process(); rm.executableURL = URL(fileURLWithPath: "/usr/sbin/networksetup")
                    rm.arguments = ["-removepreferredwirelessnetwork", "en0", ssid]
                    try? rm.run(); rm.waitUntilExit()
                }
                let proc = Process()
                proc.executableURL = URL(fileURLWithPath: "/usr/sbin/networksetup")
                proc.arguments = ["-setairportnetwork", "en0", ssid, pwd]
                let pipe = Pipe(); proc.standardOutput = pipe; proc.standardError = pipe
                do {
                    try proc.run(); proc.waitUntilExit()
                    let out = String(decoding: pipe.fileHandleForReading.readDataToEndOfFile(), as: UTF8.self)
                    ok = (proc.terminationStatus == 0 && !out.lowercased().contains("fail") && !out.lowercased().contains("error"))
                    msg = out.trimmingCharacters(in: .whitespacesAndNewlines)
                } catch { msg = error.localizedDescription }
                if ok { break }
                if attempt < 6 { Thread.sleep(forTimeInterval: 4) }
            }
            DispatchQueue.main.async {
                if ok {
                    UserDefaults.standard.set(pwd, forKey: "wifiPwd.\(ssid)")
                    self.log(L("[√] 已发送连接请求，几秒自动检测连上…", "[√] Join request sent, detecting connection…") + "\n", self.cOK)
                } else { self.status(L("连接失败", "Join failed"), self.cErr); self.log(L("[x] 连接失败：", "[x] Join failed: ") + (msg.isEmpty ? L("检查热点名/密码", "check SSID/password") : msg) + "\n", self.cErr) }
                self.refreshStatus()
            }
        }
    }

    @objc func onAction(_ sender: NSButton) {
        let action = sender.tag  // 0=get 1=setCN 2=setJP
        if action != 0 {
            let a = NSAlert()
            a.messageText = action == 1 ? L("确认设为 CN？", "Set region to CN?") : L("确认回滚为 JP？", "Roll back to JP?")
            a.informativeText = L("写入后相机会自动重启。", "The camera will reboot automatically after writing.")
            a.addButton(withTitle: L("执行", "Run")); a.addButton(withTitle: L("取消", "Cancel"))
            guard a.runModal() == .alertFirstButtonReturn else { return }
        }
        busy = true
        status(L("正在执行…", "Working…"), cInfo)
        DispatchQueue.global().async { self.doAction(action) }
    }

    func doAction(_ action: Int) {
        func ui(_ block: @escaping () -> Void) { DispatchQueue.main.async(execute: block) }
        func finish() { ui { self.busy = false; self.refreshStatus() } }
        defer { finish() }
        if !probeCamera(cameraIP) {
            ui { self.status(L("请把 WiFi 切到相机热点，切好自动继续…", "Switch WiFi to the camera hotspot — it continues automatically…"), self.cWarn); self.log(L("[*] 等待连接相机热点…", "[*] Waiting for camera hotspot…") + "\n", self.cWarn) }
            let deadline = Date().addingTimeInterval(120)
            while !probeCamera(cameraIP) && Date() < deadline { Thread.sleep(forTimeInterval: 1) }
            guard probeCamera(cameraIP) else {
                ui { self.status(L("等不到相机热点，已取消", "Camera hotspot not found, cancelled"), self.cErr); self.log(L("[x] 超时未检测到相机", "[x] Timed out waiting for camera") + "\n", self.cErr) }
                return
            }
        }
        do {
            let rb = try cameraRoundTrip(host: cameraIP, payload: buildFrame(fn: 2, value: 0))
            guard let v = parseRegionFromReply(rb) else {
                ui { self.status(L("没读到回读", "No readback received"), self.cErr); self.log(L("[x] 相机应答里没有地区信息", "[x] No region info in camera reply") + "\n", self.cErr) }
                return
            }
            let cur = REGION_NAME[v] ?? "?"
            ui { self.regionLabel.stringValue = L("当前地区：", "Region: ") + cur }
            if action == 0 {
                ui { self.status(L("当前地区：", "Current region: ") + cur, self.cOK); self.log(L("[√] 当前地区：", "[√] Current region: ") + cur + "\n", self.cOK) }
                return
            }
            let target = action == 1 ? 6 : 8
            let targetName = REGION_NAME[target]!
            ui { self.log(L("[*] 写入地区 = ", "[*] Writing region = ") + targetName + "…\n") }
            _ = try cameraRoundTrip(host: cameraIP, payload: buildFrame(fn: 1, value: UInt32(target)))
            Thread.sleep(forTimeInterval: 0.4)
            let rb2 = try cameraRoundTrip(host: cameraIP, payload: buildFrame(fn: 2, value: 0))
            let v2 = parseRegionFromReply(rb2)
            let got = v2.map { REGION_NAME[$0] ?? "?" } ?? "?"
            ui { self.regionLabel.stringValue = L("当前地区：", "Region: ") + got }
            if v2 == target {
                ui {
                    self.status(L("已设为 ", "Set to ") + got + L(" ✓，相机正在自动重启生效", " ✓ — camera is rebooting to apply"), self.cOK)
                    self.log(L("[√] 回读地区：", "[√] Readback region: ") + got + L("，与目标一致", ", matches target") + "\n", self.cOK)
                    self.log(L("[√] 已触发相机自动重启（热点将断开，重启后按新地区拉起）", "[√] Camera reboot triggered (hotspot will drop; it comes back with the new region)") + "\n", self.cOK)
                }
                _ = try? cameraRoundTrip(host: cameraIP, payload: buildRebootFrame())
                Thread.sleep(forTimeInterval: 2)
                restoreInternetWifi()
            } else {
                ui { self.status(L("回读 ", "Readback ") + got + L(" 与目标不符", " does not match target"), self.cErr); self.log(L("[x] 回读地区：", "[x] Readback region: ") + got + L("，与目标 ", ", target ") + targetName + L(" 不符", " mismatch") + "\n", self.cErr) }
            }
        } catch {
            ui { self.status(L("相机执行失败：", "Camera operation failed: ") + error.localizedDescription, self.cErr); self.log(L("[x] 执行失败：", "[x] Execution failed: ") + error.localizedDescription + "\n", self.cErr) }
        }
    }

    // 执行后切回日常网络（相机重启热点断开；删偏好防止自动回连相机）
    func restoreInternetWifi() {
        log(L("[*] 切回日常网络…", "[*] Switching back to your regular network…") + "\n", cDim)
        let camSSID = currentSSID()
        let ssidToRemove = (camSSID != nil && ssidLooksCamera(camSSID!)) ? camSSID! : ssidField.stringValue.trimmingCharacters(in: .whitespaces)
        if !ssidToRemove.isEmpty {
            let rm = Process(); rm.executableURL = URL(fileURLWithPath: "/usr/sbin/networksetup")
            rm.arguments = ["-removepreferredwirelessnetwork", "en0", ssidToRemove]
            try? rm.run(); rm.waitUntilExit()
        }
        let off = Process(); off.executableURL = URL(fileURLWithPath: "/usr/sbin/networksetup")
        off.arguments = ["-setairportpower", "en0", "off"]; try? off.run(); off.waitUntilExit()
        Thread.sleep(forTimeInterval: 2)
        let on = Process(); on.executableURL = URL(fileURLWithPath: "/usr/sbin/networksetup")
        on.arguments = ["-setairportpower", "en0", "on"]; try? on.run(); on.waitUntilExit()
    }

    static let logTimeFmt: DateFormatter = { let f = DateFormatter(); f.dateFormat = "HH:mm:ss"; return f }()
    // 任何线程都能安全调用：UI 操作一律跳主线程（后台直接写 NSTextView 会和布局引擎死锁）
    func log(_ s: String, _ color: NSColor? = nil) {
        let line = s.trimmingCharacters(in: .newlines)
        guard !line.isEmpty else { return }
        let stamped = "[\(Self.logTimeFmt.string(from: Date()))] \(line)\n"
        if let h = logFileHandle { try? h.write(contentsOf: stamped.data(using: .utf8)!) }
        let work = {
            self.statusLabel.stringValue = line; self.statusLabel.textColor = color ?? self.cInfo
            let attrs: [NSAttributedString.Key: Any] = [.font: NSFont.monospacedSystemFont(ofSize: 11, weight: .regular), .foregroundColor: color ?? self.cInfo]
            self.logView.textStorage?.append(NSAttributedString(string: stamped, attributes: attrs))
            self.logView.scrollToEndOfDocument(nil)
        }
        if Thread.isMainThread { work() } else { DispatchQueue.main.async(execute: work) }
    }
    func openLogFile() {
        let dir = NSHomeDirectory() + "/Library/Logs"
        try? FileManager.default.createDirectory(atPath: dir, withIntermediateDirectories: true)
        let path = dir + "/x2d-region-local.log"
        if !FileManager.default.fileExists(atPath: path) { FileManager.default.createFile(atPath: path, contents: nil) }
        logFileHandle = try? FileHandle(forWritingTo: URL(fileURLWithPath: path))
        try? logFileHandle?.seekToEnd()
        try? logFileHandle?.write(contentsOf: "\n======== \(Date()) 启动 ========\n".data(using: .utf8)!)
    }
    func status(_ s: String, _ c: NSColor) { statusLabel.stringValue = s; statusLabel.textColor = c }
}

let app = NSApplication.shared
app.setActivationPolicy(.regular)
let delegate = AppDelegate()
app.delegate = delegate
app.run()
