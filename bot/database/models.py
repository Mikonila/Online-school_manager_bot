from sqlalchemy import Column, Integer, String, Text, DateTime
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import declarative_base
from datetime import datetime
import os

Base = declarative_base()

class Message(Base):
    __tablename__ = "messages"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer)
    age = Column(String)
    experience = Column(String)
    question = Column(Text)
    answer = Column(Text)
    timestamp = Column(DateTime, default=datetime.utcnow)

# Подключение к БД
DB_URL = os.getenv("DB_URL")

engine = create_async_engine(DB_URL, echo=False)
async_session = async_sessionmaker(engine, expire_on_commit=False)

async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

async def log_interaction(user_id, age, experience, question, answer):
    async with async_session() as session:
        msg = Message(
            user_id=user_id,
            age=age,
            experience=experience,
            question=question,
            answer=answer
        )
        session.add(msg)
        await session.commit()
