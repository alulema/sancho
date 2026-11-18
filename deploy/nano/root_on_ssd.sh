#!/usr/bin/env bash
# T3 of SPEC_E0: the Nano's root filesystem moves to the SSD (ADR-0016).
#
# The bootloader, kernel and initrd stay on the microSD: U-Boot reads
# /boot/extlinux/extlinux.conf there, and the stock L4T initrd mounts the root given
# by root=PARTUUID=…. The microSD system is left intact as the fallback entry.
#
# Usage (none of them reboots):
#   sudo root_on_ssd.sh check      shows the plan; changes nothing
#   sudo root_on_ssd.sh copy       copies the running system to the SSD (repeatable)
#   sudo root_on_ssd.sh switch     final copy, then the SSD becomes the default entry
#   sudo root_on_ssd.sh rollback   the microSD becomes the default entry again
#   root_on_ssd.sh status          where / is mounted and which entry is the default
#
# If the Nano does not boot from the SSD: put the microSD in another Linux machine
# and set "DEFAULT primary" in boot/extlinux/extlinux.conf.
set -euo pipefail

readonly LABEL="sancho-root"
readonly SSD_MOUNT="/mnt/sancho-root"
readonly MICROSD_DEV="/dev/mmcblk0p1"
readonly MICROSD_MOUNT="/mnt/microsd" # where the microSD is mounted once on the SSD
readonly ENTRY="ssd"
readonly FALLBACK="primary"
# Kernel, initrd and bootloader are read from the microSD: if apt updated them on the
# SSD, the modules there would no longer match the kernel that boots.
readonly HELD="nvidia-l4t-kernel nvidia-l4t-kernel-dtbs nvidia-l4t-kernel-headers
nvidia-l4t-initrd nvidia-l4t-bootloader nvidia-l4t-xusb-firmware"

fail() {
    echo "ERROR: $1" >&2
    exit 1
}

need_root() { [[ "$(id -u)" == "0" ]] || fail "must run as root (sudo)"; }

root_source() { findmnt -n -o SOURCE /; }

# The extlinux.conf that U-Boot reads, wherever the system booted from.
extlinux() {
    if [[ "$(root_source)" == "$MICROSD_DEV" ]]; then
        echo "/boot/extlinux/extlinux.conf"
    else
        mountpoint -q "$MICROSD_MOUNT" || fail "the microSD is not mounted at $MICROSD_MOUNT"
        echo "$MICROSD_MOUNT/boot/extlinux/extlinux.conf"
    fi
}

ssd_device() {
    local device
    device="$(blkid -L "$LABEL")" || fail "no partition labeled $LABEL (prepare_ssd.sh)"
    [[ "$(blkid -s TYPE -o value "$device")" == "ext4" ]] || fail "$device is not ext4"
    echo "$device"
}

default_entry() { awk '$1 == "DEFAULT" {print $2}' "$1"; }

preflight() {
    need_root
    grep -q "R32 (release), REVISION: 7" /etc/nv_tegra_release || fail "expected L4T R32.7"
    [[ "$(root_source)" == "$MICROSD_DEV" ]] || fail "/ is not on $MICROSD_DEV: already on the SSD?"
    device="$(ssd_device)"
    partuuid="$(blkid -s PARTUUID -o value "$device")"
    [[ -n "$partuuid" ]] || fail "$device has no PARTUUID"
    microsd_uuid="$(blkid -s UUID -o value "$MICROSD_DEV")"
    mountpoint -q "$SSD_MOUNT" || mount "$SSD_MOUNT"
    [[ "$(findmnt -n -o SOURCE "$SSD_MOUNT")" == "$device" ]] || fail "$SSD_MOUNT is not $device"
    ssd_uuid="$(blkid -s UUID -o value "$device")"
}

# Copies / to the SSD. -x stays on the root filesystem (no /proc, /sys, /dev, /run,
# nor the SSD itself). /var/lib/docker is excluded: Docker's data is already on the
# SSD at that same path (docker_on_ssd.sh), and excluded paths are not deleted.
sync_root() {
    rsync -aAXH --numeric-ids -x --delete --info=stats1 \
        --exclude=/var/lib/docker --exclude=/lost+found --exclude='/tmp/*' \
        / "$SSD_MOUNT/"
}

