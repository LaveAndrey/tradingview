# models.py
from sqlalchemy import create_engine, Column, Integer, String, DateTime, func
from sqlalchemy.orm import sessionmaker, DeclarativeBase
from datetime import datetime
from dotenv import load_dotenv
import os

load_dotenv()

# Настройка базы данных (SQLite для примера)
DATABASE_URL = os.getenv('DATABASE_URLMYSQL')  # Используйте PostgreSQL или MySQL для продакшена
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})

# Создание сессии
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Базовый класс для моделей
class Base(DeclarativeBase):
    pass

# Модель для хранения данных о срабатываниях
class Trade(Base):
    __tablename__ = "trades"
    id = Column(Integer, primary_key=True, index=True)
    action = Column(String, nullable=False)  # "buy" или "sell"
    symbol = Column(String, nullable=False)  # Символ монеты (например, BTC)
    price = Column(String, nullable=False)  # Цена
    timestamp = Column(DateTime, default=datetime.utcnow)  # Время срабатывания

# Модель для хранения ежедневных отчётов
class DailyReport(Base):
    __tablename__ = "daily_reports"
    id = Column(Integer, primary_key=True, index=True)
    date = Column(DateTime, default=datetime.utcnow)  # Дата отчёта
    buy_count = Column(Integer, default=0)  # Количество buy за день
    sell_count = Column(Integer, default=0)  # Количество sell за день

# Создание таблиц в базе данных
Base.metadata.create_all(bind=engine)

# Функция для получения сессии базы данных
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()