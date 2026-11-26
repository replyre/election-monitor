# The field service (Pulse): one image, three processes (api, bot, worker).
# Pulse finds db/migrations and db/seeds next to the pulse package, so it runs
# from a source checkout at /app rather than as an installed package.
# psycopg is built from source against Debian's libpq: the binary wheel bundles
# its own libpq, OpenSSL and PCRE2, which security updates never reach.
FROM python:3.11.18-slim-bookworm AS build
RUN apt-get update && apt-get install -y --no-install-recommends gcc libc6-dev libpq-dev \
    && rm -rf /var/lib/apt/lists/*
COPY pyproject.toml constraints.txt ./
RUN python -c "import tomllib; print('\n'.join(tomllib.load(open('pyproject.toml','rb'))['project']['dependencies']))" \
        | sed 's/^psycopg\[binary,pool\]/psycopg[c,pool]/' > requirements.txt \
    && grep -v '^psycopg-binary' constraints.txt > constraints-image.txt \
    && pip wheel --no-cache-dir --wheel-dir /wheels -c constraints-image.txt -r requirements.txt \
        "psycopg-c==$(sed -n 's/^psycopg==//p' constraints.txt)"

FROM python:3.11.18-slim-bookworm

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONPATH=/app \
    MEDIA_DIR=/data/media

WORKDIR /app

RUN apt-get update && apt-get upgrade -y && apt-get install -y --no-install-recommends libpq5 \
    && rm -rf /var/lib/apt/lists/*

RUN --mount=type=bind,from=build,source=/wheels,target=/wheels \
    pip install --no-index --find-links /wheels /wheels/*.whl \
    && pip uninstall -y setuptools wheel

COPY pulse ./pulse
COPY db ./db
COPY scripts ./scripts

RUN useradd --create-home --uid 10003 pulse \
    && install -d -m 0700 -o pulse -g pulse /data/media
USER pulse

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/healthz', timeout=4).status == 200 else 1)"
CMD ["uvicorn", "pulse.api.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000", \
     "--workers", "1", "--proxy-headers", "--forwarded-allow-ips", "*", "--no-server-header"]
