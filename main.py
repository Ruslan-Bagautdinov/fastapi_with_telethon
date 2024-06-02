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

from io import BytesIO
import urllib.parse
import requests
from urllib.parse import quote
from tempfile import NamedTemporaryFile

import qrcode
import os

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
    def encode_phrase(phrase):
        """
        Encode the phrase using UTF-8

        """
        encoded_phrase = urllib.parse.quote(phrase.encode('utf-8'), safe='')
        # Replace '%' with '^%^' to match the format you've described
        # formatted_encoded_phrase = encoded_phrase.replace('%', '^%^')
        return encoded_phrase

    def get_items(query):

        query = encode_phrase(query)

        url = f"https://search.wb.ru/exactmatch/ru/common/v5/search?ab_testing=false&appType=1&curr=rub&dest=-1257786&query={query}&resultset=catalog&sort=popular&spp=30&suppressSpellcheck=false"

        headers = {
            'Accept': '*/*',
            'Accept-Language': 'ru-RU,ru;q=0.8',
            'Connection': 'keep-alive',
            'Origin': 'https://www.wildberries.ru',
            'Referer': 'https://www.wildberries.ru/',
            'Sec-Fetch-Dest': 'empty',
            'Sec-Fetch-Mode': 'cors',
            'Sec-Fetch-Site': 'cross-site',
            'Sec-GPC': '1',
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36',
            'sec-ch-ua': '"Brave";v="125", "Chromium";v="125", "Not.A/Brand";v="24"',
            'sec-ch-ua-mobile': '?0',
            'sec-ch-ua-platform': 'Windows',
            'x-queryid': 'qid362479734171725507720240601205136'
        }
        response = requests.get(url=url, headers=headers)
        return response.json()

    def filter_items(response):

        products = []
        products_raw = response.get('data', {}).get('products', None)

        if products_raw != None and len(products_raw) > 0:
            for product in products_raw[:10]:
                name = product.get('name', None)
                id = product.get('id', None)
                products.append({
                    'name': name,
                    'link': f'https://www.wildberries.ru/catalog/{id}/detail.aspx',
                })
        return products

    response = get_items(query)
    products = filter_items(response)
    return products


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
            # coroutine without await to force Telethon not to wait for code from Telegram
            # but allow qr_login() to be initiated in the function 'render_qr_code'

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
