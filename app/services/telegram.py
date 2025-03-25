import requests
from app.config import Config
import logging

logger = logging.getLogger(__name__)

class TelegramBot:
    @staticmethod
    def send_message(chat_id: str, text: str) -> dict:
        url = f'https://api.telegram.org/bot{Config.TOKEN}/sendMessage'
        payload = {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "Markdown",
            "disable_web_page_preview": True
        }
        try:
            response = requests.post(url, json=payload, timeout=10)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            logger.error(f"Telegram send error: {str(e)}")
            return {"status": "error", "message": str(e)}