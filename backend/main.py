from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.api.routes import router
from backend.core.auth import ensure_admin_user
from backend.core.database import init_db
from backend.core.database import SessionLocal
from backend.core.config import get_settings


settings = get_settings()
app = FastAPI(title="Multi-Agent Customer Support Resolution Platform")
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(router)


@app.on_event("startup")
def on_startup() -> None:
    settings.validate_production()
    init_db()
    db = SessionLocal()
    try:
        ensure_admin_user(db)
    finally:
        db.close()
