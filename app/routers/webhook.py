from fastapi import APIRouter, Request, HTTPException, Depends
from sqlalchemy.orm import Session
from pydantic import BaseModel
from datetime import datetime
import logging
from app.models import Trade, Counter
from app.database import get_db
from app.services.telegram import TelegramBot
from app.services.coingecko import CoinGeckoService
from app.config import Config

router = APIRouter()
logger = logging.getLogger(__name__)
coingecko = CoinGeckoService()


class WebhookPayload(BaseModel):
    ticker: str
    close: str
    strategy: dict


@router.post("/webhook")
async def webhook(request: Request, db: Session = Depends(get_db)):
    try:

        # Получаем данные от TradingView
        data = await request.json()
        logger.info(f"Received data: {data}")  # Логируем полученные данные

        # Извлекаем переменные из данных
        ticker = data.get('ticker', 'N/A')  # Пример: BTCUSDT.P, ETHUSDT.P и т.д.
        close = data.get('close', 'N/A')
        action = data.get('strategy.order.action', 'N/A')

        if action.lower() == 'buy':
            action_emoji = '🟢'
        elif action.lower() == 'sell':
            action_emoji = '🔴'
        else:
            action_emoji = '⚪'  # Если действие неизвестно, используем белый кружок

        # Извлекаем символ монеты из тикера (например, BTCUSDT.P → BTC)
        symbol = coingecko.extract_symbol(ticker.lower())
        logger.info(f"Extracted symbol: {symbol.lower()}")

        try:
            price = float(close)
        except ValueError:
            logger.error(f"Invalid price format: {close}")
            raise HTTPException(status_code=400, detail="Invalid price format")

        # Получаем капитализацию и объем за 24 часа
        market_cap, volume_24h = coingecko.get_market_data(symbol)

        # Формируем текст сообщения
        message = (
            f"{action_emoji} *{action.upper()}* \n\n"
            f"*{symbol.upper()}*\n\n"
            f"PRICE - *{price}$*\n"
            f"MARKET CAP - *{coingecko.format_number(market_cap)}$*\n"
            f"24H VOLUME - *{coingecko.format_number(volume_24h)}$*\n\n"
            f"Trading on the MEXC exchange - *https://promote.mexc.com/r/scn7giWq*"
        )

        try:
            TelegramBot.send_message(text=message, chat_id=Config.CHAT_ID_TRADES)  # Явно указываем параметр
        except Exception as e:
            logger.error(f"Failed to send Telegram message: {e}")
            raise HTTPException(status_code=500, detail="Failed to send notification")

        logger.info(f"Message to be sent: {message}")

        # Записываем данные в базу данных
        trade = Trade(action=action.lower(), symbol=symbol, price=price, timestamp=datetime.utcnow())
        db.add(trade)
        db.commit()

        # Возвращаем успешный ответ
        return {"status": "success", "message": "Alert processed"}

    except Exception as e:
        # Логируем ошибку
        print("Error:", str(e))
        raise HTTPException(status_code=500, detail=str(e))