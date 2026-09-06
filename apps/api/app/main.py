from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.routes.auth import router as auth_router
from app.routes.trips import router as trips_router

app = FastAPI(title="Puppycat Travel API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(auth_router)
app.include_router(trips_router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
