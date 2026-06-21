from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import get_settings
from app.errors import PuppycatError
from app.routes import auth, documents, trips

settings = get_settings()

app = FastAPI(
    title="Puppycat Travel API",
    version="0.1.0",
    description=(
        "Verified AI travel itinerary planner. Itineraries pass a real-time verification "
        "stage (live hours, closures, strikes, weather) before they are returned."
    ),
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(PuppycatError)
async def puppycat_error_handler(_: Request, exc: PuppycatError) -> JSONResponse:
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.message})


@app.get("/health", tags=["meta"])
async def health() -> dict[str, str]:
    return {"status": "ok"}


app.include_router(auth.router)
app.include_router(trips.router)
app.include_router(documents.router)
