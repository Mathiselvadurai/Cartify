from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from database import get_db

router = APIRouter(prefix="/admin", tags=["Administration"])

@router.get("/overview")
def get_admin_overview(db: Session = Depends(get_db)):
    """
    Returns administrative summary statistics for trains, schedules, reservations, and cancellations.
    """
    return {
        "status": "ready",
        "total_trains": 0,
        "active_schedules": 0,
        "total_reservations": 0,
        "total_cancellations": 0,
        "scheduling_engine_status": "standby"
    }
