from fastapi import APIRouter, Request, HTTPException, Depends
from sqlalchemy.orm import Session
from pydantic import BaseModel
import hashlib
import logging
from datetime import datetime
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
async def handle_webhook(request: Request, db: Session = Depends(get_db)):
    try:
        # Получаем и проверяем данные
        data = await request.json()
        if not all(k in data for k in ["ticker", "close", "strategy"]):
            raise HTTPException(status_code=400, detail="Missing required fields")

        try:
            float(data["close"])
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid price format")

        # Проверяем действие
        action = data.get("strategy", {}).get("order", {}).get("action", "").lower()
        if action not in ("buy", "sell"):
            raise HTTPException(status_code=400, detail="Invalid action")

        # Генерируем ID сделки
        signal_id = hashlib.sha256(
            f"{data['ticker']}-{data['close']}-{datetime.utcnow().timestamp()}".encode()
        ).hexdigest()

        # Проверяем дубликаты
        if db.query(Trade).filter(Trade.signal_id == signal_id).first():
            return {"status": "duplicate"}

        # Обновляем счетчик
        counter = db.query(Counter).first() or Counter()
        if action == "buy":
            counter.buy_count += 1
        else:
            counter.sell_count += 1

        # Получаем данные о монете
        symbol = coingecko.extract_symbol(data["ticker"])
        market_data = coingecko.get_market_data(symbol)

        # Сохраняем сделку
        trade = Trade(
            action=action,
            symbol=symbol,
            price=data["close"],
            signal_id=signal_id
        )

        db.add_all([counter, trade])
        db.commit()

        # Отправляем уведомление
        message = (
            f"{'🟢' if action == 'buy' else '🔴'} *{action.upper()}*\n\n"
            f"*{symbol}*\n"
            f"💰 Price: *{data['close']}$*\n"
            f"🏦 Market Cap: *{coingecko.format_number(market_data['market_cap'])}$*\n"
            f"📊 24h Vol: *{coingecko.format_number(market_data['volume_24h'])}$*\n\n"
            f"🔗 Trading on the MEXC exchange - *https://promote.mexc.com/r/scn7giWq*"
        )
        TelegramBot.send_message(Config.CHAT_ID_TRADES, message)

        return {
            "status": "success",
            "symbol": symbol,
            "action": action,
            "price": data["close"]
        }

    except Exception as e:
        logger.error(f"Error: {str(e)}")
        db.rollback()
        raise HTTPException(status_code=500, detail="Internal server error")