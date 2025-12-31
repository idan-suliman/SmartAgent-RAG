# backend/app/api/admin.py
from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel
from typing import Optional
from backend.app.core.security import require_admin
from backend.app.core.config_manager import config_manager

router = APIRouter(prefix="/admin", tags=["admin"])

# מודל הנתונים שמגיע מהדפדפן
class ConfigUpdate(BaseModel):
    openai_api_key: Optional[str] = None
    google_api_key: Optional[str] = None
    system_prompt: Optional[str] = None
    important_concepts: Optional[str] = None

@router.get("/config")
def get_config(x_admin_code: str | None = Header(default=None, alias="X-Admin-Code")):
    """
    מחזיר את ההגדרות השמורות בקובץ הדינמי בלבד.
    דורש הרשאת מפתח (Admin Code).
    """
    require_admin(x_admin_code)
    
    # טוען את ההגדרות מהקובץ הדינמי
    cfg = config_manager.load_config()
    
    # שים לב: אנחנו מחזירים בדיוק מה שיש בקובץ הדינמי.
    # אם המשתמש לא שמר מפתח ב-JSON (כי הוא משתמש ב-.env),
    # השדה כאן יהיה ריק. זה מצוין לאבטחה - ה-.env לא נחשף לדפדפן.
    return cfg

@router.post("/config")
def update_config(payload: ConfigUpdate, x_admin_code: str | None = Header(default=None, alias="X-Admin-Code")):
    """
    שומר הגדרות חדשות לקובץ הדינמי.
    דורש הרשאת מפתח.
    """
    require_admin(x_admin_code)
    
    # ממירים את המידע למילון, תוך התעלמות משדות שלא נשלחו
    data = payload.model_dump(exclude_unset=True)
    
    # שמירה באמצעות המנהל שיצרנו קודם
    config_manager.save_config(data)
    
    return {"ok": True, "message": "ההגדרות נשמרו בהצלחה"}