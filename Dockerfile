# Container for running the Wyckoff scanner as a Google Cloud Run Job.
FROM python:3.12-slim

# Avoid interactive prompts; keep Python output unbuffered for Cloud Logging.
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY scanner.py .

# Cloud Run Jobs run this to completion, then exit. --email implies --no-open.
ENTRYPOINT ["python", "scanner.py", "--email"]
