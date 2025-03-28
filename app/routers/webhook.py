from fastapi import APIRouter, Request, HTTPException, Depends, status
from sqlalchemy.orm import Session
from sqlalchemy import select
from pydantic import BaseModel, validator, Field
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
    ticker: str = Field(..., min_length=3, max_length=10, regex=r'^[A-Z]+$')
    close: str
    strategy: Optional[dict] = Field(None, description="Strategy details including order action")

    @validator('close')
    def validate_close(cls, v):
        try:
            float(v)
            return v
        except ValueError:
            raise ValueError("Price must be a valid number")


async def validate_webhook_request(request: Request):
    """Централизованная валидация входящего запроса"""
    try:
        if not request.headers.get("content-type") == "application/json":
            raise HTTPException(
                status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                detail="Unsupported Media Type"
            )

        body = await request.json()
        return WebhookPayload(**body)

    except ValueError as e:
        logger.error(f"JSON parsing error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid JSON format"
        )


def process_trade_action(data: dict) -> str:
    """Извлечение и валидация торгового действия"""
    action = (data.get('strategy', {}).get('order', {}).get('action', '')).lower()
    if action not in ('buy', 'sell'):
        logger.error(f"Invalid action received: {action}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Action must be either 'buy' or 'sell'"
        )
    return action


def generate_trade_id(ticker: str, price: str) -> str:
    """Генерация уникального ID для сделки"""
    return hashlib.sha256(
        f"{ticker}-{price}-{datetime.utcnow().isoformat()}".encode()
    ).hexdigest()


async def check_duplicate_trade(db: Session, trade_id: str) -> bool:
    """Проверка на дубликат сделки"""
    return db.execute(
        select(Trade).where(Trade.signal_id == trade_id).limit(1)
    ).scalar() is not None


async def update_trade_stats(db: Session, action: str):
    """Обновление счетчиков сделок"""
    counter = db.execute(
        select(Counter).with_for_update()
    ).scalar_one_or_none() or Counter(buy_count=0, sell_count=0)

    if action == 'buy':
        counter.buy_count += 1
    else:
        counter.sell_count += 1

    db.add(counter)
    return counter


async def send_telegram_notification(symbol: str, action: str, price: str, market_data: dict):
    """Отправка уведомления в Telegram"""
    message = (
        f"{'🟢' if action == 'buy' else '🔴'} *{action.upper()}*\n\n"
        f"*{symbol}*\n"
        f"💰 Price: *{price}$*\n"
        f"🏦 Market Cap: *{coingecko.format_number(market_data['market_cap'])}$*\n"
        f"📊 24h Vol: *{coingecko.format_number(market_data['volume_24h'])}$*\n\n"
        f"🔗 [Trade on MEXC](https://www.mexc.com/exchange/{symbol}_USDT)"
    )

    TelegramBot.send_message(Config.CHAT_ID_TRADES, message)


@router.post(
    "",
    response_model=dict,
    status_code=status.HTTP_201_CREATED,
    responses={
        400: {"description": "Invalid input data"},
        409: {"description": "Duplicate trade detected"},
        500: {"description": "Internal server error"}
    }
)
async def handle_webhook(
        request: Request,
        db: Session = Depends(get_db)
):
    """
    Process trading webhook with validation and duplicate checking.

    Expected JSON payload:
    {
        "ticker": "BTCUSDT",
        "close": "50000.00",
        "strategy": {
            "order": {
                "action": "buy"
            }
        }
    }
    """
    try:
        # Валидация входящего запроса
        payload = await validate_webhook_request(request)
        data = payload.dict()
        logger.info(f"Processing webhook for {data['ticker']}")

        # Генерация и проверка ID сделки
        signal_id = generate_trade_id(data['ticker'], data['close'])
        if await check_duplicate_trade(db, signal_id):
            logger.warning(f"Duplicate trade detected: {signal_id}")
            return {
                "status": "duplicate",
                "signal_id": signal_id
            }

        # Определение действия
        action = process_trade_action(data)

        # Обновление статистики
        await update_trade_stats(db, action)

        # Получение рыночных данных
        market_info = coingecko.get_market_data(
            coingecko.extract_symbol(data['ticker'])
        )

        # Создание записи о сделке
        trade = Trade(
            action=action,
            symbol=market_info['symbol'],
            price=data['close'],
            signal_id=signal_id
        )
        db.add(trade)
        db.commit()

        # Отправка уведомления
        await send_telegram_notification(
            market_info['symbol'],
            action,
            data['close'],
            market_info
        )

        return {
            "status": "success",
            "symbol": market_info['symbol'],
            "action": action,
            "price": data['close'],
            "signal_id": signal_id
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}", exc_info=True)
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error"
        )