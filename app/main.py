from fastapi import FastAPI
from contextlib import asynccontextmanager
from routers.webhook import router as webhook_router
from services.sheduler import start_scheduler
from app.database import Base, engine
from sqlalchemy import text
import logging


logger = logging.getLogger(__name__)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('webhooks.log')
    ]
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Инициализация при запуске
    logger.info("Creating database tables...")
    try:
        # Для синхронного движка (как у вас в database.py)
        Base.metadata.create_all(bind=engine)
        logger.info("Database tables created successfully")

        # Простая проверка подключения
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
            logger.info("Database connection test passed")

    except Exception as e:
        logger.error(f"Database initialization failed: {e}")
        raise

    # Запуск планировщика
    try:
        start_scheduler()
        logger.info("Scheduler started successfully")
    except Exception as e:
        logger.error(f"Failed to start scheduler: {e}")

    yield  # Здесь работает приложение

    # Завершение работы
    logger.info("Shutting down application...")


logger.info("BD create")

app = FastAPI(lifespan=lifespan)
app.include_router(webhook_router)

if __name__ == '__main__':
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=5000)