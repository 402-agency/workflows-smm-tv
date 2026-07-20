# syntax=docker/dockerfile:1

# ---------------------------------------------------------------------------
# Frontend build stage: compile Tailwind CSS with the standalone CLI (no Node).
# Produces app/static/css/app.css which is copied into the runtime image.
# ---------------------------------------------------------------------------
FROM debian:bookworm-slim AS assets
WORKDIR /assets
ARG TAILWIND_VERSION=v3.4.17
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && curl -sSL -o /usr/local/bin/tailwindcss \
        "https://github.com/tailwindlabs/tailwindcss/releases/download/${TAILWIND_VERSION}/tailwindcss-linux-x64" \
    && chmod +x /usr/local/bin/tailwindcss
COPY tailwind.config.js ./tailwind.config.js
COPY app/templates ./app/templates
COPY app/static/css/input.css ./app/static/css/input.css
RUN tailwindcss -c ./tailwind.config.js \
        -i ./app/static/css/input.css \
        -o ./app/static/css/app.css --minify

# ---------------------------------------------------------------------------
# Runtime image
# ---------------------------------------------------------------------------
FROM python:3.12-slim AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    HF_HOME=/models

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Bring in the compiled stylesheet from the assets stage.
COPY --from=assets /assets/app/static/css/app.css /app/app/static/css/app.css

RUN chmod +x docker/entrypoint.sh && mkdir -p /models

EXPOSE 8000
ENTRYPOINT ["docker/entrypoint.sh"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
