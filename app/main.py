import logging
import os
import secrets
import time
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.security import APIKeyHeader
from mem0 import Memory
from pydantic import BaseModel, Field


logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
load_dotenv()


def _env_int(name: str, default: int) -> int:
    value = os.environ.get(name)
    if not value:
        return default
    return int(value)


def _env_float(name: str, default: float) -> float:
    value = os.environ.get(name)
    if not value:
        return default
    return float(value)


def _build_default_config() -> Dict[str, Any]:
    llm_provider = os.environ.get("LLM_PROVIDER", "openai")
    embedder_provider = os.environ.get("EMBEDDER_PROVIDER", "openai")
    openai_api_key = os.environ.get("OPENAI_API_KEY", "")
    llm_api_key = os.environ.get("LLM_API_KEY") or openai_api_key
    embedder_api_key = os.environ.get("EMBEDDER_API_KEY") or openai_api_key

    if llm_provider == "openai" and not llm_api_key:
        raise RuntimeError("OPENAI_API_KEY or LLM_API_KEY is required for the default Mem0 LLM config.")
    if embedder_provider == "openai" and not embedder_api_key:
        raise RuntimeError(
            "OPENAI_API_KEY or EMBEDDER_API_KEY is required for the default Mem0 embedder config."
        )

    qdrant_config: Dict[str, Any] = {
        "host": os.environ.get("QDRANT_HOST", "mem0-store"),
        "port": _env_int("QDRANT_PORT", 6333),
        "collection_name": os.environ.get("QDRANT_COLLECTION_NAME", "mem0"),
    }
    qdrant_api_key = os.environ.get("QDRANT_API_KEY")
    if qdrant_api_key:
        qdrant_config["api_key"] = qdrant_api_key

    config: Dict[str, Any] = {
        "version": "v1.1",
        "vector_store": {
            "provider": "qdrant",
            "config": qdrant_config,
        },
        "llm": {
            "provider": llm_provider,
            "config": {
                "api_key": llm_api_key,
                "model": os.environ.get("LLM_MODEL", "gpt-4.1-nano-2025-04-14"),
                "temperature": _env_float("LLM_TEMPERATURE", 0.2),
            },
        },
        "embedder": {
            "provider": embedder_provider,
            "config": {
                "api_key": embedder_api_key,
                "model": os.environ.get("EMBEDDER_MODEL", "text-embedding-3-small"),
            },
        },
        "history_db_path": os.environ.get("HISTORY_DB_PATH", "/app/history/history.db"),
    }
    return config


def _initialize_memory_instance() -> Memory:
    retries = _env_int("MEM0_STARTUP_RETRIES", 20)
    delay_seconds = _env_float("MEM0_STARTUP_DELAY_SECONDS", 3.0)
    config = _build_default_config()
    last_error: Optional[Exception] = None

    for attempt in range(1, retries + 1):
        try:
            logging.info("Initializing Mem0 (attempt %s/%s)", attempt, retries)
            return Memory.from_config(config)
        except Exception as exc:  # pragma: no cover - startup retry path
            last_error = exc
            logging.warning("Mem0 initialization failed: %s", exc)
            if attempt < retries:
                time.sleep(delay_seconds)

    raise RuntimeError(f"Failed to initialize Mem0 after {retries} attempts: {last_error}")


ADMIN_API_KEY = os.environ.get("ADMIN_API_KEY", "")
MIN_KEY_LENGTH = 16
if not ADMIN_API_KEY:
    logging.warning("ADMIN_API_KEY not set - API endpoints are unsecured.")
elif len(ADMIN_API_KEY) < MIN_KEY_LENGTH:
    logging.warning(
        "ADMIN_API_KEY is shorter than %d characters - consider using a longer key for production.",
        MIN_KEY_LENGTH,
    )

MEMORY_INSTANCE = _initialize_memory_instance()

app = FastAPI(
    title="Mem0 OSS REST API",
    description=(
        "A REST API for managing and searching memories with Mem0 Open Source.\n\n"
        "When the ADMIN_API_KEY environment variable is set, protected endpoints require "
        "the `X-API-Key` header."
    ),
    version="1.0.0",
)

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def _json_response(payload: Any) -> JSONResponse:
    return JSONResponse(content=jsonable_encoder(payload))


async def verify_api_key(api_key: Optional[str] = Depends(api_key_header)) -> Optional[str]:
    if ADMIN_API_KEY:
        if api_key is None:
            raise HTTPException(
                status_code=401,
                detail="X-API-Key header is required.",
                headers={"WWW-Authenticate": "ApiKey"},
            )
        if not secrets.compare_digest(api_key, ADMIN_API_KEY):
            raise HTTPException(
                status_code=401,
                detail="Invalid API key.",
                headers={"WWW-Authenticate": "ApiKey"},
            )
    return api_key


class Message(BaseModel):
    role: str = Field(..., description="Role of the message.")
    content: str = Field(..., description="Message content.")


class MemoryCreate(BaseModel):
    messages: List[Message] = Field(..., description="List of messages to store.")
    user_id: Optional[str] = None
    agent_id: Optional[str] = None
    run_id: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None
    infer: Optional[bool] = Field(None, description="Whether to extract facts from messages.")
    memory_type: Optional[str] = Field(None, description="Type of memory to store.")
    prompt: Optional[str] = Field(None, description="Custom prompt for fact extraction.")


class MemoryUpdate(BaseModel):
    text: str = Field(..., description="New content to update the memory with.")
    metadata: Optional[Dict[str, Any]] = Field(None, description="Metadata to update.")


