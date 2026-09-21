from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.clients import AppClients
from app.config import settings
from app.errors import GeminiError, PlanningError
from app.plan_jobs import PlanGenerationRunner
from app.routes.auth import router as auth_router
from app.routes.documents import router as documents_router
from app.routes.trips import router as trips_router


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    clients = AppClients.create(settings)
    plan_generations = PlanGenerationRunner(clients)
    app.state.clients = clients
    app.state.plan_generations = plan_generations
    try:
        await clients.start()
        await plan_generations.start()
        yield
    finally:
        try:
            await plan_generations.close()
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
app.include_router(documents_router)


@app.exception_handler(GeminiError)
async def handle_gemini_error(
    _request: Request, error: GeminiError
) -> JSONResponse:
    return JSONResponse(
        status_code=error.status_code,
        content={"detail": error.detail()},
    )


@app.exception_handler(PlanningError)
async def handle_planning_error(
    _request: Request, error: PlanningError
) -> JSONResponse:
    return JSONResponse(
        status_code=error.status_code,
        content={"detail": error.detail()},
    )


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
