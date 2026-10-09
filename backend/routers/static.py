import os

from fastapi import APIRouter
from fastapi.responses import FileResponse

from config import FRONTEND_PATH

router = APIRouter()


@router.get("/api/v1/health")
async def health_check():
    return {"status": "ok"}


@router.get("/")
async def root_index():
    return FileResponse(os.path.join(FRONTEND_PATH, "index.html"))


@router.get("/admin")
async def admin_index():
    return FileResponse(os.path.join(FRONTEND_PATH, "admin.html"))


@router.get("/account-action")
async def account_action_index():
    return FileResponse(os.path.join(FRONTEND_PATH, "account-action.html"))
