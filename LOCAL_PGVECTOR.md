# Local PostgreSQL + pgvector

Use the pgvector-enabled Docker Compose profile for local RAG/vector development.

Default host port, matching `backend/.env.development`:

```powershell
$env:POSTGRES_PASSWORD='replace-with-local-password'
docker compose -f docker-compose.pgvector.yml up -d
cd backend
.\venv\Scripts\python.exe -m alembic upgrade head
```

The container keeps PostgreSQL on port `5432` internally, while Windows host
tools and backend commands should connect through `localhost:5433`:

```powershell
$env:POSTGRES_PASSWORD='replace-with-local-password'
$env:POSTGRES_PORT='5433'
docker compose -f docker-compose.pgvector.yml up -d
cd backend
$env:POSTGRES_PASSWORD='replace-with-local-password'
$env:POSTGRES_PORT='5433'
.\venv\Scripts\python.exe -m alembic upgrade head
```

Azure production remains configured through the same environment variables:
`POSTGRES_HOST`, `POSTGRES_PORT`, `POSTGRES_DB`, `POSTGRES_USER`,
`POSTGRES_PASSWORD`, `POSTGRES_SSLMODE`, or `DATABASE_URL`. The Azure PostgreSQL
server must provide the `vector` extension before applying the pgvector migration.
