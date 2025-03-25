from fastapi import APIRouter, Request, HTTPException, Depends
from sqlalchemy.orm import Session
from app.models import Trade
from app.database import get_db
from app.services.telegram import TelegramBot
from app.services.coingecko import CoinGeckoService
from app.config import Config
from app.services.trading import get_or_create_counter
import logging

router = APIRouter()
logger = logging.getLogger(__name__)
coingecko_service = CoinGeckoService()

@router.post("/webhook")
async def webhook(request: Request, db: Session = Depends(get_db)):
    """Обработчик вебхуков от TradingView"""
    try:
        data = await request.json()
        logger.info(f"Incoming webhook data: {data.get('ticker')} {data.get('strategy.order.action')}")

        ticker = data.get('ticker', 'N/A')
        close = data.get('close', 'N/A')
        action = data.get('strategy.order.action', 'N/A').lower()

        counter = get_or_create_counter(db)

        if action == 'buy':
            counter.buy_count += 1
            action_emoji = '🟢'
        elif action == 'sell':
            counter.sell_count += 1
            action_emoji = '🔴'
        else:
            action_emoji = '⚪'

        db.commit()

        symbol = coingecko_service.extract_symbol(ticker)
        market_cap, volume_24h = coingecko_service.get_market_data(symbol)

        message = (
            f"{action_emoji} *{action.upper()}*\n\n"
            f"*{symbol.upper()}*\n"
            f"💰 PRICE: *{close}$*\n"
            f"🏦 MARKET CAP: *{coingecko_service.format_number(market_cap)}$*\n"
            f"📊 24H VOL: *{coingecko_service.format_number(volume_24h)}$*\n\n"
            f"🔗 MEXC: https://promote.mexc.com/r/scn7giWq"
        )

        TelegramBot.send_message(Config.CHAT_ID_TRADES, message)

        trade = Trade(action=action, symbol=symbol, price=close)
        db.add(trade)
        db.commit()

        return {
            "status": "success",
            "symbol": symbol,
            "action": action,
            "buy_count": counter.buy_count,
            "sell_count": counter.sell_count
        }
    except Exception as e:
        logger.error(f"Webhook error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))