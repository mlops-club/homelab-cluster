#!/usr/bin/env bash
# Purpose: Apply or revert the macOS host settings that let the MacBook run the homelab k3s agent VM 24/7
# Scope: Root-level macOS changes only: power management, socket_vmnet bridge binary, Lima sudoers, boot autostart
# Overview: Idempotent. `apply` snapshots the current pmset settings before changing anything so `revert`
#     restores them exactly. Changes made:
#       1. pmset: never sleep on AC (lid closed included via `disablesleep 1`), no standby/hibernate/powernap,
#          wake on LAN, keep TCP alive, display sleeps after 2 minutes.
#       2. socket_vmnet copied to /opt/socket_vmnet (Lima requires a root-owned binary) and Lima's sudoers file
#          installed so the bridged network can start without a password.
#       3. The `cluster-node-5` Lima instance registered as a LaunchDaemon (starts at boot, KeepAlive restarts it).
#     Battery protection uses macOS's built-in Charge Limit (System Settings > Battery > Charging), not this script.
# Dependencies: Homebrew `lima` and `socket_vmnet` formulae, an existing `cluster-node-5` Lima instance
# Interfaces: sudo ./host-setup.sh apply|revert|pause|status   (pause = stop the VM without uninstalling)   (run as root via sudo; SUDO_USER owns the Lima instance)
# Implementation: LaunchDaemon ${DAEMON_PLIST} mirrors Lima's own boot-autostart template. Backup lives in ~SUDO_USER/.config/homelab-macbook-node/pmset-backup.txt

set -euo pipefail

INSTANCE="cluster-node-5"
ACTION="${1:-status}"
USER_NAME="${SUDO_USER:-$(stat -f %Su /dev/console)}"
USER_HOME="$(dscl . -read "/Users/${USER_NAME}" NFSHomeDirectory | awk '{print $2}')"
STATE_DIR="${USER_HOME}/.config/homelab-macbook-node"
PMSET_BACKUP="${STATE_DIR}/pmset-backup.txt"
LIMACTL="/opt/homebrew/bin/limactl"
VMNET_SRC="/opt/homebrew/opt/socket_vmnet/bin"
VMNET_DST="/opt/socket_vmnet/bin"

DAEMON_LABEL="io.lima-vm.daemon.${INSTANCE}"
DAEMON_PLIST="/Library/LaunchDaemons/${DAEMON_LABEL}.plist"

write_daemon_plist() {
  local workdir="${USER_HOME}/.lima/${INSTANCE}"
  cat >"${DAEMON_PLIST}" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>${DAEMON_LABEL}</string>
  <key>UserName</key><string>${USER_NAME}</string>
  <key>EnvironmentVariables</key>
  <dict>
    <key>LIMA_HOME</key><string>${USER_HOME}/.lima</string>
    <key>HOME</key><string>${USER_HOME}</string>
    <key>PATH</key><string>/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin</string>
  </dict>
  <key>ProgramArguments</key>
  <array>
    <string>${LIMACTL}</string><string>start</string><string>${INSTANCE}</string><string>--foreground</string>
  </array>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
  <key>ThrottleInterval</key><integer>30</integer>
  <key>StandardErrorPath</key><string>${workdir}/launchd.stderr.log</string>
  <key>StandardOutPath</key><string>${workdir}/launchd.stdout.log</string>
  <key>WorkingDirectory</key><string>${workdir}</string>
  <key>ProcessType</key><string>Background</string>
</dict>
</plist>
PLIST
  chmod 644 "${DAEMON_PLIST}"
  plutil -lint "${DAEMON_PLIST}" >/dev/null
}

as_user() { sudo -u "${USER_NAME}" -H "$@"; }

require_root() {
  if [[ "${EUID}" -ne 0 ]]; then
    echo "run with sudo: sudo $0 ${ACTION}" >&2
    exit 1
  fi
}

