import pytest


@pytest.mark.asyncio
async def test_movie_to_cinema_to_showtimes_flow(client, catalogue):
    movies = await client.get("/movies", params={"available_only": "true"})
    assert movies.status_code == 200
    assert [item["id"] for item in movies.json()] == [catalogue["movie_id"]]

    aggregation = await client.get(
        f"/movies/{catalogue['movie_id']}/showtimes",
        params={"city": "Hồ Chí Minh"},
    )
    assert aggregation.status_code == 200
    body = aggregation.json()
    assert body["cinemas"][0]["id"] == catalogue["cinema_id"]
    assert body["cinemas"][0]["showtimes"][0]["id"] == catalogue["showtime_id"]

    showtimes = await client.get(
        "/showtimes", params={"cinema_id": catalogue["cinema_id"]}
    )
    assert showtimes.status_code == 200
    assert showtimes.json()[0]["cinema_name"] == "Test Cinema"


@pytest.mark.asyncio
async def test_nearby_cinema_distance_and_coordinate_validation(client, catalogue):
    response = await client.get(
        "/cinemas",
        params={"latitude": 10.7768, "longitude": 106.7008, "radius_km": 5},
    )
    assert response.status_code == 200
    assert response.json()[0]["id"] == catalogue["cinema_id"]
    assert response.json()[0]["distance_km"] < 1

    invalid = await client.get("/cinemas", params={"latitude": 10.7})
    assert invalid.status_code == 422


@pytest.mark.asyncio
async def test_showtime_inventory(client, catalogue):
    response = await client.get(f"/showtimes/{catalogue['showtime_id']}")
    assert response.status_code == 200
    assert [seat["seat_label"] for seat in response.json()["seats"]] == ["A1", "A2"]
    assert {seat["status"] for seat in response.json()["seats"]} == {"available"}
