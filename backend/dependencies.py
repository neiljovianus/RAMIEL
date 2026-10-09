import datetime
from typing import Optional

from fastapi import HTTPException, Header
from jose import jwt, JWTError
from sqlalchemy import text

from config import AUTH_CONFIG
from database import db_engine


def get_current_user(authorization: Optional[str] = Header(None)):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Token not found.")
    token = authorization.split(" ", 1)[1]
    try:
        payload = jwt.decode(token, AUTH_CONFIG["jwt_secret"], algorithms=["HS256"])
        user_id = int(payload["sub"])
        if not db_engine:
            raise HTTPException(status_code=503, detail="Database unavailable.")
        with db_engine.connect() as conn:
            user = conn.execute(text("""
                SELECT username, role, account_status, account_expires_at, password_expires_at
                FROM users WHERE id=:id
            """), {"id": user_id}).fetchone()
        if not user:
            raise HTTPException(status_code=401, detail="Account not found.")
        if user[2] != "active":
            raise HTTPException(status_code=403, detail="This account is suspended.")
        if user[3] and user[3] <= datetime.datetime.now():
            raise HTTPException(status_code=403, detail="This account has expired.")
        if user[4] and user[4] <= datetime.datetime.now():
            raise HTTPException(status_code=403, detail="Password expired. Use the reset link sent to your email.")
        return {"id": user_id, "username": user[0], "role": user[1]}
    except HTTPException:
        raise
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid or expired token.")


def can_manage_user(viewer_role: str, target_role: str) -> bool:
    if viewer_role == "dev":
        return True
    if viewer_role == "admin":
        return target_role != "dev"
    return False


def require_dev(
    x_dev_secret: Optional[str] = Header(None),
    authorization: Optional[str] = Header(None)
):
    if x_dev_secret == AUTH_CONFIG["dev_secret"]:
        return True
    if authorization and authorization.startswith("Bearer "):
        token = authorization.split(" ", 1)[1]
        try:
            payload = jwt.decode(token, AUTH_CONFIG["jwt_secret"], algorithms=["HS256"])
            if payload.get("role") in ("admin", "dev"):
                return True
        except JWTError:
            pass
    raise HTTPException(status_code=403, detail="Admin or Developer access denied.")


def require_db():
    if not db_engine:
        raise HTTPException(status_code=503, detail="Database unavailable.")
    return db_engine
