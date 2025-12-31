# backend/app/settings.py
from __future__ import annotations
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[2]

class Settings(BaseSettings):
    # טוען משתנים מקובץ .env רק אם הם קיימים (בשביל ה-API KEY)
    model_config = SettingsConfigDict(
        env_file=str(PROJECT_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # =========================================================
    # 1. SECRETS (From .env)
    # =========================================================
    openai_api_key: str | None = None


    # =========================================================
    # 2. APP CONFIG (System Logic - Hardcoded Defaults)
    # =========================================================
    admin_code: str = "1111"  # הקוד לכניסת מפתח
    
    # Paths
    data_dir: str = str(PROJECT_ROOT / "data")
    inbox_dir: str = str(PROJECT_ROOT / "data" / "INBOX")
    index_dir: str = str(PROJECT_ROOT / "data" / "INDEX")

    # =========================================================
    # 3. RAG PIPELINE CONFIG
    # =========================================================
    # Models Configuration
    # הגדרות ספציפיות לכל ספק כדי למנוע בלבול
    openai_chat_model: str = "gpt-5.2"

    
    # ברירת מחדל כללית (אם לא נבחר כלום)
    default_chat_model: str = "gpt-4o"
    
    # נשאר לתמיכה אחורה בקוד ישן שעוד לא עדכנו (מפנה ל-default)
    chat_model: str = "gpt-4o"

    # Embedding Model (OpenAI - Existing Index)
    embed_model: str = "text-embedding-3-large"
    embed_dimensions: int = 3072  # גודל וקטור למודל Large

    # Search Settings
    top_k: int = 10           # כמות תוצאות רגילה ל-GPT (חסכוני)


    # Chunking (Text Splitting)
    chunk_mode: str = "smart"  # 'simple' or 'smart'
    
    # הגדרות צ'אנקינג (Smart Mode)
    min_words: int = 60
    max_words: int = 180
    break_threshold: float = 0.20
    respect_headings: bool = True
    keep_bullets: bool = True

    # הגדרות צ'אנקינג (Simple Mode Fallback)
    max_chars: int = 400
    overlap: int = 100
    
    # מגבלות טכניות (Hard Limits)
    lex_max_tokens: int = 80       # מקסימום טוקנים לחיפוש לקסיקלי
    embed_max_chars: int = 6000    # מקסימום תווים לצ'אנק בודד (למניעת קריסת OpenAI)
    hard_split_overlap: int = 200  # חפיפה בחיתוך קשיח

    # =========================================================
    # 4. OCR & EXTRACTION CONFIG
    # =========================================================
    # PDF / OCR
    ocr_enabled: bool = True
    ocr_lang: str = "heb+eng"
    ocr_dpi: int = 300
    ocr_max_pixels: int = 18000000  # הגנה מקריסת זיכרון
    ocr_max_pages: int = 5          # לא לנסות לעשות OCR על ספר שלם
    tesseract_cmd: str = ""         # השאר ריק אם זה ב-PATH, או הכנס נתיב מלא

settings = Settings()