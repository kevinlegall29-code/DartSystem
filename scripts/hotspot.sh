#!/bin/bash
# Crée un hotspot Wi-Fi autonome sur le Raspberry Pi (Bookworm / NetworkManager).
# Les tablettes/téléphones/PC se connectent directement au Pi, sans box internet.
#
# Usage : bash scripts/hotspot.sh [SSID] [MOT_DE_PASSE]
set -e

SSID="${1:-DartSystem}"
PASSWORD="${2:-darts12345}"   # 8 caractères minimum
CON="dartsystem-hotspot"

echo "=== Configuration Hotspot Wi-Fi (NetworkManager) ==="

# Supprime un éventuel ancien hotspot du même nom
sudo nmcli connection delete "$CON" 2>/dev/null || true

# Crée la connexion point d'accès
sudo nmcli connection add type wifi ifname wlan0 con-name "$CON" autoconnect yes ssid "$SSID"
sudo nmcli connection modify "$CON" \
    802-11-wireless.mode ap \
    802-11-wireless.band bg \
    ipv4.method shared \
    wifi-sec.key-mgmt wpa-psk \
    wifi-sec.psk "$PASSWORD"

# Active le hotspot
sudo nmcli connection up "$CON"

IP=$(nmcli -g IP4.ADDRESS device show wlan0 | cut -d/ -f1 | head -1)
echo ""
echo "=== Hotspot actif ==="
echo "SSID     : $SSID"
echo "Password : $PASSWORD"
echo "IP du Pi : ${IP:-10.42.0.1}"
echo ""
echo "Sur ton téléphone/PC : connecte-toi au Wi-Fi '$SSID'"
echo "Puis ouvre : http://${IP:-10.42.0.1}:8080"
echo ""
echo "Le hotspot redémarre automatiquement à chaque boot du Pi."
