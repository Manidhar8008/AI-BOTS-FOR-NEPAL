from fastapi import APIRouter

router = APIRouter()


@router.get("/health", summary="API health check")
async def health_check() -> dict[str, str]:
    """Small readiness endpoint for Docker and local smoke tests."""
    return {"status": "ok"}
