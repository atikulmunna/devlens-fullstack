FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY worker.py ./worker.py
COPY config.py ./config.py
COPY .env.example ./.env.example

CMD ["python", "worker.py"]
