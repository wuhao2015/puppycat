import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

from app.db import engine
from app.main import app


@pytest_asyncio.fixture(autouse=True)
async def clean_test_database():
    async with engine.begin() as connection:
        database_name = await connection.scalar(text("select current_database()"))
        assert database_name == "puppycat_test"
        await connection.execute(
            text("truncate table itineraries, trips, users, api_cache cascade")
        )
    await engine.dispose()

    yield

    async with engine.begin() as connection:
        database_name = await connection.scalar(text("select current_database()"))
        assert database_name == "puppycat_test"
        await connection.execute(
            text("truncate table itineraries, trips, users, api_cache cascade")
        )
    await engine.dispose()


@pytest_asyncio.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as test_client:
        yield test_client
