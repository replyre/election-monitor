FROM node:20.20-alpine AS build
WORKDIR /build
COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY . .
RUN npm run build

# Unprivileged nginx: runs as uid 101 and listens on 8080, so the container
# needs no root and no capabilities. Packages are upgraded at build time so a
# rebuild picks up Alpine's security fixes.
FROM nginxinc/nginx-unprivileged:1.30-alpine
USER root
RUN apk upgrade --no-cache && rm -f /etc/nginx/conf.d/*.conf
COPY docker/nginx.conf /etc/nginx/conf.d/default.conf
COPY docker/snippets /etc/nginx/snippets
COPY --from=build /build/dist /usr/share/nginx/html
USER 101
EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=3s --retries=3 \
    CMD wget -qO- http://127.0.0.1:8080/healthz >/dev/null || exit 1
