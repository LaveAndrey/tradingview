from fastapi import FastAPI
from routers.webhook import router as webhook_router
from services.sheduler import start_scheduler
from database import Base, engine
import logging
from models import *  # Импорт всех моделей для создания таблиц

# Настройка логгирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('webhooks.log')
    ]
)

logger = logging.getLogger(__name__)

app = FastAPI()


@app.on_event("startup")
async def startup():
    """Инициализация при запуске"""
    try:
        # Создание таблиц БД
        Base.metadata.create_all(bind=engine)
        logger.info("Database tables created successfully")

        # Инициализация планировщика
        start_scheduler()
        logger.info("Scheduler started successfully")

    except Exception as e:
        logger.error(f"Startup error: {str(e)}")
        raise


# Подключение роутеров
app.include_router(
    webhook_router,
    prefix="/api/v1",
    tags=["webhooks"]
)


@app.get("/health")
async def health_check():
    """Эндпоинт для проверки работоспособности"""
    return {"status": "ok", "message": "Service is running"}


if __name__ == '__main__':
    import uvicorn

    logger.info("Starting application...")
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=5000,
        log_config=None  # Используем настройки логгирования выше
    )