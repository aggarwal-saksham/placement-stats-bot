import os
from dotenv import load_dotenv

load_dotenv()

# API Keys and Tokens
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")

# Google Sheets Configuration
GOOGLE_SHEETS_CREDENTIALS_PATH = os.getenv("GOOGLE_SHEETS_CREDENTIALS_PATH", "credentials.json")
GOOGLE_SHEET_ID_OR_URL = os.getenv("GOOGLE_SHEET_ID_OR_URL", "1E7CtZmrXG_YiV6bATHOLBa9NnSvvwh68MUqWdTsykL4")

# Fallback Local Excel Path for offline testing / fallback
DEFAULT_LOCAL_EXCEL_PATH = r"C:\Users\DELL\Downloads\2027 unoff stats (1).xlsx"
