// X2D / 907 WiFi 地区设置 —— 开源本地版（无任何服务器，帧信息全部本地构造）
// 通过相机 WiFi 热点（TCP 30303 → testd 产测通道）读/写 wifiRegion，并可触发相机重启。
// 交叉编译：CGO_ENABLED=0 GOOS=windows GOARCH=amd64 go build -ldflags -H=windowsgui
package main

import (
	_ "embed"
	"fmt"
	"image/color"
	"net"
	"os"
	"os/exec"
	"runtime"
	"strings"
	"sync"
	"time"

	"gioui.org/app"
	"gioui.org/font"
	"gioui.org/font/opentype"
	"gioui.org/layout"
	"gioui.org/op"
	"gioui.org/op/clip"
	"gioui.org/op/paint"
	"gioui.org/text"
	"gioui.org/unit"
	"gioui.org/widget"
	"gioui.org/widget/material"
)

//go:embed assets/uifont.otf
var uiFontBytes []byte

var cameraIP = "192.168.2.1"

func init() {
	if v := os.Getenv("X2D_CAM_IP"); v != "" {
		cameraIP = v
	}
}

// ———— 相机协议（帧信息全部本地，无任何网络服务）————
// 帧 257B：[05 00][09][05][fc] + 252B sutest_cmd：
//   +00 u32le cmd | +04 u32le func(1=set 2=get) | +08 u32le cookie
//   +0C u32le CRC16-XMODEM(body[0x10:0xFC]) | +14 u32le field=13 | +18 u32le value
// 重启：cmd=52 OsSystemCommand(func=1)，命令串放 +0x14 起 NUL 结尾。

const (
	camPort      = 30303
	cmdProdCfg   = 49
	cmdOsSys     = 52
	fieldRegion  = 13
	funcSet      = 1
	funcGet      = 2
	regionCN     = 6
	regionJP     = 8
	rebootCmdStr = "/system/bin/reboot"
)

var regionNames = map[uint32]string{0: "EU", 1: "US", 2: "2gOnly", 3: "None", 4: "AU", 5: "CA",
	6: "CN", 7: "IN", 8: "JP", 9: "KR", 10: "SG", 11: "AE", 12: "RadioOff"}

func crc16XModem(b []byte) uint16 {
	var crc uint16
	for _, x := range b {
		crc ^= uint16(x) << 8
		for i := 0; i < 8; i++ {
			if crc&0x8000 != 0 {
				crc = (crc << 1) ^ 0x1021
			} else {
				crc <<= 1
			}
		}
	}
	return crc
}

func putU32(b []byte, off int, v uint32) {
	b[off] = byte(v)
	b[off+1] = byte(v >> 8)
	b[off+2] = byte(v >> 16)
	b[off+3] = byte(v >> 24)
}
func leU32(b []byte, off int) uint32 {
	return uint32(b[off]) | uint32(b[off+1])<<8 | uint32(b[off+2])<<16 | uint32(b[off+3])<<24
}

func buildFrame(fn, value uint32) []byte {
	body := make([]byte, 252)
	putU32(body, 0x00, cmdProdCfg)
	putU32(body, 0x04, fn)
	putU32(body, 0x08, uint32(time.Now().UnixNano()&0x7fffffff|0x10000))
	putU32(body, 0x14, fieldRegion)
	putU32(body, 0x18, value)
	putU32(body, 0x0C, uint32(crc16XModem(body[0x10:0xFC])))
	f := []byte{0x05, 0x00, 0x09, 0x05, 0xFC}
	return append(f, body...)
}

func buildRebootFrame() []byte {
	body := make([]byte, 252)
	putU32(body, 0x00, cmdOsSys)
	putU32(body, 0x04, 1)
	putU32(body, 0x08, uint32(time.Now().UnixNano()&0x7fffffff|0x10000))
	copy(body[0x14:], rebootCmdStr+"\x00")
	putU32(body, 0x0C, uint32(crc16XModem(body[0x10:0xFC])))
	f := []byte{0x05, 0x00, 0x09, 0x05, 0xFC}
	return append(f, body...)
}

