import inspect
import logging
import os
import secrets
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException
from fastapi.encoders import jsonable_encoder
from fastapi.responses import FileResponse, JSONResponse
from fastapi.security import APIKeyHeader
from fastapi.staticfiles import StaticFiles
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
    qdrant_url = os.environ.get("QDRANT_URL")
    qdrant_api_key = os.environ.get("QDRANT_API_KEY")

    if llm_provider == "openai" and not llm_api_key:
        raise RuntimeError("OPENAI_API_KEY or LLM_API_KEY is required for the default Mem0 LLM config.")
    if embedder_provider == "openai" and not embedder_api_key:
        raise RuntimeError(
            "OPENAI_API_KEY or EMBEDDER_API_KEY is required for the default Mem0 embedder config."
        )

    qdrant_config: Dict[str, Any] = {
        "collection_name": os.environ.get("QDRANT_COLLECTION_NAME", "mem0"),
    }
    if qdrant_url:
        if not qdrant_api_key:
            raise RuntimeError("QDRANT_URL requires QDRANT_API_KEY when using Mem0's Qdrant url-based config.")
        qdrant_config["url"] = qdrant_url
        qdrant_config["api_key"] = qdrant_api_key
    else:
        qdrant_config["host"] = os.environ.get("QDRANT_HOST", "mem0-store")
        qdrant_config["port"] = _env_int("QDRANT_PORT", 6333)
        if qdrant_api_key:
            logging.warning(
                "Ignoring QDRANT_API_KEY because QDRANT_URL is not set. "
                "For the internal mem0-store service, using an API key would force HTTPS and break local HTTP connectivity."
            )

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
BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"

app = FastAPI(
    title="Mem0 OSS REST API",
    description=(
        "A REST API for managing and searching memories with Mem0 Open Source.\n\n"
        "When the ADMIN_API_KEY environment variable is set, protected endpoints require "
        "the `X-API-Key` header."
    ),
    version="1.0.0",
)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

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
    limit: Optional[int] = Field(None, description="Alias for top_k for Mem0 SDKs that use limit.")
    threshold: Optional[float] = Field(None, description="Minimum similarity score for results.")


def _prepare_search_kwargs(search_req: SearchRequest) -> tuple[Dict[str, Any], bool]:
    supported_params = inspect.signature(MEMORY_INSTANCE.search).parameters
    search_kwargs: Dict[str, Any] = {}

    for field_name in ("user_id", "run_id", "agent_id", "filters"):
        value = getattr(search_req, field_name)
        if value is not None and field_name in supported_params:
            search_kwargs[field_name] = value

    requested_limit = search_req.limit if search_req.limit is not None else search_req.top_k
    if requested_limit is not None:
        if "top_k" in supported_params:
            search_kwargs["top_k"] = requested_limit
        elif "limit" in supported_params:
            search_kwargs["limit"] = requested_limit
        else:
            logging.warning(
                "Search request asked for a result limit, but this Mem0 SDK version supports neither top_k nor limit."
            )

    threshold_is_native = False
    if search_req.threshold is not None:
        if "threshold" in supported_params:
            search_kwargs["threshold"] = search_req.threshold
            threshold_is_native = True
        else:
            logging.info("Mem0 SDK search() does not expose threshold; applying threshold filtering in the API layer.")

    return search_kwargs, threshold_is_native


def _apply_score_threshold(results: Any, threshold: Optional[float]) -> Any:
    if threshold is None or not isinstance(results, list):
        return results

    filtered_results = []
    skipped_items = 0

    for item in results:
        if not isinstance(item, dict):
            filtered_results.append(item)
            skipped_items += 1
            continue

        score = item.get("score")
        if score is None:
            filtered_results.append(item)
            skipped_items += 1
            continue

        try:
            if float(score) >= threshold:
                filtered_results.append(item)
        except (TypeError, ValueError):
            filtered_results.append(item)
            skipped_items += 1

    if skipped_items:
        logging.warning(
            "Threshold filtering skipped %s search result(s) because they did not expose a numeric score.",
            skipped_items,
        )

    return filtered_results


def _unwrap_vector_store_results(raw_results: Any) -> List[Any]:
    if raw_results is None:
        return []

    if isinstance(raw_results, (tuple, list)) and raw_results:
        first_element = raw_results[0]
        if isinstance(first_element, (list, tuple)):
            return list(first_element)

    if isinstance(raw_results, list):
        return raw_results

    return [raw_results]


