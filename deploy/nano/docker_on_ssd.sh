#!/usr/bin/env bash
# Provisional until T3 of SPEC_E0: mounts the SSD system partition and moves Docker's
# data there, so container tests (T2) have room while the root filesystem stays on the
# microSD. T3 undoes this: the mount, the data-root setting and the drop-in go away,
# and images are pulled again.
#
# Usage: sudo docker_on_ssd.sh   (run prepare_ssd.sh first)
set -euo pipefail

readonly LABEL="sancho-root"
readonly MOUNT_POINT="/mnt/sancho-root"
readonly DATA_ROOT="$MOUNT_POINT/var/lib/docker"
readonly DAEMON_JSON="/etc/docker/daemon.json"
readonly DROP_IN="/etc/systemd/system/docker.service.d/sancho-ssd.conf"

fail() {
    echo "ERROR: $1" >&2
    exit 1
}

[[ "$(id -u)" == "0" ]] || fail "must run as root"
device="$(blkid -L "$LABEL")" || fail "no partition labeled $LABEL; run prepare_ssd.sh first"
[[ "$(blkid -s TYPE -o value "$device")" == "ext4" ]] || fail "$device is not ext4"
uuid="$(blkid -s UUID -o value "$device")"

mkdir -p "$MOUNT_POINT"
if ! grep -q "UUID=$uuid" /etc/fstab; then
    cp /etc/fstab /etc/fstab.sancho-backup
    echo "UUID=$uuid $MOUNT_POINT ext4 defaults,nofail,x-systemd.device-timeout=10s 0 2" >> /etc/fstab
fi
mountpoint -q "$MOUNT_POINT" || mount "$MOUNT_POINT"
mkdir -p "$DATA_ROOT"

# Docker must not start without the SSD, or it would write its data to the microSD.
mkdir -p "$(dirname "$DROP_IN")"
printf '[Unit]\nRequiresMountsFor=%s\n' "$MOUNT_POINT" > "$DROP_IN"

[[ -f "$DAEMON_JSON.sancho-backup" || ! -f "$DAEMON_JSON" ]] || cp "$DAEMON_JSON" "$DAEMON_JSON.sancho-backup"
python3 - "$DAEMON_JSON" "$DATA_ROOT" <<'PY'
import json
import os
import sys

path, data_root = sys.argv[1], sys.argv[2]
config = {}
if os.path.exists(path):
    with open(path) as f:
        config = json.load(f)
config["data-root"] = data_root
with open(path, "w") as f:
    json.dump(config, f, indent=4)
    f.write("\n")
PY

systemctl daemon-reload
systemctl restart docker
echo "Docker root: $(docker info --format '{{.DockerRootDir}}')"
df -h "$MOUNT_POINT"
