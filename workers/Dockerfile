FROM python:3.12-slim

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY worker.py ./worker.py
COPY config.py ./config.py
COPY db.py ./db.py
COPY parse_worker.py ./parse_worker.py
COPY embed_worker.py ./embed_worker.py
COPY analyze_worker.py ./analyze_worker.py
COPY embeddings.py ./embeddings.py
COPY reliability.py ./reliability.py
COPY telemetry.py ./telemetry.py
COPY tests ./tests
COPY pytest.ini ./pytest.ini
COPY .env.example ./.env.example

CMD ["python", "worker.py"]
