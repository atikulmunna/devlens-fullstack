.PHONY: up down logs backend worker

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
