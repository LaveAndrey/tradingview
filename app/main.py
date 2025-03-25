from fastapi import FastAPI
from routers.webhook import router as webhook_router
from services.sheduler import start_scheduler
import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler()]
)

app = FastAPI()
app.include_router(webhook_router)

# Инициализация планировщика
start_scheduler()

if __name__ == '__main__':
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=5000)