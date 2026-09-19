.PHONY: up down remove codex-login

up:
	docker compose up --build -d

down:
	docker compose down

# Deletes requests, photos, settings and AI authentication.
remove:
	docker compose down --volumes --rmi local

codex-login:
	docker compose exec web codex -c 'cli_auth_credentials_store="file"' login --device-auth
