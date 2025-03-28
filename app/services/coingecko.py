from pycoingecko import CoinGeckoAPI
import logging
from typing import Dict, Union
from time import sleep

logger = logging.getLogger(__name__)


class CoinGeckoService:
    def __init__(self, retries: int = 3, delay: float = 1.0):
        self.cg = CoinGeckoAPI()
        self.retries = retries
        self.delay = delay  # Задержка между попытками

    def get_market_data(self, symbol: str) -> Dict[str, Union[int, float, str]]:
        """Получение рыночных данных из CoinGecko

        Возвращает словарь с ключами:
        - market_cap
        - volume_24h
        - symbol
        - error (при наличии ошибки)
        """
        result = {
            'market_cap': 'N/A',
            'volume_24h': 'N/A',
            'symbol': symbol.upper(),
            'error': None
        }

        for attempt in range(self.retries):
            try:
                logger.info(f"Fetching data for {symbol.upper()} (attempt {attempt + 1}/{self.retries})")

                # Получаем список монет с обработкой ошибок
                coins_list = self._safe_get_coins_list()
                if not coins_list:
                    continue

                # Находим совпадения
                matching_coins = [
                    c for c in coins_list
                    if c.get("symbol", "").lower() == symbol.lower()
                ]

                if not matching_coins:
                    logger.warning(f"No matches for symbol: {symbol}")
                    result['error'] = f"No matches for symbol: {symbol}"
                    return result

                # Получаем данные по монете
                coin_id = matching_coins[0]["id"]
                coin_data = self.cg.get_coin_by_id(coin_id)
                market_data = coin_data.get('market_data', {})

                # Извлекаем значения с защитой от ошибок
                result['market_cap'] = self._safe_get_value(market_data, 'market_cap')
                result['volume_24h'] = self._safe_get_value(market_data, 'total_volume')

                logger.info(
                    f"Successfully fetched data for {symbol.upper()}: "
                    f"Cap=${self.format_number(result['market_cap'])} "
                    f"Vol=${self.format_number(result['volume_24h'])}"
                )
                return result

            except Exception as e:
                error_msg = f"Attempt {attempt + 1} failed: {str(e)}"
                logger.error(error_msg)
                result['error'] = error_msg
                if attempt < self.retries - 1:
                    sleep(self.delay)

        return result

    def _safe_get_coins_list(self) -> list:
        """Безопасное получение списка монет"""
        try:
            coins_list = self.cg.get_coins_list()
            if not isinstance(coins_list, list):
                logger.warning("Invalid coins list format")
                return []
            return coins_list
        except Exception as e:
            logger.error(f"Error getting coins list: {str(e)}")
            return []

    def _safe_get_value(self, market_data: dict, key: str) -> Union[int, float, str]:
        """Безопасное извлечение числового значения"""
        try:
            value = market_data.get(key, {}).get('usd')
            if isinstance(value, (int, float)):
                return int(value) if value == int(value) else round(value, 2)
            return 'N/A'
        except Exception as e:
            logger.warning(f"Error extracting {key}: {str(e)}")
            return 'N/A'

    @staticmethod
    def extract_symbol(ticker: str) -> str:
        """Извлечение символа из тикера"""
        if not isinstance(ticker, str):
            logger.warning(f"Invalid ticker type: {type(ticker)}")
            return ''

        ticker = ticker.upper()
        for suffix in ["USDT.P", "USDT"]:
            if ticker.endswith(suffix):
                return ticker[:-len(suffix)]
        return ticker

    @staticmethod
    def format_number(value: Union[int, float, str], default: str = "N/A") -> str:
        """Форматирование чисел с разделителями"""
        if isinstance(value, (int, float)):
            return f"{int(value):,}" if value == int(value) else f"{value:,.2f}"
        return default