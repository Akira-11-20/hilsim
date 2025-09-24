FROM python:3.11-slim

# Install minimal dependencies
RUN pip install --no-cache-dir pyzmq numpy

# Create app directory
WORKDIR /app

# Copy server scripts
COPY server.py delay_server.py 

# Expose port
EXPOSE 5555

# Run server
CMD ["python", "server.py"]