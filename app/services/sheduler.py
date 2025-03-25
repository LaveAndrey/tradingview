from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from pytz import timezone
from app.database import SessionLocal
from app.services.trading import reset_counters

scheduler = BackgroundScheduler()
moscow_tz = timezone('Europe/Moscow')

def scheduled_reset():
    db = SessionLocal()
    try:
        reset_counters(db)
    finally:
        db.close()

def start_scheduler():
    scheduler.add_job(
        scheduled_reset,
        trigger=CronTrigger(hour=3, minute=0, timezone=moscow_tz)
    )
    scheduler.start()