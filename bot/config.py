import os
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv()

@dataclass
class Config:
    BOT_TOKEN: str
    OPENAI_API_KEY: str
    ADMINS: list
    MAIN_SHEET_ID: str
    COURSES_SHEET_ID: str
    TARIFFS_SHEET_ID: str
    CREDENTIALS_PATH: str

def load_config() -> Config:
    return Config(
        BOT_TOKEN=os.getenv("BOT_TOKEN", ""),
        OPENAI_API_KEY=os.getenv("OPENAI_API_KEY", ""),
        ADMINS=os.getenv("ADMINS", "").split(",") if os.getenv("ADMINS") else [],
        MAIN_SHEET_ID=os.getenv("MAIN_SHEET_ID", "1RHWlD3afHMUh7QWORNZJ_g2e03vMHtF0rSuYRNl4uJU"),
        COURSES_SHEET_ID=os.getenv("COURSES_SHEET_ID", "1XN9SxS2PkYK7NVE2ma66eeitQlv6VEwtCaO92ji8Sow"),
        TARIFFS_SHEET_ID=os.getenv("TARIFFS_SHEET_ID", "1AunTrKemY3Zrtvc0AzkRnLrjsEm86I8UqcVJBBY6kq4"),
        CREDENTIALS_PATH=os.getenv("CREDENTIALS_PATH", "bot/services/credentials.json")
    )
