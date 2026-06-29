#!/bin/bash
# Installation DartSystem sur Raspberry Pi 4
set -e

echo "=== DartSystem — Installation ==="

# Dépendances système
sudo apt update
sudo apt install -y python3-pip python3-venv libopencv-dev python3-opencv git

# Virtualenv
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

# Fichiers __init__.py
touch detection/__init__.py
touch detection/cameras/__init__.py
touch detection/calibration/__init__.py
touch detection/detection/__init__.py
touch detection/scoring/__init__.py
touch api/__init__.py
touch api/routes/__init__.py

# Service systemd
sudo tee /etc/systemd/system/dartsystem.service > /dev/null <<EOF
[Unit]
Description=DartSystem API
After=network.target

[Service]
Type=simple
User=pi
WorkingDirectory=$(pwd)
ExecStart=$(pwd)/venv/bin/uvicorn api.main:app --host 0.0.0.0 --port 8080
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable dartsystem
sudo systemctl start dartsystem

echo ""
echo "=== Installation terminée ==="
echo "API disponible sur : http://$(hostname -I | cut -d' ' -f1):8080"
echo "Santé API : http://$(hostname -I | cut -d' ' -f1):8080/health"
