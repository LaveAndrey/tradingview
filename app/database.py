from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.declarative import declarative_base
from app.config import Config

engine = create_engine(Config.DATABASE_URL)

SessionLocal = sessionmaker(bind=engine)

Base = declarative_base()
def create_db():
    Base.metadata.create_all(bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()