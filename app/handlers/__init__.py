from aiogram import Router

from app.handlers.admin import router as admin_router
from app.handlers.actions import router as actions_router
from app.handlers.commands import router as commands_router
from app.handlers.payments import router as payments_router
from app.handlers.voice import router as voice_router
from app.middlewares import UserProfileMiddleware


def get_router() -> Router:
    router = Router()
    router.message.outer_middleware(UserProfileMiddleware())
    router.include_router(admin_router)
    router.include_router(commands_router)
    router.include_router(payments_router)
    router.include_router(actions_router)
    router.include_router(voice_router)
    return router
