FROM python:3.11-slim

# Install minimal dependencies
RUN pip install --no-cache-dir pyzmq pandas matplotlib numpy

# Create app directory
WORKDIR /app

# Copy client script
COPY client.py enhanced_client.py

# Default command
CMD ["python", "client.py"]