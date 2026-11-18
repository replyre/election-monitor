#!/usr/bin/env bash
# Print one self-contained script that installs the current deploy files on the
# VM, enables the job timers and runs deploy.sh. Sent with
# `az vm run-command create`, whose parameters arrive as environment variables:
#   IMAGE_TAG (required), REGISTRY (optional), GHCR_TOKEN/GHCR_USER (protected).
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"


cat <<'HEAD'
#!/usr/bin/env bash
set -euo pipefail
: "${IMAGE_TAG:?IMAGE_TAG parameter is required}"
put() { base64 -d | install -D -m "$2" /dev/stdin "$1"; }
HEAD

for spec in \
    "$HERE/../docker-compose.prod.yml:/opt/giridih/docker-compose.prod.yml:0644" \
    "$HERE/deploy.sh:/opt/giridih/deploy.sh:0750" \
    "$HERE/run-job.sh:/opt/giridih/run-job.sh:0750" \
    "$HERE/backup-upload.sh:/opt/giridih/backup-upload.sh:0750"; do
    IFS=: read -r src dst mode <<<"$spec"
    echo "put $dst $mode <<'B64'"; base64 < "$src"; echo "B64"
done
for unit in "$HERE"/systemd/*; do
    echo "put /etc/systemd/system/$(basename "$unit") 0644 <<'B64'"; base64 < "$unit"; echo "B64"
done

cat <<'TAIL'
systemctl daemon-reload
systemctl enable --now giridih-news.timer giridih-refresh.timer giridih-backup.timer >/dev/null
export REGISTRY="${REGISTRY:-ghcr.io/replyre}"
/opt/giridih/deploy.sh "$IMAGE_TAG"
TAIL
