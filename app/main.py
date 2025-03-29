from fastapi import FastAPI
from contextlib import asynccontextmanager
from routers.webhook import router as webhook_router
from app.config import Config
import logging
import gspread
from oauth2client.service_account import ServiceAccountCredentials

logger = logging.getLogger(__name__)

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('webhooks.log')
    ]
)

# Конфигурация Google Sheets
GOOGLE_SHEETS_CREDENTIALS = "credentials.json"
SPREADSHEET_ID = Config.ID_TABLES


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Инициализация подключения к Google Таблицам
    logger.info("Initializing Google Sheets connection...")
    try:
        scope = ["https://spreadsheets.google.com/feeds",
                 "https://www.googleapis.com/auth/drive"]
        creds = ServiceAccountCredentials.from_json_keyfile_name(
            GOOGLE_SHEETS_CREDENTIALS, scope)
        client = gspread.authorize(creds)

        # Проверяем доступ к таблице
        sheet = client.open_by_key(SPREADSHEET_ID).sheet1
        logger.info("Successfully connected to Google Sheets")

        # Сохраняем клиент в состоянии приложения
        app.state.google_sheets = client
        app.state.sheet = sheet

    except Exception as e:
        logger.error(f"Google Sheets initialization failed: {e}")
        raise

    yield  # Здесь работает приложение

    # Завершение работы
    logger.info("Application shutting down")


app = FastAPI(lifespan=lifespan)
app.include_router(webhook_router)

if __name__ == '__main__':
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=5000)