// 相机连通性探测
func cameraOK() bool {
	c, err := net.DialTimeout("tcp", net.JoinHostPort(cameraIP, "30303"), 1500*time.Millisecond)
	if err != nil {
		return false
	}
	c.Close()
	return true
}

func forwardToCamera(frame []byte) ([]byte, error) {
	c, err := net.DialTimeout("tcp", net.JoinHostPort(cameraIP, "30303"), 6*time.Second)
	if err != nil {
		return nil, err
	}
	defer c.Close()
	c.SetReadDeadline(time.Now().Add(1500 * time.Millisecond))
	if _, err := c.Write(frame); err != nil {
		return nil, err
	}
	var buf []byte
	tmp := make([]byte, 4096)
	for {
		n, err := c.Read(tmp)
		if n > 0 {
			buf = append(buf, tmp[:n]...)
		}
		if err != nil {
			break
		}
	}
	if len(buf) == 0 {
		return nil, fmt.Errorf("相机无应答")
	}
	return buf, nil
}

func forwardReboot() {
	c, err := net.DialTimeout("tcp", net.JoinHostPort(cameraIP, "30303"), 6*time.Second)
	if err != nil {
		return
	}
	defer c.Close()
	_, _ = c.Write(buildRebootFrame())
}

func parseRegionReply(buf []byte) (uint32, bool) {
	for off := 0; off+257 <= len(buf); off += 257 {
		f := buf[off : off+257]
		if f[0] != 0x09 || f[1] != 0 || f[2] != 0x05 || f[3] != 0x09 {
			continue
		}
		body := f[5:]
		if leU32(body, 0x00) != cmdProdCfg {
			continue
		}
		return leU32(body, 0x18) & 0xFFFF, true
	}
	return 0, false
}

// ———— UI ————
type App struct {
	w *app.Window

	ssidEdit  widget.Editor
	pwdEdit   widget.Editor
	btnJoin   widget.Clickable
	btnManual widget.Clickable
	btnGet    widget.Clickable
	btnCN     widget.Clickable
	btnJP     widget.Clickable
	logList   widget.List

	mu            sync.Mutex
	status        string
	statusCol     color.NRGBA
	logs          []string
	running       bool
	confirmTarget string
	confirmAt     time.Time
}

var (
	colOK   = color.NRGBA{0x4c, 0xd9, 0x7b, 0xff}
	colWarn = color.NRGBA{0xf0, 0xa8, 0x3a, 0xff}
	colErr  = color.NRGBA{0xf0, 0x6a, 0x6a, 0xff}
	colInfo = color.NRGBA{0xec, 0xec, 0xee, 0xff}
	colDim  = color.NRGBA{0x99, 0x99, 0x9e, 0xff}
)

func (a *App) setStatus(s string, c color.NRGBA) {
	a.mu.Lock()
	a.status, a.statusCol = s, c
	a.mu.Unlock()
	if a.w != nil {
		a.w.Invalidate()
	}
}
func (a *App) log(s string) {
	a.mu.Lock()
	a.logs = append(a.logs, fmt.Sprintf("[%s] %s", time.Now().Format("15:04:05"), s))
	a.mu.Unlock()
	if a.w != nil {
		a.w.Invalidate()
	}
}
func (a *App) setRunning(b bool) {
	a.mu.Lock()
	a.running = b
	a.mu.Unlock()
	if a.w != nil {
		a.w.Invalidate()
	}
}

func main() {
	go func() {
		w := new(app.Window)
		w.Option(app.Title("X2D / 907 WiFi 地区设置"), app.Size(unit.Dp(560), unit.Dp(560)))
		a := &App{w: w}
		a.logList.Axis = layout.Vertical
		a.ssidEdit.SingleLine = true
		a.pwdEdit.SingleLine = true
		a.setStatus("先在相机上打开 WiFi 热点，连上后即可操作", colInfo)
		if err := a.run(); err != nil {
			fmt.Fprintln(os.Stderr, err)
			os.Exit(1)
		}
		os.Exit(0)
	}()
	app.Main()
}

