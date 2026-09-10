# PriceWatch Container Definition
FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy project specification
COPY pyproject.toml .

# Install dependencies including LLM extras
RUN pip install --no-cache-dir -e ".[dev,llm]"

# Copy application source code
COPY . .

# Expose API/Dashboard port
EXPOSE 8000

# Default command: launch PriceWatch server
CMD ["pricewatch", "serve", "--port", "8000"]
