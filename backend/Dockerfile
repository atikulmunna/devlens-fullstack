FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY alembic ./alembic
COPY alembic.ini ./alembic.ini
COPY tests ./tests
COPY pytest.ini ./pytest.ini
COPY .env.example ./.env.example

EXPOSE 8000

CMD ["sh", "-c", "if [ \"${MIGRATE_ON_STARTUP:-0}\" = \"1\" ]; then alembic upgrade head; fi; uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
