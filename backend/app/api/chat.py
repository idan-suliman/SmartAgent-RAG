# backend/app/api/chat.py
"""
Chat API Endpoint
-----------------
Handles the RAG (Retrieval-Augmented Generation) chat flow:
1. Receives user message and history.
2. Rewrites the query for better search (optional).
3. Retrieves relevant chunks from the Knowledge Base (Search Engine).
4. Handles ad-hoc file uploads (if provided).
5. Constructs the prompt and streams the response from OpenAI.
"""

from __future__ import annotations

import json
import shutil
import uuid
import os
from typing import List, Dict, Any, Generator, Optional
from pathlib import Path

from fastapi import APIRouter, Request, UploadFile, File
from fastapi.responses import StreamingResponse, JSONResponse
from openai import OpenAI

from backend.app.settings import settings
from backend.app.core.search_engine import search_engine
from backend.app.core.config_manager import config_manager
from backend.app.core.extraction_manager import extract_text_from_file
from backend.app.core.chunking import chunk_text_for_embedding

router = APIRouter()

# =========================================================
# HELPER FUNCTIONS
# =========================================================

def _get_dynamic_openai_client() -> Optional[OpenAI]:
    """
    Creates an OpenAI client using the API key from the dynamic configuration 
    (admin settings). Falls back to the .env file if missing.
    """
    key = config_manager.get_key("openai_api_key", "openai_api_key")
    if not key:
        return None
    return OpenAI(api_key=key)

# =========================================================
# AD-HOC FILE UPLOAD LOGIC
# =========================================================

@router.post("/chat/upload")
async def upload_temp_file(file: UploadFile = File(...)):
    """
    Uploads a file to a temporary directory (`data/temp_uploads`) and returns a file_id.
    This allows the chat stream to process the file without sending large payloads.
    """
    try:
        upload_dir = Path("data/temp_uploads")
        upload_dir.mkdir(parents=True, exist_ok=True)
        
        # Generate unique filename
        ext = Path(file.filename).suffix or ".txt"
        file_id = f"{uuid.uuid4()}_{file.filename}"
        file_path = upload_dir / file_id
        
        # Save file
        with file_path.open("wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
            
        return JSONResponse({"ok": True, "file_id": file_id, "filename": file.filename})
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=500)


def _process_uploaded_file(
    file_id: str, 
    client: OpenAI, 
    query_text: str
) -> List[Dict[str, Any]]:
    """
    Processes a temporarily uploaded file:
    1. Extracts text.
    2. Chunks the text.
    3. Generates embeddings on-the-fly.
    4. Performs an in-memory vector search against the user's query.
    
    Returns the top matching chunks.
    """
    upload_dir = Path("data/temp_uploads")
    file_path = upload_dir / file_id
    
    if not file_path.exists():
        print(f"[ADHOC] File not found: {file_path}")
        return []
    
    print(f"[ADHOC] Processing {file_id}...")
        
    try:
        # 1. Extract Text
        text = extract_text_from_file(file_path)
        if not text:
            print("[ADHOC] Extraction returned empty text.")
            return []

        # Cleanup: Delete file after extraction to save space
        try:
            file_path.unlink()
        except OSError:
            pass

        # 2. Chunk Text
        chunks = chunk_text_for_embedding(text)
        if not chunks:
            return []

        print(f"[ADHOC] Generated {len(chunks)} chunks. Embedding...")

        # 3. Create Embeddings (Documents & Query)
        resp = client.embeddings.create(input=chunks, model=settings.embed_model)
        chunk_vecs = [d.embedding for d in resp.data]
        
        q_resp = client.embeddings.create(input=[query_text], model=settings.embed_model)
        q_vec = q_resp.data[0].embedding

        # 4. Rank Chunks (In-Memory Search)
        scores = search_engine.rank_adhoc_chunks(q_vec, chunk_vecs)
        
        results = []
        for i, score in enumerate(scores):
            results.append({
                "source_path": f"[TEMP] {file_id}", 
                "title": f"Ad-Hoc Chunk {i+1}",
                "text": chunks[i],
                "score": float(score)
            })

        # Sort by score descending
        results.sort(key=lambda x: x["score"], reverse=True)
        return results[:5]  # Top 5 ad-hoc chunks

    except Exception as e:
        print(f"[ADHOC] Process error: {e}")
        return []


