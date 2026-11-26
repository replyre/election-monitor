# The web tier: the core app at /, the field screens at /field/, and the proxy
# in front of both APIs. Built from the repository root (see
# Dockerfile.dockerignore, which admits only the two frontends).
FROM node:20.20-alpine AS core
WORKDIR /build
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ .
RUN npm run build

FROM node:20.20-alpine AS field
WORKDIR /build
COPY field-service/web/package.json field-service/web/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY field-service/web/ .
RUN npm run build

# Alpine's own nginx package: it carries security fixes before the nginx.org
# images are rebuilt (CVE-2026-113425 was fixed here first). Runs as the
# package's own unprivileged nginx user (uid 100).
FROM alpine:3.24
RUN apk upgrade --no-cache && apk add --no-cache nginx \
    && rm -rf /etc/nginx/http.d /var/lib/nginx/html
COPY frontend/docker/nginx-main.conf /etc/nginx/nginx.conf
COPY frontend/docker/nginx.conf /etc/nginx/conf.d/default.conf
COPY frontend/docker/snippets /etc/nginx/snippets
COPY --from=core /build/dist /usr/share/nginx/html
COPY --from=field /build/dist /usr/share/nginx/html/field
USER nginx
EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=3s --retries=3 \
    CMD wget -qO- http://127.0.0.1:8080/healthz >/dev/null || exit 1
CMD ["nginx", "-g", "daemon off;"]
