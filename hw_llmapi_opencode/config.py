import os
from dotenv import find_dotenv, load_dotenv

load_dotenv(find_dotenv())

deepseek_url = os.getenv("DEEPSEEK_URL")
deepseek_api_key = os.getenv("DEEPSEEK_API_KEY")