import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
APP_URL = os.getenv("APP_URL", "http://localhost:8000")
ADMIN_ID = os.getenv("ADMIN_ID", "")
PORT = int(os.getenv("PORT", 8000))
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///english_app.db")
