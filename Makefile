.PHONY: dev test seed eval
dev:
	docker compose up --build
test:
	cd backend && pytest --cov=app
	cd frontend && npm test && npm run typecheck && npm run build
seed:
	cd backend && python -m app.seed
eval:
	cd backend && python -m app.ml.evaluate --sweep