func (a *App) run() error {
	th := material.NewTheme()
	if face, err := opentype.Parse(uiFontBytes); err == nil {
		th.Shaper = text.NewShaper(text.WithCollection([]text.FontFace{{Font: font.Font{Typeface: "ui"}, Face: face}}))
	}
	th.Palette.Bg = color.NRGBA{0x20, 0x20, 0x24, 0xff}
	th.Palette.Fg = color.NRGBA{0xec, 0xec, 0xee, 0xff}
	th.Palette.ContrastBg = color.NRGBA{0x3d, 0x5a, 0x99, 0xff}
	th.Palette.ContrastFg = color.NRGBA{0xff, 0xff, 0xff, 0xff}
	var ops op.Ops
	for {
		switch e := a.w.Event().(type) {
		case app.DestroyEvent:
			return e.Err
		case app.FrameEvent:
			gtx := app.NewContext(&ops, e)
			a.layout(gtx, th)
			e.Frame(gtx.Ops)
		}
	}
}

func (a *App) layout(gtx layout.Context, th *material.Theme) layout.Dimensions {
	a.handleClicks(gtx)
	paint.FillShape(gtx.Ops, th.Palette.Bg, clip.Rect{Max: gtx.Constraints.Max}.Op())
	return layout.UniformInset(unit.Dp(16)).Layout(gtx, func(gtx layout.Context) layout.Dimensions {
		return layout.Flex{Axis: layout.Vertical}.Layout(gtx,
			layout.Rigid(func(gtx layout.Context) layout.Dimensions {
				return material.Label(th, unit.Sp(18), "X2D / 907 WiFi 地区设置").Layout(gtx)
			}),
			layout.Rigid(layout.Spacer{Height: unit.Dp(12)}.Layout),
			layout.Rigid(func(gtx layout.Context) layout.Dimensions {
				return layout.Flex{}.Layout(gtx,
					layout.Flexed(1.2, func(gtx layout.Context) layout.Dimensions {
						e := material.Editor(th, &a.ssidEdit, "热点名（如 X2D II 100C 012343 / CFV 100C 008987）")
						return layout.UniformInset(unit.Dp(4)).Layout(gtx, e.Layout)
					}),
					layout.Flexed(1, func(gtx layout.Context) layout.Dimensions {
						e := material.Editor(th, &a.pwdEdit, "热点密码")
						return layout.UniformInset(unit.Dp(4)).Layout(gtx, e.Layout)
					}),
					layout.Rigid(func(gtx layout.Context) layout.Dimensions {
						b := material.Button(th, &a.btnJoin, "连接")
						return layout.UniformInset(unit.Dp(4)).Layout(gtx, b.Layout)
					}),
					layout.Rigid(func(gtx layout.Context) layout.Dimensions {
						b := material.Button(th, &a.btnManual, "我已手动连好")
						return layout.UniformInset(unit.Dp(4)).Layout(gtx, b.Layout)
					}),
				)
			}),
			layout.Rigid(layout.Spacer{Height: unit.Dp(12)}.Layout),
			layout.Rigid(func(gtx layout.Context) layout.Dimensions {
				return layout.Flex{}.Layout(gtx,
					layout.Flexed(1, func(gtx layout.Context) layout.Dimensions {
						b := material.Button(th, &a.btnGet, "查看当前地区")
						return layout.UniformInset(unit.Dp(4)).Layout(gtx, b.Layout)
					}),
					layout.Flexed(1, func(gtx layout.Context) layout.Dimensions {
						txt := "设为 CN 解锁5G"
						if a.confirmTarget == "cn" && time.Since(a.confirmAt) < 3*time.Second {
							txt = "再点一次确认CN"
						}
						b := material.Button(th, &a.btnCN, txt)
						return layout.UniformInset(unit.Dp(4)).Layout(gtx, b.Layout)
					}),
					layout.Flexed(1, func(gtx layout.Context) layout.Dimensions {
						txt := "设为 JP 恢复"
						if a.confirmTarget == "jp" && time.Since(a.confirmAt) < 3*time.Second {
							txt = "再点一次确认JP"
						}
						b := material.Button(th, &a.btnJP, txt)
						return layout.UniformInset(unit.Dp(4)).Layout(gtx, b.Layout)
					}),
				)
			}),
			layout.Rigid(layout.Spacer{Height: unit.Dp(12)}.Layout),
			layout.Rigid(func(gtx layout.Context) layout.Dimensions {
				a.mu.Lock()
				s, c := a.status, a.statusCol
				a.mu.Unlock()
				lb := material.Body1(th, s)
				lb.Color = c
				lb.TextSize = unit.Sp(14)
				return lb.Layout(gtx)
			}),
			layout.Rigid(layout.Spacer{Height: unit.Dp(8)}.Layout),
			layout.Flexed(1, func(gtx layout.Context) layout.Dimensions {
				a.mu.Lock()
				logs := append([]string(nil), a.logs...)
				a.mu.Unlock()
				return material.List(th, &a.logList).Layout(gtx, len(logs), func(gtx layout.Context, i int) layout.Dimensions {
					lb := material.Body2(th, logs[i])
					lb.Color = colInfo
					return layout.UniformInset(unit.Dp(2)).Layout(gtx, lb.Layout)
				})
			}),
			layout.Rigid(func(gtx layout.Context) layout.Dimensions {
				lb := material.Caption(th, "完全本地运行：无任何服务器/授权。设为 CN/JP 后相机会自动重启生效。")
				lb.Color = colDim
				return lb.Layout(gtx)
			}),
		)
	})
}

