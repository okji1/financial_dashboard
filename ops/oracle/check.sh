#!/usr/bin/env bash
# Read-only checks. Does not print environments or alter collector ownership.
set -euo pipefail
for name in api web; do
  systemctl is-active "financial-dashboard-$name.service"
done
curl --fail --silent --show-error --max-time 20 http://127.0.0.1:5000/health
curl --fail --silent --show-error --max-time 20 http://127.0.0.1:5000/ready
curl --fail --silent --show-error --max-time 20 https://151-145-41-202.sslip.io/health
curl --fail --silent --show-error --max-time 20 \
  -H 'Origin: https://financial-dashboard-six-chi.vercel.app' \
  --dump-header /dev/stderr https://151-145-41-202.sslip.io/api/gold-premium
