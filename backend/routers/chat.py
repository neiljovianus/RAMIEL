import os
import re
import datetime
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Request, HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy import text
from markdown_it import MarkdownIt
from google.genai import types

from config import HISTORY_PATH, cprint
from database import db_engine
from schemas import ChatRequest
from dependencies import get_current_user, require_db
from ai.tools import _current_role
from ai.client import MODELS, current_model_idx, api_key, generate_chat_title
from ai.pipeline import process_ai

router = APIRouter()

@router.post("/api/chat/init")
async def init_chat_session(request: Request, db=Depends(require_db), current_user=Depends(get_current_user)):
    data = await request.json()
    user_msg = data.get("message", "")
    if not user_msg:
        raise HTTPException(status_code=400, detail="Empty message")
    
    session_title = await generate_chat_title(user_msg)
    with db_engine.begin() as conn:
        res = conn.execute(
            text("INSERT INTO chat_sessions (user_id, title, updated_at) VALUES (:uid,:t,NOW())"),
            {"uid": current_user["id"], "t": session_title}
        )
        session_id = res.lastrowid
        
    return {"session_id": session_id, "session_title": session_title}

md = MarkdownIt()


@router.post("/api/chat")
async def chat_endpoint(request: ChatRequest, current_user: dict = Depends(get_current_user), _db: None = Depends(require_db)):
    user_msg = request.message
    if not user_msg:
        return JSONResponse(content={"answer": "Empty message."})
    if not api_key:
        return JSONResponse(content={"answer": "Error: API key not configured."})

    _current_role.set(current_user["role"])
    user_id = current_user["id"]
    
    if current_user["role"] != "admin":
        with db_engine.begin() as conn:
            token_row = conn.execute(text("SELECT tokens FROM user_tokens WHERE user_id=:uid"), {"uid": user_id}).fetchone()
            if not token_row or token_row[0] <= 0:
                return JSONResponse(content={"answer": "Token habis. Hubungi admin untuk mengisi ulang."})
            conn.execute(text("UPDATE user_tokens SET tokens = tokens - 1 WHERE user_id=:uid"), {"uid": user_id})

    session_id = request.session_id
    session_title = None

    try:
        with db_engine.connect() as conn:
            if session_id:
                sess = conn.execute(
                    text("SELECT id FROM chat_sessions WHERE id=:sid AND user_id=:uid"),
                    {"sid": session_id, "uid": user_id},
                ).fetchone()
                if not sess:
                    session_id = None

            if not session_id:
                session_title = await generate_chat_title(user_msg)
                res = conn.execute(
                    text("INSERT INTO chat_sessions (user_id, title, updated_at) VALUES (:uid,:t,NOW())"),
                    {"uid": user_id, "t": session_title},
                )
                session_id = res.lastrowid
                conn.commit()

            # Determine parent_id for the new user message
            current_parent_id = request.parent_id
            
            if request.edit_message_id:
                # Find the parent of the message being edited
                edit_msg = conn.execute(
                    text("SELECT parent_id FROM chat_messages WHERE id=:mid AND session_id=:sid"),
                    {"mid": request.edit_message_id, "sid": session_id}
                ).fetchone()
                if edit_msg:
                    current_parent_id = edit_msg[0]

            # Insert the user message
            import json
            att_json = json.dumps(request.files) if request.files else None
            res_user = conn.execute(
                text("INSERT INTO chat_messages (session_id, role, content, parent_id, attachments, created_at) VALUES (:sid,'user',:c,:pid,:att,NOW())"),
                {"sid": session_id, "c": user_msg, "pid": current_parent_id, "att": att_json},
            )
            user_msg_id = res_user.lastrowid
            conn.commit()
            
            # Trace history up to root
            history_rows = []
            trace_id = current_parent_id
            while trace_id:
                row = conn.execute(
                    text("SELECT parent_id, role, content FROM chat_messages WHERE id=:tid AND session_id=:sid"),
                    {"tid": trace_id, "sid": session_id}
                ).fetchone()
                if not row:
                    break
                history_rows.append((row[1], row[2])) # role, content
                trace_id = row[0] # parent_id
            
            history_rows.reverse()
            
            ai_history = []
            for r, c in history_rows[:-1]:
                ai_role = 'user' if r == 'user' else 'model'
                ai_history.append(types.Content(role=ai_role, parts=[types.Part.from_text(text=c)]))

            ai_history = ai_history[-8:]
    except Exception as e:
        cprint("db", f"Session init error: {e}")
        ai_history = []

    now = datetime.datetime.now(ZoneInfo("Asia/Jakarta"))
    user_token_est = len(user_msg.split())
    audit_log = [
        "=" * 60,
        f"[USER] {current_user['username']} (Role: {current_user['role']})",
        f"[TIME] {now.strftime('%Y-%m-%d %H:%M:%S')}",
        f"[MODEL] {MODELS[current_model_idx]}",
        "-" * 60,
        f"[USER INPUT] (Est. ~{user_token_est} tokens)",
        user_msg, "",
        "[DATA LOOKUP]",
    ]

    try:
        response, ai_audit, total_prompt_t, total_cand_t, final_c_t = await process_ai(user_msg, ai_history, files=request.files)
        audit_log.extend(ai_audit)

        final_text = ""
        try:
            if response.candidates and response.candidates[0].finish_reason:
                finish_reason = str(response.candidates[0].finish_reason)
                if "STOP" not in finish_reason and finish_reason != "1":
                    final_text = f"Sorry, I cannot process this request. (Reason: {finish_reason})"
            if not final_text:
                final_text = response.text or "Sorry, I cannot process this request (empty response)."
        except Exception as e:
            final_text = f"Sorry, I cannot process this request ({e})."

        final_text = re.sub(r'\n{3,}', '\n\n', final_text).strip()

        audit_log.extend([
            "",
            f"[AI FINAL ANSWER] (Tokens: {final_c_t} output)",
            final_text, "",
            f"[TOTAL] Input: {total_prompt_t} | Output: {total_cand_t} | Total: {total_prompt_t + total_cand_t}",
            "=" * 60,
        ])

        sources = []
        if response.candidates and getattr(response.candidates[0], "grounding_metadata", None):
            gm = response.candidates[0].grounding_metadata
            if getattr(gm, "grounding_chunks", None):
                for chunk in gm.grounding_chunks:
                    if getattr(chunk, "web", None):
                        sources.append({"title": getattr(chunk.web, "title", "Source"), "uri": getattr(chunk.web, "uri", "")})

        try:
            with db_engine.connect() as conn:
                import json
                src_json = json.dumps(sources) if sources else None
                res_msg = conn.execute(
                    text("INSERT INTO chat_messages (session_id, role, content, parent_id, source, created_at) VALUES (:sid,'system',:c,:pid,:src,NOW())"),
                    {"sid": session_id, "c": final_text, "pid": user_msg_id, "src": src_json},
                )
                ai_msg_id = res_msg.lastrowid
                conn.execute(
                    text("UPDATE chat_sessions SET updated_at=NOW() WHERE id=:sid"),
                    {"sid": session_id},
                )
                conn.commit()
        except Exception as e:
            cprint("db", f"Response save error: {e}")
            ai_msg_id = None

        today_str = now.strftime('%d %B %Y')
        write_header = True
        if os.path.exists(HISTORY_PATH):
            with open(HISTORY_PATH, "r", encoding="utf-8") as f:
                first_line = f.readline().strip()
                if today_str in first_line:
                    write_header = False
        with open(HISTORY_PATH, "w" if write_header else "a", encoding="utf-8") as f:
            if write_header:
                f.write(f"Date: {today_str}\n\n")
            f.write("\n".join(audit_log) + "\n")



        cprint("ai", f"Tokens: {total_prompt_t}+{total_cand_t} | Answer: {final_text[:80]}...")
        return JSONResponse(content={
            "answer": md.render(final_text),
            "raw_answer": final_text,
            "source": sources,
            "session_id": session_id,
            "session_title": session_title,
            "user_msg_id": user_msg_id,
            "ai_msg_id": ai_msg_id,
            "created_at": now.isoformat(),
        })
    except Exception as e:
        cprint("error", str(e))
        return JSONResponse(content={
            "answer": f"Error: {e}", "session_id": session_id, "session_title": session_title,
        })


@router.post("/api/shutdown")
async def shutdown_server():
    import threading, time as _t
    cprint("sys", "Shutdown requested...")
    def _kill():
        _t.sleep(0.4)
        os._exit(0)
    threading.Thread(target=_kill, daemon=True).start()
    return {"message": "Server shutting down.", "is_frozen": True}
