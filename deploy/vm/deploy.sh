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
# The named tunnel runs once its token is installed. Until then the temporary
# quick tunnel (docker-compose.quicktunnel.yml) serves the app, if present.
# Either way no port is published.
FILES=(-f "$ROOT/docker-compose.prod.yml")
SERVICES=(api web)
if [[ -s "$ROOT/env/cloudflared.env" ]]; then
    SERVICES+=(cloudflared)
elif [[ -f "$ROOT/docker-compose.quicktunnel.yml" ]]; then
    FILES+=(-f "$ROOT/docker-compose.quicktunnel.yml")
    SERVICES+=(quicktunnel)
fi
# The field service runs once its settings (bot token and roles) are installed.
PULSE=0
CORE_SERVICES=("${SERVICES[@]}")
if [[ -s "$ROOT/env/pulse.env" ]]; then
    PULSE=1
    SERVICES+=(pulse-api pulse-bot pulse-worker)
    install -d -m 0700 -o 10003 -g 10003 /var/lib/giridih/pulse-media
fi
compose() { IMAGE_TAG="$1" docker compose "${FILES[@]}" "${@:2}"; }
log() { echo "[deploy $(date -u +%H:%M:%S)] $*"; }

if [[ -n "${GHCR_TOKEN:-}" ]]; then
    echo "$GHCR_TOKEN" | docker login ghcr.io -u "${GHCR_USER:-deploy}" --password-stdin >/dev/null
fi

log "pulling $TAG (previous: ${PREV:-none})"
compose "$TAG" --profile jobs pull --quiet api web jobs
(( PULSE )) && compose "$TAG" --profile jobs pull --quiet pulse-api

log "migrations"
compose "$TAG" --profile jobs run --rm --entrypoint python jobs -m db.apply_migrations
log "admin allow-list bootstrap"
compose "$TAG" --profile jobs run --rm --entrypoint python jobs -m scripts.ensure_admins
if (( PULSE )); then
    log "field service migrations"
    compose "$TAG" --profile jobs run --rm pulse-tools pulse.migrate
fi

healthy() {   # healthy <tag> <pulse 0|1>
    local deadline=$((SECONDS + 120))
    while (( SECONDS < deadline )); do
        if compose "$1" exec -T web wget -qO- http://127.0.0.1:8080/api/health 2>/dev/null \
                | grep -q '"database":true' \
           && { (( ! $2 )) || compose "$1" exec -T pulse-api python -c \
                "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/healthz', timeout=4)" \
                >/dev/null 2>&1; }; then
            return 0
        fi
        sleep 3
    done
    return 1
}

# Pulse's own go-live gate: secrets, migrations, media store, Telegram, and a
# finished worker run (so it waits for the worker's first cycle).
preflight() {
    local deadline=$((SECONDS + 180)) out=""
    while (( SECONDS < deadline )); do
        if out="$(compose "$1" --profile jobs run --rm pulse-tools scripts.preflight 2>&1)"; then
            echo "$out" | grep -E "OK|WARN" | sed 's/^/    /'
            return 0
        fi
        sleep 15
    done
    echo "$out" | sed 's/^/    /'
    return 1
}

log "switching to $TAG"
compose "$TAG" up -d --remove-orphans "${SERVICES[@]}"
if healthy "$TAG" "$PULSE" && { (( ! PULSE )) || { log "field service preflight"; preflight "$TAG"; }; }; then
    echo "$TAG" > "$STATE/current_tag"
    [[ -n "$PREV" && "$PREV" != "$TAG" ]] && echo "$PREV" > "$STATE/previous_tag"
    log "healthy on $TAG"
else
    log "health check failed on $TAG"
    compose "$TAG" logs --tail 80 api web || true
    (( PULSE )) && compose "$TAG" logs --tail 60 pulse-api pulse-bot pulse-worker || true
    if [[ -n "$PREV" ]]; then
        log "rolling back to $PREV"
        # A release from before the field service has no image for it.
        prev_services=("${CORE_SERVICES[@]}") prev_pulse=0
        if (( PULSE )) && docker image inspect "${REGISTRY:-ghcr.io/replyre}/election-monitor-pulse:$PREV" >/dev/null 2>&1; then
            prev_services=("${SERVICES[@]}") prev_pulse=1
        else
            compose "$TAG" stop pulse-api pulse-bot pulse-worker >/dev/null 2>&1 || true
        fi
        compose "$PREV" up -d "${prev_services[@]}"
        healthy "$PREV" "$prev_pulse" && log "back on $PREV" || log "ROLLBACK ALSO UNHEALTHY"
    fi
    exit 1
fi

# Keep the current and previous images for rollback; drop the rest.
keep="$TAG|${PREV:-none}"
docker images --format '{{.Repository}}:{{.Tag}}' \
    | grep -E '/election-monitor-(api|web|jobs|pulse):' \
    | grep -vE ":($keep)$" \
    | xargs -r docker rmi >/dev/null 2>&1 || true
docker image prune -f >/dev/null
docker logout ghcr.io >/dev/null 2>&1 || true
