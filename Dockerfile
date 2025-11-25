# Dockerfile for the MLOX Streamlit Application

# 1. Base Image
# Use a slim Python image for a smaller footprint and better security.
FROM python:3.12-slim

# 2. Set Working Directory
# This is where the application code will live inside the container.
WORKDIR /app

# 3. Copy Application Code
# Copy the entire project context into the image.
# This assumes the Docker build is run from the project root.
COPY . .


# 4. Install Dependencies
# Install the mlox package itself along with Streamlit and other UI dependencies.
# Using `pip install .` will install mlox and its dependencies (like requests, fabric)
# if they are defined in a setup.py or pyproject.toml.
# We add streamlit and other UI-specific packages here.
# --no-cache-dir is used to keep the final image size down.
RUN pip install -e ".[dev]"  

# 5. Expose Port
# Streamlit runs on port 8501 by default. This makes it accessible from outside the container.
EXPOSE 8501

# 6. Healthcheck (Optional but good practice)
HEALTHCHECK --interval=15s --timeout=5s --start-period=30s \
  CMD curl --fail http://localhost:8501/_stcore/health || exit 1

ENV PYTHONPATH=/app

# 7. Entrypoint. The working directory is now /app/mlox.
# This defines the command to run the Streamlit application.
# We run app.py directly and bind to all network interfaces so it's accessible outside the container.
ENTRYPOINT ["streamlit", "run", "mlox/app.py", "--server.port=8501", "--server.address=0.0.0.0"]
