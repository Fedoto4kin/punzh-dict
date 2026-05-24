.PHONY: format up build

format:
	@echo "Formatting code in Docker..."
	docker exec punzh_django sh -c "python -m isort . && python -m black ."

build:
	@echo "Build project"
	docker compose build

up:
	@echo "Run project"
	docker compose up -d

down:
	@echo "Stop project"
	docker compose down

# todo: migrate

# todo: shell

# todo: manage.py

# todo: install python packages

