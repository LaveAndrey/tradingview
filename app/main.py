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

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Контекст жизненного цикла приложения"""
    try:
        # Проверка файла credentials
        if not GOOGLE_SHEETS_CREDENTIALS.exists():
            raise FileNotFoundError(f"Credentials file not found at {GOOGLE_SHEETS_CREDENTIALS}")

        scope = [
            "https://spreadsheets.google.com/feeds",
            "https://www.googleapis.com/auth/drive"
        ]

        # Загрузка и авторизация
        creds = ServiceAccountCredentials.from_json_keyfile_name(
            str(GOOGLE_SHEETS_CREDENTIALS), scope)
        client = gspread.authorize(creds)

        # Проверка подключения
        sheet = client.open_by_key(SPREADSHEET_ID).sheet1
        sheet.get_all_records()  # Тестовый запрос

        # Сохранение в состоянии приложения
        app.state.google_sheets = client
        logger.info("Google Sheets initialized")

    except Exception as e:
        logger.critical(f"Initialization failed: {str(e)}")
        raise

    yield  # Работа приложения

    logger.info("Application shutdown")

app = FastAPI(
    lifespan=lifespan,
    title="TradingView Webhook Processor"
)

app.include_router(webhook_router)

if __name__ == '__main__':
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=5000)