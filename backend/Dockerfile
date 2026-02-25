FROM python:3.12-slim

WORKDIR /app

RUN pip install uv

COPY pyproject.toml ./
COPY uv.lock* ./

RUN uv sync --frozen --no-cache

# Add the virtual environment's bin directory to PATH so all commands use it
ENV PATH="/app/.venv/bin:$PATH"

COPY . .
