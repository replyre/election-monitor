#!/usr/bin/env bash
# Install deploy/env/*.env (and backup.conf) on the VM as root-only files.
# The contents travel as run-command *protected* parameters: encrypted, never
# echoed, never stored in the run's output.
#   RG=giridih-prod VM=giridih-vm ./deploy/vm/push-env.sh
set -euo pipefail
RG="${RG:-giridih-prod}"; VM="${VM:-giridih-vm}"
ENV_DIR="$(cd "$(dirname "$0")/.." && pwd)/env"
args=()
b64() { base64 < "$1" | tr -d '\n'; }
for f in api jobs; do
    [[ -f "$ENV_DIR/$f.env" ]] || { echo "missing $ENV_DIR/$f.env"; exit 1; }
    args+=("ENV_$(echo "$f" | tr a-z A-Z)=$(b64 "$ENV_DIR/$f.env")")
done
# Optional until a domain and tunnel exist / backups are configured.
[[ -f "$ENV_DIR/cloudflared.env" ]] && args+=("ENV_CLOUDFLARED=$(b64 "$ENV_DIR/cloudflared.env")")
[[ -f "$ENV_DIR/pulse.env" ]] && args+=("ENV_PULSE=$(b64 "$ENV_DIR/pulse.env")")
[[ -f "$ENV_DIR/backup.conf" ]] && args+=("ENV_BACKUP=$(b64 "$ENV_DIR/backup.conf")")

script='set -eu
umask 077
install -d -m 0700 /opt/giridih/env
w() { [ -n "$2" ] && printf %s "$2" | base64 -d > "/opt/giridih/env/$1" && chmod 600 "/opt/giridih/env/$1" && echo "wrote $1"; }
w api.env "$ENV_API"; w jobs.env "$ENV_JOBS"
w cloudflared.env "${ENV_CLOUDFLARED:-}" || true
w pulse.env "${ENV_PULSE:-}" || true
w backup.conf "${ENV_BACKUP:-}" || true'

az vm run-command create -g "$RG" --vm-name "$VM" --name push-env --script "$script" \
    --protected-parameters "${args[@]}" --async-execution false --timeout-in-seconds 120 -o none
az vm run-command show -g "$RG" --vm-name "$VM" --name push-env --instance-view \
    --query 'instanceView.{state:executionState, out:output, err:error}' -o yaml
az vm run-command delete -g "$RG" --vm-name "$VM" --name push-env --yes -o none
