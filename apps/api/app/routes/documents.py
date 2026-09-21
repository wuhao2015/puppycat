import re
import unicodedata

from fastapi import APIRouter, Depends, Response
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from app.auth import get_current_user, get_owned_trip
from app.db import get_session
from app.documents import render_itinerary_pdf
from app.errors import ItineraryNotFoundError
from app.models import User
from app.planner import latest_itinerary
from app.schemas import Itinerary


router = APIRouter(prefix="/api/trips", tags=["documents"])


@router.post("/{trip_id}/documents/itinerary")
async def download_itinerary(
    trip_id: str,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> Response:
    trip = await get_owned_trip(
        session,
        trip_id=trip_id,
        current_user=current_user,
    )
    record = await latest_itinerary(session, trip.id)
    if record is None:
        raise ItineraryNotFoundError()

    itinerary = Itinerary.model_validate(record.data)
    pdf = await run_in_threadpool(render_itinerary_pdf, itinerary)
    filename = _itinerary_filename(itinerary.destination)
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={
            "Cache-Control": "no-store",
            "Content-Disposition": f'attachment; filename="{filename}"',
            "X-Content-Type-Options": "nosniff",
        },
    )


def _itinerary_filename(destination: str) -> str:
    ascii_destination = unicodedata.normalize("NFKD", destination).encode(
        "ascii", "ignore"
    ).decode("ascii")
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_destination.lower()).strip("-")
    return f"itinerary-{slug or 'trip'}.pdf"
