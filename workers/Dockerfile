FROM python:3.12-slim

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY *.py ./
COPY tests ./tests
COPY pytest.ini ./pytest.ini
COPY .env.example ./.env.example

CMD ["python", "worker.py"]
