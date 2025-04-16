from openai import AsyncOpenAI
from bot.config import load_config
from pathlib import Path
import logging

logger = logging.getLogger(__name__)

# Загружаем конфигурацию
config = load_config()
client = AsyncOpenAI(api_key=config.OPENAI_API_KEY)


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

    # Формируем user-промпт
    user_prompt = f"""
Контекст (база знаний):
{knowledge.strip()}

Информация о пользователе:
{user_data.strip()}

История переписки:
{history.strip()}

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
