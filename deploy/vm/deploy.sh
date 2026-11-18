#!/usr/bin/env bash
# Roll the stack forward to one image tag, or back to the last good one.
#
#   /opt/giridih/deploy.sh <git-sha>
#
# Order matters: migrations (which also let giridih_app sign in) and the login
# bootstrap run with the NEW jobs image before the API switches over; then the
# API and web restart, and the release only counts once /api/health answers
# through nginx. Anything failing after the switch puts the previous tag back.
set -euo pipefail

TAG="${1:?usage: deploy.sh <image tag>}"
ROOT=/opt/giridih
STATE="$ROOT/state"
cd "$ROOT"
mkdir -p "$STATE"

PREV="$(cat "$STATE/current_tag" 2>/dev/null || true)"
compose() { IMAGE_TAG="$1" docker compose -f "$ROOT/docker-compose.prod.yml" "${@:2}"; }
# The tunnel joins once its token is installed; until then the stack runs
# privately (nothing can reach it either way: no port is published).
SERVICES=(api web)
if [[ -s "$ROOT/env/cloudflared.env" ]]; then SERVICES+=(cloudflared); fi
log() { echo "[deploy $(date -u +%H:%M:%S)] $*"; }

if [[ -n "${GHCR_TOKEN:-}" ]]; then
    echo "$GHCR_TOKEN" | docker login ghcr.io -u "${GHCR_USER:-deploy}" --password-stdin >/dev/null
fi

log "pulling $TAG (previous: ${PREV:-none})"
compose "$TAG" --profile jobs pull --quiet api web jobs

log "migrations"
compose "$TAG" --profile jobs run --rm --entrypoint python jobs -m db.apply_migrations
log "login bootstrap"
compose "$TAG" --profile jobs run --rm --entrypoint python jobs -m scripts.ensure_single_user

healthy() {
    local deadline=$((SECONDS + 120))
    while (( SECONDS < deadline )); do
        if compose "$1" exec -T web wget -qO- http://127.0.0.1:8080/api/health 2>/dev/null \
                | grep -q '"database":true'; then
            return 0
        fi
        sleep 3
    done
    return 1
}

log "switching to $TAG"
compose "$TAG" up -d --remove-orphans "${SERVICES[@]}"
if healthy "$TAG"; then
    echo "$TAG" > "$STATE/current_tag"
    [[ -n "$PREV" && "$PREV" != "$TAG" ]] && echo "$PREV" > "$STATE/previous_tag"
    log "healthy on $TAG"
else
    log "health check failed on $TAG"
    compose "$TAG" logs --tail 80 api web || true
    if [[ -n "$PREV" ]]; then
        log "rolling back to $PREV"
        compose "$PREV" up -d --remove-orphans "${SERVICES[@]}"
        healthy "$PREV" && log "back on $PREV" || log "ROLLBACK ALSO UNHEALTHY"
    fi
    exit 1
fi

# Keep the current and previous images for rollback; drop the rest.
keep="$TAG|${PREV:-none}"
docker images --format '{{.Repository}}:{{.Tag}}' \
    | grep -E '/election-monitor-(api|web|jobs):' \
    | grep -vE ":($keep)$" \
    | xargs -r docker rmi >/dev/null 2>&1 || true
docker image prune -f >/dev/null
docker logout ghcr.io >/dev/null 2>&1 || true
