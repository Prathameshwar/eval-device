#!/bin/sh
set -eu
test "$(id -u)" = 0
test "$#" = 1
case "$1" in ''|.|..|*[!0-9A-Za-z._-]*) exit 1;; esac
release="/opt/pi-test/releases/$1"
test "$(realpath "$release")" = "$release"
test ! -e /opt/pi-test/current.next && test ! -L /opt/pi-test/current.next
test -x "$release/bin/pi-test"
"$release/bin/python" -c 'import pi_test.service, training_client.runtime, sounddevice, av, cv2'
previous=$(readlink /opt/pi-test/current)
case "$previous" in /opt/pi-test/releases/*) ;; *) exit 1;; esac
test "$(realpath "$previous")" = "$previous"
systemctl stop pi-test.service
ln -s "$release" /opt/pi-test/current.next
mv -Tf /opt/pi-test/current.next /opt/pi-test/current
if ! systemctl start pi-test.service; then
    ln -s "$previous" /opt/pi-test/current.next
    mv -Tf /opt/pi-test/current.next /opt/pi-test/current
    systemctl start pi-test.service || true
    echo 'Rollback failed; restored the previous executable and preserved state.'
    exit 1
fi
echo 'Executable rolled back. Device identity and queued archives were preserved.'
