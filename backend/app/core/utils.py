# backend/app/core/utils.py
from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict
from openai import OpenAI
from backend.app.settings import settings

_openai_client = None

def get_openai_client():
    global _openai_client
    if _openai_client is None and settings.openai_api_key:
        _openai_client = OpenAI(api_key=settings.openai_api_key)
    return _openai_client

class JobStatusManager:
    """
    Manages atomic status file updates for long-running jobs (indexing/embedding).
    Handles file locking issues on Windows via retries.
    """
    def __init__(self, file_path: Path):
        self.file_path = file_path

    def _utc_iso(self) -> str:
        """Returns current UTC timestamp in ISO format."""
        return datetime.now(timezone.utc).isoformat()

    def load(self) -> Dict[str, Any]:
        """Loads the status file. Returns default idle state if file is missing."""
        if not self.file_path.exists():
            return {"ok": True, "state": "idle", "updated_at": self._utc_iso()}
        try:
            return json.loads(self.file_path.read_text(encoding="utf-8"))
        except Exception:
            return {"ok": False, "state": "unknown", "updated_at": self._utc_iso()}

    def update(self, payload: Dict[str, Any]) -> None:
        """
        Atomically updates the status file.
        Uses a temporary file + replace strategy to prevent read/write collisions.
        """
        payload["updated_at"] = self._utc_iso()
        
        # Ensure parent directory exists
        self.file_path.parent.mkdir(parents=True, exist_ok=True)
        
        tmp = self.file_path.with_suffix(self.file_path.suffix + ".tmp")
        try:
            tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
            tmp.replace(self.file_path)
        except PermissionError:
            print(f"[WARN] Could not update status file {self.file_path.name} (locked).")
        except Exception as e:
            print(f"[ERR] Status update failed: {e}")

    def start_job(self, initial_state: Dict[str, Any]) -> None:
        """Sets the state to running and initializes start time."""
        initial_state.update({
            "ok": True,
            "state": "running",
            "started_at": self._utc_iso(),
            "eta_sec": None
        })
        self.update(initial_state)

    def fail_job(self, message: str) -> None:
        """Sets the state to error."""
        self.update({
            "ok": False,
            "state": "error",
            "message": message,
            "finished_at": self._utc_iso()
        })

    def complete_job(self, final_stats: Dict[str, Any]) -> None:
        """Sets the state to done and records finish time."""
        final_stats.update({
            "ok": True,
            "state": "done",
            "finished_at": self._utc_iso(),
            "eta_sec": 0.0
        })
        self.update(final_stats)