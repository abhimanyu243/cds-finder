# CDS View Finder: one container, one process.
# Mount a folder at /data with the metadata files; the mapping database is created there too.
#   docker build -t cds-view-finder .
#   docker run -d -p 8000:8000 -v /srv/cds-finder:/data --name cds-view-finder cds-view-finder

FROM python:3.12-slim AS build
COPY --from=ghcr.io/astral-sh/uv:0.11 /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never
WORKDIR /app
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-dev --no-install-project
COPY cds_finder ./cds_finder
RUN uv sync --frozen --no-dev --no-editable

FROM python:3.12-slim
RUN useradd --uid 10001 --no-create-home --shell /usr/sbin/nologin finder \
    && mkdir /data && chown finder:finder /data
COPY --from=build /app/.venv /app/.venv
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    CDS_FINDER_DATA_DIR=/data \
    CDS_FINDER_DB_PATH=/data/cds_finder.db \
    CDS_FINDER_HOST=0.0.0.0 \
    CDS_FINDER_PORT=8000 \
    CDS_FINDER_LOG_JSON=true
USER finder
VOLUME /data
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=60s \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=4)"
CMD ["cds-finder", "serve"]
