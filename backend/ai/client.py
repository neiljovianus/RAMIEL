import asyncio

from google import genai
from google.genai import types

from config import GOOGLE_AI_CONFIG, cprint
from ai.tools import query_table_data, list_files, read_file

SYSTEM_INSTRUCTION = (
    "Kamu RAMIEL, CS AI. Jawab SINGKAT, LANGSUNG.\n"
    "RAHASIA: Jangan sebut DB/tabel/tools ke user.\n"
    "DB kosong+kamu tahu=jawab FAKTA NYATA saja. Pertanyaan fiksi/tidak nyata \u2192 sarankan hubungi CS.\n"
    "DB: 'cerita'(id,judul,kategori,konten,tahun_terbit,jumlah_halaman), "
    "'playstore_reviews'(id,app_name,user_name,rating,review_date,problem_category,content,kategori).\n"
    "Untuk dokumen perusahaan: list_files\u2192read_file. Jangan mengarang jika dokumen tidak ada.\n"
    "EFISIENSI: Minta kolom seperlunya saja. Pakai 'category' bukan keyword untuk filter. "
    "Jangan tarik 'konten' kecuali diminta. "
    "Jika data sudah cukup STOP query, jangan ulang. "
    "Nilai 'xxx' \u2192 tulis persis 'xxx', tanpa tambahan penjelasan apapun."
)

MODELS = [
    "gemini-3.8-flash",
    "gemini-3.7-flash",
    "gemini-3.6-flash",
    "gemini-3.5-flash",
    "gemini-3.5-flash-lite",
    "gemini-3.1-flash-lite",
    "gemini-3.1-pro-preview",
    "gemini-3-flash-preview",
    "gemini-omni-1.1-flash",
    "gemini-2.5-flash",
    "gemini-2.5-flash-lite",
    "gemini-2.5-pro",
]
# Remove duplicates while preserving order
MODELS = list(dict.fromkeys(MODELS))
current_model_idx = 0
api_key = GOOGLE_AI_CONFIG.get("api_key", "").strip()
client = genai.Client(api_key=api_key) if api_key else None


def create_chat_session(history=None):
    if not client:
        cprint("api", "API key empty, chat not initialized.")
        return None
    chat_obj = client.aio.chats.create(
        model=MODELS[current_model_idx],
        config=types.GenerateContentConfig(
            system_instruction=SYSTEM_INSTRUCTION,
            tools=[query_table_data, list_files, read_file, {"google_search": {}}],
            automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
            safety_settings=[
                types.SafetySetting(category="HARM_CATEGORY_HATE_SPEECH", threshold="BLOCK_NONE"),
                types.SafetySetting(category="HARM_CATEGORY_HARASSMENT", threshold="BLOCK_NONE"),
                types.SafetySetting(category="HARM_CATEGORY_SEXUALLY_EXPLICIT", threshold="BLOCK_NONE"),
                types.SafetySetting(category="HARM_CATEGORY_DANGEROUS_CONTENT", threshold="BLOCK_NONE"),
            ],
        ),
        history=history or [],
    )
    cprint("api", f"Chat session created ({MODELS[current_model_idx]})")
    return chat_obj


async def safe_send_message(chat_obj, input_data):
    global current_model_idx
    retry_count = 0
    while True:
        try:
            res = await chat_obj.send_message(input_data)
            return res, chat_obj
        except Exception as e:
            err_msg = str(e).lower()
            if any(k in err_msg for k in ("429", "404", "503", "500", "504")):
                if "404" not in err_msg and retry_count < 4:
                    retry_count += 1
                    wait_time = 2 ** retry_count
                    cprint("ai", f"API busy. Retrying in {wait_time}s ({retry_count}/4)...")
                    await asyncio.sleep(wait_time)
                    continue
                if current_model_idx < len(MODELS) - 1:
                    current_model_idx += 1
                    retry_count = 0
                    cprint("ai", f"Falling back to: {MODELS[current_model_idx]}")
                    chat_obj = create_chat_session(history=chat_obj.get_history())
                    continue
            raise

async def generate_chat_title(user_msg: str) -> str:
    if not client:
        return "New Chat"
    try:
        response = await client.aio.models.generate_content(
            model=MODELS[current_model_idx],
            contents=f"Summarize this into a short chat title (2-4 words maximum, no quotes, no formatting): {user_msg}",
        )
        return response.text.strip().strip('"\'')
    except Exception as e:
        cprint("ai", f"Title gen error: {e}")
        return "New Chat"
