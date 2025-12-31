# backend/app/core/extractors/smart_pdf_extractor.py
# -*- coding: utf-8 -*-
from __future__ import annotations

import io
import os
from typing import List, Optional

import fitz  # PyMuPDF
import pytesseract
from PIL import Image

# Import shared utilities
from backend.app.core.text_utils import clean_text_output, evaluate_quality
from backend.app.settings import settings  # <--- Import Settings

# -------------------------
# Configuration (From Settings now)
# -------------------------
if settings.tesseract_cmd:
    pytesseract.pytesseract.tesseract_cmd = settings.tesseract_cmd

OCR_LANG = settings.ocr_lang
OCR_DPI = settings.ocr_dpi
OCR_MAX_PIXELS = settings.ocr_max_pixels
OCR_MAX_PAGES = settings.ocr_max_pages
OCR_CONFIG = "--oem 1 --psm 6" # Hardcoded is fine for standard usage

def _build_lang_try_list(lang: str) -> List[str]:
    """Builds a prioritized list of languages to try for OCR."""
    langs: List[str] = []
    primary = (lang or "").strip()
    if primary:
        langs.append(primary)

    # Fallback languages (Hardcoded logic is fine here, or move to settings if needed)
    fb = ["heb", "eng"]
    for x in fb:
        if x not in langs:
            langs.append(x)

    return langs


# -------------------------
# Extraction Logic
# -------------------------
def extract_text_pymupdf(pdf_path: str) -> str:
    """Fast extraction for text-based PDFs using PyMuPDF."""
    doc = fitz.open(pdf_path)
    try:
        return "\n".join(page.get_text("text") for page in doc)
    finally:
        doc.close()


def _pixmap_to_image(page: fitz.Page, dpi: int) -> Optional[Image.Image]:
    """
    Renders a PDF page to a PIL.Image object.
    Includes a safety mechanism to downscale huge images (memory protection).
    """
    try:
        pix = page.get_pixmap(dpi=dpi, alpha=False)
        
        # Safety check for memory bombs
        pixels = pix.width * pix.height
        if pixels > OCR_MAX_PIXELS:
            # Scale down to safe limits
            scale = (OCR_MAX_PIXELS / max(pixels, 1)) ** 0.5
            m = fitz.Matrix(scale, scale)
            pix = page.get_pixmap(matrix=m, alpha=False)

        return Image.open(io.BytesIO(pix.tobytes("png")))
    except Exception:
        return None


def extract_text_ocr(pdf_path: str, dpi: int = OCR_DPI, lang: str = OCR_LANG) -> str:
    """
    OCR Fallback: Converts PDF pages to images and runs Tesseract.
    Restricted by OCR_MAX_PAGES to prevent timeouts on large docs.
    """
    if not settings.ocr_enabled:
        return ""

    langs_to_try = _build_lang_try_list(lang)

    doc = fitz.open(pdf_path)
    out: List[str] = []
    
    ocr_count = 0
    
    try:
        for page_num, page in enumerate(doc, start=1):
            # Safety Break
            if ocr_count >= OCR_MAX_PAGES:
                out.append(f"\n\n[Stopped OCR after {OCR_MAX_PAGES} pages to prevent timeout]\n")
                break

            img = None
            try:
                img = _pixmap_to_image(page, dpi=dpi)
                if img is None:
                    continue

                page_text = ""
                # Try defined languages in order
                for L in langs_to_try:
                    try:
                        page_text = pytesseract.image_to_string(img, lang=L, config=OCR_CONFIG)
                        if page_text and len(page_text.strip()) > 10:
                            break
                    except Exception:
                        continue

                clean = (page_text or "").strip()
                if clean:
                    out.append(f"\n\n--- PAGE {page_num} ---\n{clean}")
                    ocr_count += 1
                
            except Exception:
                continue
            finally:
                if img:
                    try: img.close()
                    except: pass

    finally:
        doc.close()

    return "\n".join(out).strip()


# -------------------------
# Public API
# -------------------------
def extract_text_from_pdf(pdf_path: str) -> str:
    """
    Main Entry Point:
    1. Try fast extraction (PyMuPDF).
    2. Evaluate quality.
    3. If quality is poor, fallback to OCR.
    """
    fast_text = extract_text_pymupdf(pdf_path)

    try:
        # Check if the extracted text is good enough
        is_good, _ = evaluate_quality(fast_text, file_size_bytes=os.path.getsize(pdf_path))
    except Exception:
        is_good = True 

    if not is_good:
        print(f"[PDF] Quality check failed for {os.path.basename(pdf_path)}, running OCR...")
        ocr_text = extract_text_ocr(pdf_path)
        
        if len(ocr_text) > len(fast_text) * 0.5:
            return clean_text_output(ocr_text)
            
    return clean_text_output(fast_text)


__all__ = ["extract_text_from_pdf"]