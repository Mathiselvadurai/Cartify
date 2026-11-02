from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from database import get_db

router = APIRouter(prefix="/cancellations", tags=["Cancellations"])

@router.get("/overview")
def get_cancellations(db: Session = Depends(get_db)):
    """
    Overview of cancelled bookings.
    """
    return {
        "cancellations": [],
        "message": "Cancellation overview ready. No records present."
    }
