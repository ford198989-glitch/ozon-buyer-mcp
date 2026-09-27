FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY pyproject.toml README.md ./
COPY src ./src
COPY entrypoint.sh /entrypoint.sh

RUN pip install . \
    && playwright install --with-deps chromium \
    && apt-get update \
    && apt-get install -y --no-install-recommends xvfb xauth \
    && rm -rf /var/lib/apt/lists/*

RUN useradd -m -u 10001 appuser
USER appuser

ENV OZON_HEADLESS=0 \
    OZON_TRANSPORT=stdio \
    OZON_PORT=8084

ENTRYPOINT ["/entrypoint.sh"]
