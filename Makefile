.PHONY: help up down build logs restart \
        backend-install backend-run backend-test backend-migrate backend-lint \
        frontend-install frontend-run frontend-build frontend-test \
        migrate-postgres clean

help:
	@echo "MLOps Platform — common commands"
	@echo ""
	@echo "  make up                  Start backend+frontend via docker compose"
	@echo "  make up-postgres         Same, with the postgres profile enabled"
	@echo "  make down                Stop and remove containers"
	@echo "  make logs                Tail logs from all services"
	@echo ""
	@echo "  make backend-install     Install backend deps locally (venv assumed active)"
	@echo "  make backend-run         Run the backend locally with uvicorn --reload"
	@echo "  make backend-test        Run backend pytest suite"
	@echo "  make backend-migrate     Apply Alembic migrations locally"
	@echo "  make backend-seed        Populate the running API with sample demo data"
	@echo ""
	@echo "  make frontend-install    npm install"
	@echo "  make frontend-run        ng serve"
	@echo "  make frontend-build      Production build"
	@echo "  make frontend-test       Karma/Jasmine unit tests"

# --- Docker Compose ---
up:
	docker compose up --build

up-postgres:
	docker compose --profile postgres up --build

down:
	docker compose down

logs:
	docker compose logs -f

restart:
	docker compose restart

# --- Backend (local, no Docker) ---
backend-install:
	cd backend && pip install -r requirements.txt

backend-run:
	cd backend && uvicorn app.main:app --reload --port 8000

backend-test:
	cd backend && pytest -v

backend-migrate:
	cd backend && alembic upgrade head

backend-seed:
	cd backend && python scripts/seed_demo_data.py

backend-lint:
	cd backend && python -m py_compile $$(find app -name '*.py')

# --- Frontend (local, no Docker) ---
frontend-install:
	cd frontend && npm ci

frontend-run:
	cd frontend && npm start

frontend-build:
	cd frontend && npm run build -- --configuration production

frontend-test:
	cd frontend && npm test -- --watch=false --browsers=ChromeHeadless

clean:
	rm -rf backend/mlops.db backend/__pycache__ backend/.pytest_cache
	rm -rf frontend/dist frontend/.angular