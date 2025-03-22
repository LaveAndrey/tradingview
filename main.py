from fastapi import FastAPI, Request, HTTPException
from pycoingecko import CoinGeckoAPI
import requests

app = FastAPI()

# Токен вашего Telegram-бота
TOKEN = '7848154062:AAGRfSaAuxp2NBMWEf3Y3KjZW8ZGy29ijPY'
# ID вашего чата в Telegram
CHAT_ID = '-4618962576'

# Инициализация CoinGecko API
cg = CoinGeckoAPI()


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
        return f"{value:,.2f}"  # Форматируем число
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

        print(f"Market Cap: {market_cap}, 24H Volume: {volume_24h}")
        return market_cap, volume_24h

    except Exception as e:
        print(f"Error in get_market_data: {e}")
        return 'N/A', 'N/A'


# Маршрут для обработки Webhook от TradingView
@app.post("/webhook")
async def webhook(request: Request):
    try:
        # Получаем данные от TradingView
        data = await request.json()
        print("Received data:", data)  # Логируем полученные данные

        # Извлекаем переменные из данных
        ticker = data.get('ticker', 'N/A')  # Пример: BTCUSDT.P, ETHUSDT.P и т.д.
        close = data.get('close', 'N/A')
        volume = data.get('volume', 'N/A')
        action = data.get('strategy.order.action', 'N/A')

        # Извлекаем символ монеты из тикера (например, BTCUSDT.P → BTC)
        symbol = extract_symbol(ticker)
        print(f"Extracted symbol: {symbol}")

        # Получаем капитализацию и объем за 24 часа
        market_cap, volume_24h = get_market_data(symbol)

        # Формируем текст сообщения
        message = (
            f"Reddington VIP LIMIT ORDER *{action}*\n\n"
            f"*{symbol.upper()}*\n"
            f"PRICE - *{close} USDT*\n"
            f"VOLUME - *{volume}*\n"
            f"MARKET CAP - *{format_number(market_cap)}$*\n"
            f"24H VOLUME - *{format_number(volume_24h)}$*\n\n"
            f"Trading on the MEXC exchange - *https://promote.mexc.com/r/scn7giWq*"
        )

        print(f"Message to be sent: {message}")

        # Отправляем сообщение в Telegram
        send_telegram_message(message)

        # Возвращаем успешный ответ
        return {"status": "success", "message": "Alert processed"}

    except Exception as e:
        # Логируем ошибку
        print("Error:", str(e))
        raise HTTPException(status_code=500, detail=str(e))


# Запуск сервера
if __name__ == '__main__':
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=5000)