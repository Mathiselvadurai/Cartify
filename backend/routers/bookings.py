from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from database import get_db

router = APIRouter(prefix="/bookings", tags=["Bookings"])

@router.get("/pnr/{pnr_number}")
def get_pnr_status(pnr_number: str, db: Session = Depends(get_db)):
    """
    Lookup reservation by PNR.
    In this foundation stage, returns not found empty state until bookings are created via scheduling engine.
    """
    return {
        "pnr_number": pnr_number.upper(),
        "found": False,
        "message": f"PNR {pnr_number} not found. Booking engine pipeline is in development."
    }

@router.get("/history")
def get_booking_history(db: Session = Depends(get_db)):
    """
    Returns passenger booking history.
    """
    return {
        "bookings": [],
        "message": "No reservation history available in initial database."
    }
