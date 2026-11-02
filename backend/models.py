from datetime import datetime
from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, Text
from sqlalchemy.orm import relationship
from database import Base

class Train(Base):
    """
    Train schedule and inventory entity.
    Stores route information and total seat capacities.
    """
    __tablename__ = "trains"

    id = Column(Integer, primary_key=True, index=True)
    train_number = Column(String(10), unique=True, nullable=False, index=True)
    train_name = Column(String(100), nullable=False)
    source = Column(String(50), nullable=False, index=True)
    destination = Column(String(50), nullable=False, index=True)
    departure_time = Column(String(10), nullable=False)
    arrival_time = Column(String(10), nullable=False)
    duration = Column(String(20), nullable=False)
    base_fare = Column(Float, nullable=False)
    total_seats = Column(Integer, default=60, nullable=False)
    available_seats = Column(Integer, default=60, nullable=False)

    bookings = relationship("Booking", back_populates="train")


class Booking(Base):
    """
    Reservation entity storing completed booking details.
    """
    __tablename__ = "bookings"

    id = Column(Integer, primary_key=True, index=True)
    pnr_number = Column(String(10), unique=True, nullable=False, index=True)
    train_id = Column(Integer, ForeignKey("trains.id"), nullable=False)
    journey_date = Column(String(20), nullable=False)
    contact_email = Column(String(120), nullable=True)
    contact_phone = Column(String(20), nullable=True)
    total_fare = Column(Float, nullable=False)
    # Statuses: CONFIRMED, WAITING, CANCELLED
    status = Column(String(20), default="CONFIRMED", nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    train = relationship("Train", back_populates="bookings")
    passengers = relationship("Passenger", back_populates="booking", cascade="all, delete-orphan")


class Passenger(Base):
    """
    Individual passenger record belonging to a booking.
    """
    __tablename__ = "passengers"

    id = Column(Integer, primary_key=True, index=True)
    booking_id = Column(Integer, ForeignKey("bookings.id"), nullable=False)
    full_name = Column(String(100), nullable=False)
    age = Column(Integer, nullable=False)
    gender = Column(String(10), nullable=False)
    seat_number = Column(String(10), nullable=True)
    status = Column(String(20), default="CONFIRMED", nullable=False)

    booking = relationship("Booking", back_populates="passengers")


class Cancellation(Base):
    """
    Record of cancelled reservations and refund tracking.
    """
    __tablename__ = "cancellations"

    id = Column(Integer, primary_key=True, index=True)
    pnr_number = Column(String(10), nullable=False, index=True)
    booking_id = Column(Integer, nullable=False)
    refund_amount = Column(Float, nullable=False)
    cancellation_reason = Column(Text, nullable=True)
    cancelled_at = Column(DateTime, default=datetime.utcnow)


class SchedulingLog(Base):
    """
    Operating System Scheduling audit log.
    Records how each booking request process was queued, scheduled,
    and executed (FCFS, SJF, Priority) by the OS engine.
    """
    __tablename__ = "scheduling_logs"

    id = Column(Integer, primary_key=True, index=True)
    request_id = Column(String(50), unique=True, nullable=False)
    algorithm = Column(String(30), nullable=False) # e.g., FCFS, SJF, PRIORITY
    burst_time = Column(Integer, nullable=False)   # Simulated execution burst time
    priority_level = Column(Integer, default=3)    # 1 (High/VIP/Tatkal) to 5 (Low)
    waiting_time_ms = Column(Float, default=0.0)
    turnaround_time_ms = Column(Float, default=0.0)
    status = Column(String(20), default="COMPLETED") # QUEUED, PROCESSING, COMPLETED
    created_at = Column(DateTime, default=datetime.utcnow)
