# backend/app/core/text_utils.py
# -*- coding: utf-8 -*-
from __future__ import annotations
import re
import unicodedata
from typing import Tuple, Dict

HEBREW_RANGE = r"\u0590-\u05FF"
_BIDI_AND_ZERO_WIDTH = re.compile(r"[\u200e\u200f\u202a-\u202e\u2066-\u2069\u200b\u200c\u200d\uFEFF]")

def clean_text_output(text: str) -> str:
    """
    Unified text cleaning for both extraction and chunking.
    """
    if not text:
        return ""
    
    # 1. Unicode Normalize
    text = unicodedata.normalize("NFKC", text)
    
    # 2. Remove Bidi/Control chars (Critical for Hebrew)
    text = _BIDI_AND_ZERO_WIDTH.sub("", text)
    
    # 3. Normalize newlines
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    
    # 4. Fix broken hyphenation (word-\nword -> wordword)
    text = re.sub(r"(?<=\w)-\n(?=\w)", "", text)
    
    # 5. Collapse multiple spaces
    text = re.sub(r"[ \t]+", " ", text)
    
    # 6. Limit max consecutive newlines (paragraphs)
    text = re.sub(r"\n{3,}", "\n\n", text)
    
    return text.strip()

def evaluate_quality(
    text: str,
    min_chars: int = 30,
    min_chars_per_kb: float = 0.5,
    file_size_bytes: int = 0
) -> Tuple[bool, Dict[str, float]]:
    """
    Evaluates if the extracted text is valid or requires OCR fallback.
    
    Criteria:
    1. Text is not too short relative to file size (avoids scanned images acting as text).
    2. Contains sufficient Hebrew characters (if expected).
    3. Detects broken encoding (gibberish).

    Returns:
        (is_good: bool, metrics: dict)
    """
    text = text or ""
    length = len(text)
    
    # Avoid division by zero
    kb = max(1.0, file_size_bytes / 1024.0) if file_size_bytes > 0 else 1.0
    chars_per_kb = length / kb

    hebrew_chars = len(re.findall(rf"[{HEBREW_RANGE}]", text))
    ratio_heb = hebrew_chars / max(1, length)
    
    newline_ratio = text.count("\n") / max(1, length)
    
    metrics = {
        "length": float(length),
        "chars_per_kb": float(chars_per_kb),
        "hebrew_ratio": float(ratio_heb),
        "newline_ratio": float(newline_ratio)
    }

    # 1. Check for Scanned Image (Very short text in large file)
    if file_size_bytes > 0 and length < min_chars and chars_per_kb < min_chars_per_kb:
        return False, metrics

    # 2. Check for Broken Encoding (Hebrew letters but broken words/lines)
    # A sequence of 5+ single Hebrew letters separated by spaces is suspicious.
    broken_hebrew_seq = len(re.findall(rf"(?:[{HEBREW_RANGE}]\s+){{5,}}", text))
    if ratio_heb > 0.05 and broken_hebrew_seq > 2:
        return False, metrics

    # 3. Absolute minimum length check
    if length < 10:
        return False, metrics

    return True, metrics