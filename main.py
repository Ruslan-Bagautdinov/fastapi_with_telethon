from fastapi import FastAPI, HTTPException, Request, Query, UploadFile, File
from fastapi.responses import RedirectResponse, StreamingResponse
from pydantic import BaseModel, Field

from telethon.sync import TelegramClient
from telethon.tl.types import User, Channel, Chat
from telethon.tl.functions.messages import GetHistoryRequest, SendMessageRequest

from telethon.errors import (
    SessionPasswordNeededError,
    PhoneNumberInvalidError,
    UsernameNotOccupiedError,
    UsernameInvalidError,
    PeerIdInvalidError
)

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager

from bs4 import BeautifulSoup
from io import BytesIO
from urllib.parse import quote
from tempfile import NamedTemporaryFile

import qrcode
import os
import time

# own imports
from config import YOUR_API_ID, YOUR_API_HASH

app = FastAPI()


# The dict clients simulates a database for storing Telethon client sessions
clients = {}

# The dict messages_by_chat simulates a database for storing messages from chats
messages_by_chat = {}


class LoginResponse(BaseModel):
    """Response model for logging in."""
    status: str = Field(..., description="Status of the login process")
    qr_link_url: str = Field(None, description="URL to the QR code image for login")


class MessageRequest(BaseModel):
    """Request model for sending a message."""
    message_text: str = Field(..., description="The text of the message to send.")
    phone: str = Field(..., description="The phone number of the sender, used for authentication.")
    username: str = Field(..., description="The username or phone number of the recipient.")


def generate_qr_code(url):
    """ Function for generating an image with a QRCode from a URL received from Telegram"""
    qr = qrcode.main.QRCode(version=1, box_size=10, border=5)
    qr.add_data(url)
    qr.make(fit=True)
    img = qr.make_image(fill='black', back_color='white')
    buffer = BytesIO()
    img.save(buffer)
    buffer.seek(0)
    return buffer


def get_username(sender) -> str:
    """ Function for extracting username or chat title from a chat message"""
    user_name = ''
    if isinstance(sender, User):
        if sender.first_name:
            user_name += sender.first_name
            if sender.last_name:
                user_name += (' ' + sender.last_name)
        elif sender.username:
            user_name += sender.username
        elif sender.phone:
            user_name += sender.phone

    elif isinstance(sender, (Channel, Chat)):
        if sender.title:
            user_name += sender.title
        elif sender.username:
            user_name += sender.username
    return user_name


def scrape_wildberries(query):
    """ Function for scraping products from Wildberries.ru"""
    # Setup webdriver
    webdriver_service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=webdriver_service)

    try:
        url = f"https://www.wildberries.ru/catalog/0/search.aspx?search={query}"
        driver.get(url)

        # Waits 10 seconds for the page to load and JavaScript to execute
        time.sleep(10)

        soup = BeautifulSoup(driver.page_source, 'html.parser')

        product_elements = soup.find_all('article', class_='product-card')[:10]

        products = []
        for element in product_elements:
            product_link_element = element.find('a', class_='j-card-link')
            if product_link_element:
                product_name = product_link_element['aria-label']
                product_link = f"https://www.wildberries.ru{product_link_element['href']}"
                products.append({'name': product_name, 'link': product_link})

        return products
    finally:
        driver.quit()


@app.on_event("startup")
async def startup_event():
    pass


# When the program exits, terminating all sessions from dict clients
@app.on_event("shutdown")
async def shutdown_event():
    if clients:
        for phone, client in clients.items():
            print(f"Shutting down session for {phone}")
            await client.log_out()
            await client.disconnect()
    else:
        print("No clients to shutdown.")


# Чтобы сразу открывались /docs
@app.get("/")
async def root():
    return RedirectResponse(url='/docs')


