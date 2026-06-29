#!/bin/bash
# Fixe l'exposition identique sur les 3 caméras OV9732
# Appelé avant le démarrage du service dartsystem

EXPOSURE=${1:-300}

for dev in /dev/video0 /dev/video1 /dev/video2; do
    if [ -e "$dev" ]; then
        v4l2-ctl -d "$dev" --set-ctrl=auto_exposure=1 2>/dev/null
        v4l2-ctl -d "$dev" --set-ctrl=exposure_time_absolute=$EXPOSURE 2>/dev/null
        echo "Exposition $EXPOSURE sur $dev"
    fi
done
