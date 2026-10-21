FROM python:3.12-slim

# ---------------------------------------------------------------------
# Python configuration
# ---------------------------------------------------------------------

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app


# ---------------------------------------------------------------------
# Application directory
# ---------------------------------------------------------------------

WORKDIR /app


# ---------------------------------------------------------------------
# Python dependencies
# ---------------------------------------------------------------------

COPY requirements-lock.txt .

RUN pip install \
    --no-cache-dir \
    -r requirements-lock.txt


# ---------------------------------------------------------------------
# Application code
# ---------------------------------------------------------------------

COPY src ./src
COPY helpers ./helpers
COPY data ./data


# ---------------------------------------------------------------------
# Experiment results directory
# ---------------------------------------------------------------------

RUN mkdir -p /app/results/experiments


# ---------------------------------------------------------------------
# Default application
#
# Docker Compose and Kubernetes will override this command depending
# on which application the container is running.
# ---------------------------------------------------------------------

CMD ["python", "-m", "src.ur_pipeline.monolith_api"]