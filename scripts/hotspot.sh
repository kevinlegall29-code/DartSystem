#!/bin/bash
# Configure le Raspberry Pi en point d'accès Wi-Fi autonome
# Les tablettes/téléphones se connectent directement au RPi, sans box Internet
set -e

SSID="DartSystem"
PASSWORD="darts1234"
IP="192.168.50.1"

echo "=== Configuration Hotspot Wi-Fi ==="

sudo apt install -y hostapd dnsmasq

# Configuration hostapd
sudo tee /etc/hostapd/hostapd.conf > /dev/null <<EOF
interface=wlan0
driver=nl80211
ssid=$SSID
hw_mode=g
channel=7
wmm_enabled=0
macaddr_acl=0
auth_algs=1
wpa=2
wpa_passphrase=$PASSWORD
wpa_key_mgmt=WPA-PSK
rsn_pairwise=CCMP
EOF

sudo sed -i 's|#DAEMON_CONF=""|DAEMON_CONF="/etc/hostapd/hostapd.conf"|' /etc/default/hostapd

# IP statique
sudo tee -a /etc/dhcpcd.conf > /dev/null <<EOF
interface wlan0
    static ip_address=$IP/24
    nohook wpa_supplicant
EOF

# DHCP pour les clients
sudo tee /etc/dnsmasq.conf > /dev/null <<EOF
interface=wlan0
dhcp-range=192.168.50.10,192.168.50.50,255.255.255.0,24h
EOF

sudo systemctl unmask hostapd
sudo systemctl enable hostapd
sudo systemctl restart hostapd
sudo systemctl restart dnsmasq

echo ""
echo "=== Hotspot configuré ==="
echo "SSID     : $SSID"
echo "Password : $PASSWORD"
echo "IP RPi   : $IP"
echo "API URL  : http://$IP:8080"
