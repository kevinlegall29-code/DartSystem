#!/bin/bash
# Désactive le hotspot et laisse NetworkManager se reconnecter au Wi-Fi maison.
set -e

CON="dartsystem-hotspot"

echo "=== Désactivation du hotspot ==="
sudo nmcli connection down "$CON" 2>/dev/null || true
sudo nmcli connection modify "$CON" autoconnect no 2>/dev/null || true

# Réactive la connexion automatique aux réseaux Wi-Fi connus
sudo nmcli radio wifi on
echo "Hotspot désactivé. Le Pi va se reconnecter au Wi-Fi maison."
echo "Réseaux connus :"
nmcli -g NAME,TYPE connection show | grep wireless || true