# =========================================================
# QUERY OPTIMIZATION
# =========================================================

def _rewrite_query(client: Optional[OpenAI], history: List[Dict[str, str]], current_msg: str) -> str:
    """
    Uses an LLM call to rewrite the user's query into an optimal search query.
    Takes into account the conversation history.
    """
    if not client or not history:
        return current_msg

    context_msgs = history[-4:]
    
    # System Prompt for Query Rewriting (Hebrew)
    system_prompt = (
        "אתה עורך דין ישראלי בכיר ומומחה למערכות אחזור מידע (Information Retrieval). "
        "תפקידך: לקבל היסטוריית שיחה ושאלה אחרונה של משתמש, ולנסח מחדש שאילתת חיפוש אופטימלית למאגר משפטי."
        "\n\n"
        "הנחיות לביצוע:"
        "\n1. עצמאות: השאילתה חייבת להיות מובנת בפני עצמה ללא צורך בהיסטוריה."
        "\n2. העשרת מונחים: הוסף מילים נרדפות משפטיות רלוונטיות."
        "\n3. מיקוד: השמט מילות קישור מיותרות והתמקד במונחי המפתח."
        "\n4. אל תענה על השאלה! הפלט שלך הוא אך ורק השאילתה המשוכתבת."
    )

    messages = [{"role": "system", "content": system_prompt}]
    
    for h in context_msgs:
        role = h.get("role")
        content = h.get("content")
        # Normalize roles
        if role and content:
            if role not in ["system", "user", "assistant"]:
                role = "user"
            messages.append({"role": role, "content": content})
            
    messages.append({"role": "user", "content": f"שאלה נוכחית: {current_msg}"})

    try:
        completion = client.chat.completions.create(
            model="gpt-4o",  # Use a smart model for rewriting
            messages=messages,
            temperature=0.1,
            max_tokens=150
        )
        rewritten = completion.choices[0].message.content.strip()
        # Cleanup quotes
        return rewritten.replace('"', '').replace("'", "").replace("\n", " ")
    except Exception as e:
        print(f"[REWRITE ERROR] Fallback to original. Error: {e}")
        return current_msg


def _format_context(results: List[Dict[str, Any]], max_chars_each: int = 1500) -> str:
    """
    Formats the search results into a string block to be injected into the system prompt.
    """
    if not results:
        return ""
    
    parts = ["--- מקורות מהמאגר (לשימוש בתשובה) ---"]
    for i, r in enumerate(results, start=1):
        src = r.get("source_path") or "unknown"
        title = r.get("title") or ""
        txt = (r.get("text") or "").strip()
        score = r.get("score", 0)
        
        # Truncate long chunks
        if len(txt) > max_chars_each:
            txt = txt[:max_chars_each].rstrip() + " ...[המשך קטע]"
            
        parts.append(f"מקור [{i}] (ציון התאמה: {score}):\nקובץ: {src} | כותרת: {title}\nתוכן: {txt}")
        
    parts.append("--- סוף מקורות ---")
    return "\n\n".join(parts)


# =========================================================
# CHAT STREAM ENDPOINT
# =========================================================

