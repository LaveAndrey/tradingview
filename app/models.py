from sqlalchemy import Column, Integer, String, DateTime
from sqlalchemy.orm import DeclarativeBase
from datetime import datetime

class Base(DeclarativeBase):
    pass

class Trade(Base):
    __tablename__ = "trades"
    id = Column(Integer, primary_key=True)
    signal_id = Column(String(50), unique=True, index=True)  # Для поиска дубликатов
    action = Column(String(10), nullable=False)
    symbol = Column(String(20), nullable=False, index=True)
    price = Column(String(20), nullable=False)
    timestamp = Column(DateTime, default=datetime.utcnow, index=True)

class DailyReport(Base):
    __tablename__ = "daily_reports"
    id = Column(Integer, primary_key=True, index=True)
    date = Column(DateTime, default=datetime.utcnow)
    buy_count = Column(Integer, default=0)
    sell_count = Column(Integer, default=0)

class Counter(Base):
    __tablename__ = "counters"
    id = Column(Integer, primary_key=True)
    buy_count = Column(Integer, default=0)
    sell_count = Column(Integer, default=0)

