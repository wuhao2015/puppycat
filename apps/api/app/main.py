from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.clients import AppClients
from app.config import settings
from app.errors import GeminiError
from app.routes.auth import router as auth_router
from app.routes.trips import router as trips_router


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    clients = AppClients.create(settings)
    app.state.clients = clients
    try:
        await clients.start()
        yield
    finally:
        await clients.close()


app = FastAPI(title="Puppycat Travel API", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(auth_router)
app.include_router(trips_router)


@app.exception_handler(GeminiError)
async def handle_gemini_error(
    _request: Request, error: GeminiError
) -> JSONResponse:
    return JSONResponse(
        status_code=error.status_code,
        content={"detail": error.detail()},
    )


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
