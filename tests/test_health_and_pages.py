import pytest


@pytest.mark.asyncio
async def test_health(client):
    response = await client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@pytest.mark.asyncio
async def test_home_returns_html_instead_of_null(client, catalogue):
    response = await client.get("/")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert "<!DOCTYPE html>" in response.text
    assert "Step 9 Test Movie" in response.text


@pytest.mark.asyncio
async def test_movie_cinema_and_nearby_pages(client, catalogue):
    movie = await client.get(f"/movie/{catalogue['movie_id']}")
    cinema = await client.get(f"/cinema/{catalogue['cinema_id']}")
    nearby = await client.get("/nearby-cinemas")
    assert movie.status_code == cinema.status_code == nearby.status_code == 200
    assert "Step 9 Test Movie" in movie.text
    assert "Test Cinema" in cinema.text
    assert nearby.headers["content-type"].startswith("text/html")


@pytest.mark.asyncio
async def test_missing_html_resources_return_404_page(client):
    assert (await client.get("/movie/99999")).status_code == 404
    assert (await client.get("/cinema/99999")).status_code == 404
