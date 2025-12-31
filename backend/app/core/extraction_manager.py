from __future__ import annotations
import os
from pathlib import Path
from typing import Optional

# Import existing extractors
from backend.app.core.extractors.smart_pdf_extractor import extract_text_from_pdf
from backend.app.core.extractors.smart_docx_extractor import extract_text_from_docx
from backend.app.core.extractors.smart_doc_extractor import extract_text_from_doc

def extract_text_from_file(file_path: Path | str) -> str:
    """
    Unified extraction entry point.
    Determines file type by extension and calls the appropriate extractor.
    Returns cleaned text string.
    """
    path_obj = Path(file_path)
    if not path_obj.exists():
        raise FileNotFoundError(f"File not found: {file_path}")

    ext = path_obj.suffix.lower()
    abs_path = str(path_obj.absolute())

    try:
        if ext == ".pdf":
            return extract_text_from_pdf(abs_path)
        elif ext == ".docx":
            return extract_text_from_docx(abs_path)
        elif ext == ".doc":
            return extract_text_from_doc(abs_path)
        else:
            # Default to text
            with open(path_obj, "r", encoding="utf-8", errors="ignore") as f:
                return f.read()
    except Exception as e:
        print(f"[EXTRACT_MGR] Error extracting {abs_path}: {e}")
        return ""
