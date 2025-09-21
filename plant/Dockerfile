FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY pyproject.toml .
RUN pip install --no-cache-dir pyzmq>=26.0.0 pyyaml>=6.0.0 numpy>=2.3.0

# Copy application code
COPY app/ ./

# Create logs directory
RUN mkdir -p /app/logs

# Expose port
EXPOSE 5555

CMD ["python", "main.py"]