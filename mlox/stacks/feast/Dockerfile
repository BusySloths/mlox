FROM python:3.11-slim

# Install necessary dependencies for building Feast extras
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Install Feast with Redis and Postgres support
RUN pip install --no-cache-dir pandas "feast[redis,postgres]==0.54.0" grpcio grpcio-health-checking grpcio-reflection psycopg2-binary

# Set the working directory
WORKDIR /app
