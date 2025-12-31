# backend/app/core/config_manager.py
"""
Configuration Manager
---------------------
Manages dynamic settings and secrets:
1. Loads API Keys from .env environment file via settings.py logic.
2. Manages system prompts and keywords stored in data files.
3. Provides a unified interface for Admin configuration UI.
"""

from __future__ import annotations
import re
from pathlib import Path
from typing import Dict, Any, Optional
from backend.app.settings import settings, PROJECT_ROOT

# Relative Path Calculation
CURRENT_DIR = Path(__file__).resolve().parent  # backend/app/core
BACKEND_DIR = CURRENT_DIR.parent.parent        # backend
ROOT_DIR = BACKEND_DIR.parent                  # Project Root

# File Paths
KEYWORDS_PATH = CURRENT_DIR / "keywords.py"
DATA_DIR = ROOT_DIR / "data"
ENV_PATH = ROOT_DIR / ".env"

# Prompt File Paths
PROMPT_MAIN_PATH = DATA_DIR / "system_prompt.txt"
PROMPT_REWRITE_PATH = DATA_DIR / "rewrite_prompt.txt"
PROMPT_NO_RESULTS_PATH = DATA_DIR / "no_results_prompt.txt"
PROMPT_FALLBACK_PATH = DATA_DIR / "fallback_prompt.txt"

# Defaults
DEFAULT_MAIN = (
    "אתה עוזר משפטי בכיר. עליך לענות על שאלות בהתבסס על המידע שסופק בלבד. "
    "הקפד על דיוק, צטט מקורות, והימנע מהמצאות."
)

DEFAULT_REWRITE = (
    "אתה עורך דין ישראלי בכיר ומומחה למערכות אחזור מידע (Information Retrieval). "
    "תפקידך: לקבל היסטוריית שיחה ושאלה אחרונה של משתמש, ולנסח מחדש שאילתת חיפוש אופטימלית למאגר משפטי."
    "\n\n"
    "הנחיות לביצוע:"
    "\n1. עצמאות: השאילתה חייבת להיות מובנת בפני עצמה ללא צורך בהיסטוריה."
    "\n2. העשרת מונחים: הוסף מילים נרדפות משפטיות רלוונטיות."
    "\n3. מיקוד: השמט מילות קישור מיותרות והתמקד במונחי המפתח."
    "\n4. אל תענה על השאלה! הפלט שלך הוא אך ורק השאילתה המשוכתבת."
)

DEFAULT_NO_RESULTS = "[לא נמצאו מקורות רלוונטיים במאגר. ענה על סמך ידע משפטי כללי, אך סייג את תשובתך.]"
DEFAULT_FALLBACK = "אתה עוזר משפטי חכם."


