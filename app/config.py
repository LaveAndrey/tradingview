from dotenv import load_dotenv
import os

load_dotenv()

class Config:
    TOKEN = os.getenv('TOKENTELEGRAM')
    CHAT_ID_TRADES = os.getenv('CHAT_IDTELEGRAM')
    CHAT_ID_REPORTS = os.getenv('CHAT_ID_REPORTS')
    DATABASE_URL = os.getenv('DATABASE_URLMYSQL')
    ID_TABLES = os.getenv('ID_TABLES')
    COINMARKETCAP_API_KEY = os.getenv('COINMARKETCAP_API_KEY')
