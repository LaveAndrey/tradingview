from pycoingecko import CoinGeckoAPI
import logging
from typing import Tuple, Optional, Dict
from time import sleep
import asyncio
from functools import lru_cache

logger = logging.getLogger(__name__)

class CoinGeckoService:
    def __init__(self, retries: int = 3, delay: float = 1.0):
        self.cg = CoinGeckoAPI()
        self.retries = retries
        self.delay = delay
        self._coin_cache = {}  # Кэш для хранения данных о монетах

    async def _get_all_coins(self) -> Dict:
        """Получает и кэширует список всех монет с их ID"""
        if not self._coin_cache:
            try:
                coins = self.cg.get_coins_list()
                self._coin_cache = {coin['symbol']: coin for coin in coins}
                logger.info("Кэш монет успешно обновлен")
            except Exception as e:
                logger.error(f"Ошибка получения списка монет: {e}")
                raise
        return self._coin_cache

    async def get_market_data(self, symbol: str) -> Tuple[Optional[float], Optional[float]]:
        """Получает рыночные данные с кэшированием"""
        try:
            coins = await self._get_all_coins()
            coin_data = coins.get(symbol.lower())
            if not coin_data:
                logger.warning(f"Монета {symbol} не найдена")
                return None, None

            for attempt in range(self.retries):
                try:
                    data = self.cg.get_coin_by_id(coin_data['id'])
                    market_data = data.get('market_data', {})
                    market_cap = market_data.get('market_cap', {}).get('usd')
                    volume = market_data.get('total_volume', {}).get('usd')
                    return market_cap, volume
                except Exception as e:
                    logger.error(f"Попытка {attempt + 1} не удалась: {e}")
                    if attempt < self.retries - 1:
                        await asyncio.sleep(self.delay)

            return None, None
        except Exception as e:
            logger.error(f"Ошибка в get_market_data: {e}")
            return None, None


    @staticmethod
    def extract_symbol(ticker: str) -> str:
        """Извлекает чистый символ из тикера"""
        ticker = ticker.upper()
        for suffix in ["USDT.P", "USDT", "PERP", "USD.P"]:
            if ticker.endswith(suffix):
                return ticker[:-len(suffix)]
        return ticker

    @staticmethod
    def format_number(value: Optional[float]) -> str:
        """Форматирует числа с разделителями"""
        if value is None:
            return "N/A"
        return f"{value:,.2f}" if isinstance(value, float) else f"{int(value):,}"