@app.post("/login", response_model=LoginResponse)
async def login(
        phone: str = Query(..., description="Phone number to login with"),
        request: Request = None):
    try:
        if phone in clients and await clients[phone].is_user_authorized():
            return {"status": "logined", "qr_link_url": None}
        else:
            # # Saves the client to the dict clients
            clients[phone] = TelegramClient(None, YOUR_API_ID, YOUR_API_HASH, system_version="4.16.30-vxCUSTOM")
            #                                      ^ ^ ^
            # Parameter session = None, not (str | Path | Session) to avoid creating session files on disk
            # Client sessions are stored in the dict clients

            await clients[phone].connect()

            clients[phone].start(phone=lambda: phone)
            # ^ ^ ^
            # coroutine without await so that Telethon does not wait for code from Telegram
            # but allowed to initiate qr_login() in the function render_qr_code

            encoded_phone = quote(phone)
            qr_code_url = f"/qr_code/{encoded_phone}"
            full_url = f"{request.url.scheme}://{request.url.hostname}:{request.url.port}{qr_code_url}"

            return {"status": "waiting_qr_login", "qr_link_url": full_url}
    except SessionPasswordNeededError:
        raise HTTPException(status_code=400, detail="Two-step verification is enabled for this account.")
    except PhoneNumberInvalidError:
        raise HTTPException(status_code=400, detail="Invalid phone number.")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/qr_code/{phone}", response_description="Page with QR code image for login")
async def render_qr_code(phone: str):
    if phone not in clients:
        raise HTTPException(status_code=404, detail="Client not found")

    try:
        qr_login = await clients[phone].qr_login()
        qr_code_buffer = generate_qr_code(qr_login.url)

        # StreamingResponse allows you to see the QRCode directly in /docs
        return StreamingResponse(qr_code_buffer, media_type="image/png")

    except SessionPasswordNeededError:
        raise HTTPException(status_code=400, detail="Two-step verification is enabled for this account.")
    except PhoneNumberInvalidError:
        raise HTTPException(status_code=400, detail="Invalid phone number.")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/check/login")
async def check_login(phone: str = Query(..., description="Phone number to check login status for")):
    if phone not in clients:
        return {"status": "error", "detail": "Client not found"}
    if await clients[phone].is_user_authorized():
        return {"status": "logined"}
    else:
        return {"status": "waiting_qr_login"}


@app.get("/messages")
async def get_messages(phone: str = Query(..., description="Phone number associated with the Telegram account"),
                       uname: str = Query(..., description="Username of the chat to fetch messages from")):

    if phone not in clients:
        raise HTTPException(status_code=404, detail="Client not found")

    try:
        entity = await clients[phone].get_entity(uname)
        posts = await clients[phone](GetHistoryRequest(
            peer=entity,
            limit=50,
            offset_date=None,
            offset_id=0,
            max_id=0,
            min_id=0,
            add_offset=0,
            hash=0))

        messages = []
        for message in posts.messages:

            # From message gets entity (User, Chat or Channel)
            sender = await clients[phone].get_entity(message.sender_id)

            username = get_username(sender)
            messages.append({
                'username': username,
                'is_self': message.out,
                'message_text': message.message
            })
            # Saves messages to the dict messages_by_chat with the key username
            messages_by_chat[username] = messages

        return {'messages': messages}

    except (UsernameNotOccupiedError, UsernameInvalidError, PeerIdInvalidError) as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/messages")
async def send_message(request: MessageRequest):
    try:
        phone = request.phone
        # By username gets entity (User, Chat or Channel)
        peer = await clients[phone].get_input_entity(request.username)

        await clients[phone](SendMessageRequest(
            peer=peer,
            message=request.message_text
        ))

        return {"status": "ok"}
    except PeerIdInvalidError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


class InputMediaVideo:
    pass


@app.post("/messages/media")
async def send_media(phone: str, username: str, media_file: UploadFile = File(...)):
    if phone not in clients:
        raise HTTPException(status_code=400, detail="Client not found for the provided phone number.")

    try:
        # By username gets entity (User, Chat or Channel)
        peer = await clients[phone].get_input_entity(username)

        # Saves the downloaded file to a temporary file
        temp_file = NamedTemporaryFile(
            delete=False,
            suffix=os.path.splitext(media_file.filename)[1]    # with the original name
        )
        temp_file.write(await media_file.read())
        temp_file.close()

        await clients[phone].send_file(
            peer,
            file=temp_file.name,
            force_document=False
        )
        # Delete temporary file
        os.unlink(temp_file.name)

        return {"status": "ok"}
    except PeerIdInvalidError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/wild")
async def wildberries_search(query: str = Query(..., description="Enter the product name to search for")):
    try:
        product_data = scrape_wildberries(query)
        return {'products': product_data}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
