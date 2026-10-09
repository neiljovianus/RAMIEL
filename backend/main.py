import uvicorn
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from config import FRONTEND_PATH, cprint
from ai.client import MODELS, current_model_idx
from routers import chat, auth, sessions, dev, static, admin

app = FastAPI(title="RAMIEL AI")

app.include_router(chat.router)
app.include_router(auth.router)
app.include_router(sessions.router)
app.include_router(dev.router)
app.include_router(admin.router)
app.include_router(static.router)

app.mount("/", StaticFiles(directory=FRONTEND_PATH), name="frontend")

if __name__ == "__main__":
    cprint("sys", f"Service started ({MODELS[current_model_idx]})")
    uvicorn.run("main:app", host="127.0.0.1", port=8000)

