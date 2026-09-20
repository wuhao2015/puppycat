from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.clients import AppClients
from app.db import SessionLocal
from app.errors import GeminiError, NoNewTripRequirementsError, PlanningError
from app.models import PlanGeneration, Trip
from app.planner import generate_plan
from app.schemas import ChatMessage


logger = logging.getLogger(__name__)

ACTIVE_GENERATION_STATUSES = ("queued", "running")
POLL_INTERVAL_SECONDS = 2.0
WORKER_COUNT = 2


async def latest_plan_generation(
    session: AsyncSession, trip_id: str
) -> PlanGeneration | None:
    return await session.scalar(
        select(PlanGeneration)
        .where(PlanGeneration.trip_id == trip_id)
        .order_by(PlanGeneration.created_at.desc(), PlanGeneration.id.desc())
        .limit(1)
    )


async def enqueue_plan_generation(
    session: AsyncSession,
    *,
    trip: Trip,
) -> PlanGeneration:
    locked_trip = await session.scalar(
        select(Trip).where(Trip.id == trip.id).with_for_update()
    )
    if locked_trip is None:
        raise RuntimeError("Trip disappeared while queuing plan generation")

    messages = [
        ChatMessage.model_validate(payload)
        for payload in (locked_trip.chat_messages or [])
    ]
    if not any(message.role == "user" for message in messages):
        raise NoNewTripRequirementsError()
    input_message_ts = max(message.ts for message in messages)

    active = await session.scalar(
        select(PlanGeneration)
        .where(
            PlanGeneration.trip_id == locked_trip.id,
            PlanGeneration.status.in_(ACTIVE_GENERATION_STATUSES),
        )
        .order_by(PlanGeneration.created_at.desc(), PlanGeneration.id.desc())
        .limit(1)
    )
    if active is not None:
        await session.commit()
        return active

    generation = await session.scalar(
        select(PlanGeneration).where(
            PlanGeneration.trip_id == locked_trip.id,
            PlanGeneration.input_message_ts == input_message_ts,
        )
    )
    if generation is None:
        generation = PlanGeneration(
            trip_id=locked_trip.id,
            input_message_ts=input_message_ts,
        )
        session.add(generation)
    elif generation.status == "failed":
        generation.status = "queued"
        generation.itinerary_id = None
        generation.error_code = None
        generation.error_message = None
        generation.started_at = None
        generation.completed_at = None

    await session.commit()
    await session.refresh(generation)
    return generation


class PlanGenerationRunner:
    def __init__(self, clients: AppClients) -> None:
        self._clients = clients
        self._wake = asyncio.Event()
        self._tasks: list[asyncio.Task[None]] = []

    async def start(self) -> None:
        async with SessionLocal() as session:
            await session.execute(
                update(PlanGeneration)
                .where(PlanGeneration.status == "running")
                .values(status="queued", started_at=None)
            )
            await session.commit()
        self._tasks = [
            asyncio.create_task(
                self._run(),
                name=f"plan-generation-runner-{worker_number}",
            )
            for worker_number in range(1, WORKER_COUNT + 1)
        ]
        self.notify()

    async def close(self) -> None:
        if not self._tasks:
            return
        for task in self._tasks:
            task.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks = []

    def notify(self) -> None:
        self._wake.set()

    async def run_once(self) -> bool:
        generation_id = await _claim_next_generation()
        if generation_id is None:
            return False
        await _execute_generation(generation_id, clients=self._clients)
        return True

    async def _run(self) -> None:
        while True:
            self._wake.clear()
            try:
                while await self.run_once():
                    pass
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Plan generation worker iteration failed")
            try:
                await asyncio.wait_for(
                    self._wake.wait(),
                    timeout=POLL_INTERVAL_SECONDS,
                )
            except TimeoutError:
                pass


async def _claim_next_generation() -> str | None:
    async with SessionLocal() as session:
        generation = await session.scalar(
            select(PlanGeneration)
            .where(PlanGeneration.status == "queued")
            .order_by(PlanGeneration.created_at.asc(), PlanGeneration.id.asc())
            .with_for_update(skip_locked=True)
            .limit(1)
        )
        if generation is None:
            return None

        generation.status = "running"
        generation.started_at = datetime.now(timezone.utc)
        generation.completed_at = None
        generation.error_code = None
        generation.error_message = None
        await session.commit()
        return generation.id


async def _execute_generation(
    generation_id: str,
    *,
    clients: AppClients,
) -> None:
    async with SessionLocal() as session:
        generation = await session.get(PlanGeneration, generation_id)
        if generation is None or generation.status != "running":
            return
        trip = await session.get(Trip, generation.trip_id)
        if trip is None:
            return
        previous_generation = await session.scalar(
            select(PlanGeneration)
            .where(
                PlanGeneration.trip_id == generation.trip_id,
                PlanGeneration.status == "succeeded",
                PlanGeneration.id != generation.id,
            )
            .order_by(
                PlanGeneration.completed_at.desc(),
                PlanGeneration.created_at.desc(),
                PlanGeneration.id.desc(),
            )
            .limit(1)
        )

        try:
            itinerary = await generate_plan(
                session,
                trip=trip,
                clients=clients,
                through=generation.input_message_ts,
                previous_input_message_ts=(
                    previous_generation.input_message_ts
                    if previous_generation is not None
                    else None
                ),
            )
            generation.itinerary_id = itinerary.id
            generation.status = "succeeded"
            generation.completed_at = datetime.now(timezone.utc)
            await session.commit()
        except asyncio.CancelledError:
            await session.rollback()
            await _requeue_generation(generation_id)
            raise
        except (GeminiError, PlanningError) as error:
            await session.rollback()
            await _fail_generation(
                generation_id,
                code=error.error_code,
                message=error.public_message,
            )
        except Exception:
            await session.rollback()
            logger.exception(
                "Unexpected plan generation failure",
                extra={"plan_generation_id": generation_id},
            )
            await _fail_generation(
                generation_id,
                code="plan_generation_failed",
                message="Puppycat could not create the travel plan",
            )


async def _requeue_generation(generation_id: str) -> None:
    async with SessionLocal() as session:
        generation = await session.get(PlanGeneration, generation_id)
        if generation is None or generation.status != "running":
            return
        generation.status = "queued"
        generation.started_at = None
        await session.commit()


async def _fail_generation(
    generation_id: str,
    *,
    code: str,
    message: str,
) -> None:
    async with SessionLocal() as session:
        generation = await session.get(PlanGeneration, generation_id)
        if generation is None:
            return
        generation.status = "failed"
        generation.error_code = code
        generation.error_message = message
        generation.completed_at = datetime.now(timezone.utc)
        await session.commit()