def _format_vector_store_results(raw_results: Any) -> List[Dict[str, Any]]:
    promoted_payload_keys = ["user_id", "agent_id", "run_id", "actor_id", "role"]
    core_and_promoted_keys = {
        "data",
        "memory",
        "text",
        "content",
        "hash",
        "created_at",
        "updated_at",
        "id",
        "text_lemmatized",
        "attributed_to",
        *promoted_payload_keys,
    }

    formatted_results: List[Dict[str, Any]] = []
    for item in _unwrap_vector_store_results(raw_results):
        payload = getattr(item, "payload", None)
        item_id = getattr(item, "id", None)

        if isinstance(item, dict):
            payload = item.get("payload", item)
            item_id = item.get("id", item_id)

        if not isinstance(payload, dict):
            payload = {}

        memory_item: Dict[str, Any] = {
            "id": str(item_id) if item_id is not None else None,
            "memory": payload.get("data") or payload.get("memory") or payload.get("text") or payload.get("content") or "",
            "hash": payload.get("hash"),
            "created_at": payload.get("created_at"),
            "updated_at": payload.get("updated_at"),
        }

        for key in promoted_payload_keys:
            if key in payload:
                memory_item[key] = payload[key]

        additional_metadata = {key: value for key, value in payload.items() if key not in core_and_promoted_keys}
        if additional_metadata:
            memory_item["metadata"] = additional_metadata

        formatted_results.append(memory_item)

    return formatted_results


def _extract_collection_count(collection_info: Any) -> Optional[int]:
    if collection_info is None:
        return None

    if hasattr(collection_info, "model_dump"):
        dumped = collection_info.model_dump()
        if dumped != collection_info:
            return _extract_collection_count(dumped)

    candidate_keys = ("points_count", "vectors_count", "count", "row_count")
    if isinstance(collection_info, dict):
        for key in candidate_keys:
            value = collection_info.get(key)
            if isinstance(value, int) and value >= 0:
                return value
        return None

    for key in candidate_keys:
        value = getattr(collection_info, key, None)
        if isinstance(value, int) and value >= 0:
            return value

    return None


def _determine_global_list_limit() -> tuple[int, bool]:
    fallback_limit = _env_int("MEM0_GLOBAL_LIST_FALLBACK_LIMIT", 1000)
    vector_store = getattr(MEMORY_INSTANCE, "vector_store", None)
    if vector_store is None:
        return fallback_limit, True

    if hasattr(vector_store, "col_info"):
        try:
            collection_count = _extract_collection_count(vector_store.col_info())
            if collection_count is not None:
                return max(collection_count, 1), False
        except Exception as exc:
            logging.warning("Could not determine vector store size for global listing: %s", exc)

    return fallback_limit, True


def _call_vector_store_list(vector_store: Any, *, filters: Optional[Dict[str, Any]], limit: int) -> Any:
    attempts = [
        ((), {"filters": filters, "top_k": limit}),
        ((), {"filters": filters, "limit": limit}),
        ((), {"filters": filters, "topK": limit}),
        ((filters, limit), {}),
        ((filters,), {"top_k": limit}),
        ((filters,), {"limit": limit}),
        ((filters,), {"topK": limit}),
        ((filters,), {}),
        ((), {}),
    ]
    last_type_error: Optional[TypeError] = None

    for args, kwargs in attempts:
        try:
            return vector_store.list(*args, **kwargs)
        except TypeError as exc:
            last_type_error = exc
            continue

    raise RuntimeError(
        "Could not call vector_store.list() with any supported signature. "
        f"Last error: {last_type_error}"
    )


def _list_all_memories() -> Dict[str, Any]:
    vector_store = getattr(MEMORY_INSTANCE, "vector_store", None)
    if vector_store is None:
        raise RuntimeError("Mem0 vector store is not available.")

    limit, used_fallback_limit = _determine_global_list_limit()

    raw_results = _call_vector_store_list(vector_store, filters=None, limit=limit)
    formatted_results = _format_vector_store_results(raw_results)

    response: Dict[str, Any] = {
        "results": formatted_results,
        "scope": "all",
        "total": len(formatted_results),
    }
    if used_fallback_limit and len(formatted_results) >= limit:
        response["warning"] = (
            "The vector store size could not be determined exactly. "
            f"Returned the first {limit} memories from the store."
        )

    return response


@app.get("/", include_in_schema=False)
def home() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


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
    try:
        if not any([user_id, run_id, agent_id]):
            return _json_response(_list_all_memories())

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
        search_kwargs, threshold_is_native = _prepare_search_kwargs(search_req)
        results = MEMORY_INSTANCE.search(query=search_req.query, **search_kwargs)
        if search_req.threshold is not None and not threshold_is_native:
            results = _apply_score_threshold(results, search_req.threshold)
        return _json_response(results)
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
