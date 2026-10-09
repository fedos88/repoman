FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

RUN useradd --system --uid 10001 --home-dir /nonexistent --shell /usr/sbin/nologin repoman \
    && install -d -o repoman -g repoman /var/lib/repoman

WORKDIR /app
COPY pyproject.toml ./
COPY src ./src
RUN pip install .

# Swagger UI assets are served locally: /api/docs must work without internet access.
ARG SWAGGER_UI_VERSION=5.33.1
ARG SWAGGER_UI_INTEGRITY=sha512-H872wWkA53bFIsGgi7OWgmq+CRWw3nFQGdJWRqOB9wNwTm6e5ol34+qPDkV4AJlK+gglM2EsJiOOzsGsEGbluA==
COPY scripts/fetch_swagger_ui.py /tmp/
RUN python /tmp/fetch_swagger_ui.py "$SWAGGER_UI_VERSION" "$SWAGGER_UI_INTEGRITY" \
        "$(python -c 'import repoman.docs as d; print(d.SWAGGER_UI_DIR)')" \
    && rm /tmp/fetch_swagger_ui.py

USER repoman
ENV REPOMAN_STORAGE_PATH=/var/lib/repoman
VOLUME ["/var/lib/repoman"]
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD ["python", "-c", "import os, urllib.request; port = os.environ.get('REPOMAN_LISTEN', ':8000').rpartition(':')[2]; urllib.request.urlopen(f'http://127.0.0.1:{port}/healthz', timeout=3)"]

CMD ["python", "-m", "repoman"]
