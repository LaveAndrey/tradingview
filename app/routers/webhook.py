from fastapi import APIRouter, Request, HTTPException, BackgroundTasks
from pydantic import BaseModel
from datetime import datetime
from typing import Dict
import asyncio
import logging
from app.services.telegram import TelegramBot
from app.services.coingecko import CoinGeckoService
from app.config import Config
import pytz

router = APIRouter()
logger = logging.getLogger(__name__)
coingecko = CoinGeckoService()

# Настройки Google Sheets
SPREADSHEET_ID = Config.ID_TABLES  # ID вашей Google Таблицы

update_tasks: Dict[str, asyncio.Task] = {}


async def update_price_periodically(sheet, row_index: int, symbol: str, signal_price: float, action: str):
    """Фоновая задача для периодического обновления цен"""
    try:
        intervals = [
            ('15m', 15 * 60),
            ('1h', 60 * 60),
            ('4h', 4 * 60 * 60),
            ('1d', 24 * 60 * 60)
        ]

        moscow_tz = pytz.timezone('Europe/Moscow')

        # Получаем время сигнала один раз в начале
        signal_time_str = sheet.cell(row_index, 4).value
        if not signal_time_str:
            logger.error(f"Не найдено время сигнала для строки {row_index}")
            if symbol in update_tasks:
                update_tasks.pop(symbol)
            return

        try:
            # Парсим время и устанавливаем временную зону
            naive_signal_time = datetime.strptime(signal_time_str, "%Y-%m-%d %H:%M:%S")
            signal_time = moscow_tz.localize(naive_signal_time)
        except ValueError as e:
            logger.error(f"Неверный формат времени сигнала: {signal_time_str}. Ошибка: {e}")
            if symbol in update_tasks:
                update_tasks.pop(symbol)
            return

        while True:
            try:
                # Получаем текущую цену
                current_price = await coingecko.get_current_price(symbol)

                # Рассчитываем изменение цены
                if action.lower() == 'buy':
                    price_change = ((current_price - signal_price) / signal_price) * 100  # Лонг
                else:
                    price_change = ((signal_price - current_price) / signal_price) * 100  # Шорт

                # Рассчитываем прошедшее время с учетом временной зоны
                current_time = datetime.now(moscow_tz)
                time_passed = (current_time - signal_time).total_seconds()

                # Обновляем интервалы
                for interval_name, interval_seconds in intervals:
                    if time_passed >= interval_seconds:
                        close_col = 5 + intervals.index((interval_name, interval_seconds)) * 2
                        change_col = close_col + 1

                        # Проверяем, не обновляли ли уже этот интервал
                        if not sheet.cell(row_index, close_col).value:
                            try:
                                sheet.update_cell(row_index, close_col, current_price)
                                sheet.update_cell(row_index, change_col, f"{price_change:.2f}%")
                                format_cell(sheet, row_index, change_col, price_change)
                                logger.info(f"Обновлен интервал {interval_name} для {symbol}")
                            except Exception as update_error:
                                logger.error(f"Ошибка обновления ячейки: {update_error}")
                                continue  # Продолжаем с следующим интервалом

                await asyncio.sleep(60)  # Пауза между проверками

            except Exception as e:
                logger.error(f"Временная ошибка в задаче обновления цен: {e}")
                await asyncio.sleep(300)  # Увеличиваем задержку при ошибках

                # Проверяем, существует ли еще строка в таблице
                try:
                    if not sheet.cell(row_index, 1).value:  # Проверяем первый столбец
                        logger.info(f"Строка {row_index} больше не существует, завершаем задачу")
                        if symbol in update_tasks:
                            update_tasks.pop(symbol)
                        return
                except Exception as check_error:
                    logger.error(f"Ошибка проверки строки: {check_error}")
                    if symbol in update_tasks:
                        update_tasks.pop(symbol)
                    return

    except Exception as e:
        logger.error(f"Критическая ошибка в фоновой задаче: {e}")
        if symbol in update_tasks:
            update_tasks.pop(symbol)

def format_cell(sheet, row: int, col: int, value: float):
    """Применяет цвет к ячейке на основе значения"""
    try:
        if value >= 0:
            # Зелёный для положительных значений
            sheet.format(
                f"{chr(64 + col)}{row}",
                {"textFormat": {"foregroundColor": {"red": 0, "green": 0.7, "blue": 0}}}
            )
        else:
            # Красный для отрицательных
            sheet.format(
                f"{chr(64 + col)}{row}",
                {"textFormat": {"foregroundColor": {"red": 0.8, "green": 0, "blue": 0}}}
            )
    except Exception as e:
        logger.error(f"Failed to format cell: {e}")

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
        market_cap, volume_24h = await coingecko.get_market_data(symbol)

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
                datetime.now(pytz.timezone('Europe/Moscow')).strftime("%Y-%m-%d %H:%M:%S"),
                "", "", "", "", "", "", "", ""
            ])

            row_index = len(sheet.get_all_values())

            task = asyncio.create_task(
                update_price_periodically(sheet, row_index, symbol, float(price), action)
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