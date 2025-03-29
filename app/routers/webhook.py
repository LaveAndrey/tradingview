from fastapi import APIRouter, Request, HTTPException
from pydantic import BaseModel
from datetime import datetime
import logging
from app.services.telegram import TelegramBot
from app.services.coingecko import CoinGeckoService
from app.config import Config

router = APIRouter()
logger = logging.getLogger(__name__)
coingecko = CoinGeckoService()

# Настройки Google Sheets
SPREADSHEET_ID = Config.ID_TABLES  # ID вашей Google Таблицы


class WebhookPayload(BaseModel):
    ticker: str
    close: str
    strategy: dict


@router.post("/webhook")
async def webhook(request: Request):
    try:
        # Проверка инициализации клиента
        if not hasattr(request.app.state, 'google_sheets'):
            logger.error("Google Sheets client not initialized")
            raise HTTPException(status_code=503, detail="Service unavailable")

        client = request.app.state.google_sheets

        try:
            sheet = client.open_by_key(SPREADSHEET_ID).sheet1
        except Exception as e:
            logger.error(f"Sheet access error: {str(e)}")
            raise HTTPException(status_code=500, detail="Spreadsheet access error")

        # Обработка данных...
        data = await request.json()
        logger.info(f"Processing data: {data}")

        # Извлекаем переменные
        ticker = data.get('ticker', 'N/A')
        close = data.get('close', 'N/A')
        action = data.get('strategy.order.action', 'N/A')

        # Эмодзи для действия
        action_emoji = '🟢' if action.lower() == 'buy' else '🔴' if action.lower() == 'sell' else '⚪'

        # Получаем символ монеты
        symbol = coingecko.extract_symbol(ticker.lower())
        logger.info(f"Extracted symbol: {symbol.lower()}")

        try:
            price = float(close)
        except ValueError:
            logger.error(f"Invalid price format: {close}")
            raise HTTPException(status_code=400, detail="Invalid price format")

        # Получаем рыночные данные
        market_cap, volume_24h = coingecko.get_market_data(symbol)

        # Формируем сообщение для Telegram
        message = (
            f"{action_emoji} *{action.upper()}* \n\n"
            f"*{symbol.upper()}*\n\n"
            f"PRICE - *{price}$*\n"
            f"MARKET CAP - *{coingecko.format_number(market_cap)}$*\n"
            f"24H VOLUME - *{coingecko.format_number(volume_24h)}$*\n\n"
            f"Trading on the MEXC exchange - *https://promote.mexc.com/r/scn7giWq*"
        )

        # Отправляем в Telegram
        try:
            TelegramBot.send_message(text=message, chat_id=Config.CHAT_ID_TRADES)
        except Exception as e:
            logger.error(f"Failed to send Telegram message: {e}")
            raise HTTPException(status_code=500, detail="Failed to send notification")

        # Записываем данные в Google Таблицу
        try:
            sheet.append_row([
                datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
                action.lower(),
                symbol.upper(),
                price,
                market_cap,
                volume_24h
            ])
        except Exception as e:
            logger.error(f"Failed to write to Google Sheets: {e}")
            raise HTTPException(status_code=500, detail="Failed to save data")

        return {"status": "success", "message": "Alert processed"}

    except HTTPException:
        raise  # Пробрасываем уже обработанные ошибки
    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")