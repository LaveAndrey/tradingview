from datetime import datetime
from pytz import timezone
from app.models import Counter, DailyReport
from app.services.telegram import TelegramBot
from app.config import Config
import logging

logger = logging.getLogger(__name__)

def get_or_create_counter(db):
    counter = db.query(Counter).first()
    if not counter:
        counter = Counter()
        db.add(counter)
        db.commit()
    return counter

def reset_counters(db):
    try:
        counter = get_or_create_counter(db)
        daily_report = DailyReport(
            buy_count=counter.buy_count,
            sell_count=counter.sell_count
        )
        db.add(daily_report)

        report_date = datetime.now(timezone('Europe/Moscow')).strftime("%Y-%m-%d")
        report_msg = (
            f"📊 *Daily Trading Report ({report_date})*\n\n"
            f"🟢 BUY Count: *{counter.buy_count}*\n"
            f"🔴 SELL Count: *{counter.sell_count}*\n\n"
            f"Total Trades: *{counter.buy_count + counter.sell_count}*"
        )

        TelegramBot.send_message(Config.CHAT_ID_REPORTS, report_msg)
        logger.info(f"Report sent. Buy: {counter.buy_count}, Sell: {counter.sell_count}")

        counter.buy_count = 0
        counter.sell_count = 0
        db.commit()
    except Exception as e:
        logger.error(f"Reset counters error: {str(e)}")
        raise