from __future__ import annotations

from fastapi import Header, HTTPException
from backend.app.settings import settings

def require_admin(x_admin_code: str | None = Header(default=None)) -> None:
    """
    Dependency to verify the Admin Code from the request header.
    Raises 401 if the code does not match the server configuration.
    """
    expected = (settings.admin_code or "").strip()
    got = (x_admin_code or "").strip()
    
    if expected and got != expected:
        raise HTTPException(status_code=401, detail="Invalid admin code")