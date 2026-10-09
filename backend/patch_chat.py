import re

with open('d:/njovi/Documents/Workspace/Projects/Vistakom/RAMIEL_AI/backend/routers/chat.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Pattern to replace lines 74-111 in chat.py
# Using a precise replacement logic
start_idx = content.find("if request.lock_edit_id and request.staged_user")
end_idx = content.find("for r, c in history_rows")

if start_idx != -1 and end_idx != -1:
    replacement1 = """
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
            res_user = conn.execute(
                text("INSERT INTO chat_messages (session_id, role, content, parent_id, created_at) VALUES (:sid,'user',:c,:pid,NOW())"),
                {"sid": session_id, "c": user_msg, "pid": current_parent_id},
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
            """
    content = content[:start_idx] + replacement1.lstrip() + content[end_idx:]


# Replace the AI message save logic
start_idx_ai = content.find("if not is_temp_branch:")
end_idx_ai = content.find("except Exception as e:", start_idx_ai)

if start_idx_ai != -1 and end_idx_ai != -1:
    # Need to go back a little to get the right indentation or just replace the block inside try
    replacement2 = """
                    res_msg = conn.execute(
                        text("INSERT INTO chat_messages (session_id, role, content, parent_id, created_at) VALUES (:sid,'system',:c,:pid,NOW())"),
                        {"sid": session_id, "c": final_text, "pid": user_msg_id},
                    )
                    ai_msg_id = res_msg.lastrowid
                    conn.execute(
                        text("UPDATE chat_sessions SET updated_at=NOW() WHERE id=:sid"),
                        {"sid": session_id},
                    )
                    conn.commit()
        """
    content = content[:start_idx_ai] + replacement2.lstrip() + content[end_idx_ai:]

with open('d:/njovi/Documents/Workspace/Projects/Vistakom/RAMIEL_AI/backend/routers/chat.py', 'w', encoding='utf-8') as f:
    f.write(content)

print("Patch applied successfully.")

