import asyncio

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app
from tests.conftest import register_and_login


@pytest.mark.asyncio
async def test_hold_release_and_restore_holds(client, catalogue):
    await register_and_login(client, "holder@example.com")
    url = f"/bookings/hold/{catalogue['showtime_id']}/{catalogue['seat_1_id']}"
    hold = await client.post(url)
    assert hold.status_code == 200
    assert hold.json()["hold_expires_in_seconds"] == 300

    holds = await client.get(f"/bookings/holds/{catalogue['showtime_id']}")
    assert holds.status_code == 200
    assert holds.json()[0]["seat_id"] == catalogue["seat_1_id"]

    inventory = await client.get(f"/showtimes/{catalogue['showtime_id']}")
    seat = next(item for item in inventory.json()["seats"] if item["id"] == catalogue["seat_1_id"])
    assert seat["status"] == "held"

    assert (await client.delete(url)).status_code == 204
    assert (await client.get(f"/bookings/holds/{catalogue['showtime_id']}")).json() == []


@pytest.mark.asyncio
async def test_booking_marks_inventory_and_prevents_second_booking(client, catalogue):
    await register_and_login(client, "winner@example.com")
    payload = {
        "showtime_id": catalogue["showtime_id"],
        "seat_ids": [catalogue["seat_1_id"], catalogue["seat_2_id"]],
    }
    booked = await client.post("/bookings", json=payload)
    assert booked.status_code == 201, booked.text
    assert len(booked.json()["seats"]) == 2

    conflict = await client.post("/bookings", json=payload)
    assert conflict.status_code == 409
    assert "đặt" in conflict.json()["detail"]


@pytest.mark.asyncio
async def test_two_users_cannot_hold_same_seat_concurrently(catalogue):
    transport = ASGITransport(app=app)
    async with (
        AsyncClient(transport=transport, base_url="http://test") as first,
        AsyncClient(transport=transport, base_url="http://test") as second,
    ):
        await register_and_login(first, "race-one@example.com")
        await register_and_login(second, "race-two@example.com")
        url = f"/bookings/hold/{catalogue['showtime_id']}/{catalogue['seat_1_id']}"
        responses = await asyncio.gather(first.post(url), second.post(url))
        assert sorted(response.status_code for response in responses) == [200, 409]
