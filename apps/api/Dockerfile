FROM python:3.12-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        libpango-1.0-0 \
        libpangocairo-1.0-0 \
        libgdk-pixbuf-2.0-0 \
        libffi-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY pyproject.toml .
COPY apps/api/lookout ./apps/api/lookout

RUN pip install --no-cache-dir -e ".[dev]"

CMD ["sh", "-c", "alembic upgrade head && uvicorn lookout.api:create_app --factory --host 0.0.0.0 --port 8000"]
