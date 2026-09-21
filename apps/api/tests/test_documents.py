from datetime import date, datetime, time, timezone
from io import BytesIO
from uuid import uuid4

from httpx import AsyncClient
from pypdf import PdfReader

from app.db import SessionLocal
from app.models import Itinerary as ItineraryRecord
from app.schemas import Day, Item, Itinerary


async def _register(client: AsyncClient, prefix: str) -> dict[str, str]:
    response = await client.post(
        "/api/auth/register",
        json={
            "email": f"{prefix}-{uuid4()}@example.com",
            "password": "correct-horse-battery-staple",
            "signup_code": "test-signup-code",
        },
    )
    assert response.status_code == 201
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def _itinerary(activity_title: str) -> Itinerary:
    travel_date = date(2027, 4, 12)
    return Itinerary(
        destination="Kyoto, Japan",
        start_date=travel_date,
        end_date=travel_date,
        days=[
            Day(
                date=travel_date,
                title="Historic Kyoto",
                accommodation="Kyoto Station Hotel",
                items=[
                    Item(
                        id=f"item-{activity_title}",
                        start_time=time(9),
                        end_time=time(11),
                        title=activity_title,
                        description="A recognizable daily itinerary activity.",
                        kind="generic",
                    )
                ],
            )
        ],
    )


async def _save_itinerary(
    trip_id: str,
    itinerary: Itinerary,
    *,
    created_at: datetime,
) -> None:
    async with SessionLocal() as session:
        session.add(
            ItineraryRecord(
                trip_id=trip_id,
                data=itinerary.model_dump(mode="json"),
                created_at=created_at,
            )
        )
        await session.commit()


async def test_itinerary_pdf_uses_latest_saved_version(
    client: AsyncClient,
) -> None:
    owner = await _register(client, "document-owner")
    trip = (await client.post("/api/trips", headers=owner)).json()
    await _save_itinerary(
        trip["id"],
        _itinerary("Old garden visit"),
        created_at=datetime(2027, 1, 1, tzinfo=timezone.utc),
    )
    await _save_itinerary(
        trip["id"],
        _itinerary("Latest temple visit"),
        created_at=datetime(2027, 1, 2, tzinfo=timezone.utc),
    )

    response = await client.post(
        f"/api/trips/{trip['id']}/documents/itinerary",
        headers=owner,
    )

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert response.headers["content-disposition"] == (
        'attachment; filename="itinerary-kyoto-japan.pdf"'
    )
    assert response.headers["cache-control"] == "no-store"
    assert response.content.startswith(b"%PDF-")
    assert len(response.content) > 1_000

    text = "\n".join(
        page.extract_text() or "" for page in PdfReader(BytesIO(response.content)).pages
    )
    assert "Kyoto, Japan" in text
    assert "12 April 2027" in text
    assert "Latest temple visit" in text
    assert "Old garden visit" not in text


async def test_itinerary_pdf_rejects_missing_and_other_users_trips(
    client: AsyncClient,
) -> None:
    owner = await _register(client, "document-owner")
    other = await _register(client, "document-other")
    trip = (await client.post("/api/trips", headers=owner)).json()

    missing_itinerary = await client.post(
        f"/api/trips/{trip['id']}/documents/itinerary",
        headers=owner,
    )
    assert missing_itinerary.status_code == 404
    assert missing_itinerary.json()["detail"]["code"] == "itinerary_not_found"

    other_user = await client.post(
        f"/api/trips/{trip['id']}/documents/itinerary",
        headers=other,
    )
    assert other_user.status_code == 404
    assert other_user.json()["detail"] == "Trip not found"

    nonexistent = await client.post(
        "/api/trips/not-a-trip/documents/itinerary",
        headers=owner,
    )
    assert nonexistent.status_code == 404
    assert nonexistent.json()["detail"] == "Trip not found"
