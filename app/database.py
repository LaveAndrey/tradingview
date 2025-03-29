from sqlalchemy import create_engine
from sqlalchemy import Column, Integer, String, Numeric, Enum, DateTime
from sqlalchemy.orm import sessionmaker, DeclarativeBase
from app.config import Config
from datetime import datetime

# Для SQLite
engine = create_engine(
    Config.DATABASE_URL,
    connect_args={
        "check_same_thread": False,  # Для SQLite должно быть False
        "timeout": 30
    },
    pool_pre_ping=True,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

class Base(DeclarativeBase):
    pass

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

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()