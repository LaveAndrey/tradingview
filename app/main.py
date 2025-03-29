from fastapi import FastAPI
from contextlib import asynccontextmanager
from routers.webhook import router as webhook_router
from app.config import Config
import logging
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import os
from pathlib import Path

# Базовый путь проекта
BASE_DIR = Path(__file__).parent.parent

# Настройка логирования (только в main.py)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(BASE_DIR / 'webhooks.log')
    ]
)
logger = logging.getLogger(__name__)

# Конфигурация Google Sheets
GOOGLE_SHEETS_CREDENTIALS = BASE_DIR / "credentials.json"
SPREADSHEET_ID = Config.ID_TABLES

COLUMN_HEADERS = [
    "Timestamp",
    "Ticker",
    "Price",
    "Action",
    "Market Cap",
    "24h Volume",
    "Custom Text"
]


def init_google_sheets():
    """Инициализация подключения к Google Sheets с созданием заголовков"""
    if not GOOGLE_SHEETS_CREDENTIALS.exists():
        raise FileNotFoundError(f"Credentials file not found at {GOOGLE_SHEETS_CREDENTIALS}")

    scope = [
        "https://spreadsheets.google.com/feeds",
        "https://www.googleapis.com/auth/drive"
    ]

    creds = ServiceAccountCredentials.from_json_keyfile_name(
        str(GOOGLE_SHEETS_CREDENTIALS), scope)
    client = gspread.authorize(creds)

    try:
        spreadsheet = client.open_by_key(SPREADSHEET_ID)
        sheet = spreadsheet.sheet1

        # Проверяем и создаем заголовки если нужно
        existing_headers = sheet.row_values(1)
        if not existing_headers or existing_headers != COLUMN_HEADERS:
            if existing_headers:
                sheet.clear()
            sheet.insert_row(COLUMN_HEADERS, index=1)
            logger.info("Created column headers in Google Sheet")

        return client, sheet

    except Exception as e:
        logger.error(f"Failed to initialize sheet: {str(e)}")
        raise


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Управление жизненным циклом приложения"""
    try:
        client, sheet = init_google_sheets()
        app.state.google_sheets = client
        app.state.sheet = sheet
        logger.info("Google Sheets initialized successfully")

        yield

    except Exception as e:
        logger.critical(f"Application startup failed: {str(e)}")
        raise
    finally:
        logger.info("Application shutdown")

app = FastAPI(
    lifespan=lifespan,
    title="TradingView Webhook Processor"
)

app.include_router(webhook_router)

if __name__ == '__main__':
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=5000)