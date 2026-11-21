#!/usr/bin/env bash
# Copy the newest pg_dump to private Azure Blob storage with the VM's managed
# identity: no storage key on the machine. The container's lifecycle policy
# deletes blobs after 30 days; the dump directory keeps 14 days locally.
set -euo pipefail
. /opt/giridih/env/backup.conf          # STORAGE_ACCOUNT=..., CONTAINER=...
latest="$(ls -1t /var/lib/giridih/backups/giridih-*.sql.gz 2>/dev/null | head -1)"
[[ -n "$latest" ]] || { echo "no backup file to upload"; exit 1; }

token="$(curl -fsS -H Metadata:true \
  'http://169.254.169.254/metadata/identity/oauth2/token?api-version=2018-02-01&resource=https%3A%2F%2Fstorage.azure.com%2F' \
  | python3 -c 'import json,sys; print(json.load(sys.stdin)["access_token"])')"

curl -fsS -X PUT -T "$latest" \
  -H "Authorization: Bearer $token" \
  -H "x-ms-version: 2021-08-06" \
  -H "x-ms-blob-type: BlockBlob" \
  -H "Content-Type: application/gzip" \
  "https://${STORAGE_ACCOUNT}.blob.core.windows.net/${CONTAINER}/$(basename "$latest")"
echo "uploaded $(basename "$latest") ($(stat -c %s "$latest") bytes)"
