import os

from dotenv import find_dotenv, load_dotenv

load_dotenv(find_dotenv())

YOUR_API_ID = int(os.getenv('YOUR_API_ID'))
YOUR_API_HASH = os.getenv('YOUR_API_HASH')
YOUR_PHONE_NUMBER = os.getenv('YOUR_PHONE_NUMBER')
