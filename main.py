
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routers.events import router as events_router
from app.routers.programs import router as programs_router
from app.routers.committee import router as committee_router
from app.routers.donations import router as donations_router
from app.routers.users import router as users_router
from app.routers.announcements import router as announcements_router
from app.routers.gallery import router as gallery_router
from app.routers.goshala import router as goshala_router
from app.routers.nakshatra import router as nakshatra_router
from app.routers.registrations import router as registrations_router

# Page-level media router
from app.routers.pages import router as pages_router

# Program Registration router
from app.routers.program_registrations import (
    router as program_registrations_router
)

# Existing authentication router
from app.auth.auth import router as auth_router

# Email OTP router
from app.routers.email_otp import router as email_otp_router


app = FastAPI(
    title="Temple Website & Mobile Application API",
    description="Backend API for the Temple Website and Mobile Application",
    version="1.0.0"
)


# ==================================================
# CORS Configuration
# ==================================================

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ==================================================
# Authentication routes
# ==================================================

app.include_router(auth_router)

# Email OTP routes
app.include_router(email_otp_router)


# ==================================================
# Users routes
# ==================================================

app.include_router(users_router)


# ==================================================
# Events routes
# ==================================================

app.include_router(events_router)


# ==================================================
# Programs routes
# ==================================================

app.include_router(programs_router)


# ==================================================
# Committee routes
# ==================================================

app.include_router(committee_router)


# ==================================================
# Donations routes
# ==================================================

app.include_router(donations_router)


# ==================================================
# Announcements routes
# ==================================================

app.include_router(announcements_router)


# ==================================================
# Gallery routes
# ==================================================

app.include_router(gallery_router)


# ==================================================
# Goshala routes
# ==================================================

app.include_router(goshala_router)


# ==================================================
# Nakshatra routes
# ==================================================

app.include_router(nakshatra_router)


# ==================================================
# Page-level Media routes
# ==================================================

app.include_router(pages_router)


# ==================================================
# Event Registration routes
# ==================================================

app.include_router(registrations_router)


# ==================================================
# Program Registration routes
# ==================================================

app.include_router(program_registrations_router)


# ==================================================
# Root endpoint
# ==================================================

@app.get("/")
def root():
    return {
        "message": "Temple Backend API is running successfully"
    }


# ==================================================
# Health check
# ==================================================

@app.get("/health")
def health_check():
    return {
        "status": "healthy"
    }
