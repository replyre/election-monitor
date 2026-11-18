#!/usr/bin/env bash
# Run scheduled jobs in the jobs image of the release that is live now.
#   /opt/giridih/run-job.sh news.crawl [analytics.refresh ...]
set -euo pipefail
ROOT=/opt/giridih
TAG="$(cat "$ROOT/state/current_tag")"
status=0
for job in "$@"; do
    IMAGE_TAG="$TAG" docker compose -f "$ROOT/docker-compose.prod.yml" --profile jobs \
        run --rm jobs "$job" || status=1
done
exit "$status"
