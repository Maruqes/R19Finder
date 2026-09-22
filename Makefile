.PHONY: up down remove codex-login test test-api test-frontend

up:
	docker compose up --build -d

down:
	docker compose down

# Deletes requests, photos, settings and AI authentication.
remove:
	docker compose down --volumes --rmi local

codex-login:
	docker compose exec web codex -c 'cli_auth_credentials_store="file"' login --device-auth

test: test-api test-frontend

test-api:
	docker compose run --rm --no-deps -T \
		-v "$(CURDIR)/api/tests:/app/api/tests:ro,Z" \
		web python -m unittest discover -s /app/api/tests

test-frontend:
	$(MAKE) -C frontend test
