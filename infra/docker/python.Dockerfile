# One image for every Python service (ingestion, simulator, api, init jobs) to save disk.
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
ENV PYTHONPATH=/app/common:/app/simulator:/app/ingestion:/app/routing:/app/api \
    PYTHONUNBUFFERED=1
