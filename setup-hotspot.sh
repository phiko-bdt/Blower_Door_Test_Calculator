#!/bin/bash
# 성적서 공유용 AP(핫스팟)를 NetworkManager 에 설정한다.
#
#   ./setup-hotspot.sh [인터페이스] [SSID] [비밀번호]
#   예) ./setup-hotspot.sh wlan0                 # 납품용(내장 WiFi)
#       ./setup-hotspot.sh wlan1                 # 개발용(USB 동글)
#
# 납품: 인터넷용 USB 동글(wlan1)을 빼고 내장 wlan0 을 AP 로 쓴다. 현장엔 WiFi 가
#       없으니 wlan0 은 인터넷에 안 물리고 오직 파일전송 AP 로만 쓰인다.
# 개발: 동글(wlan1)로 인터넷을 쓰려면 AP 를 wlan0 이 아니라 wlan1 에 두거나,
#       반대로 인터넷을 동글에 두고 AP 를 wlan0 에 둔다(delivery 와 동일 검증).
#
# **인터페이스를 반드시 고정(connection.interface-name)한다** — 안 그러면
# NetworkManager 가 인터넷용 wlan0 에 AP 를 올려 인터넷·원격이 끊긴다.
#
# 원격에서 인터넷이 걸린 인터페이스를 AP 로 바꾸면 그 세션이 끊긴다.
# 콘솔(모니터/키보드)이 있는 상태에서, 또는 인터넷을 다른 인터페이스로
# 옮긴 뒤 실행할 것.
set -e

# 기본값은 실기기·매뉴얼·화면 QR 안내와 같은 값이어야 한다 — 납품 때 인자
# 없이 `./setup-hotspot.sh wlan0` 로 재실행해도 SSID·비번이 어긋나지 않게.
IFACE="${1:-wlan0}"
SSID="${2:-BlowerDoor-Test}"
PASSWORD="${3:-blowerdoor123}"   # WPA 최소 8자
CON="bdt-share"

echo "AP 설정: 인터페이스=$IFACE  SSID=$SSID"

# 기존 연결이 있으면 지우고 다시 만든다 (인터페이스 바뀌었을 수 있으니)
nmcli con delete "$CON" 2>/dev/null || true

nmcli con add type wifi ifname "$IFACE" con-name "$CON" \
    autoconnect yes ssid "$SSID"
nmcli con modify "$CON" \
    connection.interface-name "$IFACE" \
    connection.autoconnect yes \
    connection.autoconnect-priority 10 \
    802-11-wireless.mode ap \
    802-11-wireless.band bg \
    ipv4.method shared \
    wifi-sec.key-mgmt wpa-psk \
    wifi-sec.psk "$PASSWORD"
nmcli con up "$CON"

# 캡티브 포털: 폰이 붙으면 성적서 목록이 자동으로 뜨게 한다.
#  - dnsmasq: AP 망의 모든 도메인을 10.42.0.1 로 (인터넷 확인 요청을 가로챔)
#  - nftables(bdt-captive.service): AP 망 80→8080 리다이렉트
HERE="$(cd "$(dirname "$0")" && pwd)"
if [ -f "$HERE/captive/dnsmasq-captive.conf" ]; then
    sudo cp "$HERE/captive/dnsmasq-captive.conf" /etc/NetworkManager/dnsmasq-shared.d/
    sudo cp "$HERE/bdt-captive.service" /etc/systemd/system/
    sudo systemctl daemon-reload
    sudo systemctl enable --now bdt-captive
    # dnsmasq 새 설정 반영 위해 AP 재시작
    nmcli con down "$CON" 2>/dev/null; sleep 1; nmcli con up "$CON"
    echo "캡티브 포털 설치됨 (폰 붙으면 성적서 목록 자동)."
fi

echo "완료. IP:"
ip -4 addr show "$IFACE" | grep -oE "inet [0-9.]+" | sed 's/^/  /'
echo "폰이 '$SSID'(비번 $PASSWORD)에 붙으면 성적서 목록이 자동으로 뜬다."
