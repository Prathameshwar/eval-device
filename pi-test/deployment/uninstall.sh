#!/bin/sh
# Stop and unregister only. Identity, media and releases require deliberate separate removal.
set -eu
test "$(id -u)" = 0
systemctl disable --now pi-test.service
rm -f /etc/systemd/system/pi-test.service
systemctl daemon-reload
echo 'Service removed. Private state, configuration and release files were preserved.'