class ConfigManager:
    def __init__(self):
        if not DATA_DIR.exists():
            try:
                DATA_DIR.mkdir(parents=True, exist_ok=True)
            except Exception:
                pass

    def load_config(self) -> Dict[str, Any]:
        """Collects configuration from all sources (.env, text files, code users)."""
        return {
            "openai_api_key": self._get_env_var("OPENAI_API_KEY"),
            # 'google_api_key' removed (Legacy)
            "important_concepts": self._read_keywords_from_code(),
            
            # Prompts
            "system_prompt": self._read_file(PROMPT_MAIN_PATH, DEFAULT_MAIN),
            "rewrite_prompt": self._read_file(PROMPT_REWRITE_PATH, DEFAULT_REWRITE),
            "no_results_prompt": self._read_file(PROMPT_NO_RESULTS_PATH, DEFAULT_NO_RESULTS),
            "fallback_prompt": self._read_file(PROMPT_FALLBACK_PATH, DEFAULT_FALLBACK),
        }

    def get_key(self, key_name: str, env_var_name: str = None) -> Optional[str]:
        """Helper to retrieve a specific key (used by chat backend)."""
        cfg = self.load_config()
        val = cfg.get(key_name)
        if val and str(val).strip():
            return str(val).strip()
        return None

    def save_config(self, data: Dict[str, Any]):
        """Persists configuration updates to their respective targets."""
        
        # 1. Update .env (API Keys)
        env_updates = {}
        if "openai_api_key" in data:
            val = data["openai_api_key"]
            if val and str(val).strip():
                env_updates["OPENAI_API_KEY"] = str(val).strip()
        
        if env_updates:
            self._update_env_file(env_updates)

        # 2. Save Prompts
        if "system_prompt" in data:
            self._write_file(PROMPT_MAIN_PATH, data["system_prompt"])
        if "rewrite_prompt" in data:
            self._write_file(PROMPT_REWRITE_PATH, data["rewrite_prompt"])
        if "no_results_prompt" in data:
            self._write_file(PROMPT_NO_RESULTS_PATH, data["no_results_prompt"])
        if "fallback_prompt" in data:
            self._write_file(PROMPT_FALLBACK_PATH, data["fallback_prompt"])

        # 3. Update Keywords Code
        if "important_concepts" in data:
            self._update_keywords_in_code(data["important_concepts"])

    # --- File Helpers ---
    def _read_file(self, path: Path, default: str) -> str:
        if path.exists():
            try:
                return path.read_text(encoding="utf-8")
            except:
                pass
        return default

    def _write_file(self, path: Path, text: str):
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")
        except Exception as e:
            print(f"Error writing file {path}: {e}")

    # --- Env File Logic ---
    def _get_env_var(self, key: str) -> str:
        if ENV_PATH.exists():
            try:
                content = ENV_PATH.read_text(encoding="utf-8")
                for line in content.splitlines():
                    if line.strip().startswith(f"{key}="):
                        return line.split("=", 1)[1].strip()
            except Exception:
                pass
        return ""

    def _update_env_file(self, updates: Dict[str, str]):
        lines = []
        if ENV_PATH.exists():
            try:
                lines = ENV_PATH.read_text(encoding="utf-8").splitlines()
            except Exception:
                pass
        
        new_lines = []
        processed = set()
        
        # Update existing lines
        for line in lines:
            key_match = False
            for key, val in updates.items():
                if line.strip().startswith(f"{key}="):
                    new_lines.append(f"{key}={val}")
                    processed.add(key)
                    key_match = True
                    break
            if not key_match:
                new_lines.append(line)
        
        # Append new keys
        for key, val in updates.items():
            if key not in processed:
                new_lines.append(f"{key}={val}")
        
        try:
            ENV_PATH.write_text("\n".join(new_lines), encoding="utf-8")
        except Exception as e:
            print(f"Error writing to .env: {e}")

    # --- Keywords Code Injection ---
    def _read_keywords_from_code(self) -> str:
        if not KEYWORDS_PATH.exists(): return ""
        try:
            content = KEYWORDS_PATH.read_text(encoding="utf-8")
            match = re.search(r'IMPORTANT_LEGAL_CONCEPTS.*=\s*\{([^}]*)\}', content, re.DOTALL)
            if match:
                raw_list = match.group(1)
                clean_items = []
                for item in raw_list.split(','):
                    item = item.strip().strip('"').strip("'")
                    if item and not item.startswith("#"):
                        clean_items.append(item)
                return ", ".join(clean_items)
        except Exception: pass
        return ""

    def _update_keywords_in_code(self, new_keywords_str: str):
        if not KEYWORDS_PATH.exists(): return
        items = [x.strip() for x in new_keywords_str.split(',') if x.strip()]
        formatted_set_content = "\n    " + ", ".join([f'"{x}"' for x in items]) + ",\n"
        try:
            content = KEYWORDS_PATH.read_text(encoding="utf-8")
            pattern = r'(IMPORTANT_LEGAL_CONCEPTS.*=\s*\{)[^}]*(\})'
            if re.search(pattern, content, re.DOTALL):
                new_content = re.sub(pattern, f"\\1{formatted_set_content}\\2", content, flags=re.DOTALL)
                KEYWORDS_PATH.write_text(new_content, encoding="utf-8")
        except Exception as e:
            print(f"Error updating keywords: {e}")

config_manager = ConfigManager()