@router.post("/chat/stream")
async def chat_stream(request: Request):
    """
    Main Chat Streaming Endpoint (Server-Sent Events).
    """
    body = await request.json()
    message = (body.get("message") or "").strip()
    history = body.get("history") or []
    requested_model = body.get("model")
    
    # 1. Routing Logic: Determine Target Model
    if not requested_model or requested_model not in ["gpt-5.2", "gpt-4o"]:
        target_model = "gpt-4o"
    else:
        target_model = requested_model

    if not message:
        # Error generator
        def err_gen(): 
            yield f"data: {json.dumps({'type':'error','message':'Empty message'}, ensure_ascii=False)}\n\n"
        return StreamingResponse(err_gen(), media_type="text/event-stream")

    # 2. Initialize OpenAI Client
    openai_client = _get_dynamic_openai_client()
    
    # 3. Process Query (Rewrite)
    rewritten_query = message
    if history and openai_client:
        rewritten_query = _rewrite_query(openai_client, history, message)
        print(f"[CHAT] Original: '{message}' | Rewritten: '{rewritten_query}'")

    # 4. Search Knowledge Base
    try:
        results = search_engine.search(query=rewritten_query, top_k=settings.top_k)
    except Exception as e:
        print(f"[SEARCH ERROR] {e}")
        results = []

    # 5. Handle Ad-Hoc File Search (if file_id present)
    file_id = body.get("file_id")
    if file_id and openai_client:
        print(f"[CHAT] Processing uploaded file ID: {file_id}")
        adhoc_results = _process_uploaded_file(file_id, openai_client, rewritten_query)
        if adhoc_results:
            # Merge results: Add ad-hoc chunks to main results
            # Strategy: Simply append and re-sort or mix? 
            # We'll append and take top K overall.
            results.extend(adhoc_results)
            results.sort(key=lambda x: x["score"], reverse=True)
            results = results[:settings.top_k]

    # 6. Build Context String
    ctx_text = _format_context(results)
    
    # Load System Prompt
    config_data = config_manager.load_config()
    current_system_prompt = config_data.get("system_prompt", "")
    if not current_system_prompt:
        current_system_prompt = "אתה עוזר משפטי חכם."

    final_system_msg = current_system_prompt
    if ctx_text:
        final_system_msg += f"\n\n{ctx_text}"
    else:
        final_system_msg += "\n\n[לא נמצאו מקורות רלוונטיים במאגר. ענה על סמך ידע משפטי כללי, אך סייג את תשובתך.]"

    # 7. Generator Function for SSE
    def gen() -> Generator[str, None]:
        try:
            # A. Stream Sources Metadata
            sources_data = [
                {
                    "file": r.get("source_path"), 
                    "score": round(float(r.get("score", 0.0)), 3),
                    "page_content": (r.get("text") or "")[:200]
                }
                for r in results
            ]
            yield f"data: {json.dumps({'type':'sources','sources': sources_data}, ensure_ascii=False)}\n\n"

            # B. Stream OpenAI Response
            if openai_client:
                print(f"[CHAT] Routing to OpenAI ({target_model})...")
                
                # Construct Messages
                messages = [{"role": "system", "content": final_system_msg}]
                for h in history[-10:]:
                    role = h.get("role")
                    content = h.get("content")
                    if role in ("user", "assistant") and content:
                        messages.append({"role": role, "content": content})
                messages.append({"role": "user", "content": message})

                # Call API
                stream = openai_client.chat.completions.create(
                    model=target_model,
                    messages=messages,
                    stream=True,
                    temperature=0.3,
                )
                
                for chunk in stream:
                    if chunk.choices and chunk.choices[0].delta.content:
                        content_chunk = chunk.choices[0].delta.content
                        yield f"data: {json.dumps({'type':'delta','delta': content_chunk}, ensure_ascii=False)}\n\n"
            else:
                yield f"data: {json.dumps({'type':'error','message': 'Missing OpenAI API Key'}, ensure_ascii=False)}\n\n"

            # C. Finish
            yield f"data: {json.dumps({'type':'done'}, ensure_ascii=False)}\n\n"

        except Exception as e:
            print(f"[STREAM ERROR] {e}")
            yield f"data: {json.dumps({'type':'error','message': str(e)}, ensure_ascii=False)}\n\n"

    return StreamingResponse(gen(), media_type="text/event-stream")