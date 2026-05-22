.PHONY: dev build up down logs clean

dev:
	docker compose up -d --build

up:
	docker compose up -d

down:
	docker compose down

logs:
	docker compose logs -f

clean:
	docker compose down -v --rmi all

seed:
	python scripts/seed_data.py

keys:
	python scripts/generate_keys.py