func (a *App) handleClicks(gtx layout.Context) {
	a.mu.Lock()
	running := a.running
	a.mu.Unlock()
	if running {
		return
	}
	if a.btnJoin.Clicked(gtx) {
		a.doJoin()
	}
	if a.btnManual.Clicked(gtx) {
		a.log("[*] 好的，请在系统设置里连上相机热点，连上后点操作即可")
	}
	if a.btnGet.Clicked(gtx) {
		go a.doAction("get", 0)
	}
	if a.btnCN.Clicked(gtx) {
		a.confirmOrStart("cn", regionCN)
	}
	if a.btnJP.Clicked(gtx) {
		a.confirmOrStart("jp", regionJP)
	}
}

func (a *App) confirmOrStart(tag string, region uint32) {
	if a.confirmTarget == tag && time.Since(a.confirmAt) < 3*time.Second {
		a.confirmTarget = ""
		go a.doAction("set", region)
		return
	}
	a.confirmTarget = tag
	a.confirmAt = time.Now()
	a.w.Invalidate()
}

// 连接相机热点（Windows 写临时 profile；macOS 用 networksetup）
func (a *App) doJoin() {
	ssid := strings.TrimSpace(a.ssidEdit.Text())
	pwd := a.pwdEdit.Text()
	if ssid == "" {
		a.setStatus("请填热点名", colWarn)
		return
	}
	a.setRunning(true)
	a.setStatus("正在连接相机热点…", colInfo)
	a.log("[*] 连接 " + ssid + "…")
	go func() {
		defer a.setRunning(false)
		var err error
		if runtime.GOOS == "windows" {
			err = joinWifiWindows(ssid, pwd)
		} else {
			err = exec.Command("/usr/sbin/networksetup", "-setairportnetwork", "en0", ssid, pwd).Run()
		}
		if err == nil {
			a.log("[√] 已发送连接请求，等待连上…")
			a.setStatus("已发送连接请求，等待连上…", colOK)
		} else {
			a.setStatus("连接失败（可手动连热点）", colWarn)
			a.log("[!] 自动连接失败：" + err.Error())
		}
	}()
}

