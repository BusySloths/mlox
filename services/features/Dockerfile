FROM python:3.8-slim

# Install necessary dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Install Feast
RUN pip install feast[redis]

# Set the working directory
WORKDIR /app
