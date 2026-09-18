#!/bin/bash
# X2D / 907 WiFi 地区一键设置 —— 双击运行，任何 Mac 无需安装任何东西
# 原理：系统自带 Perl 通过相机热点（TCP 30303）调用原厂产测命令读写 WiFi 地区
# 前置：Mac 已连接相机热点（如 X2D II 100C 012343 / CFV 100C xxxxxx）；热点休眠时先用手机 Phocus 蓝牙唤醒

HOST="192.168.2.1"

run_tool() {  # $1 = get | set, $2 = 地区值（set 时）
  MODE="$1" VALUE="${2:-0}" HOST="$HOST" /usr/bin/perl - <<'PERL_EOF'
use strict; use warnings;
use IO::Socket::INET; use IO::Select;

my $host = $ENV{HOST} || '192.168.2.1';
my ($mode, $val) = ($ENV{MODE} || 'get', ($ENV{VALUE} // 0) + 0);
my %REGIONS = (0=>'EU',1=>'US',2=>'2gOnly',3=>'None',4=>'AU',5=>'CA',
               6=>'CN',7=>'IN',8=>'JP',9=>'KR',10=>'SG',11=>'AE',12=>'RadioOff');

# CRC16-XMODEM（poly 0x1021 初值 0），与相机 camera-test 二进制指令级核对一致
sub crc16 { my $crc = 0;
  for my $b (unpack 'C*', $_[0]) { $crc ^= $b << 8;
    for (1..8) { $crc = ($crc & 0x8000) ? (($crc << 1) ^ 0x1021) & 0xFFFF : ($crc << 1) & 0xFFFF; } }
  return $crc; }
die "CRC 自检失败\n" unless crc16("123456789") == 0x31C3;

# 257 字节帧：[05 00]signal [09]origin(tcphost) [05]dest(eagle) [fc]type + 252B sutest_cmd
# sutest_cmd: +00 cmd=49(ProdConfig) +04 func(1=set 2=get) +08 cookie +0C CRC(cmd[0x10..0xFB])
#             +14 field=13(wifiRegion) +18 value
sub build_cmd { my ($func, $value) = @_;
  my $cmd = "\0" x 252;
  substr($cmd, 0x00, 4) = pack('V', 49);
  substr($cmd, 0x04, 4) = pack('V', $func);
  substr($cmd, 0x08, 4) = pack('V', 0x4842);
  substr($cmd, 0x14, 4) = pack('V', 13);
  substr($cmd, 0x18, 4) = pack('V', $value);
  substr($cmd, 0x0C, 4) = pack('V', crc16(substr($cmd, 0x10, 236)));
  return pack('C*', 0x05, 0x00, 0x09, 0x05, 0xFC) . $cmd; }

# cmd=52 OsSystemCommand(func=1)：/system/bin/reboot，init 有序关机（干净重启）
sub build_reboot {
  my $cmd = "\0" x 252;
  substr($cmd, 0x00, 4) = pack('V', 52);
  substr($cmd, 0x04, 4) = pack('V', 1);
  substr($cmd, 0x08, 4) = pack('V', 0x4842);
  my $s = "/system/bin/reboot\0";
  substr($cmd, 0x14, length($s)) = $s;
  substr($cmd, 0x0C, 4) = pack('V', crc16(substr($cmd, 0x10, 236)));
  return pack('C*', 0x05, 0x00, 0x09, 0x05, 0xFC) . $cmd; }

sub transact { my ($payload) = @_;
  my $s = IO::Socket::INET->new(PeerAddr=>$host, PeerPort=>30303, Proto=>'tcp', Timeout=>6);
  if (!$s) { print connect_fail_msg($host); exit 2; }
  $s->autoflush(1); print $s $payload;
  my $sel = IO::Select->new($s); my $buf = '';
  while ($sel->can_read(1.5)) {
    my $n = sysread($s, my $chunk, 4096); last unless $n; $buf .= $chunk;
    last if length($buf) >= 257 && length($buf) % 257 == 0; }
  close $s; return $buf; }

sub connect_fail_msg { my ($h) = @_;
  return "[x] 连不上相机 $h:30303（$!）\n" .
    "排查清单：\n" .
    "  1. Mac 是否已连接相机热点 WiFi？（系统设置 → Wi-Fi，如 X2D II 100C 012343 / CFV 100C xxxxxx）\n" .
    "  2. 相机热点是否处于唤醒状态？——相机菜单里开启 WiFi；\n" .
    "     热点休眠时先用手机 Phocus 通过蓝牙唤醒\n" .
    "  3. 相机是否 ping 得通：ping -c 2 $h\n"; }

sub show_reply { my ($label, $buf) = @_;
  print "--- $label ---\n";
  if (!length $buf) {
    print "  [!] 连接成功但 1.5s 内无应答。可能：相机正在重启 WiFi、30303 被占用。稍等重试。\n"; return undef; }
  my $value;
  while (length($buf) >= 257) {
    my $frame = substr($buf, 0, 257, '');   # 取出并移除一帧
    my ($sig, $origin, $dest) = unpack('v C C', substr($frame, 0, 4));
    printf "  signal=0x%04x origin=%d dest=%d\n", $sig, $origin, $dest;
    next unless $sig == 0x0009;             # 只看 testtx 应答
    my $r = substr($frame, 5, 252);
    my ($cmdid, $func, $cookie) = unpack('V V V', substr($r, 0, 12));
    my $crc_ok = crc16(substr($r, 0x10, 236)) == unpack('V', substr($r, 0x0C, 4));
    my ($field, $val2) = unpack('V V', substr($r, 0x14, 8));
    $value = $val2;
    printf "    cmdId=%d func=%d cookie=0x%08x crc=%s\n", $cmdid, $func, $cookie, $crc_ok ? 'OK' : 'BAD';
    printf "    field=%d 当前地区=%d（%s）\n", $field, $val2, $REGIONS{$val2} // '?';
    print  "    u32 dump:" . join('', map { sprintf " +%02x=%d", $_, unpack('V', substr($r, $_, 4)) } (0x10,0x14,0x18,0x1C,0x20)) . "\n";
  }
  return $value; }

print "[*] 连接 $host:30303 ...\n";
print "[*] 步骤一：读取当前 wifiRegion（ProdConfig get）\n";
my $cur = show_reply('GET 应答', transact(build_cmd(2, 0)));

if ($mode eq 'set') {
  printf "\n[*] 步骤二：写入 wifiRegion = %d（%s），发送一次，不重试\n", $val, $REGIONS{$val} // '?';
  show_reply('SET 应答', transact(build_cmd(1, $val)));
  select(undef, undef, undef, 0.5);
  print "\n[*] 步骤三：独立回读校验\n";
  my $now = show_reply('GET 应答', transact(build_cmd(2, 0)));
  if (defined $now && $now == $val) {
    print "\n[√] 写入成功：wifiRegion = $val（" . ($REGIONS{$val}//'?') . "）\n";
    print "[*] 触发相机自动重启（cmd 52 /system/bin/reboot）...\n";
    transact(build_reboot());
    print "[√] 相机正在有序重启，新地区随之生效（热点会断开，重启后按新地区拉起）。\n";
  } else {
    print "\n[?] 回读值与目标不一致或未收到应答，请把上面的输出截图发给排查的人。\n";
    print "[!] 请【完全重启相机】使新地区生效（射频和菜单开机时才重新初始化）。\n";
  }
} else {
  print "\n[*] 只读模式结束。菜单里选 2 可设为 CN（解锁 5G）。\n";
}
PERL_EOF
}

while true; do
  echo ""
  echo "=============================================="
  echo "   X2D / 907 WiFi 地区设置（一键工具）"
  echo "=============================================="
  echo "   1) 查看当前地区（只读，安全）"
  echo "   2) 设为 CN（6）— 解锁 5GHz"
  echo "   3) 设为 JP（8）— 恢复日版（隐藏 5GHz）"
  echo "   0) 退出"
  echo "=============================================="
  read -r -p "请选择 [0-3]: " choice
  echo ""

  case "$choice" in
    1) run_tool get ;;
    2) run_tool set 6 ;;
    3) run_tool set 8 ;;
    0) exit 0 ;;
    *) echo "无效选择"; continue ;;
  esac

  echo ""
  echo "----------------------------------------------"
  read -r -p "完成。按回车键返回菜单（改地区后相机会自动重启生效）..."
done
