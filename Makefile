.PHONY: up down logs backend worker migrate test

up:
	docker compose up -d --build

down:
	docker compose down --remove-orphans

logs:
	docker compose logs -f

backend:
	docker compose up backend -d

worker:
	docker compose up worker -d

migrate:
	docker compose exec backend alembic -c alembic.ini upgrade head

test:
	docker compose exec -e PYTHONPATH=/app backend pytest -q