class SearchRequest(BaseModel):
    query: str = Field(..., description="Search query.")
    user_id: Optional[str] = None
    run_id: Optional[str] = None
    agent_id: Optional[str] = None
    filters: Optional[Dict[str, Any]] = None
    top_k: Optional[int] = Field(None, description="Maximum number of results to return.")
    threshold: Optional[float] = Field(None, description="Minimum similarity score for results.")


@app.get("/", summary="Redirect to the OpenAPI documentation", include_in_schema=False)
def home() -> RedirectResponse:
    return RedirectResponse(url="/docs")


@app.get("/healthz", include_in_schema=False)
def healthz() -> Dict[str, str]:
    return {"status": "ok"}


@app.post("/configure", summary="Configure Mem0")
def set_config(config: Dict[str, Any], _api_key: Optional[str] = Depends(verify_api_key)) -> Dict[str, str]:
    global MEMORY_INSTANCE
    MEMORY_INSTANCE = Memory.from_config(config)
    return {"message": "Configuration set successfully"}


@app.post("/memories", summary="Create memories")
def add_memory(memory_create: MemoryCreate, _api_key: Optional[str] = Depends(verify_api_key)) -> JSONResponse:
    if not any([memory_create.user_id, memory_create.agent_id, memory_create.run_id]):
        raise HTTPException(status_code=400, detail="At least one identifier is required.")

    params = {k: v for k, v in memory_create.model_dump().items() if v is not None and k != "messages"}
    try:
        response = MEMORY_INSTANCE.add(messages=[m.model_dump() for m in memory_create.messages], **params)
        return _json_response(response)
    except Exception as exc:
        logging.exception("Error in add_memory")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/memories", summary="Get memories")
def get_all_memories(
    user_id: Optional[str] = None,
    run_id: Optional[str] = None,
    agent_id: Optional[str] = None,
    _api_key: Optional[str] = Depends(verify_api_key),
) -> JSONResponse:
    if not any([user_id, run_id, agent_id]):
        raise HTTPException(status_code=400, detail="At least one identifier is required.")

    try:
        params = {
            key: value
            for key, value in {"user_id": user_id, "run_id": run_id, "agent_id": agent_id}.items()
            if value is not None
        }
        return _json_response(MEMORY_INSTANCE.get_all(**params))
    except Exception as exc:
        logging.exception("Error in get_all_memories")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/memories/{memory_id}", summary="Get a memory")
def get_memory(memory_id: str, _api_key: Optional[str] = Depends(verify_api_key)) -> JSONResponse:
    try:
        return _json_response(MEMORY_INSTANCE.get(memory_id))
    except Exception as exc:
        logging.exception("Error in get_memory")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/memories/{memory_id}/history", summary="Get memory history")
def memory_history(memory_id: str, _api_key: Optional[str] = Depends(verify_api_key)) -> JSONResponse:
    try:
        return _json_response(MEMORY_INSTANCE.history(memory_id=memory_id))
    except Exception as exc:
        logging.exception("Error in memory_history")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.put("/memories/{memory_id}", summary="Update a memory")
def update_memory(
    memory_id: str,
    updated_memory: MemoryUpdate,
    _api_key: Optional[str] = Depends(verify_api_key),
) -> JSONResponse:
    try:
        response = MEMORY_INSTANCE.update(
            memory_id=memory_id,
            data=updated_memory.text,
            metadata=updated_memory.metadata,
        )
        return _json_response(response)
    except Exception as exc:
        logging.exception("Error in update_memory")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.delete("/memories/{memory_id}", summary="Delete a memory")
def delete_memory(memory_id: str, _api_key: Optional[str] = Depends(verify_api_key)) -> Dict[str, str]:
    try:
        MEMORY_INSTANCE.delete(memory_id=memory_id)
        return {"message": "Memory deleted successfully"}
    except Exception as exc:
        logging.exception("Error in delete_memory")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.delete("/memories", summary="Delete all memories")
def delete_all_memories(
    user_id: Optional[str] = None,
    run_id: Optional[str] = None,
    agent_id: Optional[str] = None,
    _api_key: Optional[str] = Depends(verify_api_key),
) -> Dict[str, str]:
    if not any([user_id, run_id, agent_id]):
        raise HTTPException(status_code=400, detail="At least one identifier is required.")

    try:
        params = {
            key: value
            for key, value in {"user_id": user_id, "run_id": run_id, "agent_id": agent_id}.items()
            if value is not None
        }
        MEMORY_INSTANCE.delete_all(**params)
        return {"message": "All relevant memories deleted"}
    except Exception as exc:
        logging.exception("Error in delete_all_memories")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/search", summary="Search memories")
def search_memories(search_req: SearchRequest, _api_key: Optional[str] = Depends(verify_api_key)) -> JSONResponse:
    try:
        params = {k: v for k, v in search_req.model_dump().items() if v is not None and k != "query"}
        return _json_response(MEMORY_INSTANCE.search(query=search_req.query, **params))
    except Exception as exc:
        logging.exception("Error in search_memories")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/reset", summary="Reset all memories")
def reset_memory(_api_key: Optional[str] = Depends(verify_api_key)) -> Dict[str, str]:
    try:
        MEMORY_INSTANCE.reset()
        return {"message": "All memories reset"}
    except Exception as exc:
        logging.exception("Error in reset_memory")
        raise HTTPException(status_code=500, detail=str(exc)) from exc
