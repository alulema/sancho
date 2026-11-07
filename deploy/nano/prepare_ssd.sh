#!/usr/bin/env bash
# Erases the Nano's SSD and creates the system partition for T3 of SPEC_E0.
# The rest of the disk stays unallocated for the encrypted partitions of E1.
#
# Usage: prepare_ssd.sh <device>         checks the device and prints the plan
#        sudo prepare_ssd.sh <device> --yes   erases it
set -euo pipefail
shopt -s nullglob

readonly EXPECTED_VENDOR="HIKSEMI"
readonly EXPECTED_MODEL="MD202"
readonly EXPECTED_SECTORS="488397168"
readonly ROOT_SIZE="100G"
readonly ROOT_LABEL="sancho-root"

fail() {
    echo "ERROR: $1" >&2
    exit 1
}

device="${1:-}"
confirm="${2:-}"
[[ "$device" =~ ^/dev/sd[a-z]$ ]] || fail "expected a whole disk such as /dev/sda, got '$device'"
[[ -b "$device" ]] || fail "$device is not a block device"

sysfs="/sys/block/$(basename "$device")"
vendor="$(tr -d ' ' < "$sysfs/device/vendor")"
model="$(tr -d ' ' < "$sysfs/device/model")"
sectors="$(cat "$sysfs/size")"
[[ "$vendor" == "$EXPECTED_VENDOR" ]] || fail "vendor is '$vendor', expected '$EXPECTED_VENDOR'"
[[ "$model" == "$EXPECTED_MODEL" ]] || fail "model is '$model', expected '$EXPECTED_MODEL'"
[[ "$sectors" == "$EXPECTED_SECTORS" ]] || fail "size is $sectors sectors, expected $EXPECTED_SECTORS"

mounts="$(lsblk -nro MOUNTPOINT "$device" | sed '/^$/d')"
[[ -z "$mounts" ]] || fail "$device is in use: $mounts"

echo "Disk verified: $vendor $model, $sectors sectors, not mounted."
lsblk -o NAME,SIZE,TYPE,FSTYPE,MOUNTPOINT "$device"
echo "Plan: erase $device, GPT, ${device}1 = $ROOT_SIZE ext4 '$ROOT_LABEL', rest unallocated."

if [[ "$confirm" != "--yes" ]]; then
    echo "Nothing was changed. Run as root with --yes to erase."
    exit 0
fi
[[ "$(id -u)" == "0" ]] || fail "--yes must run as root"

wipefs --all "${device}"?* "$device"
sgdisk --zap-all "$device"
sgdisk --new="1:0:+$ROOT_SIZE" --change-name="1:$ROOT_LABEL" "$device"
partprobe "$device"
udevadm settle
mkfs.ext4 -F -L "$ROOT_LABEL" "${device}1"

lsblk -o NAME,SIZE,TYPE,FSTYPE,LABEL,UUID,MOUNTPOINT "$device"