# What changes on the SSD copy so that it works as the root filesystem.
adapt_copy() {
    local target="$SSD_MOUNT"
    # fstab: no longer mount the SSD at /mnt/sancho-root (it is /); mount the microSD.
    python3 - "$target/etc/fstab" "$ssd_uuid" "$microsd_uuid" "$MICROSD_MOUNT" <<'PY'
import sys
path, ssd_uuid, microsd_uuid, microsd_mount = sys.argv[1:5]
lines = [l for l in open(path).read().splitlines()
         if "UUID=" + ssd_uuid not in l and "UUID=" + microsd_uuid not in l]
lines.append("UUID={} {} ext4 defaults,nofail,x-systemd.device-timeout=10s 0 2".format(
    microsd_uuid, microsd_mount))
open(path, "w").write("\n".join(lines) + "\n")
PY
    mkdir -p "$target$MICROSD_MOUNT"
    # Docker: back to its default /var/lib/docker, which on the SSD is the same data.
    rm -f "$target/etc/systemd/system/docker.service.d/sancho-ssd.conf"
    python3 - "$target/etc/docker/daemon.json" <<'PY'
import json, sys
path = sys.argv[1]
config = json.load(open(path))
config.pop("data-root", None)
with open(path, "w") as f:
    json.dump(config, f, indent=4)
    f.write("\n")
PY
    for package in $HELD; do
        echo "$package hold"
    done | dpkg --root="$target" --set-selections
    cat > "$target/etc/sancho-root" <<EOF
Root filesystem on the SSD (ADR-0016). Copied from $MICROSD_DEV on $(date -u +%FT%TZ).
Kernel, initrd and extlinux.conf are read from the microSD: $MICROSD_MOUNT/boot.
EOF
}

# Adds the SSD entry (a copy of the primary one with another root=) and makes it the
# default. The primary entry stays untouched as the fallback.
write_entry() {
    local conf="$1"
    [[ -f "$conf.sancho-backup" ]] || cp "$conf" "$conf.sancho-backup"
    python3 - "$conf" "$ENTRY" "$FALLBACK" "$partuuid" <<'PY'
import re, sys
path, entry, fallback, partuuid = sys.argv[1:5]
text = open(path).read()
blocks = re.split(r"(?m)^LABEL ", text)  # Python 3.6: no split on empty matches
head, labels = blocks[0], ["LABEL " + b for b in blocks[1:]]
names = [b.split()[1] for b in labels]
if fallback not in names:
    sys.exit("no LABEL {} in {}".format(fallback, path))
primary = labels[names.index(fallback)]
primary_body = primary.split("\n\n")[0].rstrip("\n") + "\n"
ssd = re.sub(r"^LABEL \S+", "LABEL " + entry, primary_body, flags=re.M)
ssd = re.sub(r"MENU LABEL .*", "MENU LABEL Sancho: root on the SSD", ssd)
ssd, n = re.subn(r"root=\S+", "root=PARTUUID=" + partuuid, ssd)
if n != 1:
    sys.exit("expected one root= in LABEL " + fallback)
labels = [b for b, name in zip(labels, names) if name != entry]
head = re.sub(r"(?m)^DEFAULT .*$", "DEFAULT " + entry, head)
open(path, "w").write(head + ssd + "\n" + "".join(labels))
PY
}

cmd_check() {
    preflight
    local conf
    conf="$(extlinux)"
    echo "Root now:        $(root_source)"
    echo "SSD partition:   $device  UUID=$ssd_uuid  PARTUUID=$partuuid"
    echo "microSD:         $MICROSD_DEV  UUID=$microsd_uuid"
    echo "extlinux.conf:   $conf (DEFAULT $(default_entry "$conf"))"
    echo "Space:           $(df -h --output=used / | tail -1 | tr -d ' ') used on /," \
        "$(df -h --output=avail "$SSD_MOUNT" | tail -1 | tr -d ' ') free on the SSD"
    echo "Docker data:     $(du -sh "$SSD_MOUNT/var/lib/docker" 2>/dev/null | cut -f1) on the SSD (kept)"
    echo "Held packages:   $(echo $HELD)"
    echo
    echo "Nothing was changed. Next: sudo $0 copy"
}

cmd_copy() {
    preflight
    sync_root
    adapt_copy
    echo "Copied. The Nano still boots from the microSD. Next: sudo $0 switch"
}

cmd_switch() {
    preflight
    [[ -f "$SSD_MOUNT/etc/sancho-root" ]] || fail "run '$0 copy' first"
    systemctl stop docker docker.socket # nothing writes while the last copy runs
    sync_root
    adapt_copy
    write_entry "$(extlinux)"
    sync
    echo "DEFAULT is now '$ENTRY' (root=PARTUUID=$partuuid); '$FALLBACK' is kept."
    echo "Docker is stopped until the reboot. Reboot with: sudo reboot"
}

cmd_rollback() {
    need_root
    local conf
    conf="$(extlinux)"
    [[ -f "$conf.sancho-backup" ]] || fail "no $conf.sancho-backup: nothing to roll back"
    sed -i "s/^DEFAULT .*/DEFAULT $FALLBACK/" "$conf"
    sync
    echo "DEFAULT is now '$FALLBACK' (microSD). Reboot with: sudo reboot"
}

cmd_status() {
    echo "Root: $(root_source)"
    local conf
    conf="$(extlinux)"
    echo "Default entry in $conf: $(default_entry "$conf")"
}

case "${1:-}" in
check) cmd_check ;;
copy) cmd_copy ;;
switch) cmd_switch ;;
rollback) cmd_rollback ;;
status) cmd_status ;;
*) fail "usage: $0 check|copy|switch|rollback|status" ;;
esac
