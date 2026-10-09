import os
import sys
import re


if getattr(sys, 'frozen', False):
    CODE_DIR = sys._MEIPASS
    FRONTEND_PATH = os.path.join(CODE_DIR, "frontend")
    CONFIG_PATH = os.path.join(os.path.dirname(sys.executable), "config.txt")
    HISTORY_PATH = os.path.join(os.path.dirname(sys.executable), "chat_history.txt")
    PROJECT_ROOT = os.path.dirname(sys.executable)
else:
    CODE_DIR = os.path.dirname(os.path.abspath(__file__))
    PROJECT_ROOT = os.path.dirname(CODE_DIR)
    FRONTEND_PATH = os.path.join(PROJECT_ROOT, "frontend")
    DATA_DIR = os.path.join(PROJECT_ROOT, "data")
    CONFIG_PATH = os.path.join(DATA_DIR, "config.txt")
    HISTORY_PATH = os.path.join(DATA_DIR, "chat_history.txt")

DB_CONFIG = {"host": "localhost", "user": "root", "password": "", "database": "dummy_db"}
GOOGLE_AI_CONFIG = {"api_key": "", "model_name": "gemini-2.5-flash"}
FILESYSTEM_CONFIG = {"doc_folder": "../data", "allowed_ext": [".txt", ".pdf", ".docx", ".xlsx", ".pptx", ".csv"]}
AUTH_CONFIG = {"jwt_secret": "changeme", "jwt_expire_hours": 8, "dev_secret": "changeme_dev"}
EMAIL_CONFIG = {
    "smtp_host": "mail.nuc.local",
    "smtp_port": 25,
    "smtp_user": "",
    "smtp_password": "",
    "from_email": "AI-Chatbot-Ramiel@nuc.local",
    "use_ssl": False,
    "use_starttls": False,
    "otp_bypass_user_ids": [0, 1],
    "otp_recipient_override_user_ids": [2, 3, 4, 5, 6],
    "otp_recipient_override_email": "neil.sumarta@nuc.local",
    "app_base_url": "http://127.0.0.1:8000",
}
ACTIVE_TABLES = {}
GLOBAL_DEBUG = True


def cprint(module: str, message: str):
    if GLOBAL_DEBUG:
        print(f"\n[{module}] {message}")


if os.path.exists(CONFIG_PATH):
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            current_section = None
            current_table = None
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if line.startswith("[") and line.endswith("]"):
                    current_section = line[1:-1].upper()
                    current_table = None
                    continue
                if current_section == "DATABASE" and "=" in line:
                    key, val = line.split("=", 1)
                    key = key.strip().lower()
                    if key == "db_name":
                        key = "database"
                    if key in DB_CONFIG:
                        DB_CONFIG[key] = val.strip()
                elif current_section == "GOOGLE_AI" and "=" in line:
                    key, val = line.split("=", 1)
                    key = key.strip().lower()
                    if key == "api_key":
                        keys = [k.strip() for k in val.split(",") if k.strip()]
                        if keys:
                            GOOGLE_AI_CONFIG["api_key"] = keys[0]
                    elif key in GOOGLE_AI_CONFIG:
                        GOOGLE_AI_CONFIG[key] = val.strip()
                elif current_section == "FILESYSTEM" and "=" in line:
                    key, val = line.split("=", 1)
                    key = key.strip().lower()
                    if key == "doc_folder":
                        FILESYSTEM_CONFIG["doc_folder"] = val.strip()
                    elif key == "allowed_ext":
                        FILESYSTEM_CONFIG["allowed_ext"] = [
                            ext.strip().lower() for ext in val.split(",") if ext.strip()
                        ]
                elif current_section == "AUTH" and "=" in line:
                    key, val = line.split("=", 1)
                    key = key.strip().lower()
                    if key == "jwt_secret":
                        AUTH_CONFIG["jwt_secret"] = val.strip()
                    elif key == "jwt_expire_hours":
                        AUTH_CONFIG["jwt_expire_hours"] = int(val.strip())
                    elif key == "dev_secret":
                        AUTH_CONFIG["dev_secret"] = val.strip()
                elif current_section == "EMAIL" and "=" in line:
                    key, val = line.split("=", 1)
                    key = key.strip().lower()
                    key_map = {
                        "smtp_host": "smtp_host",
                        "smtp_port": "smtp_port",
                        "smtp_user": "smtp_user",
                        "smtp_password": "smtp_password",
                        "from_email": "from_email",
                        "use_ssl": "use_ssl",
                        "use_starttls": "use_starttls",
                        "otp_bypass_user_ids": "otp_bypass_user_ids",
                        "otp_recipient_override_user_ids": "otp_recipient_override_user_ids",
                        "otp_recipient_override_email": "otp_recipient_override_email",
                        "app_base_url": "app_base_url",
                    }
                    if key in key_map:
                        config_key = key_map[key]
                        value = val.strip()
                        if config_key == "smtp_port":
                            EMAIL_CONFIG[config_key] = int(value)
                        elif config_key in ("use_ssl", "use_starttls"):
                            EMAIL_CONFIG[config_key] = value.lower() in ("true", "1", "yes")
                        elif config_key in ("otp_bypass_user_ids", "otp_recipient_override_user_ids"):
                            EMAIL_CONFIG[config_key] = [int(user_id.strip()) for user_id in value.split(",") if user_id.strip()]
                        else:
                            EMAIL_CONFIG[config_key] = value
                elif current_section == "TABLES":
                    match = re.match(r'^\d+\.\s*(.+)', line)
                    if match:
                        if current_table:
                            ACTIVE_TABLES[current_table].append(match.group(1).strip().lower())
                    elif ":" in line:
                        t_name, c_names = line.split(":", 1)
                        t_name = t_name.strip().lower()
                        ACTIVE_TABLES[t_name] = [
                            c.strip().lower() for c in c_names.split(",") if c.strip()
                        ]
                        current_table = t_name
                    elif "=" not in line:
                        ACTIVE_TABLES[line.strip().lower()] = []
                        current_table = line.strip().lower()
    except Exception as e:
        cprint("config", f"Config load error: {e}")
