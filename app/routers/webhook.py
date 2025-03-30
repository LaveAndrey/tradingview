from fastapi import APIRouter, Request, HTTPException, BackgroundTasks
from datetime import datetime
from typing import Dict
import asyncio
import logging
from app.services.telegram import TelegramBot
from app.services.coingecko import CoinGeckoService
from app.config import Config
import pytz
import requests

router = APIRouter()
logger = logging.getLogger(__name__)
coingecko = CoinGeckoService()

# Настройки Google Sheets
SPREADSHEET_ID = Config.ID_TABLES  # ID вашей Google Таблицы
MEXC_API_URL = "https://api.mexc.com/api/v3"

update_tasks: Dict[str, asyncio.Task] = {}


async def get_mexc_price(symbol: str) -> float:
    """Получаем текущую цену с MEXC"""
    try:
        # Очистка и валидация символа
        clean_symbol = symbol.upper().strip()
        if not clean_symbol:
            raise ValueError("Empty symbol provided")

        # Формируем торговую пару (обратите внимание на отсутствие подчеркивания)
        trading_pair = f"{clean_symbol}USDT"

        # Выполняем запрос
        response = requests.get(
            f"{MEXC_API_URL}/ticker/price",
            params={"symbol": trading_pair},
            timeout=10  # Увеличил таймаут для надежности
        )

        # Логируем URL для отладки
        logger.debug(f"MEXC API request URL: {response.url}")

        response.raise_for_status()

        data = response.json()

        # Проверяем структуру ответа
        if not isinstance(data, dict) or 'price' not in data:
            raise ValueError(f"Invalid API response structure: {data}")

        price = float(data['price'])
        logger.info(f"Успешно получена цена для {clean_symbol}: {price}")

        return price

    except requests.exceptions.HTTPError as e:
        error_detail = f"{e.response.status_code} - {e.response.text}" if e.response else str(e)
        logger.error(f"Ошибка запроса к MEXC API: {error_detail}")
        raise HTTPException(
            status_code=502,
            detail=f"MEXC API error: {error_detail}"
        )
    except requests.exceptions.RequestException as e:
        logger.error(f"Сетевая ошибка при запросе к MEXC API: {e}")
        raise HTTPException(
            status_code=503,
            detail="MEXC API temporarily unavailable"
        )
    except (ValueError, KeyError) as e:
        logger.error(f"Ошибка обработки ответа: {e}")
        raise HTTPException(
            status_code=502,
            detail=f"Invalid API response: {str(e)}"
        )
    except Exception as e:
        logger.error(f"Неожиданная ошибка: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="Internal server error"
        )


async def update_price_periodically(sheet, row_index: int, symbol: str, entry_price: float, action: str):
    """Обновление цен с MEXC каждую минуту"""
    moscow_tz = pytz.timezone('Europe/Moscow')

    try:
        # Получаем время входа один раз
        entry_time_str = sheet.cell(row_index, 4).value
        entry_time = moscow_tz.localize(datetime.strptime(entry_time_str, "%Y-%m-%d %H:%M:%S"))

        intervals = [
            ('15m', 15 * 60),
            ('1h', 60 * 60),
            ('4h', 4 * 60 * 60),
            ('1d', 24 * 60 * 60)
        ]

        while True:
            try:
                current_price = await get_mexc_price(symbol)
                current_time = datetime.now(moscow_tz)
                elapsed = (current_time - entry_time).total_seconds()

                # Расчет изменения цены
                if action.lower() == 'buy':
                    change_pct = ((current_price - entry_price) / entry_price) * 100
                else:
                    change_pct = ((entry_price - current_price) / entry_price) * 100

                # Обновляем интервалы
                for name, seconds in intervals:
                    if elapsed >= seconds:
                        col = 5 + intervals.index((name, seconds)) * 2
                        if not sheet.cell(row_index, col).value:
                            sheet.update_cell(row_index, col, current_price)
                            sheet.update_cell(row_index, col + 1, f"{change_pct:.2f}%")
                            logger.info(f"Обновлен {name} для {symbol}")

                await asyncio.sleep(60)

            except Exception as e:
                logger.error(f"Ошибка обновления: {e}")
                await asyncio.sleep(300)

    except Exception as e:
        logger.error(f"Критическая ошибка: {e}")
        if symbol in update_tasks:
            update_tasks.pop(symbol)

def format_cell(sheet, row: int, col: int, value: float):
    """Применяет цвет фона к ячейке на основе значения"""
    try:
        if value >= 0:
            # Зелёный фон для положительных значений
            sheet.format(
                f"{chr(64 + col)}{row}",
                {"backgroundColor": {"red": 0.85, "green": 0.95, "blue": 0.85}}
            )
        else:
            # Красный фон для отрицательных значений
            sheet.format(
                f"{chr(64 + col)}{row}",
                {"backgroundColor": {"red": 0.95, "green": 0.85, "blue": 0.85}}
            )
    except Exception as e:
        logger.error(f"Failed to format cell: {e}")


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
        action = data.get('strategy.order.action', 'N/A')

        symbol = coingecko.extract_symbol(ticker.lower())

        # Эмодзи для действия
        action_emoji = '🟢' if action.lower() == 'buy' else '🔴' if action.lower() == 'sell' else '⚪'

        # Получаем символ монеты
        logger.info(f"Extracted symbol: {symbol.lower()}")


        # Получаем рыночные данные
        market_cap, volume_24h = await coingecko.get_market_data(symbol)
        current_price = await get_mexc_price(symbol)

        # Формируем сообщение для Telegram
        message = (
            f"{action_emoji} *{action.upper()}* \n\n"
            f"*{symbol.upper()}*\n\n"
            f"PRICE - *{current_price}$*\n"
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
                current_price,
                datetime.now(pytz.timezone('Europe/Moscow')).strftime("%Y-%m-%d %H:%M:%S"),
                "", "", "", "", "", "", "", ""
            ])

            row_index = len(sheet.get_all_values())

            task = asyncio.create_task(
                update_price_periodically(sheet, row_index, symbol, float(current_price), action)
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