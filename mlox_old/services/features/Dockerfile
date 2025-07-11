FROM python:3.11-slim

# Install necessary dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Install Feast
RUN pip install pandas
RUN pip install feast[redis]
RUN pip install grpcio
RUN pip install grpcio-health-checking
RUN pip install grpcio-reflection

# Set the working directory
WORKDIR /app
