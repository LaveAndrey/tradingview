from pycoingecko import CoinGeckoAPI
import logging
from typing import Tuple, Optional
from time import sleep

logger = logging.getLogger(__name__)


class CoinGeckoService:
    def __init__(self, retries: int = 3, delay: float = 1.0):
        self.cg = CoinGeckoAPI()
        self.retries = retries
        self.delay = delay  # Задержка между попытками

    def get_market_data(self, symbol: str) -> Tuple[Optional[float], Optional[float]]:
        """Получение рыночных данных из CoinGecko

        Возвращает кортеж: (market_cap, volume_24h)
        """
        market_cap, volume_24h = None, None

        for attempt in range(self.retries):
            try:
                logger.info(f"Fetching data for {symbol.lower()} (attempt {attempt + 1}/{self.retries})")

                coins_list = self._safe_get_coins_list()
                if not coins_list:
                    continue

                matching_coins = [
                    c for c in coins_list
                    if c.get("symbol", "").lower() == symbol.lower()
                ]

                if not matching_coins:
                    logger.warning(f"No matches for symbol: {symbol}")
                    return None, None

                coin_id = matching_coins[0]["id"]
                coin_data = self.cg.get_coin_by_id(coin_id)
                market_data = coin_data.get('market_data', {})

                # Исправлено: извлекаем конкретные значения
                market_cap = self._safe_get_numeric_value(market_data, 'market_cap')
                volume_24h = self._safe_get_numeric_value(market_data, 'total_volume')

                logger.info(
                    f"Successfully fetched data for {symbol.lower()}: "
                    f"Cap=${self.format_number(market_cap)} "
                    f"Vol=${self.format_number(volume_24h)}"
                )
                return market_cap, volume_24h  # Теперь возвращаем только числа

            except Exception as e:
                logger.error(f"Attempt {attempt + 1} failed: {str(e)}")
                if attempt < self.retries - 1:
                    sleep(self.delay)

        return None, None

    def _safe_get_coins_list(self) -> list:
        """Безопасное получение списка монет"""
        try:
            return self.cg.get_coins_list() or []
        except Exception as e:
            logger.error(f"Error getting coins list: {str(e)}")
            return []

    def _safe_get_numeric_value(self, market_data: dict, key: str) -> Optional[float]:
        """Безопасное извлечение числового значения"""
        try:
            value = market_data.get(key, {}).get('usd')
            return float(value) if value is not None else None
        except Exception as e:
            logger.warning(f"Error extracting {key}: {str(e)}")
            return None

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
    def format_number(value: Optional[float], default: str = "N/A") -> str:
        """Форматирование чисел с разделителями"""
        if value is None:
            return default
        return f"{int(value):,}" if value == int(value) else f"{value:,.2f}"