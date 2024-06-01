import pytest
from httpx import AsyncClient
from fastapi.testclient import TestClient
from main import app, clients, messages_by_chat
from config import YOUR_PHONE_NUMBER

client = TestClient(app)

user_name = 'some_telegram_user'


@pytest.fixture(scope="module")
def anyio_backend():
    return "asyncio"


@pytest.fixture(autouse=True)
async def startup_and_shutdown_uvicorn_server():
    # Start up the server.
    async with AsyncClient(app=app, base_url="http://test") as ac:
        yield
    # Shut down the server.
    for phone, client in clients.items():
        await client.log_out()
        await client.disconnect()
    clients.clear()
    messages_by_chat.clear()


def test_root():
    response = client.get("/")
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_login():
    response = client.post("/login", json={"phone": YOUR_PHONE_NUMBER})
    assert response.status_code == 200
    assert response.json() == {"status": "waiting_qr_login", "qr_link_url": f"http://test/qr_code/{YOUR_PHONE_NUMBER}"}


@pytest.mark.asyncio
async def test_check_login():
    response = client.get("/check/login", params={"phone": YOUR_PHONE_NUMBER})
    assert response.status_code == 200
    assert response.json() == {"status": "waiting_qr_login"}


@pytest.mark.asyncio
async def test_get_messages():
    response = client.get("/messages", params={"phone": YOUR_PHONE_NUMBER, "uname": user_name})
    assert response.status_code == 200
    assert "messages" in response.json()


@pytest.mark.asyncio
async def test_send_message():
    response = client.post("/messages", json={"phone": YOUR_PHONE_NUMBER, "uname": user_name,
                           "message_text": "Hello, world!"})
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@pytest.mark.asyncio
async def test_send_media():
    # You need to create a temporary file for testing media upload
    with open("test_file.txt", "w") as f:
        f.write("Test file content")
    with open("test_file.txt", "rb") as f:
        response = client.post("/messages/media", params={"phone": YOUR_PHONE_NUMBER, "uname": user_name},
                               files={"media_file": f})
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@pytest.mark.asyncio
async def test_wildberries_search():
    response = client.get("/wild", params={"query": "любой товар"})
    assert response.status_code == 200
    assert "products" in response.json()
