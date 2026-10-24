#!/usr/bin/env bash
# Linux CI only. Test children get their own group; the Actions runner keeps network access.
# Allow loopback (including Docker port forwarding), reject IPv4/IPv6 external traffic.
set -euo pipefail

group="agentnest-offline"
chain="AGENTNEST_OFFLINE"
sudo groupadd --system "$group"
gid="$(getent group "$group" | cut -d: -f3)"
cleanup() {
  for firewall in iptables ip6tables; do
    sudo "$firewall" -D OUTPUT -m owner --gid-owner "$gid" -j "$chain" 2>/dev/null || true
    sudo "$firewall" -F "$chain" 2>/dev/null || true
    sudo "$firewall" -X "$chain" 2>/dev/null || true
  done
  sudo groupdel "$group"
}
trap cleanup EXIT

for firewall in iptables ip6tables; do
  sudo "$firewall" -N "$chain"
  sudo "$firewall" -A "$chain" -o lo -j RETURN
  # Docker rewrites localhost:5433 before filter/OUTPUT; retain the original destination.
  if [[ "$firewall" == iptables ]]; then loopback="127.0.0.1"; else loopback="::1"; fi
  sudo "$firewall" -A "$chain" -m conntrack --ctorigdst "$loopback" -j RETURN
  sudo "$firewall" -A "$chain" -j REJECT
  sudo "$firewall" -I OUTPUT 1 -m owner --gid-owner "$gid" -j "$chain"
done

# RunAs-group sudo policy differs between runners. Drop root through setpriv instead;
# retain the original user and supplementary groups, changing only the primary group.
sudo --preserve-env setpriv --reuid="$(id -u)" --regid="$gid" --init-groups env "PATH=$PATH" "$@"
