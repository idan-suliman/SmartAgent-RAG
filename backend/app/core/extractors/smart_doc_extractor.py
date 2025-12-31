# backend/app/core/extractors/smart_doc_extractor.py
# -*- coding: utf-8 -*-
from __future__ import annotations

from pathlib import Path
from backend.app.core.text_utils import clean_text_output

def extract_text_from_doc(doc_path: str) -> str:
    """
    Extracts text from legacy .DOC files using Microsoft Word via COM (Windows only).
    Requires 'pywin32' installed in the environment.
    """
    try:
        import win32com.client
    except ImportError as e:
        # Raise specific error so the indexer knows to skip or log properly
        raise RuntimeError(
            "Missing dependency for .DOC extraction. Install: pip install pywin32"
        ) from e
    except Exception:
        return ""

    src = str(Path(doc_path).resolve())

    # COM Dispatch
    try:
        word = win32com.client.Dispatch("Word.Application")
        word.Visible = False
        word.DisplayAlerts = 0  # Suppress warnings
    except Exception:
        return ""

    doc = None
    text = ""
    try:
        # Open in Read-Only mode
        doc = word.Documents.Open(src, ReadOnly=True)
        # Extract content
        text = getattr(doc.Content, "Text", "") or ""
    except Exception:
        pass
    finally:
        # Cleanup Resources
        try:
            if doc is not None:
                doc.Close(False)
        except Exception:
            pass
        try:
            word.Quit()
        except Exception:
            pass

    return clean_text_output(text)


__all__ = ["extract_text_from_doc"]