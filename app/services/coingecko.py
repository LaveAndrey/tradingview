from pycoingecko import CoinGeckoAPI
import logging
from typing import Tuple

logger = logging.getLogger(__name__)

class CoinGeckoService:
    def __init__(self):
        self.cg = CoinGeckoAPI()

    def get_market_data(self, symbol: str) -> Tuple[str, str]:
        """Получение рыночных данных из CoinGecko"""
        try:
            logger.info(f"Fetching data for {symbol.upper()}")

            coins_list = self.cg.get_coins_list()
            matching_coins = [c for c in coins_list if c["symbol"].lower() == symbol.lower()]

            if not matching_coins:
                logger.warning(f"No matches for symbol: {symbol}")
                return 'N/A', 'N/A'

            coin_id = matching_coins[0]["id"]
            coin_data = self.cg.get_coin_by_id(coin_id)
            market_data = coin_data.get('market_data', {})

            market_cap = market_data.get('market_cap', {}).get('usd', 'N/A')
            volume_24h = market_data.get('total_volume', {}).get('usd', 'N/A')

            if isinstance(market_cap, (int, float)):
                market_cap = int(market_cap)
            if isinstance(volume_24h, (int, float)):
                volume_24h = int(volume_24h)

            logger.info(f"Market data: {symbol.upper()} Cap=${market_cap:,} Vol=${volume_24h:,}")
            return market_cap, volume_24h

        except Exception as e:
            logger.error(f"Market data error: {str(e)}")
            return 'N/A', 'N/A'

    @staticmethod
    def extract_symbol(ticker: str) -> str:
        """Извлечение символа из тикера"""
        return ticker[:-6] if ticker.upper().endswith("USDT.P") else ticker

    @staticmethod
    def format_number(value, default="N/A") -> str:
        """Форматирование чисел с разделителями"""
        if isinstance(value, (int, float)):
            return f"{int(value):,}" if value == int(value) else f"{value:,.2f}"
        return default