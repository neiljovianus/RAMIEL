from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy import text
from markdown_it import MarkdownIt

from database import db_engine
from schemas import RenameSessionRequest
from dependencies import get_current_user, require_db

router = APIRouter()
md = MarkdownIt()


@router.get("/api/sessions")
async def get_sessions(current_user: dict = Depends(get_current_user), _db: None = Depends(require_db)):
    try:
        with db_engine.connect() as conn:
            rows = conn.execute(
                text("SELECT id, title, updated_at FROM chat_sessions WHERE user_id=:u ORDER BY updated_at DESC"),
                {"u": current_user["id"]},
            ).fetchall()
        return [{"id": r[0], "title": r[1], "updated_at": r[2].isoformat() if r[2] else None} for r in rows]
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})


@router.get("/api/sessions/{session_id}/messages")
async def get_session_messages(session_id: int, current_user: dict = Depends(get_current_user), _db: None = Depends(require_db)):
    try:
        with db_engine.connect() as conn:
            session = conn.execute(
                text("SELECT id FROM chat_sessions WHERE id=:sid AND user_id=:uid"),
                {"sid": session_id, "uid": current_user["id"]},
            ).fetchone()
            if not session:
                return JSONResponse(status_code=403, content={"error": "Access denied."})
            rows = conn.execute(
                text("SELECT id, role, content, created_at, parent_id, source, attachments FROM chat_messages WHERE session_id=:sid ORDER BY id ASC"),
                {"sid": session_id},
            ).fetchall()
        import json
        return [
            {
                "id": r[0],
                "role": r[1],
                "content": md.render(r[2]) if r[1] == "system" else r[2],
                "raw_content": r[2],
                "created_at": r[3].isoformat(),
                "parent_id": r[4],
                "source": json.loads(r[5]) if r[5] else [],
                "attachments": json.loads(r[6]) if r[6] else []
            }
            for r in rows
        ]
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})


@router.put("/api/sessions/{session_id}")
async def rename_session(session_id: int, req: RenameSessionRequest, current_user: dict = Depends(get_current_user), _db: None = Depends(require_db)):
    try:
        with db_engine.connect() as conn:
            sess = conn.execute(
                text("SELECT id FROM chat_sessions WHERE id=:sid AND user_id=:uid"),
                {"sid": session_id, "uid": current_user["id"]},
            ).fetchone()
            if not sess:
                return JSONResponse(status_code=403, content={"error": "Access denied."})
            new_title = req.title.strip()[:60] or "chat"
            conn.execute(
                text("UPDATE chat_sessions SET title=:t WHERE id=:sid"),
                {"t": new_title, "sid": session_id},
            )
            conn.commit()
        return {"message": "Session renamed.", "title": new_title}
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})


@router.delete("/api/sessions/{session_id}")
async def delete_session(session_id: int, current_user: dict = Depends(get_current_user), _db: None = Depends(require_db)):
    try:
        with db_engine.connect() as conn:
            sess = conn.execute(
                text("SELECT id FROM chat_sessions WHERE id=:sid AND user_id=:uid"),
                {"sid": session_id, "uid": current_user["id"]},
            ).fetchone()
            if not sess:
                return JSONResponse(status_code=403, content={"error": "Access denied."})
            conn.execute(text("DELETE FROM chat_messages WHERE session_id=:sid"), {"sid": session_id})
            conn.execute(text("DELETE FROM chat_sessions WHERE id=:sid"), {"sid": session_id})
            conn.commit()
        return {"message": "Session deleted."}
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})
