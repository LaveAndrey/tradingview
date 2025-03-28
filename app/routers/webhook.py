from fastapi import APIRouter, Request, HTTPException, Depends
from sqlalchemy.orm import Session
from sqlalchemy import select
from pydantic import BaseModel, validator
from typing import Optional
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
    strategy: Optional[dict] = None

    @validator('close')
    def validate_close(cls, v):
        try:
            float(v)
            return v
        except ValueError:
            raise ValueError("Price must be a valid number")


async def get_validated_data(request: Request):
    try:
        body = await request.body()
        if not body:
            logger.error("Received empty request body")
            raise HTTPException(status_code=400, detail="Empty request body")

        try:
            return WebhookPayload.parse_raw(body)
        except ValueError as e:
            logger.error(f"Invalid JSON data: {str(e)}")
            raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Request validation error: {str(e)}")
        raise HTTPException(status_code=400, detail="Invalid request format")


def safe_get_action(data: dict) -> str:
    """Безопасное извлечение действия из данных"""
    try:
        strategy = data.get('strategy') or {}
        order = strategy.get('order') or {}
        action = order.get('action', '').lower()
        if action not in ('buy', 'sell'):
            raise HTTPException(400, detail="Invalid action, must be 'buy' or 'sell'")
        return action
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error extracting action: {str(e)}")
        raise HTTPException(400, detail="Invalid action format")


def get_market_data_safe(ticker: str) -> dict:
    """Безопасное получение рыночных данных"""
    try:
        symbol = coingecko.extract_symbol(ticker)
        market_data = coingecko.get_market_data(symbol)
        return {
            'market_cap': market_data.get('market_cap', 'N/A'),
            'volume_24h': market_data.get('volume_24h', 'N/A'),
            'symbol': symbol
        }
    except Exception as e:
        logger.error(f"CoinGecko error: {str(e)}")
        symbol = ticker.replace('USDT', '')
        return {
            'market_cap': 'N/A',
            'volume_24h': 'N/A',
            'symbol': symbol
        }


@router.post("/webhook")
async def handle_webhook(request: Request, db: Session = Depends(get_db)):
    try:
        # Получаем и валидируем данные
        payload = await get_validated_data(request)
        data = payload.dict()
        logger.info(f"Processing webhook for {data['ticker']}")

        # Генерация ID сигнала
        signal_id = hashlib.md5(
            f"{data['ticker']}-{data['close']}-{datetime.utcnow().timestamp()}".encode()
        ).hexdigest()

        # Проверка дубликатов в отдельной транзакции
        with db.begin():
            if db.execute(select(Trade).where(Trade.signal_id == signal_id).limit(1)).scalar():
                logger.warning(f"Duplicate signal detected: {signal_id}")
                return {"status": "duplicate"}

        # Основная транзакция
        try:
            with db.begin():
                # Получаем или создаем счетчик
                counter = db.execute(
                    select(Counter).with_for_update()
                ).scalar_one_or_none() or Counter(buy_count=0, sell_count=0)  # Явная инициализация

                # Обработка действия
                action = safe_get_action(data)

                # Обновляем счетчик
                if action == 'buy':
                    counter.buy_count = (counter.buy_count or 0) + 1
                    emoji = '🟢'
                else:
                    counter.sell_count = (counter.sell_count or 0) + 1
                    emoji = '🔴'

                # Получаем данные о монете
                market_info = get_market_data_safe(data['ticker'])
                symbol = market_info['symbol']

                # Создаем сделку
                trade = Trade(
                    action=action,
                    symbol=symbol,
                    price=data['close'],
                    signal_id=signal_id
                )

                db.add_all([counter, trade])

            # Формируем и отправляем сообщение
            message = (
                f"{emoji} *{action.upper()}*\n\n"
                f"*{symbol}*\n"
                f"💰 Price: *{data['close']}$*\n"
                f"🏦 Market Cap: *{coingecko.format_number(market_info['market_cap'])}$*\n"
                f"📊 24h Vol: *{coingecko.format_number(market_info['volume_24h'])}$*\n\n"
                f"🔗 [Trade on MEXC](https://www.mexc.com/exchange/{symbol}_USDT)"
            )

            try:
                TelegramBot.send_message(Config.CHAT_ID_TRADES, message)
            except Exception as e:
                logger.error(f"Telegram send error: {str(e)}")

            return {
                "status": "success",
                "symbol": symbol,
                "action": action,
                "price": data['close'],
                "signal_id": signal_id
            }

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Transaction error: {str(e)}", exc_info=True)
            raise HTTPException(500, detail="Internal server error")

    except HTTPException as he:
        raise
    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}", exc_info=True)
        raise HTTPException(500, detail="Internal server error")