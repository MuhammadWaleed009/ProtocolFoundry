from fastapi import APIRouter
from app.core.config import get_settings

router = APIRouter(tags=["health"])


@router.get("/health")
def health():
    s = get_settings()
    return {
        "status": "ok",
        "app": s.APP_NAME,
        "env": s.ENV,
        "checkpoint_backend": s.CHECKPOINT_BACKEND,
    }
