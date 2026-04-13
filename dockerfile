FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

# Set working directory
WORKDIR /app

# Enable bytecode compilation and fix Python path
ENV UV_COMPILE_BYTECODE=1
ENV PYTHONPATH="."

# Copy project files
COPY . .

# Sync dependencies
RUN uv sync --frozen

# Expose all necessary ports
EXPOSE 8080 8181 10000 11000 12000 8501