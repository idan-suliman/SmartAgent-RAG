# backend/app/core/search_engine.py
"""
Search Engine Core
------------------
Manages the retrieval logic:
1. Loads the index (Chunks + Embeddings).
2. Performs Semantic Search (Cosine Similarity).
3. Performs Lexical Search (BM25) - if available.
4. Ranks results using a hybrid score (Weighted sum + Bonuses).
5. Supports Ad-Hoc file ranking (In-memory).
"""

from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Any, Dict, List, Optional
import numpy as np

from backend.app.settings import settings
from backend.app.core.utils import get_openai_client
from backend.app.core import keywords as kw

# Optional: rank_bm25 for lexical search
try:
    from rank_bm25 import BM25Okapi
except ImportError:
    BM25Okapi = None
    print("[WARN] 'rank_bm25' not installed. Lexical search will be disabled.")


class SearchEngine:
    _instance: Optional[SearchEngine] = None

    def __init__(self):
        self.last_mtime: float = 0.0
        self.rows: List[dict] = []
        self.embeddings: np.ndarray | None = None
        self.bm25: Any | None = None

    @classmethod
    def get_instance(cls) -> SearchEngine:
        """Singleton accessor."""
        if cls._instance is None:
            cls._instance = SearchEngine()
        return cls._instance

    def _get_stopwords(self) -> set:
        """Aggregates stopwords from Hebrew, English, and Legal dictionaries."""
        he = getattr(kw, "STOPWORDS_HE", set()) or set()
        en = getattr(kw, "STOPWORDS_EN", set()) or set()
        legal = getattr(kw, "LEGAL_STOPWORDS", set()) or set()
        return set(he) | set(en) | set(legal)

    def tokenize_query(self, query: str) -> List[str]:
        """
        Tokenizes the query for BM25:
        1. Lowercases and removes special characters.
        2. Filters out stopwords.
        """
        q = (query or "").strip().lower()
        if not q:
            return []
        
        # Keep alphanumeric and Hebrew characters
        q = re.sub(r"[^\w\u0590-\u05FF]+", " ", q)
        tokens = [t for t in q.split() if len(t) >= 2]

        sw = self._get_stopwords()
        filtered = [t for t in tokens if t not in sw]
        return filtered

    def needs_refresh(self) -> bool:
        """Checks if the index files on disk have changed since last load."""
        index_dir = Path(settings.index_dir)
        c_path = index_dir / "chunks.jsonl"
        e_path = index_dir / "embeddings.npy"

        if not c_path.exists() or not e_path.exists():
            return True 
        
        mt_chunks = c_path.stat().st_mtime
        mt_emb = e_path.stat().st_mtime
        current_max = max(mt_chunks, mt_emb)
        
        return current_max > self.last_mtime or not self.rows

    def load_index(self):
        """Loads chunks.jsonl and embeddings.npy into memory."""
        index_dir = Path(settings.index_dir)
        c_path = index_dir / "chunks.jsonl"
        e_path = index_dir / "embeddings.npy"

        if not c_path.exists() or not e_path.exists():
            print("[SEARCH] Index files missing. Skipping load.")
            self.rows = []
            self.embeddings = None
            return

        print(f"[SEARCH] Loading KB from {index_dir}...")
        t0 = time.perf_counter()

        # 1. Load Chunks
        new_rows = []
        with c_path.open("r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    new_rows.append(json.loads(line))
        
        # 2. Load Vectors
        try:
            new_emb = np.load(e_path).astype(np.float32)
        except Exception as e:
            print(f"[SEARCH] Failed to load embeddings: {e}")
            return

        # Integrity Check
        if len(new_rows) != new_emb.shape[0]:
            print(f"[SEARCH][ERR] Mismatch! rows={len(new_rows)}, emb={new_emb.shape[0]}")
            limit = min(len(new_rows), new_emb.shape[0])
            new_rows = new_rows[:limit]
            new_emb = new_emb[:limit]

        self.rows = new_rows
        self.embeddings = new_emb

        # 3. Build BM25 Index
        if BM25Okapi:
            tokenized_corpus = []
            for r in self.rows:
                tokens = r.get("lex_tokens")
                if not tokens:
                    tokens = self.tokenize_query(r.get("text", ""))
                tokenized_corpus.append(tokens)
            
            self.bm25 = BM25Okapi(tokenized_corpus)
            print(f"[SEARCH] BM25 Index built for {len(self.rows)} docs.")

        self.last_mtime = max(c_path.stat().st_mtime, e_path.stat().st_mtime)
        print(f"[SEARCH] Loaded successfully in {time.perf_counter()-t0:.3f}s")

    def _normalize_vectors(self, v: np.ndarray) -> np.ndarray:
        """L2 Normalization for Cosine Similarity."""
        norm = np.linalg.norm(v, axis=-1, keepdims=True)
        norm[norm == 0] = 1e-12
        return v / norm

    def _calculate_bonus_score(self, row: dict, query_tokens: List[str]) -> float:
        """
        Calculates distinct bonuses for results derived from metadata match
        or appearance of Important Legal Concepts.
        """
        if not query_tokens: return 0.0
        
        score = 0.0
        title = (row.get("title") or "").lower()
        src = (row.get("source_path") or "").lower()
        text_preview = (row.get("text") or "")[:500].lower() # optimization
        
        important_concepts = getattr(kw, "IMPORTANT_LEGAL_CONCEPTS", set())

        for t in query_tokens:
            # Metadata Bonus
            if t in title: score += 0.6
            if t in src: score += 0.4
            
            # Legal Concept Bonus
            if t in important_concepts:
                # Extra boost if concept appears in text body
                if t in text_preview:
                    score += 0.5

        return min(score, 3.0) 

    def search(self, query: str, top_k: int = 5, filters: Dict = None) -> List[Dict[str, Any]]:
        """
        Main Search Logic:
        1. Embed Query (OpenAI).
        2. Vector Search (Cosine).
        3. Lexical Search (BM25).
        4. Fuse scores (0.7 Vector + 0.3 BM25) + Bonus.
        """
        if self.needs_refresh():
            self.load_index()
        
        if not self.rows or self.embeddings is None:
            return []

        # 1. Embed Query
        q_vec = None
        try:
            client = get_openai_client()
            if not client: return []

            resp = client.embeddings.create(
                model=settings.embed_model,
                input=query,
                dimensions=int(settings.embed_dimensions) if settings.embed_dimensions else None
            )
            q_vec = np.array(resp.data[0].embedding, dtype=np.float32)

        except Exception as e:
            print(f"[SEARCH] Embed Error: {e}")
            return []

        # Normalize Query
        norm_q = np.linalg.norm(q_vec)
        if norm_q > 0: q_vec /= norm_q
        
        # Normalize Index
        emb_norm = self._normalize_vectors(self.embeddings)
        vec_scores = emb_norm @ q_vec

        # 2. BM25 Search
        bm25_scores = np.zeros(len(self.rows), dtype=np.float32)
        q_tokens = self.tokenize_query(query)
        
        if self.bm25 and q_tokens:
            raw_scores = self.bm25.get_scores(q_tokens)
            if raw_scores.max() > 0:
                bm25_scores = raw_scores / raw_scores.max()

        # 3. Combine Scores (Semantic + Lexical)
        final_scores = (vec_scores * 0.70) + (bm25_scores * 0.30)

        # 4. Rank & Format
        results = []
        candidates_idx = np.argsort(final_scores)[::-1]
        
        count = 0
        for idx in candidates_idx:
            if count >= top_k: break
            
            base_score = float(final_scores[idx])
            if base_score < 0.15: continue # Threshold
            
            row = self.rows[idx]
            
            # Simple metadata filtering (if requested)
            if filters:
                match = True
                for k, v in filters.items():
                    if str(row.get(k, "")).lower() != str(v).lower():
                        match = False; break
                if not match: continue

            bonus = self._calculate_bonus_score(row, q_tokens)
            final_total = base_score + bonus
            
            results.append({
                "score": round(final_total, 4),
                "base_score": round(base_score, 4),
                "source_path": row.get("source_path"),
                "title": row.get("title"),
                "chunk_index": row.get("chunk_index"),
                "text": row.get("text", ""),
                "doc_id": row.get("doc_id")
            })
            count += 1

        results.sort(key=lambda x: x["score"], reverse=True)
        return results[:top_k]

    def rank_adhoc_chunks(self, q_vec: np.ndarray, chunk_vecs: List[List[float]]) -> List[float]:
        """
        Computes cosine similarity between a query vector and a list of arbitrary chunk vectors.
        Used for Ad-Hoc file processing (in-memory context).
        """
        if not chunk_vecs:
            return []
            
        scores = []
        q = np.array(q_vec)
        q_norm = np.linalg.norm(q)
        
        for v_list in chunk_vecs:
            v = np.array(v_list)
            v_norm = np.linalg.norm(v)
            
            if q_norm == 0 or v_norm == 0:
                scores.append(0.0)
            else:
                s = np.dot(q, v) / (q_norm * v_norm)
                scores.append(float(s))
                
        return scores


search_engine = SearchEngine.get_instance()