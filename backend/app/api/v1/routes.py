from fastapi import APIRouter

from app.api.v1.api_keys import router as api_keys_router
from app.api.v1.auth import router as auth_router
from app.api.v1.chat import router as chat_router
from app.api.v1.export import public_router as public_share_router
from app.api.v1.export import router as export_router
from app.api.v1.repos import router as repos_router

api_router = APIRouter()
api_router.include_router(auth_router)
api_router.include_router(api_keys_router)
api_router.include_router(repos_router)
api_router.include_router(chat_router)
api_router.include_router(export_router)
api_router.include_router(public_share_router)
