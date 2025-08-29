from openai import AsyncOpenAI
from bot.config import load_config
from pathlib import Path
import logging
from typing import Optional

logger = logging.getLogger(__name__)

# Загружаем конфигурацию
config = load_config()
client = AsyncOpenAI(api_key=config.OPENAI_API_KEY)

MAX_HISTORY_LINES = 6  # Оставляем последние 3 вопроса и 3 ответа

def split_history(history: str):
    """Разделяет историю на строки-реплики."""
    return [line for line in history.strip().split('\n') if line.strip()]

async def build_short_history(history: str) -> str:
    lines = split_history(history)
    if len(lines) <= MAX_HISTORY_LINES:
        return '\n'.join(lines)
    # Суммаризируем старую часть истории
    summary = await generate_summary('\n'.join(lines[:-MAX_HISTORY_LINES]))
    short_history = summary + '\n' + '\n'.join(lines[-MAX_HISTORY_LINES:])
    return short_history

async def ask_gpt(
    question: str,
    knowledge: str = "",
    agent_prompt_file: str = "default_prompt.txt",
    history: str = "",
    user_data: str = ""
) -> str:
    """
    Отправляет запрос в GPT с учетом базы знаний, истории и данных пользователя.

    Аргументы:
        question (str): Вопрос пользователя.
        knowledge (str): Контекст из базы знаний.
        agent_prompt_file (str): Название system-промпта (файл в /bot/prompts).
        history (str): Переписка ранее.
        user_data (str): Инфо о пользователе (например, возраст и роль).

    Возвращает:
        str: Ответ от GPT.
    """

    # Загружаем system-промпт
    prompt_path = Path("bot/prompts") / agent_prompt_file
    if not prompt_path.exists():
        raise FileNotFoundError(f"System prompt не найден: {agent_prompt_file}")

    with open(prompt_path, "r", encoding="utf-8") as f:
        system_prompt = f.read()

    # Сжимаем историю
    short_history = await build_short_history(history)
    if short_history is None:
        short_history = ''

    # Формируем user-промпт
    user_prompt = f"""
Контекст (база знаний):
{knowledge.strip()}

Информация о пользователе:
{user_data.strip()}

История переписки (кратко):
{short_history.strip()}

Вопрос:
{question.strip()}
""".strip()

    logger.info("===== USER PROMPT =====\n%s", user_prompt)

    try:
        response = await client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            temperature=0.3,
            max_tokens=700,
        )
        return response.choices[0].message.content.strip()

    except Exception as e:
        logger.error("Ошибка при обращении к GPT: %s", str(e))
        return "Произошла ошибка при обращении к языковой модели. Попробуйте позже."

async def generate_summary(history: Optional[str]) -> str:
    """
    Генерирует краткое резюме переписки пользователя с помощью GPT.
    """
    summary_prompt_path = Path("bot/prompts/summary_prompt.txt")
    if summary_prompt_path.exists():
        with open(summary_prompt_path, "r", encoding="utf-8") as f:
            system_prompt = f.read()
    else:
        system_prompt = (
            "Ты — ассистент, который составляет краткое, информативное и полезное резюме переписки пользователя с ботом. "
            "Выдели ключевые вопросы, интересы, возраст, опыт, цели и любые важные детали. Не пиши лишнего, только суть."
        )
    history_str = history.strip() if isinstance(history, str) else ""
    user_prompt = f"История переписки:\n{history_str}\n\nСделай краткое резюме для менеджера."
    try:
        response = await client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            temperature=0.2,
            max_tokens=300,
        )
        content = response.choices[0].message.content
        return content.strip() if content else ""
    except Exception as e:
        logger.error("Ошибка при генерации резюме: %s", str(e))
        return "(Не удалось сгенерировать резюме)"
