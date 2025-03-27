from fastapi import APIRouter, Request, HTTPException, Depends
from sqlalchemy.orm import Session
from sqlalchemy import select
from app.models import Trade, Counter
from app.database import get_db
from app.services.telegram import TelegramBot
from app.services.coingecko import CoinGeckoService
from app.config import Config
import hashlib
import logging
from datetime import datetime

router = APIRouter()
logger = logging.getLogger(__name__)
coingecko = CoinGeckoService()


def create_signal_id(data: dict) -> str:
    """Генерация уникального ID сигнала"""
    unique_str = f"{data.get('ticker')}-{data.get('close')}-{datetime.utcnow().timestamp()}"
    return hashlib.md5(unique_str.encode()).hexdigest()


@router.post("/webhook")
async def handle_webhook(request: Request, db: Session = Depends(get_db)):
    try:
        data = await request.json()
        logger.info(f"Received webhook: {data}")

        # Генерация уникального ID
        signal_id = create_signal_id(data)

        # Проверка дубликата
        if db.execute(select(Trade).where(Trade.signal_id == signal_id)).scalar():
            logger.warning(f"Duplicate signal detected: {signal_id}")
            return {"status": "duplicate"}

        # Извлечение данных
        ticker = data.get('ticker', '').upper()
        price = str(data.get('close', '0'))
        action = data.get('strategy', {}).get('order', {}).get('action', '').lower()

        if action not in ('buy', 'sell'):
            raise HTTPException(400, "Invalid action")

        # Получение данных о монете
        try:
            symbol = coingecko.extract_symbol(ticker)
            market_cap, volume_24h = coingecko.get_market_data(symbol)
        except Exception as e:
            logger.error(f"CoinGecko error: {str(e)}")
            symbol = ticker.replace('USDT', '')
            market_cap, volume_24h = "N/A", "N/A"

        # Атомарная транзакция
        with db.begin():
            # Обновление счетчика
            counter = db.execute(select(Counter)).scalar_one_or_none()
            if not counter:
                counter = Counter(buy_count=0, sell_count=0)
                db.add(counter)

            if action == 'buy':
                counter.buy_count += 1
                emoji = '🟢'
            else:
                counter.sell_count += 1
                emoji = '🔴'

            # Сохранение сделки
            trade = Trade(
                action=action,
                symbol=symbol,
                price=price,
                signal_id=signal_id
            )
            db.add(trade)

        # Отправка в Telegram
        message = (
            f"{emoji} *{action.upper()}*\n\n"
            f"*{symbol}*\n"
            f"💰 Цена: *{price}$*\n"
            f"🏦 Капитализация: *{coingecko.format_number(market_cap)}$*\n"
            f"📊 Объем 24h: *{coingecko.format_number(volume_24h)}$*\n\n"
            f"🔗 Ссылка: https://www.mexc.com/ru-RU/exchange/{symbol}_USDT"
        )

        TelegramBot.send_message(Config.CHAT_ID_TRADES, message)

        return {
            "status": "success",
            "symbol": symbol,
            "action": action,
            "price": price
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Webhook processing failed: {str(e)}", exc_info=True)
        raise HTTPException(500, "Internal server error")