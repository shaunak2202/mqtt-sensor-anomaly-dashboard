FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV PYTHONUNBUFFERED=1

# The actual command run is chosen per-service in docker-compose.yml.
CMD ["python", "-m", "webapp.app"]
