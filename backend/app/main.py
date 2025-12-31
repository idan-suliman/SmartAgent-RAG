# backend/app/main.py
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from backend.app.settings import settings
from backend.app.core.utils import JobStatusManager

# Import Routers
from backend.app.api.kb_index import router as kb_index_router
from backend.app.api.kb_embed import router as kb_embed_router
from backend.app.api.kb_search import router as kb_search_router
from backend.app.api.chat import router as chat_router
from backend.app.api.admin import router as admin_router

app = FastAPI(title="SmartAgent-RAG")

# --------------------------------------------------------------------------
# 1. Static Files & UI
# --------------------------------------------------------------------------
STATIC_DIR = Path(__file__).resolve().parent / "static"
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

@app.get("/")
def root():
    return FileResponse(str(STATIC_DIR / "index.html"))

@app.get("/health")
def health():
    return {
        "status": "ok",
        "service": "SmartAgent-RAG",
        "config": {
            "inbox_dir": settings.inbox_dir,
            "index_dir": settings.index_dir,
            "top_k": settings.top_k,
            "embed_model": settings.embed_model,
            "chat_model": settings.chat_model,
        }
    }


# --------------------------------------------------------------------------
# 2. Register Routers
# --------------------------------------------------------------------------
app.include_router(kb_index_router)
app.include_router(kb_embed_router)
app.include_router(kb_search_router)
app.include_router(chat_router)
app.include_router(admin_router)


# --------------------------------------------------------------------------
# 3. Global Knowledge Base Status (For UI Top Bar)
# --------------------------------------------------------------------------
@app.get("/kb/status")
def kb_status():
    """Aggregates status from file counts, index jobs, and embedding jobs."""
    inbox = Path(settings.inbox_dir)
    index_dir = Path(settings.index_dir)

    # Fast file count
    files_count = sum(1 for _ in inbox.rglob("*") if _.is_file()) if inbox.exists() else 0

    # Approx chunk count
    chunks_path = index_dir / "chunks.jsonl"
    chunks_count = 0
    if chunks_path.exists():
        try:
            with chunks_path.open("r", encoding="utf-8") as f:
                for _ in f:
                    chunks_count += 1
        except Exception:
            pass

    # Embedding Metadata - Single provider (OpenAI)
    meta_path = index_dir / "embeddings_meta.json"
    
    emb_meta = {}
    if meta_path.exists():
        try:
            emb_meta = json.loads(meta_path.read_text(encoding="utf-8"))
        except Exception:
            pass

    # Load Job Statuses using the shared utility
    index_status_mgr = JobStatusManager(index_dir / "status_index.json")
    embed_status_mgr = JobStatusManager(index_dir / "status_embed.json")

    return {
        "files": files_count,
        "chunks": chunks_count,
        "embeddings": emb_meta.get("count", None),
        "embed_dim": emb_meta.get("dim", None),
        "embed_model": settings.embed_model,
        "chat_model": settings.chat_model,
        "top_k": settings.top_k,
        "index_status": index_status_mgr.load(),
        "embed_status": embed_status_mgr.load(),
    }