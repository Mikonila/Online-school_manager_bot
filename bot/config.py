import os
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv()

@dataclass
class Config:
    BOT_TOKEN: str
    OPENAI_API_KEY: str
    ADMINS: list

def load_config() -> Config:
    return Config(
        BOT_TOKEN=os.getenv("BOT_TOKEN"),
        OPENAI_API_KEY=os.getenv("OPENAI_API_KEY"),
        ADMINS=os.getenv("ADMINS", "").split(","),
    )
