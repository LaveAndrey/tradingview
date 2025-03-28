from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from app.config import Config

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

# Единый базовый класс для всех моделей
Base = declarative_base()

def get_db():
    """Генератор сессий для Dependency Injection"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()