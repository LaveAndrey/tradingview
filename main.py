# main.py
from fastapi import FastAPI, Request, HTTPException, Depends
from pycoingecko import CoinGeckoAPI
from dotenv import load_dotenv
import requests
import os
from datetime import datetime
from sqlalchemy.orm import Session
from bd import Trade, DailyReport, get_db, SessionLocal  # Импортируем модели и функции из models.py
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

app = FastAPI()

load_dotenv()

# Токен вашего Telegram-бота
TOKEN = os.getenv('TOKENTELEGRAM')
# ID вашего чата в Telegram
CHAT_ID = os.getenv('CHAT_IDTELEGRAM')

# Инициализация CoinGecko API
cg = CoinGeckoAPI()

# Глобальные переменные для хранения счётчиков
buy_count = 0
sell_count = 0

# Функция для сброса счётчиков в 3:00 каждый день
def reset_counters(db: Session):
    global buy_count, sell_count

    # Сохраняем текущие значения счётчиков в таблицу daily_reports
    daily_report = DailyReport(
        buy_count=buy_count,
        sell_count=sell_count
    )
    db.add(daily_report)
    db.commit()

    # Обнуляем счётчики
    buy_count = 0
    sell_count = 0
    print("Counters reset at 3:00 AM. Previous values saved to daily_reports.")

# Настройка планировщика
scheduler = BackgroundScheduler()

# Функция для запуска сброса счётчиков с использованием сессии базы данных
def scheduled_reset():
    db = SessionLocal()
    try:
        reset_counters(db)
    finally:
        db.close()

scheduler.add_job(
    scheduled_reset,
    trigger=CronTrigger(hour=3, minute=0),  # Запуск каждый день в 3:00
)
scheduler.start()

# Функция для отправки сообщения в Telegram
def send_telegram_message(text: str):
    url = f'https://api.telegram.org/bot{TOKEN}/sendMessage'
    payload = {
        "chat_id": CHAT_ID,
        "text": text,
        "parse_mode": "Markdown",
        "disable_web_page_preview": True
    }
    response = requests.post(url, json=payload)
    return response.json()

# Функция для форматирования числа или возврата значения по умолчанию
def format_number(value, default="N/A"):
    if isinstance(value, (int, float)):  # Проверяем, является ли значение числом
        if value == int(value):  # Если число целое
            return f"{int(value):,}"  # Форматируем без десятичных знаков
        else:
            return f"{value:,.2f}"  # Форматируем с двумя знаками после запятой
    return default  # Возвращаем значение по умолчанию, если это не число

# Функция для извлечения символа монеты из тикера (например, BTCUSDT → BTC)
def extract_symbol(ticker: str):
    # Удаляем только "USDT.P"
    if ticker.upper().endswith("USDT.P"):
        return ticker[:-6]  # Удаляем последние 6 символов
    return ticker  # Если формат не распознан, возвращаем исходный тикер

# Функция для получения данных о монете с использованием pycoingecko
def get_market_data(symbol: str):
    try:
        # Получаем список всех монет
        coins_list = cg.get_coins_list()
        print(f"Coins list fetched. Total coins: {len(coins_list)}")

        # Ищем монету по символу (например, btc)
        matching_coins = [coin for coin in coins_list if coin["symbol"].lower() == symbol.lower()]
        print(f"Matching coins for symbol {symbol}: {matching_coins}")

        if not matching_coins:
            print(f"No matching coins found for symbol: {symbol}")
            return 'N/A', 'N/A'

        # Выбираем первую монету из списка
        coin_id = matching_coins[0]["id"]
        print(f"Selected coin ID: {coin_id}")

        # Получаем данные о монете
        coin_data = cg.get_coin_by_id(coin_id)
        print(f"Coin data for {coin_id}: {coin_data}")

        # Извлекаем рыночную капитализацию и объем за 24 часа
        market_cap = coin_data.get('market_data', {}).get('market_cap', {}).get('usd', 'N/A')
        volume_24h = coin_data.get('market_data', {}).get('total_volume', {}).get('usd', 'N/A')

        # Убираем копейки (центы), оставляя только целую часть
        if isinstance(market_cap, (int, float)):
            market_cap = int(market_cap)  # Преобразуем в целое число
        if isinstance(volume_24h, (int, float)):
            volume_24h = int(volume_24h)  # Преобразуем в целое число

        print(f"Market Cap: {market_cap}, 24H Volume: {volume_24h}")
        return market_cap, volume_24h

    except Exception as e:
        print(f"Error in get_market_data: {e}")
        return 'N/A', 'N/A'

# Маршрут для обработки Webhook от TradingView
@app.post("/webhook")
async def webhook(request: Request, db: Session = Depends(get_db)):
    try:
        global buy_count, sell_count

        # Получаем данные от TradingView
        data = await request.json()
        print("Received data:", data)  # Логируем полученные данные

        # Извлекаем переменные из данных
        ticker = data.get('ticker', 'N/A')  # Пример: BTCUSDT.P, ETHUSDT.P и т.д.
        close = data.get('close', 'N/A')
        action = data.get('strategy.order.action', 'N/A')

        if action.lower() == 'buy':
            action_emoji = '🟢'
            buy_count += 1  # Увеличиваем счётчик buy
        elif action.lower() == 'sell':
            action_emoji = '🔴'
            sell_count += 1  # Увеличиваем счётчик sell
        else:
            action_emoji = '⚪'  # Если действие неизвестно, используем белый кружок

        # Извлекаем символ монеты из тикера (например, BTCUSDT.P → BTC)
        symbol = extract_symbol(ticker)
        print(f"Extracted symbol: {symbol}")

        # Получаем капитализацию и объем за 24 часа
        market_cap, volume_24h = get_market_data(symbol)

        # Формируем текст сообщения
        message = (
            f"{action_emoji} *{action.upper()}* \n\n"
            f"*{symbol.upper()}*\n\n"
            f"PRICE - *{close}$*\n"
            f"MARKET CAP - *{format_number(market_cap)}$*\n"
            f"24H VOLUME - *{format_number(volume_24h)}$*\n\n"
            f"Trading on the MEXC exchange - *https://promote.mexc.com/r/scn7giWq*"
        )

        print(f"Message to be sent: {message}")

        # Отправляем сообщение в Telegram
        send_telegram_message(message)

        # Записываем данные в базу данных
        trade = Trade(action=action.lower(), symbol=symbol, price=close)
        db.add(trade)
        db.commit()

        # Возвращаем успешный ответ
        return {"status": "success", "message": "Alert processed", "buy_count": buy_count, "sell_count": sell_count}

    except Exception as e:
        # Логируем ошибку
        print("Error:", str(e))
        raise HTTPException(status_code=500, detail=str(e))

# Запуск сервера
if __name__ == '__main__':
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=5000)