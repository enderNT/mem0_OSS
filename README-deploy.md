# Mem0 OSS deployment bundle for Coolify

This repository deploys Mem0 Open Source on Coolify behind a single public URL.

It does not deploy OpenMemory anymore. OpenMemory and Mem0 OSS are related projects from the same company, but they are not the same product:

- OpenMemory is the local-first MCP memory layer and UI.
- Mem0 Open Source is the self-hosted memory engine and REST API.

This bundle now runs Mem0 OSS directly with:

- `gateway`: the only public service
- `mem0-api`: a small FastAPI wrapper around `mem0ai`
- `mem0-store`: Qdrant for vector storage

The public URL serves the Mem0 OSS API:

- `/` shows the web console for managing memories
- `/docs` shows Swagger / OpenAPI UI
- `/openapi.json` exposes the schema
- `/memories`, `/search`, `/reset`, etc. are proxied to Mem0 OSS

## Why this repo uses a local API container

The official Mem0 documentation separates OpenMemory from Mem0 OSS. Mem0 OSS is configured through `mem0ai` / `Memory.from_config(...)` and can be exposed as a REST API. This repo uses a small local API container so the stack boots directly with:

- OpenAI for extraction + embeddings
- Qdrant as the vector store
- SQLite history persisted in a Docker volume

That keeps the deployment aligned with Mem0 OSS instead of relying on the OpenMemory images.

## Files

- `docker-compose.yml`: base stack for Coolify
- `docker-compose.local.yml`: optional local port exposure for plain Docker testing
- `Dockerfile`: image for the Mem0 OSS API service
- `requirements.txt`: Python dependencies for the Mem0 OSS API service
- `app/main.py`: FastAPI service that exposes Mem0 OSS over HTTP
- `.env.coolify.example`: variables to paste into Coolify or copy into a local `.env.coolify`

## Required variables

At minimum set these in Coolify:

- `OPENAI_API_KEY`
- `ADMIN_API_KEY`

Recommended defaults are already included in `.env.coolify.example`.

Important for public Git repos:

- Commit `.env.coolify.example`, not real `.env` or `.env.coolify` files.
- Put all real secrets in Coolify's environment UI or secret store.
- The repository is expected to contain `docker-compose.yml`, `Dockerfile`, `requirements.txt`, and the `app/` directory so Coolify can build `mem0-api` from source.
- `QDRANT_IMAGE` can override the full vector-store image reference from Coolify if Docker Hub pull behavior changes or you need a registry mirror.

## Coolify deployment

Use this as a `Docker Compose` resource from a Git repository.

Do not use the "paste raw compose only" flow for this repo. The stack builds `mem0-api` from the local `Dockerfile` and `app/main.py`, so Coolify needs the repository contents, not just the YAML text.

1. Push this repo to GitHub, GitLab, or another Git provider reachable by Coolify.
2. In Coolify, create a new resource from that repository.
3. Choose `Docker Compose` as the build pack.
4. Set `Base Directory` to `/` and `Docker Compose Location` to `/docker-compose.yml`.
5. Add the variables from `.env.coolify.example` into the resource environment.
6. Open the `gateway` service settings and assign a domain to it on port `80`.
7. Leave `mem0-api` and `mem0-store` without public domains.
8. Deploy.

Important:

- In Coolify, the server-level wildcard domain only enables generated domains. It does not automatically attach a domain to a compose subservice by itself.
- If the `Domains` field on `gateway` is empty, the stack can still exist but you will not get a usable public URL.
- `OPENAI_API_KEY` and `ADMIN_API_KEY` are marked as required in the compose file, so Coolify will block deployment until both are set.

## Validation after deploy

Check these endpoints from the generated Coolify URL:

- `/` should render the web console
- `/docs` should show FastAPI Swagger
- `/openapi.json` should return the OpenAPI document
- `/healthz` should return `{"status":"ok"}`

Functional smoke test with auth enabled:

```bash
curl -X POST https://your-generated-url/memories \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your-secret-api-key" \
  -d '{
    "messages": [{"role": "user", "content": "I prefer concise deployment notes."}],
    "user_id": "gabriel"
  }'
```

Then search it back:

```bash
curl -X POST https://your-generated-url/search \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your-secret-api-key" \
  -d '{
    "query": "deployment notes",
    "user_id": "gabriel"
  }'
```

## Persistence

This bundle uses isolated Mem0 OSS volumes:

- Qdrant data: `mem0_oss_qdrant_data`
- Mem0 history SQLite DB: `mem0_oss_history_data`

Those names are intentionally different from the earlier OpenMemory-oriented stack so old data is not mixed accidentally with this Mem0 OSS deployment.

## Local Docker test

If you want to validate outside Coolify:

1. Copy `.env.coolify.example` to `.env.coolify`.
2. Fill in `OPENAI_API_KEY` and `ADMIN_API_KEY`.
3. Run:

```bash
docker compose --env-file .env.coolify -f docker-compose.yml -f docker-compose.local.yml up --build -d
```

Then open:

- `http://localhost:3000/`
- `http://localhost:3000/docs`

## Notes

- Mem0 OSS docs state that the self-hosted REST server does not use the `/v1/` prefix. Use `/memories`, `/search`, etc. directly.
- `ADMIN_API_KEY` is optional in development but should be set in production; when present, requests must send `X-API-Key`.
- Qdrant is pinned through `QDRANT_IMAGE` in the example environment so GitHub-based deployments are more reproducible than using `latest`, while still letting you swap the full image reference from Coolify.
- This bundle assumes a fresh Mem0 OSS deployment. It does not promise wire compatibility with existing OpenMemory UI/MCP state.
- If you ever want the "paste compose only" deployment mode, the next step would be publishing `mem0-api` to a container registry and changing the stack to use `image:` instead of `build:`.

## Troubleshooting image pulls

If Coolify fails during `mem0-store Pulling`:

1. Confirm the server running Coolify can reach Docker Hub.
2. Retry once, because transient Docker Hub errors are common.
3. In Coolify, set `QDRANT_IMAGE=qdrant/qdrant:v1.17.1` explicitly if an older cached environment value is still present.
4. If your server uses a registry mirror or private proxy, set `QDRANT_IMAGE` to that fully qualified image reference instead.
5. If it still fails, the issue is likely host-level registry access, rate limiting, or outbound networking rather than the compose syntax.
