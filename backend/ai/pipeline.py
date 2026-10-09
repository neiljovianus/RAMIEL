import json

from google.genai import types

from config import cprint
from ai.tools import query_table_data, list_files, read_file
from ai.client import create_chat_session, safe_send_message


async def process_ai(user_msg, history, files=None):
    ai_audit = []
    total_prompt_t = 0
    total_cand_t = 0
    round_num = 1
    MAX_ROUNDS = 8

    chat_obj = create_chat_session(history=history)
    if not chat_obj:
        raise Exception("API key not configured.")

    input_data = [user_msg]
    if files:
        import base64
        for f in files:
            if "data" in f and "mime_type" in f:
                try:
                    file_bytes = base64.b64decode(f["data"])
                    input_data.append(types.Part.from_bytes(data=file_bytes, mime_type=f["mime_type"]))
                except Exception as e:
                    cprint("ai", f"Failed to decode file {f.get('name', 'unknown')}: {e}")

    response, chat_obj = await safe_send_message(chat_obj, input_data)

    while True:
        usage = response.usage_metadata
        p_t = getattr(usage, 'prompt_token_count', 0) if usage else 0
        c_t = getattr(usage, 'candidates_token_count', 0) if usage else 0
        total_prompt_t += p_t
        total_cand_t += c_t

        if not response.function_calls or round_num > MAX_ROUNDS:
            ai_audit.append(f"--- ROUND {round_num} ---")
            ai_audit.append(f"Tokens: {p_t} input")
            break

        ai_audit.append(f"--- ROUND {round_num} ---")
        ai_audit.append(f"Tokens: {p_t} input | {c_t} output")

        function_responses = []
        for fc in response.function_calls:
            ai_audit.append(f"[TOOL CALL] {fc.name}({json.dumps(fc.args, ensure_ascii=False)})")
            try:
                if fc.name == "query_table_data":
                    result = query_table_data(**fc.args)
                elif fc.name == "list_files":
                    result = list_files(**fc.args)
                elif fc.name == "read_file":
                    result = read_file(**fc.args)
                else:
                    result = {"error": f"Unknown tool: '{fc.name}'"}
            except Exception as e:
                result = {"error": str(e)}
            ai_audit.append("[TOOL RESULT]")
            ai_audit.append(json.dumps(result, indent=2, ensure_ascii=False))
            ai_audit.append("")
            function_responses.append(
                types.Part.from_function_response(name=fc.name, response=result)
            )

        round_num += 1
        cprint("ai", f"Executing {len(function_responses)} tool(s)...")
        response, chat_obj = await safe_send_message(chat_obj, function_responses)

    return response, ai_audit, total_prompt_t, total_cand_t, c_t
