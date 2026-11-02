from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import text
from database import get_db

router = APIRouter(prefix="/health", tags=["System Health"])

@router.get("")
def health_check(db: Session = Depends(get_db)):
    """
    Health check endpoint returning system status and SQLite database connectivity.
    """
    db_status = "connected"
    try:
        # Simple test query to ensure SQLite connection is alive
        db.execute(text("SELECT 1"))
    except Exception as exc:
        db_status = f"error: {str(exc)}"

    return {
        "status": "healthy",
        "service": "RailSync Railway Reservation API",
        "course": "Operating Systems - IASWE204",
        "version": "1.0.0",
        "database": {
            "engine": "SQLite",
            "status": db_status
        }
    }
