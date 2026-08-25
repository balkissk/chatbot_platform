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
ENVIRONMENT=production
DATABASE_URL=postgresql://USER:PASSWORD@HOST:5432/chatbot_db?sslmode=require
JWT_SECRET=replace-with-a-long-random-secret
JWT_ALGORITHM=HS256
FRONTEND_BASE_URL=https://your-frontend-domain
BACKEND_BASE_URL=https://your-backend-domain
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

`DATABASE_URL` can be supplied directly, or you can omit it and provide PostgreSQL parts instead:

```text
ENVIRONMENT=production
POSTGRES_HOST=your-server.postgres.database.azure.com
POSTGRES_PORT=5432
POSTGRES_DB=chatbot_db
POSTGRES_USER=your_db_user
POSTGRES_PASSWORD=your_db_password
POSTGRES_SSLMODE=require
```

`AZURE_OPENAI_ENDPOINT` must be the Azure OpenAI resource endpoint only. Do not append `/openai`, `/deployments`, or a model path. The backend passes this value to the Azure OpenAI SDK as `azure_endpoint`.

## Environment Profiles

The backend supports Spring Boot-style profiles through `ENVIRONMENT`:

- `ENVIRONMENT=development` loads `backend/.env.development`
- `ENVIRONMENT=production` loads `backend/.env.production`

The loader also reads `backend/.env` first for compatibility. Profile-specific files override values loaded from `backend/.env`, but real process environment variables, including Azure App Service application settings, always win.

Local development:

```powershell
cd backend
copy .env.example .env.development
# edit .env.development for local PostgreSQL if needed
$env:ENVIRONMENT="development"
.\venv\Scripts\python.exe -m alembic upgrade head
.\venv\Scripts\uvicorn.exe main:app --reload
```

Production:

```text
Set ENVIRONMENT=production in Azure App Service.
Set DATABASE_URL or POSTGRES_* values in Azure App Service application settings.
Do not deploy or commit backend/.env.production with real secrets.
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
VITE_BACKEND_BASE_URL=https://your-backend-domain
VITE_FRONTEND_BASE_URL=https://your-frontend-domain
PORT=8080
```

The Angular SSR server serves `/config.js` dynamically from these values, so the frontend does not need local API URLs baked into the bundle.

`FRONTEND_BASE_URL` is used by the backend to generate absolute frontend links, including password reset links. `FRONTEND_URL` and `ALLOWED_ORIGINS` are CORS inputs and should not be treated as the password reset link source. In local development use `FRONTEND_BASE_URL=http://localhost:4200`; in production set it in Azure App Service application settings to the deployed frontend URL.

`BACKEND_BASE_URL` is used by deployment features to generate widget scripts and REST API URLs. In local development use `BACKEND_BASE_URL=http://127.0.0.1:8000`.

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

## GitHub OIDC Authentication

The frontend deployment uses Azure OIDC authentication through `azure/login` instead of publish profile authentication.

A Microsoft Entra App Registration named `chatbot-factory-github-oidc` is configured for GitHub OIDC with a Federated Credential scoped to:

- Organization: `balkissk`
- Repository: `chatbot_platform`
- Branch: `main`

The App Registration has `Contributor` RBAC assigned only at the Resource Group scope:

- `rg-balkis-chatbot-factory-v2`

Do not store publish profiles or Azure credential values in the workflow file. If the App Registration is recreated in the future, update the GitHub `CLIENT_ID` secret to the new application client ID.

## Important Notes

- Do not deploy the local `backend/venv`, `node_modules`, `.idea`, or `__pycache__` folders.
- Keep `JWT_SECRET`, SMTP password, database password, and `AZURE_OPENAI_API_KEY` in Azure application settings, not in source code.
- Do not commit `.env` files or copy production secrets into `.env.example`.
