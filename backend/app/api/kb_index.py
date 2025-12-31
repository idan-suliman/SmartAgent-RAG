# backend/app/api/kb_index.py
"""
Knowledge Base Indexing API
---------------------------
Handles the ingestion of documents from the INBOX directory:
1. Iterates over supported files (PDF, DOCX, DOC, TXT).
2. Extracts text using specific extractors.
3. Chunks the text using smart splitting logic.
4. Generates a 'chunks.jsonl' file containing the processed data.
5. Supports incremental indexing (skipping unchanged files).
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
import time
import gc
import concurrent.futures
from pathlib import Path
from typing import Any, Dict, List, Optional
import shutil

from fastapi import APIRouter, Header

from backend.app.settings import settings
from backend.app.core.chunking import chunk_text
from backend.app.core.extractors.smart_pdf_extractor import extract_text_from_pdf
from backend.app.core.extractors.smart_docx_extractor import extract_text_from_docx
from backend.app.core.extractors.smart_doc_extractor import extract_text_from_doc
from backend.app.core import keywords as kw
from backend.app.core.utils import JobStatusManager
from backend.app.core.security import require_admin

# Handle legacy .doc files (Windows only)
try:
    import pythoncom
except ImportError:
    pythoncom = None
    print("[WARN] 'pythoncom' module not found. Legacy .doc files might fail in threaded mode.")

router = APIRouter(prefix="/kb", tags=["kb"])

# --- Constants ---
SUPPORTED_EXTS = {".txt", ".pdf", ".docx", ".doc"}
HEAVY_FILE_THRESHOLD_SEC = 5.0
FILE_TIMEOUT_SEC = 60 

# =========================================================
# HELPER FUNCTIONS
# =========================================================

def _hard_split_chunk(text: str, max_chars: int, overlap: int) -> List[str]:
    """
    Splits a chunk that exceeds the hard character limit into smaller pieces.
    Attempts to break at line breaks or spaces.
    """
    t = (text or "").strip()
    if not t:
        return []
    if len(t) <= max_chars:
        return [t]

    parts: List[str] = []
    start = 0
    n = len(t)
    max_chars = max(200, int(max_chars))
    overlap = max(0, int(overlap))

    while start < n:
        end = min(start + max_chars, n)
        
        cut = end
        if end < n:
            window = t[start:end]
            nl = window.rfind("\n")
            sp = window.rfind(" ")
            best = max(nl, sp)
            if best > int(0.7 * len(window)):
                cut = start + best

        piece = t[start:cut].strip()
        if piece:
            parts.append(piece)
        
        if cut >= n:
            break
            
        next_start = cut - overlap
        if next_start <= start:
            next_start = cut
            if next_start <= start: 
                next_start = start + 1
        
        start = next_start

    return parts


def _term_progress(prefix: str, done: int, total: int, started: float, extra: str = "") -> None:
    """Print a progress bar to the terminal/console."""
    pct = (done / max(total, 1)) * 100.0
    elapsed = time.perf_counter() - started
    rate = done / max(elapsed, 1e-9)
    remaining = total - done
    eta = remaining / max(rate, 1e-9)
    sys.stdout.write(
        f"\r{prefix} {done}/{total} ({pct:5.1f}%) | {rate:6.2f}/sec | ETA {eta:6.1f}s {extra}   "
    )
    sys.stdout.flush()


def _get_legacy_id(path: Path) -> str:
    """Old ID Generation: path + size + mtime (Sensitive to path changes)."""
    st = path.stat()
    h = hashlib.sha1()
    h.update(str(path.as_posix()).encode("utf-8"))
    h.update(str(st.st_size).encode("utf-8"))
    h.update(str(int(st.st_mtime)).encode("utf-8"))
    return h.hexdigest()

def _get_stable_id(path: Path) -> str:
    """New ID Generation: filename + size + mtime (Robust to folder moves)."""
    st = path.stat()
    h = hashlib.sha1()
    h.update(path.name.encode("utf-8"))
    h.update(str(st.st_size).encode("utf-8"))
    h.update(str(int(st.st_mtime)).encode("utf-8"))
    return h.hexdigest()

def _iter_files(root: Path):
    """Recursively yield all supported files in the directory."""
    for p in root.rglob("*"):
        if p.is_file() and p.suffix.lower() in SUPPORTED_EXTS:
            yield p

def _read_text_safe(fp: str) -> str:
    """
    Reads text from a file based on its extension.
    Handles extraction logic safely.
    """
    path_obj = Path(fp)
    ext = path_obj.suffix.lower()

    # COM initialization for Windows Word interop
    if ext == ".doc" and pythoncom:
        try:
            pythoncom.CoInitialize()
        except Exception:
            pass 
    
    try:
        if ext == ".txt":
            return path_obj.read_text(encoding="utf-8", errors="ignore")
        if ext == ".pdf":
            return extract_text_from_pdf(fp)
        if ext == ".docx":
            return extract_text_from_docx(fp)
        if ext == ".doc":
            return extract_text_from_doc(fp)
        return ""
    finally:
        if ext == ".doc" and pythoncom:
            try:
                pythoncom.CoUninitialize()
            except Exception:
                pass

def _read_text_with_timeout(fp: Path, timeout: int = FILE_TIMEOUT_SEC) -> str:
    """Wraps _read_text_safe in a thread with a strict timeout."""
    if str(fp).lower().endswith(".doc") and pythoncom is None:
        print(f"[INDEX][SKIP] Skipping .doc file (missing pythoncom): {fp.name}")
        return ""

    executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
    future = executor.submit(_read_text_safe, str(fp))

    try:
        return future.result(timeout=timeout)
    
    except concurrent.futures.TimeoutError:
        executor.shutdown(wait=False)
        raise TimeoutError(f"Timeout after {timeout}s - Aborted stuck thread")
    
    except Exception as e:
        executor.shutdown(wait=False)
        raise e
    
    finally:
        executor.shutdown(wait=False)


# --- Tokenization for Keyword Search (BM25) ---
_EMAIL_RE = re.compile(r"\b[\w.\-+]+@[\w.\-]+\.\w+\b", re.IGNORECASE)
_URL_RE = re.compile(r"\bhttps?://\S+\b|\bwww\.\S+\b", re.IGNORECASE)

def _lex_tokens(text: str, max_tokens: int = 80) -> List[str]:
    """Extracts lexical tokens for BM25 search."""
    if not text:
        return []

    # Use specialized tokenizer if available in core
    build_fn = getattr(kw, "build_lex_tokens", None)
    if callable(build_fn):
        try:
            return build_fn(text, max_tokens=max_tokens)
        except TypeError:
            return build_fn(text)
            
    # Fallback tokenizer
    stop_he = getattr(kw, "HE_STOPWORDS", set())
    stop_en = getattr(kw, "STOPWORDS_EN", set())
    stop_legal = getattr(kw, "LEGAL_STOPWORDS", set())
    
    t = text.lower()
    t = _EMAIL_RE.sub(" ", t)
    t = _URL_RE.sub(" ", t)
    t = re.sub(r"[^\w\u0590-\u05FF]+", " ", t)
    raw = [w for w in t.split() if len(w) >= 2]

    out: List[str] = []
    seen = set()
    all_stops = stop_he | stop_en | stop_legal

    for w in raw:
        if w in all_stops:
            continue
        if w.isdigit() and len(w) < 3:
            continue
        if w not in seen:
            seen.add(w)
            out.append(w)
        if len(out) >= max_tokens:
            break
    return out


# =========================================================
# API ENDPOINTS
# =========================================================

@router.get("/index/status")
def index_status():
    """Returns the current status of the indexing job."""
    status_mgr = JobStatusManager(Path(settings.index_dir) / "status_index.json")
    return status_mgr.load()


@router.post("/index")
def build_index(x_admin_code: str | None = Header(default=None)):
    """
    Starts the Indexing Job.
    Scans the INBOX, extracts text, chunks it, and saves to chunks.jsonl.
    Uses incremental logic to reuse existing chunks for unchanged files.
    """
    require_admin(x_admin_code)
    
    inbox = Path(settings.inbox_dir)
    index_dir = Path(settings.index_dir)
    index_dir.mkdir(parents=True, exist_ok=True)

    status_mgr = JobStatusManager(index_dir / "status_index.json")
    out_path = index_dir / "chunks.jsonl"

    if not inbox.exists():
        err = f"INBOX not found: {inbox}"
        status_mgr.fail_job(err)
        return {"ok": False, "error": err}

    # Load Configuration
    lex_max = settings.lex_max_tokens
    HARD_MAX_CHARS = settings.embed_max_chars
    OVERLAP_CHARS = settings.hard_split_overlap 

    files = list(_iter_files(inbox))
    total_files = len(files)

    started = time.perf_counter()
    heavy_files: List[Dict[str, Any]] = []
    
    base_status = {
        "total_files": total_files,
        "processed_files": 0,
        "docs_indexed": 0,
        "docs_skipped_empty": 0,
        "docs_failed": 0,
        "chunks_written": 0,
        "current_file": None,
        "heavy_files": [],
        "phase": "index"
    }
    status_mgr.start_job(base_status)

    docs_indexed = 0
    docs_skipped_empty = 0
    docs_failed = 0
    chunks_written = 0

    last_status_update = time.perf_counter()
    status_every_sec = 0.5
    
    # --- Incremental Logic Setup ---
    chunks_backup = index_dir / "chunks.old.jsonl"
    existing_chunks_map = {} # map by doc_id (could be legacy or stable)

    if out_path.exists():
        try:
            shutil.copy2(out_path, chunks_backup)
            print(f"[INDEX] Backed up chunks to {chunks_backup.name}")
            
            # Load existing chunks for reuse
            with out_path.open("r", encoding="utf-8") as f:
                for line in f:
                    try:
                        rec = json.loads(line)
                        did = rec.get("doc_id")
                        if did:
                            if did not in existing_chunks_map:
                                existing_chunks_map[did] = []
                            existing_chunks_map[did].append(rec)
                    except Exception:
                        pass
        except Exception as e:
            print(f"[INDEX][WARN] Backup failed: {e}") 

    try:
        with out_path.open("w", encoding="utf-8") as f_out:
            
            if total_files == 0:
                status_mgr.complete_job({
                    "message": "Indexing completed (no files found)",
                    "output": str(out_path),
                    **base_status
                })
                return {"ok": True, "output": str(out_path)}

            for i_file, fp in enumerate(files, start=1):
                file_start_time = time.perf_counter()
                
                # Relative path logic
                rel_path = str(fp.relative_to(inbox)).replace("\\", "/")
                folder_tag = rel_path.split("/")[0] if "/" in rel_path else "root"

                # Calculate IDs
                stable_id = _get_stable_id(fp)
                legacy_id = _get_legacy_id(fp)
                
                reusable_chunks = None
                
                # Check 1: Already indexed with Stable ID (Robust to move)
                if stable_id in existing_chunks_map:
                    reusable_chunks = existing_chunks_map[stable_id]
                
                # Check 2: Indexed with Legacy ID (Old version or file hasn't moved)
                if not reusable_chunks and legacy_id in existing_chunks_map:
                    reusable_chunks = existing_chunks_map[legacy_id]

                # Update Status UI
                now = time.perf_counter()
                if now - last_status_update >= status_every_sec:
                    elapsed = now - started
                    rate = (i_file - 1) / max(elapsed, 1e-9)
                    rem = total_files - (i_file - 1)
                    eta = rem / max(rate, 1e-9)
                    
                    base_status.update({
                        "processed_files": i_file - 1,
                        "docs_indexed": docs_indexed,
                        "docs_failed": docs_failed,
                        "chunks_written": chunks_written,
                        "elapsed_sec": round(elapsed, 3),
                        "eta_sec": round(eta, 1),
                        "current_file": rel_path,
                        "message": f"Processing {i_file}/{total_files}: {rel_path[:50]}...",
                        "heavy_files": heavy_files
                    })
                    status_mgr.update(base_status)
                    last_status_update = now

                if reusable_chunks:
                    # --- REUSE EXISTING CHUNKS ---
                    for rec in reusable_chunks:
                        rec["doc_id"] = stable_id # Migrate to stable ID if necessary
                        rec["source_path"] = rel_path
                        rec["folder_tag"] = folder_tag
                        if "chunk_id" in rec:
                            # Update chunk_id prefix if it relied on doc_id
                            suffix = rec["chunk_id"].split(":")[-1]
                            rec["chunk_id"] = f"{stable_id}:{suffix}"
                        
                        f_out.write(json.dumps(rec, ensure_ascii=False) + "\n")
                        chunks_written += 1
                        
                    docs_indexed += 1
                    continue # Skip processing
                
                # --- PROCESS NEW FILE ---
                text = ""
                try:
                    text = _read_text_with_timeout(fp, timeout=FILE_TIMEOUT_SEC).strip()
                except TimeoutError:
                    docs_failed += 1
                    sys.stdout.write("\n")
                    print(f"[INDEX][TIMEOUT] Stuck on file: {rel_path}. Skipping.")
                    heavy_files.append({"file": rel_path, "sec": FILE_TIMEOUT_SEC, "status": "TIMEOUT"})
                    continue
                except Exception as e:
                    docs_failed += 1
                    sys.stdout.write("\n")
                    print(f"[INDEX][WARN] Failed: {rel_path} | {e}")
                    continue

                file_duration = time.perf_counter() - file_start_time
                if file_duration > HEAVY_FILE_THRESHOLD_SEC:
                    heavy_files.append({
                        "file": rel_path,
                        "sec": round(file_duration, 2),
                        "size_kb": round(fp.stat().st_size / 1024, 1),
                    })
                    gc.collect()

                if not text:
                    docs_skipped_empty += 1
                else:
                    docs_indexed += 1
                    # Chunking
                    base_chunks = chunk_text(text)
                    
                    doc_id = stable_id 
                    local_chunk_index = 0
                    
                    for ch in base_chunks:
                        ch = (ch or "").strip()
                        if not ch: continue
                        
                        # Handle huge blocks
                        if len(ch) <= HARD_MAX_CHARS:
                            final_pieces = [ch]
                        else:
                            final_pieces = _hard_split_chunk(ch, max_chars=HARD_MAX_CHARS, overlap=OVERLAP_CHARS)
                        
                        for piece in final_pieces:
                            title_snippet = " ".join(piece.split()[:12])
                            
                            # Stable ID: doc_id:local_index
                            final_chunk_id = f"{doc_id}:{local_chunk_index}"
                            
                            record = {
                                "chunk_id": final_chunk_id,
                                "doc_id": doc_id,
                                "source_path": rel_path,
                                "folder_tag": folder_tag,
                                "chunk_index": chunks_written, 
                                "local_index": local_chunk_index,
                                "title": title_snippet,
                                "text": piece,
                                "lex_tokens": _lex_tokens(piece, max_tokens=lex_max),
                            }
                            f_out.write(json.dumps(record, ensure_ascii=False) + "\n")
                            chunks_written += 1
                            local_chunk_index += 1

                _term_progress(
                    prefix="[INDEX]",
                    done=i_file,
                    total=total_files,
                    started=started,
                    extra=f"| chunks={chunks_written}"
                )

        elapsed = time.perf_counter() - started
        base_status.update({
            "processed_files": total_files,
            "docs_indexed": docs_indexed,
            "docs_skipped_empty": docs_skipped_empty,
            "docs_failed": docs_failed,
            "chunks_written": chunks_written,
            "elapsed_sec": round(elapsed, 3),
            "current_file": None,
            "message": "Indexing completed",
            "output": str(out_path),
            "heavy_files": heavy_files
        })
        status_mgr.complete_job(base_status)

        print(f"\n[INDEX] Done. {chunks_written} chunks generated.")
        return base_status

    except Exception as e:
        status_mgr.fail_job(f"Fatal error: {str(e)}")
        raise