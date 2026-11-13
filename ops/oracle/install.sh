#!/usr/bin/env bash
# Oracle Linux 9 host setup. Installs files only; starts no services/collectors.
set -euo pipefail
umask 027
if [[ $EUID -ne 0 ]]; then
  echo 'Run with sudo bash ops/oracle/install.sh' >&2
  exit 1
fi
source /etc/os-release
if [[ ${ID:-} != ol || ${VERSION_ID%%.*} != 9 ]]; then
  echo 'This installer requires Oracle Linux 9.' >&2
  exit 1
fi
repo=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd -P)
# Trust this explicitly selected checkout for this invocation only (sudo/owner).
revision=$(git -c safe.directory="$repo" -C "$repo" rev-parse --verify HEAD)
base=/opt/financial-dashboard
release=$base/releases/$revision
if [[ -e $base/current || -L $base/current ]]; then
  echo 'An installation already exists. Use the documented release update procedure.' >&2
  exit 1
fi
dnf install -y python3.12 python3.12-pip git podman
if ! getent passwd financial-dashboard >/dev/null; then
  useradd --system --home-dir /var/lib/financial-dashboard --shell /sbin/nologin financial-dashboard
fi
install -d -m 0755 "$base/releases" "$release"
git -c safe.directory="$repo" -C "$repo" archive "$revision" backend ops/oracle | tar -xf - -C "$release"
python3.12 -m venv "$release/venv"
"$release/venv/bin/python" -m pip install --no-cache-dir -r "$release/backend/requirements.txt"
"$release/venv/bin/python" -m compileall -q "$release/backend"
chgrp -R financial-dashboard "$release"
chmod -R g+rX "$release"
# This HTTPS proxy image has Linux ARM64 and AMD64 variants. Persist ACME data.
podman pull docker.io/library/caddy:2
install -d -m 0700 /etc/financial-dashboard
if [[ ! -f /etc/financial-dashboard/backend.env ]]; then
  install -m 0600 "$release/ops/oracle/backend.env.example" /etc/financial-dashboard/backend.env
fi
if [[ ! -f /etc/financial-dashboard/web.env ]]; then
  printf '%s\n' 'DASHBOARD_HOST=151-145-41-202.sslip.io' > /etc/financial-dashboard/web.env
  chmod 0600 /etc/financial-dashboard/web.env
fi
install -m 0644 "$release/ops/oracle/Caddyfile" /etc/financial-dashboard/Caddyfile
for name in api collector web; do
  install -m 0644 "$release/ops/oracle/financial-dashboard-$name.service" /etc/systemd/system/
done
ln -s "$release" "$base/current"
systemctl daemon-reload
echo 'Installed. No services were started or enabled; no firewall rules changed.'
echo 'Next: sudoedit /etc/financial-dashboard/backend.env'