apply() {
  require_root
  as_user mkdir -p "${STATE_DIR}"
  if [[ ! -f "${PMSET_BACKUP}" ]]; then
    pmset -g custom >"${PMSET_BACKUP}"
    pmset -g | awk '/SleepDisabled/ {print "SleepDisabled", $2}' >>"${PMSET_BACKUP}"
    chown "${USER_NAME}" "${PMSET_BACKUP}"
    echo "saved pmset backup to ${PMSET_BACKUP}"
  fi

  # 1. Power: stay awake on AC with the lid closed. Battery profile keeps normal sleep so an unplugged
  #    laptop still protects itself, except disablesleep which is global by design.
  pmset -c sleep 0 disksleep 0 standby 0 powernap 0 womp 1 tcpkeepalive 1 displaysleep 2 ttyskeepawake 1
  pmset -a disablesleep 1
  pmset -a autorestart 1 2>/dev/null || true

  # 2. socket_vmnet + Lima sudoers for bridged networking.
  mkdir -p "${VMNET_DST}"
  install -o root -g wheel -m 0755 "${VMNET_SRC}/socket_vmnet" "${VMNET_SRC}/socket_vmnet_client" "${VMNET_DST}/"
  as_user "${LIMACTL}" sudoers >/tmp/lima-sudoers.$$
  visudo -cf /tmp/lima-sudoers.$$ >/dev/null
  install -o root -g wheel -m 0440 /tmp/lima-sudoers.$$ /private/etc/sudoers.d/lima
  rm -f /tmp/lima-sudoers.$$

  # 3. Start the VM at boot and restart it if the Lima host agent dies.
  # Mirrors the plist `limactl autostart enable --condition boot` renders, but with unconditional KeepAlive:
  # a guest `poweroff` makes the host agent exit 0, which Lima's SuccessfulExit=false policy would not restart.
  # Written directly because limactl
  # refuses to run as root and its own sudo calls cannot prompt from a non-interactive context.
  if as_user "${LIMACTL}" list -q | grep -qx "${INSTANCE}"; then
    write_daemon_plist
    # Hand the VM over to launchd: a VM started by hand would make `start --foreground` fail.
    if ! launchctl print "system/${DAEMON_LABEL}" >/dev/null 2>&1 &&
      [[ "$(as_user "${LIMACTL}" list "${INSTANCE}" --format '{{.Status}}')" == "Running" ]]; then
      as_user "${LIMACTL}" stop "${INSTANCE}"
    fi
    launchctl bootout "system/${DAEMON_LABEL}" 2>/dev/null || true
    launchctl bootstrap system "${DAEMON_PLIST}"
  else
    echo "instance ${INSTANCE} not found; create it, then re-run apply to register autostart" >&2
  fi
  status
}

revert() {
  require_root
  launchctl bootout "system/${DAEMON_LABEL}" 2>/dev/null || true
  rm -f "${DAEMON_PLIST}"
  rm -f /private/etc/sudoers.d/lima
  rm -rf /opt/socket_vmnet

  pmset -a disablesleep 0
  if [[ -f "${PMSET_BACKUP}" ]]; then
    # Restore each AC/battery value captured by `pmset -g custom`.
    local section=""
    while read -r key value _; do
      case "${key}" in
        "Battery") section="-b" ;;
        "AC") section="-c" ;;
        "SleepDisabled") pmset -a disablesleep "${value}" ;;
        "" | "Sleep" | "hibernatefile") ;;
        *) [[ -n "${section}" && "${value}" =~ ^[0-9]+$ ]] && pmset "${section}" "${key}" "${value}" 2>/dev/null || true ;;
      esac
    done <"${PMSET_BACKUP}"
    echo "restored pmset from ${PMSET_BACKUP}"
  else
    echo "no pmset backup found; only disablesleep was reset" >&2
  fi
  status
}

pause() {
  require_root
  # Unload the daemon and stop the VM until the next `apply` or host reboot (the plist stays installed).
  launchctl bootout "system/${DAEMON_LABEL}" 2>/dev/null || true
  as_user "${LIMACTL}" stop "${INSTANCE}" 2>/dev/null || true
  status
}

status() {
  echo "--- pmset (AC) ---"
  pmset -g custom | sed -n '/AC Power/,$p'
  pmset -g | grep -E "SleepDisabled|autorestart" || true
  echo "--- socket_vmnet ---"
  ls -l "${VMNET_DST}" 2>/dev/null || echo "not installed"
  echo "--- sudoers ---"
  ls -l /private/etc/sudoers.d/lima 2>/dev/null || echo "not installed"
  echo "--- launchd ---"
  launchctl print "system/${DAEMON_LABEL}" 2>/dev/null | grep -E "state =|pid =|last exit" || echo "daemon not loaded"
}

case "${ACTION}" in
  apply) apply ;;
  revert) revert ;;
  pause) pause ;;
  status) status ;;
  *) echo "usage: sudo $0 apply|revert|pause|status" >&2; exit 2 ;;
esac
