# backend/app/api/kb_search.py
from __future__ import annotations

from typing import Any, Dict
from fastapi import APIRouter, HTTPException

from backend.app.settings import settings
from backend.app.core.search_engine import search_engine

router = APIRouter(prefix="/kb", tags=["kb"])

@router.post("/search")
def search_kb_endpoint(payload: Dict[str, Any]):
    """
    Hybrid search endpoint.
    Payload: {"query": str, "top_k": int, "filters": dict}
    """
    if not getattr(settings, "openai_api_key", None):
        raise HTTPException(status_code=400, detail="OPENAI_API_KEY is missing.")

    query = (payload.get("query") or "").strip()
    if not query:
        raise HTTPException(status_code=400, detail="Query is required.")

    top_k = int(payload.get("top_k") or settings.top_k)
    filters = payload.get("filters", {})

    try:
        # Delegate logic to the engine
        results = search_engine.search(query=query, top_k=top_k, filters=filters)
        
        return {
            "ok": True,
            "query": query,
            "results": results,
            "total_docs": len(search_engine.rows)
        }
    except Exception as e:
        print(f"[SEARCH API ERROR] {e}")
        raise HTTPException(status_code=500, detail=str(e))