func joinWifiWindows(ssid, pwd string) error {
	esc := func(s string) string {
		r := strings.NewReplacer("&", "&amp;", "<", "&lt;", ">", "&gt;", `"`, "&quot;", "'", "&apos;")
		return r.Replace(s)
	}
	var auth, enc, key string
	if pwd == "" {
		auth, enc = "open", "none"
	} else {
		auth, enc, key = "WPA2PSK", "AES", "<sharedKey><keyType>passPhrase</keyType><protected>false</protected><keyMaterial>"+esc(pwd)+"</keyMaterial></sharedKey>"
	}
	hexUpper := func(b []byte) string {
		var sb strings.Builder
		for _, x := range b {
			fmt.Fprintf(&sb, "%02X", x)
		}
		return sb.String()
	}
	profile := `<?xml version="1.0"?><WLANProfile xmlns="http://www.microsoft.com/networking/WLAN/profile/v1"><name>` + esc(ssid) + `</name><SSIDConfig><SSID><hex>` + hexUpper([]byte(ssid)) + `</hex><name>` + esc(ssid) + `</name></SSID></SSIDConfig><connectionType>ESS</connectionType><connectionMode>auto</connectionMode><autoSwitch>false</autoSwitch><MSM><security><authEncryption><authentication>` + auth + `</authentication><encryption>` + enc + `</encryption><useOneX>false</useOneX></authEncryption>` + key + `</security></MSM></WLANProfile>`
	tmp, err := os.CreateTemp("", "x2d-wifi-*.xml")
	if err != nil {
		return err
	}
	defer os.Remove(tmp.Name())
	if _, err := tmp.WriteString(profile); err != nil {
		return err
	}
	tmp.Close()
	if out, err := exec.Command("netsh", "wlan", "add", "profile", "filename="+tmp.Name(), "user=all").CombinedOutput(); err != nil {
		return fmt.Errorf("add profile: %s", strings.TrimSpace(string(out)))
	}
	if out, err := exec.Command("netsh", "wlan", "connect", "name="+ssid).CombinedOutput(); err != nil {
		return fmt.Errorf("connect: %s", strings.TrimSpace(string(out)))
	}
	return nil
}

// 执行：等热点 → get 或 set(+reboot)
func (a *App) doAction(action string, region uint32) {
	a.setRunning(true)
	defer a.setRunning(false)
	if !cameraOK() {
		a.setStatus("请把 WiFi 切到相机热点，切好自动继续…", colWarn)
		a.log("[*] 等待连接相机热点…（切换后自动继续）")
		deadline := time.Now().Add(120 * time.Second)
		for !cameraOK() && time.Now().Before(deadline) {
			time.Sleep(time.Second)
		}
		if !cameraOK() {
			a.setStatus("等不到相机热点，已取消", colErr)
			a.log("[x] 超时未检测到相机")
			return
		}
	}
	a.setStatus("正在对相机执行…", colInfo)

	// 读一次（set 前也读，作为执行前状态）
	rb, err := forwardToCamera(buildFrame(funcGet, 0))
	if err != nil {
		a.setStatus("相机执行失败", colErr)
		a.log("[x] 读取失败：" + err.Error())
		return
	}
	v, ok := parseRegionReply(rb)
	if !ok {
		a.setStatus("没读到回读", colErr)
		a.log("[x] 相机应答里没有地区信息")
		return
	}
	cur := regionNames[v]
	a.log("[i] 执行前地区：" + cur)
	if action == "get" {
		a.setStatus("当前地区："+cur, colOK)
		a.log("[√] 当前地区：" + cur)
		return
	}

	// set
	target := regionNames[region]
	a.log("[*] 写入地区 = " + target + "…")
	rb, err = forwardToCamera(buildFrame(funcSet, region))
	if err != nil {
		a.setStatus("写入失败", colErr)
		a.log("[x] 写入失败：" + err.Error())
		return
	}
	time.Sleep(400 * time.Millisecond)
	rb, err = forwardToCamera(buildFrame(funcGet, 0))
	if err != nil {
		a.setStatus("回读失败", colErr)
		a.log("[x] 回读失败：" + err.Error())
		return
	}
	v2, _ := parseRegionReply(rb)
	got := regionNames[v2]
	if v2 == region {
		a.setStatus("已设为 "+got+" ✓，相机正在自动重启生效", colOK)
		a.log("[√] 回读地区：" + got + "，与目标一致")
		a.log("[√] 已触发相机自动重启（热点将断开，重启后按新地区拉起）")
		forwardReboot()
	} else {
		a.setStatus("回读 "+got+" 与目标不符", colErr)
		a.log("[x] 回读地区：" + got + "，与目标 " + target + " 不符")
	}
}
