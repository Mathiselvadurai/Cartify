from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from typing import Optional
from database import get_db

router = APIRouter(prefix="/trains", tags=["Trains"])

@router.get("/search")
def search_trains(
    source: Optional[str] = Query(None, description="Source station"),
    destination: Optional[str] = Query(None, description="Destination station"),
    date: Optional[str] = Query(None, description="Journey date (YYYY-MM-DD)"),
    db: Session = Depends(get_db)
):
    """
    Search trains by source, destination, and journey date.
    Initial foundational endpoint: Returns empty list or initial message until full schedule data is seeded.
    """
    return {
        "source": source,
        "destination": destination,
        "date": date,
        "trains": [],
        "message": "Train search endpoint active. Ready for live train schedule dataset."
    }
