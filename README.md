# FastAPI with Telethon

## Description

The web interface for a Telegram client. Based on FastAPI and Telethon. 
Provides users with the ability to authenticate to their Telegram account using a QR code, 
send and receive text and media messages, and search for products on marketplace.

## Features

- **User Authentication**: Users can authenticate with their Telegram account using a QR code. The application handles the login process and stores in memory the necessary session data.
- **Message Retrieval**: The application fetches new text messages from the Telegram API and stores them in memory, categorized by chats.
- **Message Sending**: Users can send text and media messages to other Telegram users through the web interface.
- **Wildberries Parsing**: The application provides an API endpoint that triggers a parsing process for Wildberries.ru with the query "любой товар" and city "Москва". The application sends the top 10 product names along with their links to the user.

## Installation

To set up and run the application, follow these steps:

1. Clone the repository:

```bash
git clone https://github.com/Ruslan-Bagautdinov/Fastapi_with_Telethon.git
```

2. Navigate to the directory:

```bash
cd Fastapi_with_Telethon
```

3. Create the `.env` file in the root directory and set the following environment variables:

```bash
# .env
YOUR_API_ID=<your-api-id>
YOUR_API_HASH=<your-api-hash>
YOUR_PHONE_NUMBER=<your-phone-number>
```

4. Build and run the Docker containers:

```bash
docker-compose up --build -d
```

## Usage

Once the application is up and running, you can access it by opening your web browser and navigating to `http://localhost:80`.

## Endpoints

The following endpoints are available in the FastAPI application.
The `{phone}` parameter should be replaced with user's phone number.

### GET /

This is the root endpoint of the application. It redirects to /docs for easy usage of OpenAPI.

```bash
GET http://localhost:80/
```

### POST /login

This endpoint is used to initiate the login process with a QR code.
Requires the user's `{phone}` as a query parameter in the URL.

```bash

POST http://localhost:80/login?phone={phone}
```

### GET /qr_code/{phone}

This endpoint is used to render the QR code for the login process.
Requires the user's `{phone}` as a query parameter in the URL.
Scan the QR code using the Telegram app on your smartphone to complete the login.

```bash
GET http://localhost:80/qr_code/{phone}
```

### GET /check/login

This endpoint is used to check the login status of the user.
Requires the the user's `{phone}` as a query parameter in the URL.
It returns a JSON response indicating the user's login status.


```bash
GET http://localhost:80/check/login?phone={phone}
```

### GET /messages

This endpoint is used to retrieve new text messages from the Telegram API and store them in the database, separated by chats.
Requires the user's `{phone}` and the chat username `{uname}` as a query parameters in the URL.

```bash
GET http://localhost:80/messages?phone={phone}&uname={chat username}
```

### POST /messages

This endpoint is used to send a text message to another Telegram user. 
Requires a JSON payload with the user's phone number, the recipient's phone number and the message text.

```bash
POST http://localhost:80/messages
Content-Type: application/json

{ 
  "phone": "string",
  "username": "string",
  "message_text": "string",
}
```

### POST /messages/media

This endpoint is used to send media (e.g., images, videos) to another Telegram user. 
Requires a JSON payload with the user's phone number, the recipient's phone number and the media file.

```bash
POST http://localhost:80/messages/media
Content-Type: application/json

{
  "phone": "string",
  "username": "string",
  "media": "<media-file>"
}
```

### GET /wild

This endpoint is used to trigger a parsing process for products with any `{query}`. It returns the top 10 product names with links to the product pages.

```bash
GET http://localhost/wild?query={query}
```






## License

This project is licensed under the MIT License. For more details, see the [LICENSE](LICENSE) file.

## Contact

If you have any questions or need support, please contact us at [ruslan3odey@gmail.com](mailto:ruslan3odey@gmail.com).
