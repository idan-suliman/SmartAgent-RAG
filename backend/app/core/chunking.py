# backend/app/core/chunking.py
from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass
from typing import List
from backend.app.core.text_utils import clean_text_output as clean_text
from backend.app.settings import settings


# -------------------------
# Config
# -------------------------
@dataclass(frozen=True)
class ChunkingConfig:
    # mode: "simple" (chars+overlap) or "smart" (paragraph/heading aware + words)
    mode: str = "smart"

    # simple mode
    max_chars: int = 400
    overlap: int = 100

    # smart mode
    min_words: int = 60
    max_words: int = 180
    break_threshold: float = 0.20  # lower => more splits; 0 disables cohesion-based splitting
    respect_headings: bool = True
    keep_bullets: bool = True


def config_from_settings() -> ChunkingConfig:
    return ChunkingConfig(
        mode=settings.chunk_mode,
        max_chars=settings.max_chars,
        overlap=settings.overlap,
        min_words=settings.min_words,
        max_words=settings.max_words,
        break_threshold=settings.break_threshold,
        respect_headings=settings.respect_headings,
        keep_bullets=settings.keep_bullets,
    )


# -------------------------
# Text cleanup (Hebrew-friendly)
# -------------------------
_BIDI_AND_ZERO_WIDTH = re.compile(r"[\u200e\u200f\u202a-\u202e\u2066-\u2069\u200b\u200c\u200d\uFEFF]")
_MULTI_SPACE = re.compile(r"[ \t]+")


# -------------------------
# Structure detection
# -------------------------
_HEADING_RE = re.compile(
    r"""^(
        (?:פרק|סעיף|נספח|כותרת)\s*\d+[\.\)]?   # Hebrew legal headings
        |(?:chapter|section|appendix)\s*\d+[\.\)]?
        |[A-Z][A-Z0-9\s\-]{3,}                 # ALL CAPS-ish
    )\s*[:\-–—]?\s*$""",
    re.IGNORECASE | re.VERBOSE,
)

_BULLET_RE = re.compile(
    r"""^(
        [•\-\–\—\*]
        |\(?\d{1,3}\)?[\.\)]
        |\(?[א-ת]{1,3}\)?[\.\)]
        |\(?[a-zA-Z]{1,3}\)?[\.\)]
    )\s+""",
    re.VERBOSE,
)


def is_heading(line: str) -> bool:
    if not line:
        return False
    # Short-ish, no ending period, and matches heading patterns
    if len(line) > 120:
        return False
    if line.endswith("."):
        return False
    return bool(_HEADING_RE.match(line))


def is_bullet(line: str) -> bool:
    return bool(_BULLET_RE.match(line or ""))


def paragraphize(text: str, respect_headings: bool = True, keep_bullets: bool = True) -> List[str]:
    """
    Convert raw text into logical blocks:
    - headings start new blocks
    - bullets can be kept as separate blocks
    - blank lines create paragraph boundaries
    """
    text = clean_text(text)
    if not text:
        return []

    raw_lines = text.split("\n")

    blocks: List[str] = []
    buf: List[str] = []

    def flush():
        nonlocal buf
        if buf:
            blocks.append(" ".join(buf).strip())
            buf = []

    for ln in raw_lines:
        if not ln:
            flush()
            continue

        if respect_headings and is_heading(ln):
            flush()
            blocks.append(ln.strip())
            continue

        if keep_bullets and is_bullet(ln):
            flush()
            blocks.append(ln.strip())
            continue

        buf.append(ln.strip())

    flush()
    return [b for b in blocks if b]


# -------------------------
# Tokenization + cohesion
# -------------------------
_WORD_RE = re.compile(r"[A-Za-z0-9\u0590-\u05FF]+")


def words(text: str) -> List[str]:
    return _WORD_RE.findall((text or "").lower())


def bow(text: str) -> Counter[str]:
    return Counter(words(text))


def cosine(c1: Counter[str], c2: Counter[str]) -> float:
    if not c1 or not c2:
        return 0.0
    # dot product
    dot = 0.0
    for k, v in c1.items():
        if k in c2:
            dot += v * c2[k]
    n1 = math.sqrt(sum(v * v for v in c1.values()))
    n2 = math.sqrt(sum(v * v for v in c2.values()))
    if n1 == 0.0 or n2 == 0.0:
        return 0.0
    return float(dot / (n1 * n2))


