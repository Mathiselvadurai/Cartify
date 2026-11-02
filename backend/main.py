import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from database import init_db
from routers import health, trains, bookings, cancellations, admin

# Initialize FastAPI application
app = FastAPI(
    title="RailSync Railway Reservation API",
    description="Backend API for RailSync Railway Reservation Management System. Course: Operating Systems (IASWE204).",
    version="1.0.0"
)

# Configure CORS for local development with React/Vite
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "*"
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register modular API routers
app.include_router(health.router, prefix="/api")
app.include_router(trains.router, prefix="/api")
app.include_router(bookings.router, prefix="/api")
app.include_router(cancellations.router, prefix="/api")
app.include_router(admin.router, prefix="/api")

@app.on_event("startup")
def on_startup():
    """
    Application startup event: Initialize SQLite database schema.
    """
    init_db()

@app.get("/")
def root():
    return {
        "project": "RailSync - Railway Reservation Management System",
        "course": "Operating Systems (IASWE204)",
        "docs_url": "/docs",
        "health_check": "/api/health"
    }

if __name__ == "__main__":
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)
