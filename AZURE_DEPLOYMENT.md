# Azure Deployment

This project is prepared as two deployable services:

- `frontend`: Angular SSR app running on Node.
- `backend`: FastAPI app running with Gunicorn/Uvicorn.

## Required Azure Resources

- Azure App Service or Azure Container Apps for `frontend`
- Azure App Service or Azure Container Apps for `backend`
- Azure Database for PostgreSQL
- Optional external LLM/Ollama service reachable by the backend

## Backend Settings

Set these application settings in Azure:

```text
DATABASE_URL=postgresql://USER:PASSWORD@HOST:5432/chatbot_db?sslmode=require
JWT_SECRET=replace-with-a-long-random-secret
JWT_ALGORITHM=HS256
FRONTEND_URL=https://your-frontend-domain
ALLOWED_ORIGINS=https://your-frontend-domain
API_BASE_URL=https://your-backend-domain
PUBLIC_API_BASE_URL=https://your-backend-domain
OLLAMA_BASE_URL=https://your-llm-service-domain
EMBEDDING_PROVIDER=ollama
EMBEDDING_MODEL=nomic-embed-text
SMTP_HOST=
SMTP_PORT=587
SMTP_USERNAME=
SMTP_PASSWORD=
SMTP_FROM=
```

Backend container startup runs:

```sh
alembic upgrade head && gunicorn -k uvicorn.workers.UvicornWorker -w ${WEB_CONCURRENCY:-2} -b 0.0.0.0:${PORT:-8000} main:app
```

Health check path:

```text
/health
```

## Frontend Settings

Set these application settings in Azure:

```text
PUBLIC_API_BASE_URL=https://your-backend-domain
PUBLIC_FRONTEND_BASE_URL=https://your-frontend-domain
PORT=8080
```

The Angular SSR server serves `/config.js` dynamically from these values, so the frontend does not need local API URLs baked into the bundle.

## Docker Build Examples

Backend:

```sh
docker build -t chatbot-factory-backend ./backend
docker run -p 8000:8000 --env-file ./backend/.env chatbot-factory-backend
```

Frontend:

```sh
docker build -t chatbot-factory-frontend ./frontend
docker run -p 8080:8080 -e PUBLIC_API_BASE_URL=http://localhost:8000 chatbot-factory-frontend
```

## Important Notes

- Do not deploy the local `backend/venv`, `node_modules`, `.idea`, or `__pycache__` folders.
- Keep `JWT_SECRET`, SMTP password, and database password in Azure application settings, not in source code.
- `OLLAMA_BASE_URL` cannot point to `localhost` in Azure unless Ollama is deployed in the same container/network and reachable from the backend.
