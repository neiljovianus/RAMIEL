from fastapi import APIRouter, Depends, HTTPException, Body
from sqlalchemy import text
from typing import List, Dict

from database import db_engine
from dependencies import get_current_user, require_db

router = APIRouter()

def require_admin(current_user: dict = Depends(get_current_user)):
    if current_user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Forbidden")
    return current_user

@router.get("/api/admin/users")
async def list_users(admin: dict = Depends(require_admin)):
    with db_engine.connect() as conn:
        users = conn.execute(text("""
            SELECT u.id, u.username, u.role, COALESCE(t.tokens, 0) as tokens
            FROM users u
            LEFT JOIN user_tokens t ON u.id = t.user_id
            ORDER BY u.id
        """)).fetchall()
        
    return {"users": [{"id": row[0], "username": row[1], "role": row[2], "tokens": row[3]} for row in users]}

@router.post("/api/admin/users/{user_id}/tokens")
async def update_user_tokens(user_id: int, payload: dict = Body(...), admin: dict = Depends(require_admin)):
    tokens = payload.get("tokens")
    if tokens is None or not isinstance(tokens, int):
        raise HTTPException(status_code=400, detail="Invalid tokens value")
        
    with db_engine.begin() as conn:
        # Check if user exists
        user = conn.execute(text("SELECT id FROM users WHERE id=:uid"), {"uid": user_id}).fetchone()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
            
        conn.execute(text("""
            INSERT INTO user_tokens (user_id, tokens) VALUES (:uid, :tok)
            ON DUPLICATE KEY UPDATE tokens = :tok
        """), {"uid": user_id, "tok": tokens})
        
    return {"status": "success", "tokens": tokens}

