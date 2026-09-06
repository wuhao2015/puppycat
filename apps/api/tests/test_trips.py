from collections.abc import Mapping
from typing import Any
from uuid import uuid4

from httpx import AsyncClient


async def register(client: AsyncClient, name: str) -> dict[str, str]:
    response = await client.post(
        "/api/auth/register",
        json={
            "email": f"{name}-{uuid4()}@example.com",
            "password": "correct-horse-battery-staple",
            "signup_code": "test-signup-code",
        },
    )
    assert response.status_code == 201
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def assert_trip_fields(trip: Mapping[str, Any], *, includes_messages: bool) -> None:
    expected = {
        "id",
        "title",
        "destination",
        "start_date",
        "end_date",
        "created_at",
        "updated_at",
    }
    if includes_messages:
        expected.update({"preferences", "chat_messages"})
    assert set(trip) == expected


async def test_trip_crud_messages_and_stable_list_order(client: AsyncClient) -> None:
    owner = await register(client, "owner")

    first_response = await client.post("/api/trips", headers=owner)
    assert first_response.status_code == 201
    first = first_response.json()
    assert first["title"] == "New trip"
    assert first["preferences"] == {}
    assert first["chat_messages"] == []
    assert_trip_fields(first, includes_messages=True)

    second_response = await client.post(
        "/api/trips", headers=owner, json={"title": "Kyoto in spring"}
    )
    assert second_response.status_code == 201
    second = second_response.json()

    message_response = await client.post(
        f"/api/trips/{first['id']}/chat",
        headers=owner,
        json={"content": "  Seven relaxed days in Kyoto  "},
    )
    assert message_response.status_code == 201
    message = message_response.json()
    assert message["assistant_status"] == "gemini_not_connected"
    assert message["message"]["role"] == "user"
    assert message["message"]["content"] == "Seven relaxed days in Kyoto"
    assert message["message"]["ts"]

    second_message_response = await client.post(
        f"/api/trips/{first['id']}/chat",
        headers=owner,
        json={"role": "user", "content": "Gardens and local food"},
    )
    assert second_message_response.status_code == 201

    detail_response = await client.get(f"/api/trips/{first['id']}", headers=owner)
    assert detail_response.status_code == 200
    detail = detail_response.json()
    assert [item["content"] for item in detail["chat_messages"]] == [
        "Seven relaxed days in Kyoto",
        "Gardens and local food",
    ]

    list_response = await client.get("/api/trips", headers=owner)
    assert list_response.status_code == 200
    listed = list_response.json()
    assert [trip["id"] for trip in listed] == [first["id"], second["id"]]
    assert all(
        set(trip)
        == {
            "id",
            "title",
            "destination",
            "start_date",
            "end_date",
            "created_at",
            "updated_at",
        }
        for trip in listed
    )

    rename_response = await client.patch(
        f"/api/trips/{first['id']}",
        headers=owner,
        json={"title": "  Kyoto gardens  "},
    )
    assert rename_response.status_code == 200
    assert rename_response.json()["title"] == "Kyoto gardens"

    invalid_role = await client.post(
        f"/api/trips/{first['id']}/chat",
        headers=owner,
        json={"role": "assistant", "content": "Not allowed"},
    )
    assert invalid_role.status_code == 422

    blank_message = await client.post(
        f"/api/trips/{first['id']}/chat",
        headers=owner,
        json={"content": "   "},
    )
    assert blank_message.status_code == 422

    delete_response = await client.delete(f"/api/trips/{second['id']}", headers=owner)
    assert delete_response.status_code == 204
    assert not delete_response.content
    assert (
        await client.get(f"/api/trips/{second['id']}", headers=owner)
    ).status_code == 404


async def test_trips_are_private_to_their_owner(client: AsyncClient) -> None:
    owner = await register(client, "owner")
    other_user = await register(client, "other")
    trip = (await client.post("/api/trips", headers=owner)).json()

    assert (await client.get("/api/trips", headers=other_user)).json() == []
    assert (
        await client.get(f"/api/trips/{trip['id']}", headers=other_user)
    ).status_code == 404
    assert (
        await client.patch(
            f"/api/trips/{trip['id']}",
            headers=other_user,
            json={"title": "Taken over"},
        )
    ).status_code == 404
    assert (
        await client.post(
            f"/api/trips/{trip['id']}/chat",
            headers=other_user,
            json={"content": "Taken over"},
        )
    ).status_code == 404
    assert (
        await client.delete(f"/api/trips/{trip['id']}", headers=other_user)
    ).status_code == 404

    owner_detail = await client.get(f"/api/trips/{trip['id']}", headers=owner)
    assert owner_detail.status_code == 200
    assert owner_detail.json()["title"] == "New trip"
    assert owner_detail.json()["chat_messages"] == []


async def test_trip_endpoints_require_authentication(client: AsyncClient) -> None:
    assert (await client.get("/api/trips")).status_code == 401
    assert (await client.post("/api/trips")).status_code == 401