# -------------------------
# Chunking modes
# -------------------------
def chunk_simple_chars(text: str, max_chars: int, overlap: int) -> List[str]:
    """
    Character-based chunking with overlap.
    Good as fallback when structure is messy.
    """
    text = " ".join(clean_text(text).split())
    if not text:
        return []

    max_chars = max(50, int(max_chars))
    overlap = int(max(0, min(overlap, max_chars - 1)))

    out: List[str] = []
    i = 0
    n = len(text)
    while i < n:
        end = min(i + max_chars, n)
        chunk = text[i:end].strip()
        if chunk:
            out.append(chunk)
        if end >= n:
            break
        i = end - overlap
    return out


def chunk_smart_words(text: str, cfg: ChunkingConfig) -> List[str]:
    """
    Structure-aware chunking:
    - builds blocks using paragraphize (headings/bullets preserved)
    - assembles blocks into chunks by word ranges
    - optional cohesion-based split (cosine on bag-of-words)
    """
    blocks = paragraphize(text, respect_headings=cfg.respect_headings, keep_bullets=cfg.keep_bullets)
    if not blocks:
        return []

    min_w = max(20, int(cfg.min_words))
    max_w = max(min_w + 20, int(cfg.max_words))
    thr = float(cfg.break_threshold)

    chunks: List[str] = []
    cur_blocks: List[str] = []
    cur_wc = 0
    cur_bow = Counter()

    def flush():
        nonlocal cur_blocks, cur_wc, cur_bow
        if cur_blocks:
            chunks.append(" ".join(cur_blocks).strip())
        cur_blocks = []
        cur_wc = 0
        cur_bow = Counter()

    for b in blocks:
        b_words = words(b)
        b_wc = len(b_words)
        b_bow = Counter(b_words)

        # If next block is a heading and we already have enough content, split before heading
        if cfg.respect_headings and is_heading(b) and cur_wc >= min_w:
            flush()

        # Cohesion-based split: if the next block is "topic-shift" and we already have enough words
        if thr > 0 and cur_wc >= min_w and cur_bow:
            sim = cosine(cur_bow, b_bow)
            if sim < thr:
                flush()

        # If adding this block would exceed max_words, split (but try not to create tiny chunks)
        if cur_wc > 0 and (cur_wc + b_wc) > max_w:
            flush()

        cur_blocks.append(b)
        cur_wc += b_wc
        cur_bow.update(b_bow)

        # If we grew too large (single huge block), hard split by words
        if cur_wc > max_w * 1.5:
            big = " ".join(cur_blocks).strip()
            ws = words(big)
            flush()
            for i in range(0, len(ws), max_w):
                part = " ".join(ws[i : i + max_w]).strip()
                if part:
                    chunks.append(part)

    flush()

    # Final cleanup: remove empties / super tiny chunks by merging forward when possible
    cleaned: List[str] = []
    for c in chunks:
        if not c.strip():
            continue
        if cleaned and len(words(c)) < max(12, min_w // 5):
            cleaned[-1] = (cleaned[-1] + " " + c).strip()
        else:
            cleaned.append(c.strip())

    return cleaned


def chunk_text(text: str, cfg: ChunkingConfig | None = None) -> List[str]:
    """
    Main entry:
    - cfg.mode == "smart": structure+words (recommended for legal)
    - cfg.mode == "simple": chars+overlap
    """
    cfg = cfg or config_from_settings()

    if cfg.mode.lower() == "simple":
        return chunk_simple_chars(text, max_chars=cfg.max_chars, overlap=cfg.overlap)

    # smart (default) with fallback
    out = chunk_smart_words(text, cfg)
    if out:
        return out
    return chunk_simple_chars(text, max_chars=cfg.max_chars, overlap=cfg.overlap)


def chunk_text_for_embedding(text: str) -> List[str]:
    """
    Unified chunking pipeline for RAG:
    1. Standard Chunking (Structure aware)
    2. Hard Split (Safety limit 1500 chars)
    
    This is the SINGLE SOURCE OF TRUTH for how text becomes vectors.
    """
    # 1. Base Chunking
    base_chunks = chunk_text(text)
    
    # 2. Hard Split Safety Net
    final_chunks = []
    MAX_CHARS = 1500
    
    for c in base_chunks:
        if len(c) > MAX_CHARS:
            # If a chunk is massive (rare but possible), split it blindly
            for i in range(0, len(c), MAX_CHARS):
                final_chunks.append(c[i:i+MAX_CHARS])
        else:
            final_chunks.append(c)
            
    return final_chunks
