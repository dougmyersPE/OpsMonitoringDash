FROM python:3.12-slim

WORKDIR /app

RUN pip install uv

COPY pyproject.toml ./
COPY uv.lock* ./

RUN uv sync --frozen --no-cache

COPY . .
