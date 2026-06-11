# Azure Deployment

This project is prepared as two deployable services:

- `frontend`: Angular SSR app running on Node.
- `backend`: FastAPI app running with Gunicorn/Uvicorn.

## Required Azure Resources

- Azure App Service or Azure Container Apps for `frontend`
- Azure App Service or Azure Container Apps for `backend`
- Azure Database for PostgreSQL
- Azure OpenAI resource with chat and embedding deployments

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
AI_PROVIDER=azure_openai
EMBEDDING_PROVIDER=azure_openai
AZURE_OPENAI_ENDPOINT=https://your-resource-name.openai.azure.com
AZURE_OPENAI_API_KEY=replace-with-azure-openai-key
AZURE_OPENAI_DEPLOYMENT=gpt-4o-mini
AZURE_OPENAI_EMBEDDING_DEPLOYMENT=text-embedding-3-small
AZURE_OPENAI_API_VERSION=2024-02-15-preview
SMTP_HOST=
SMTP_PORT=587
SMTP_USERNAME=
SMTP_PASSWORD=
SMTP_FROM=
```

`AZURE_OPENAI_ENDPOINT` must be the Azure OpenAI resource endpoint only. Do not append `/openai`, `/deployments`, or a model path. The backend passes this value to the Azure OpenAI SDK as `azure_endpoint`.

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
- Keep `JWT_SECRET`, SMTP password, database password, and `AZURE_OPENAI_API_KEY` in Azure application settings, not in source code.
- Do not commit `.env` files or copy production secrets into `.env.example`.
