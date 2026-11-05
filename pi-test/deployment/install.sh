#!/bin/sh
# Install from a reviewed, complete ARM64 wheelhouse. No model downloads or source builds.
set -eu
test "$(id -u)" = 0 || { echo 'Run as root'; exit 1; }
test "$#" = 2 || { echo 'Usage: install.sh VERSION WHEELHOUSE'; exit 1; }
version=$1
case "$version" in ''|.|..|*[!0-9A-Za-z._-]*) echo 'Invalid version'; exit 1;; esac
test "$(uname -m)" = aarch64 || { echo 'This installer targets ARM64 Raspberry Pi OS'; exit 1; }
python3 -c 'import sys; assert (3,12) <= sys.version_info[:2] < (3,14), "Python 3.12/3.13 required"'
wheelhouse=$(realpath "$2")
test -d "$wheelhouse"
base=/opt/pi-test
release="$base/releases/$version"
test ! -L "$base" && test ! -L "$base/releases" || { echo 'Release root must not be a symlink'; exit 1; }
test ! -e "$base/current.next" && test ! -L "$base/current.next" || { echo 'Interrupted update marker exists; inspect it before retrying'; exit 1; }
test ! -e "$release" && test ! -L "$release" || { echo 'Release already exists; choose a new version'; exit 1; }
here=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
getent group pi-test >/dev/null || groupadd --system pi-test
id pi-test >/dev/null 2>&1 || useradd --system --gid pi-test --home-dir /var/lib/pi-test --shell /usr/sbin/nologin pi-test
for group in audio video render; do
    getent group "$group" >/dev/null || groupadd --system "$group"
    usermod -a -G "$group" pi-test
done
install -d -m 0755 "$base/releases"
install -d -m 0700 -o pi-test -g pi-test /var/lib/pi-test
install -d -m 0750 -o root -g pi-test /etc/pi-test
if test ! -e /etc/pi-test/config.toml; then
    install -m 0640 -o root -g pi-test "$here/config.example.toml" /etc/pi-test/config.toml
fi
python3 -m venv "$release"
"$release/bin/python" -m pip install --no-index --only-binary=:all: --require-hashes --find-links "$wheelhouse" -r "$wheelhouse/release-requirements.txt"
"$release/bin/python" -c 'import importlib.metadata,sys; assert importlib.metadata.version("pi-test") == sys.argv[1]' "$version"
"$release/bin/python" -c 'import pi_test.service, training_client.runtime, sounddevice, av, cv2'
test ! -e "$base/current" || test -L "$base/current" || { echo 'Current release marker is not a symlink'; exit 1; }
previous=$(readlink "$base/current" || true)
if test -n "$previous"; then
    case "$previous" in "$base"/releases/*) ;; *) echo 'Current release is outside the release root'; exit 1;; esac
    test "$(realpath "$previous")" = "$previous" || { echo 'Current release contains redirects'; exit 1; }
fi
unit=/etc/systemd/system/pi-test.service
test ! -L "$unit" || { echo 'Service unit must not be a symlink'; exit 1; }
unit_backup=
if test -e "$unit"; then
    unit_backup=$(mktemp "$base/.pi-test-unit.XXXXXXXX")
    cp -p "$unit" "$unit_backup"
fi
was_active=0
if systemctl is-active --quiet pi-test.service; then was_active=1; fi
was_enabled=0
if systemctl is-enabled --quiet pi-test.service; then was_enabled=1; fi
switch_started=0
enable_started=0
recover() {
    status=$?
    trap - 0 1 2 3 15
    if test "$status" -ne 0 && test "$switch_started" = 1; then
        set +e
        restored=1
        systemctl stop pi-test.service || restored=0
        rm -f "$base/current.next" || restored=0
        if test -n "$previous"; then
            ln -s "$previous" "$base/current.next" && mv -Tf "$base/current.next" "$base/current" || restored=0
        else
            rm -f "$base/current" || restored=0
        fi
        if test "$was_enabled" = 0 && test "$enable_started" = 1; then systemctl disable pi-test.service || restored=0; fi
        if test -n "$unit_backup"; then cp -p "$unit_backup" "$unit" || restored=0; else rm -f "$unit" || restored=0; fi
        systemctl daemon-reload || restored=0
        if test "$was_enabled" = 1; then systemctl enable pi-test.service || restored=0; fi
        if test "$was_active" = 1; then systemctl start pi-test.service || restored=0; fi
        if test "$restored" = 1; then
            echo 'Update failed; previous service configuration and release were restored.' >&2
        else
            echo "Update failed and rollback was incomplete; inspect $unit_backup, $unit and $base/current." >&2
            exit "$status"
        fi
    fi
    if test -n "$unit_backup"; then rm -f "$unit_backup"; fi
    exit "$status"
}
trap recover 0
trap 'exit 1' 1 2 3 15
if test -e /etc/systemd/system/pi-test.service || test -n "$previous"; then
    # A failed stop must not switch an active device to a different release.
    switch_started=1
    systemctl stop pi-test.service
fi
switch_started=1
install -m 0644 "$here/pi-test.service" "$unit"
ln -s "$release" "$base/current.next"
mv -Tf "$base/current.next" "$base/current"
systemctl daemon-reload
enable_started=1
systemctl enable pi-test.service
systemctl start pi-test.service
echo 'Installed. Edit configuration, enroll the device, then restart. Boot does not capture.'
