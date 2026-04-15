# mem0_OSS

Plug-and-play Mem0 OSS deployment for Coolify using Docker Compose from a Git repository.

This repository is structured to be pushed directly to GitHub and deployed from Coolify as a `Docker Compose` resource that builds the API image from the repo contents.

## What this deploys

- `gateway`: the only public service
- `mem0-api`: a FastAPI wrapper around `mem0ai`
- `mem0-store`: Qdrant for vector storage

This is a Mem0 OSS API deployment, not OpenMemory.

## Web console

The FastAPI service now serves a lightweight management UI at `/`.

- `/` provides a browser-based console for create, read, update, delete, search, history, configure, and reset actions.
- Listing supports both scoped retrieval and full-store retrieval: if `user_id`, `agent_id`, and `run_id` are all empty, the console and `GET /memories` return every stored memory.
- `/docs` keeps the OpenAPI / Swagger interface available for direct API inspection.

## GitHub to Coolify flow

1. Push this repository to GitHub.
2. In Coolify, create a new resource from that GitHub repository.
3. Select `Docker Compose` and point Coolify to `/docker-compose.yml`.
4. Add the variables from `.env.coolify.example` in the Coolify environment UI.
5. Expose only the `gateway` service with a domain on port `80`.

If Coolify reports a failure while `mem0-store` is pulling, set `QDRANT_IMAGE` explicitly in the resource environment. The default is now `qdrant/qdrant:v1.17.1`.
If `mem0-api` fails with an SSL error during startup, clear `QDRANT_API_KEY` unless you are intentionally using an external `QDRANT_URL`.

## Coolify

Use this repo as a `Docker Compose` resource from Git.

Required environment variables:

- `OPENAI_API_KEY`
- `ADMIN_API_KEY`

Main compose file:

- [docker-compose.yml](./docker-compose.yml)

Detailed deployment guide:

- [README-deploy.md](./README-deploy.md)
