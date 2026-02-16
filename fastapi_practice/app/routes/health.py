from fastapi import APIRouter

router = APIRouter()


@router.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy"}


@router.get("/")
async def root():
    """Root endpoint with API info."""
    return {
        "message": "Welcome to FastAPI Practice!",
        "docs": "/docs",
        "health": "/health",
    }
