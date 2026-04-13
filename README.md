# mem0_OSS

Plug-and-play Mem0 OSS deployment for Coolify using Docker Compose from a Git repository.

## What this deploys

- `gateway`: the only public service
- `mem0-api`: a FastAPI wrapper around `mem0ai`
- `mem0-store`: Qdrant for vector storage

This is a Mem0 OSS API deployment, not OpenMemory.

## Coolify

Use this repo as a `Docker Compose` resource from Git.

Required environment variables:

- `OPENAI_API_KEY`
- `ADMIN_API_KEY`

Main compose file:

- [docker-compose.yml](./docker-compose.yml)

Detailed deployment guide:

- [README-deploy.md](./README-deploy.md)
