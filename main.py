# main.py
from fastapi import FastAPI, Request, HTTPException, Depends
from pycoingecko import CoinGeckoAPI
from dotenv import load_dotenv
from pytz import timezone
import requests
import uvicorn
import os
from datetime import datetime
from sqlalchemy.orm import Session
from bd import Trade, DailyReport, get_db, SessionLocal
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
import logging
from typing import Tuple

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

app = FastAPI()
load_dotenv()

# Конфигурация
TOKEN = os.getenv('TOKENTELEGRAM')
CHAT_ID_TRADES = os.getenv('CHAT_IDTELEGRAM')
CHAT_ID_REPORTS = os.getenv('CHAT_ID_REPORTS')
cg = CoinGeckoAPI()

# Глобальные счетчики (в продакшене лучше использовать БД)
buy_count = 0
sell_count = 0


class TelegramBot:
    @staticmethod
    def send_message(chat_id: str, text: str) -> dict:
        """Отправка сообщения в Telegram"""
        url = f'https://api.telegram.org/bot{TOKEN}/sendMessage'
        payload = {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "Markdown",
            "disable_web_page_preview": True
        }
        try:
            response = requests.post(url, json=payload, timeout=10)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            logger.error(f"Telegram send error: {str(e)}")
            return {"status": "error", "message": str(e)}


def reset_counters(db: Session) -> None:
    """Сброс счетчиков и отправка ежедневного отчета"""
    global buy_count, sell_count

    try:
        daily_report = DailyReport(
            buy_count=buy_count,
            sell_count=sell_count
        )
        db.add(daily_report)
        db.commit()

        report_date = datetime.now(timezone('Europe/Moscow')).strftime("%Y-%m-%d")
        report_msg = (
            f"📊 *Daily Trading Report ({report_date})*\n\n"
            f"🟢 BUY Count: *{buy_count}*\n"
            f"🔴 SELL Count: *{sell_count}*\n\n"
            f"Total Trades: *{buy_count + sell_count}*"
        )

        TelegramBot.send_message(CHAT_ID_REPORTS, report_msg)
        logger.info(f"Report sent. Buy: {buy_count}, Sell: {sell_count}")

        buy_count, sell_count = 0, 0
    except Exception as e:
        logger.error(f"Reset counters error: {str(e)}")
        raise


# Планировщик
scheduler = BackgroundScheduler()
moscow_tz = timezone('Europe/Moscow')


def scheduled_reset():
    db = SessionLocal()
    try:
        reset_counters(db)
    finally:
        db.close()


scheduler.add_job(
    scheduled_reset,
    trigger=CronTrigger(hour=3, minute=0, timezone=moscow_tz)
)
scheduler.start()


def format_number(value, default="N/A") -> str:
    """Форматирование чисел с разделителями"""
    if isinstance(value, (int, float)):
        return f"{int(value):,}" if value == int(value) else f"{value:,.2f}"
    return default


def extract_symbol(ticker: str) -> str:
    """Извлечение символа из тикера"""
    return ticker[:-6] if ticker.upper().endswith("USDT.P") else ticker


def get_market_data(symbol: str) -> Tuple[str, str]:
    """Получение рыночных данных из CoinGecko"""
    try:
        logger.info(f"Fetching data for {symbol.upper()}")

        coins_list = cg.get_coins_list()
        matching_coins = [c for c in coins_list if c["symbol"].lower() == symbol.lower()]

        if not matching_coins:
            logger.warning(f"No matches for symbol: {symbol}")
            return 'N/A', 'N/A'

        coin_id = matching_coins[0]["id"]
        coin_data = cg.get_coin_by_id(coin_id)
        market_data = coin_data.get('market_data', {})

        market_cap = market_data.get('market_cap', {}).get('usd', 'N/A')
        volume_24h = market_data.get('total_volume', {}).get('usd', 'N/A')

        if isinstance(market_cap, (int, float)):
            market_cap = int(market_cap)
        if isinstance(volume_24h, (int, float)):
            volume_24h = int(volume_24h)

        logger.info(f"Market data: {symbol.upper()} Cap=${market_cap:,} Vol=${volume_24h:,}")
        return market_cap, volume_24h

    except Exception as e:
        logger.error(f"Market data error: {str(e)}")
        return 'N/A', 'N/A'


@app.post("/webhook")
async def webhook(request: Request, db: Session = Depends(get_db)):
    """Обработчик вебхуков от TradingView"""
    try:
        global buy_count, sell_count

        data = await request.json()
        logger.info(f"Incoming webhook data: {data.get('ticker')} {data.get('strategy.order.action')}")

        ticker = data.get('ticker', 'N/A')
        close = data.get('close', 'N/A')
        action = data.get('strategy.order.action', 'N/A').lower()

        if action == 'buy':
            buy_count += 1
            action_emoji = '🟢'
        elif action == 'sell':
            sell_count += 1
            action_emoji = '🔴'
        else:
            action_emoji = '⚪'

        symbol = extract_symbol(ticker)
        market_cap, volume_24h = get_market_data(symbol)

        message = (
            f"{action_emoji} *{action.upper()}*\n\n"
            f"*{symbol.upper()}*\n"
            f"💰 PRICE: *{close}$*\n"
            f"🏦 MARKET CAP: *{format_number(market_cap)}$*\n"
            f"📊 24H VOL: *{format_number(volume_24h)}$*\n\n"
            f"🔗 MEXC: https://promote.mexc.com/r/scn7giWq"
        )

        TelegramBot.send_message(CHAT_ID_TRADES, message)

        trade = Trade(action=action, symbol=symbol, price=close)
        db.add(trade)
        db.commit()

        return {
            "status": "success",
            "symbol": symbol,
            "action": action,
            "buy_count": buy_count,
            "sell_count": sell_count
        }

    except Exception as e:
        logger.error(f"Webhook error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == '__main__':
    uvicorn.run(app, host="0.0.0.0", port=5000)