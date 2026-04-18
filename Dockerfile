FROM python:3.12-slim

LABEL org.opencontainers.image.title="CodeAtlas"
LABEL org.opencontainers.image.description="MCP server that builds real-time code knowledge graphs"
LABEL org.opencontainers.image.source="https://github.com/AryanSaini26/CodeAtlas"
LABEL org.opencontainers.image.licenses="MIT"

RUN apt-get update \
    && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY pyproject.toml README.md LICENSE ./
COPY src/ ./src/

RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir ".[all]"

WORKDIR /repo

ENTRYPOINT ["codeatlas"]
CMD ["--help"]
