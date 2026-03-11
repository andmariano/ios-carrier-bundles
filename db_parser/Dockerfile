FROM python:3.11-slim

WORKDIR /workspace

# Build deps for psycopg2
RUN apt-get update \
    && apt-get install -y --no-install-recommends libpq-dev gcc \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir psycopg2-binary requests

# Bake scripts into image (overridden by the repo volume mount in docker-compose)
COPY ingest_to_db.py db_parser/ingest_to_db.py
COPY db_schema.sql   db_parser/db_schema.sql

CMD ["python", "db_parser/ingest_to_db.py", "--mode", "github-issues"]
