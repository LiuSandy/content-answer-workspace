import pytest
from sqlalchemy.exc import DBAPIError
from app.bootstrap.server import handle_db_exception


@pytest.mark.asyncio
async def test_db_exception_handler():
    error = DBAPIError("DB connection failed", params=None, orig=Exception("Connection refused"))
    response = await handle_db_exception(None, error)
    assert response.status_code == 503
    payload = response.body.decode("utf-8")
    assert "database_error" in payload
