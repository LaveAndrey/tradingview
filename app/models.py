from sqlalchemy import Column, Integer, String, Numeric, Enum, DateTime, Index
from app.database import Base
from datetime import datetime


class Trade(Base):
    __tablename__ = "trades"
    __table_args__ = {'extend_existing': True}

    id = Column(Integer, primary_key=True)
    action = Column(Enum('buy', 'sell', name='action_type'))
    symbol = Column(String(20), nullable=False, index=True)
    price = Column(Numeric(10, 2))  # Вместо String(20)
    timestamp = Column(DateTime, default=datetime.utcnow, index=True)

class DailyReport(Base):
    __tablename__ = "daily_reports"
    __table_args__ = {'extend_existing': True}

    id = Column(Integer, primary_key=True, index=True)
    date = Column(DateTime, default=datetime.utcnow)
    buy_count = Column(Integer, default=0)
    sell_count = Column(Integer, default=0)

class Counter(Base):
    __tablename__ = "counters"
    __table_args__ = {'extend_existing': True}

    id = Column(Integer, primary_key=True)
    buy_count = Column(Integer, default=0)
    sell_count = Column(Integer, default=0)



