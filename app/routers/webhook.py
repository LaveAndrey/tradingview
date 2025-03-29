from fastapi import APIRouter, Request, HTTPException, BackgroundTasks
from pydantic import BaseModel
from datetime import datetime
from typing import Dict
import asyncio
import logging
from app.services.telegram import TelegramBot
from app.services.coingecko import CoinGeckoService
from app.config import Config

router = APIRouter()
logger = logging.getLogger(__name__)
coingecko = CoinGeckoService()

# Настройки Google Sheets
SPREADSHEET_ID = Config.ID_TABLES  # ID вашей Google Таблицы

update_tasks: Dict[str, asyncio.Task] = {}


async def update_price_periodically(sheet, row_index: int, symbol: str, signal_price: float):
    """Фоновая задача для периодического обновления цен"""
    try:
        intervals = [
            ('15m', 15 * 60),
            ('1h', 60 * 60),
            ('4h', 4 * 60 * 60),
            ('1d', 24 * 60 * 60)
        ]

        while True:
            current_price = coingecko.get_current_price(symbol)

            # Обновляем все интервалы, для которых прошло достаточно времени
            for interval_name, interval_seconds in intervals:
                # Получаем время сигнала из колонки D (4-я колонка)
                signal_time_str = sheet.cell(row_index, 4).value
                signal_time = datetime.strptime(signal_time_str, "%Y-%m-%d %H:%M:%S")
                time_passed = (datetime.utcnow() - signal_time).total_seconds()

                if time_passed >= interval_seconds:
                    # Определяем позиции колонок
                    close_col = 5 + intervals.index((interval_name, interval_seconds)) * 2
                    change_col = close_col + 1

                    # Если ячейка ещё не заполнена
                    if not sheet.cell(row_index, close_col).value:
                        # Рассчитываем изменение
                        price_change = ((current_price - signal_price) / signal_price) * 100

                        # Обновляем таблицу
                        sheet.update_cell(row_index, close_col, current_price)
                        sheet.update_cell(row_index, change_col, f"{price_change:.2f}%")

            # Проверяем обновления каждую минуту
            await asyncio.sleep(60)

    except Exception as e:
        logger.error(f"Price update task failed: {e}")
        # Удаляем задачу при ошибке
        if symbol in update_tasks:
            update_tasks.pop(symbol)

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
            logger.info(message)
        except Exception as e:
            logger.error(f"Failed to send Telegram message: {e}")
            raise HTTPException(status_code=500, detail="Failed to send notification")

        # Записываем данные в Google Таблицу
        try:
            sheet.append_row([
                symbol.upper(),
                action.lower(),
                price,
                datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
                "", "", "", "", "", "", "", ""
            ])

            row_index = len(sheet.get_all_values())

            task = asyncio.create_task(
                update_price_periodically(sheet, row_index, symbol, float(price))
            )
            update_tasks[symbol] = task

        except Exception as e:
            logger.error(f"Failed to write to Google Sheets: {e}")
            raise HTTPException(status_code=500, detail="Failed to save data")

        return {"status": "success", "message": "Alert processed"}

    except HTTPException:
        raise  # Пробрасываем уже обработанные ошибки
    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")