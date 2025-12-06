from openai import AsyncOpenAI
from bot.config import load_config
from pathlib import Path
import logging
from typing import Optional
import re

logger = logging.getLogger(__name__)

# Загружаем конфигурацию
config = load_config()
client = AsyncOpenAI(api_key=config.OPENAI_API_KEY)

MAX_HISTORY_LINES = 6  # Оставляем последние 3 вопроса и 3 ответа

def split_history(history: str):
    """Разделяет историю на строки-реплики."""
    return [line for line in history.strip().split('\n') if line.strip()]

def fix_course_recommendations(response: str, question: str = "") -> str:
    """
    ЖЕСТКО исправляет рекомендации курсов в ответе GPT по возрасту и опыту
    """
    logger.info("=== НАЧИНАЕМ ЖЕСТКОЕ ИСПРАВЛЕНИЕ ===")
    logger.info(f"Оригинальный ответ: {response[:200]}...")
    
    # ПАРСИМ ВОПРОС ПОЛЬЗОВАТЕЛЯ
    age = None
    experience = None
    
    # Ищем возраст
    age_match = re.search(r'(\d+)\s*лет', question)
    if age_match:
        age = int(age_match.group(1))
        logger.info(f"Возраст: {age} лет")
    
    # Ищем опыт
    if "учил" in question.lower() or "изучал" in question.lower() or "проходил" in question.lower():
        experience = "есть опыт"
        logger.info("Опыт: есть")
    else:
        experience = "без опыта"
        logger.info("Опыт: нет")
    
    logger.info(f"Возраст: {age}, Опыт: {experience}")
    
    # ЖЕСТКАЯ ЗАМЕНА ВЫДУМАННЫХ КУРСОВ
    fake_replacements = {
        r"Minecraft.*?создание игр на Lua.*?": "Minecraft",
        r"Minecraft.*?разработка игр на блоках.*?": "Minecraft", 
        r"Minecraft Level 1.*?": "Minecraft",
        r"Minecraft Junior.*?": "Minecraft",
        r"Scratch игры.*?": "Scratch Level 1",
        r"Roblox.*?создание игр на Lua.*?": "Roblox Studio",
        r"Unity.*?разработка игр на блоках.*?": "Unity Level 1",
        r"Python.*?путешествие по.*?странам.*?": "Python Level 1",
        r"Python.*?географию.*?английский.*?": "Python Level 1"
    }
    
    fixed_response = response
    for pattern, replacement in fake_replacements.items():
        if re.search(pattern, fixed_response, re.IGNORECASE):
            fixed_response = re.sub(pattern, replacement, fixed_response, flags=re.IGNORECASE)
            logger.warning(f"ЗАМЕНЕНО: {pattern} → {replacement}")
    
    # ГОТОВЫЕ ШАБЛОНЫ ПО ВОЗРАСТУ И ОПЫТУ
    if age and experience and "scratch" in experience.lower():
        if age <= 7:
            logger.warning(f"{age} ЛЕТ + SCRATCH - ГОТОВЫЙ ШАБЛОН!")
            fixed_response = f"""Отлично, что ваш ребенок уже знаком с Scratch! 

Если вы хотите продолжить изучение Scratch, то рекомендую курс Scratch Level 2. Здесь ребенок создаст более сложные проекты, такие как квесты и головоломки, изучит программирование с переменными, циклами и условиями.

Если же хочется попробовать что-то новое, то отлично подойдет Scratch Junior! Это оптимальный вариант для {age} лет, который развивает логику и креативность через создание простых игр.

Также могу предложить: Paint, 3D моделирование. У нас более 25 курсов на выбор!

Какой из этих вариантов больше заинтересует вашего ребенка? Могу прислать ссылки на программы курсов и демо-уроки!"""
            return fixed_response
            
        elif age <= 10:
            logger.warning(f"{age} ЛЕТ + SCRATCH - ГОТОВЫЙ ШАБЛОН!")
            fixed_response = f"""Отлично, что ваш ребенок уже знаком с Scratch! 

Если вы хотите продолжить изучение Scratch, то рекомендую курс Scratch Level 2. Здесь ребенок создаст более сложные проекты, такие как квесты и головоломки, изучит программирование с переменными, циклами и условиями.

Если же хочется попробовать что-то новое, то отлично подойдет Minecraft! Это оптимальный вариант для {age} лет, который развивает логику и креативность в 3D-среде.

Также могу предложить: Paint, 3D моделирование. У нас более 25 курсов на выбор!

Какой из этих вариантов больше заинтересует вашего ребенка? Могу прислать ссылки на программы курсов и демо-уроки!

Если эта подборка не устраивает, я могу сделать новую - у нас более 25 курсов на разный возраст и опыт!"""
            return fixed_response
            
        elif age <= 12:
            logger.warning(f"{age} ЛЕТ + SCRATCH - ГОТОВЫЙ ШАБЛОН!")
            fixed_response = f"""Отлично, что ваш ребенок уже знаком с Scratch! 

Если вы хотите продолжить изучение Scratch, то рекомендую курс Scratch Level 2. Здесь ребенок создаст более сложные проекты, такие как квесты и головоломки, изучит программирование с переменными, циклами и условиями.

Если же хочется попробовать что-то новое, то отлично подойдет Roblox Studio! Это оптимальный вариант для {age} лет, который развивает логику и креативность через создание игр на Lua.

Также могу предложить: Paint, 3D моделирование. У нас более 25 курсов на выбор!

Какой из этих вариантов больше заинтересует вашего ребенка? Могу прислать ссылки на программы курсов и демо-уроки!

Если эта подборка не устраивает, я могу сделать новую - у нас более 25 курсов на разный возраст и опыт!"""
            return fixed_response
            
        elif age > 12:
            logger.warning(f"{age} ЛЕТ + SCRATCH - ГОТОВЫЙ ШАБЛОН!")
            fixed_response = f"""Отлично, что ваш ребенок уже знаком с Scratch! 

Если вы хотите продолжить изучение Scratch, то рекомендую курс Scratch Level 2. Здесь ребенок создаст более сложные проекты, такие как квесты и головоломки, изучит программирование с переменными, циклами и условиями.

Если же хочется попробовать что-то новое, то отлично подойдет Unity Level 1! Это оптимальный вариант для {age} лет, который развивает логику и креативность через разработку игр на блоках.

Также могу предложить: Paint, 3D моделирование. У нас более 25 курсов на выбор!

Какой из этих вариантов больше заинтересует вашего ребенка? Могу прислать ссылки на программы курсов и демо-уроки!

Если эта подборка не устраивает, я могу сделать новую - у нас более 25 курсов на разный возраст и опыт!"""
            return fixed_response
    
    # Убираем Python для маленьких детей
    if "Python" in fixed_response:
        if age and age <= 7:
            replacement = "Scratch Junior"
        elif age and age <= 9:
            replacement = "Minecraft"
        elif age and age <= 11:
            replacement = "Minecraft"
        elif age and age <= 13:
            replacement = "Roblox Studio"
        else:
            replacement = "Unity Level 1"
        
        fixed_response = fixed_response.replace("Python Level 1", replacement)
        fixed_response = fixed_response.replace("Python Level 2", replacement)
        logger.warning(f"Python ЗАМЕНЕН на {replacement}")
    
    # Убираем сложные курсы для маленьких
    if age and age <= 8:
        fixed_response = fixed_response.replace("Roblox", "Minecraft")
        fixed_response = fixed_response.replace("Unity", "Minecraft")
        fixed_response = fixed_response.replace("Pygame", "Minecraft")
        logger.warning("Сложные курсы заменены на Minecraft для 8 лет")
    
    # Убираем Arduino для детей младше 10 лет
    if age and age < 10:
        fixed_response = fixed_response.replace("Arduino", "Minecraft")
        logger.warning("Arduino заменен на Minecraft для детей младше 10 лет")
    
    # Убираем Web-разработку для детей младше 12 лет
    if age and age < 12:
        fixed_response = fixed_response.replace("Web-разработка", "Minecraft")
        logger.warning("Web-разработка заменена на Minecraft для детей младше 12 лет")
    
    # Убираем Unity Level 1 для детей младше 12 лет
    if age and age < 12:
        fixed_response = fixed_response.replace("Unity Level 1", "Minecraft")
        logger.warning("Unity Level 1 заменен на Minecraft для детей младше 12 лет")
    
    # Убираем Pygame для детей младше 11 лет
    if age and age < 11:
        fixed_response = fixed_response.replace("Pygame", "Minecraft")
        logger.warning("Pygame заменен на Minecraft для детей младше 11 лет")
    
    # Убираем Scratch Level 1 для детей 9+ лет (он для 7-8 лет)
    if age and age >= 9:
        fixed_response = fixed_response.replace("Scratch Level 1", "Scratch Level 2")
        logger.warning("Scratch Level 1 заменен на Scratch Level 2 для детей 9+ лет")
    
    # Убираем второстепенные курсы, заменяем на основные
    if "Colobot" in fixed_response:
        fixed_response = fixed_response.replace("Colobot", "Minecraft")
        logger.warning("Colobot (второстепенный курс) заменен на Minecraft")
    
    if "Paint" in fixed_response and age and age >= 10:
        fixed_response = fixed_response.replace("Paint", "Roblox Studio")
        logger.warning("Paint заменен на Roblox Studio для детей 10+ лет")
    
    if "GIMP" in fixed_response:
        fixed_response = fixed_response.replace("GIMP", "Minecraft")
        logger.warning("GIMP (второстепенный курс) заменен на Minecraft")
    
    if "Photoshop" in fixed_response:
        fixed_response = fixed_response.replace("Photoshop", "Minecraft")
        logger.warning("Photoshop (второстепенный курс) заменен на Minecraft")
    
    # Убираем дублирование
    if fixed_response.count("Minecraft") > 1:
        fixed_response = re.sub(r"Minecraft.*?Minecraft", "Minecraft", fixed_response)
        logger.warning("Убрано дублирование Minecraft")
    
    if fixed_response.count("Roblox") > 1:
        fixed_response = re.sub(r"Roblox.*?Roblox", "Roblox", fixed_response)
        logger.warning("Убрано дублирование Roblox")
    
    # Убираем дублирование Scratch Level 2
    if fixed_response.count("Scratch Level 2") > 1:
        # Оставляем только первое упоминание, остальные заменяем на Paint
        first_occurrence = fixed_response.find("Scratch Level 2")
        if first_occurrence != -1:
            # Заменяем все последующие упоминания на Paint
            before_first = fixed_response[:first_occurrence]
            after_first = fixed_response[first_occurrence + len("Scratch Level 2"):]
            after_first = after_first.replace("Scratch Level 2", "Paint")
            fixed_response = before_first + "Scratch Level 2" + after_first
            logger.warning("Убрано дублирование Scratch Level 2")
    
    # НЕ добавляем дополнительные курсы автоматически
    # Пользователь должен сам спросить про конкретные курсы
    logger.info("Дополнительные курсы не добавляются автоматически - только по запросу пользователя")
    
    logger.info(f"ИСПРАВЛЕННЫЙ ОТВЕТ: {fixed_response[:200]}...")
    return fixed_response

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
    logger.info(f"Загружаем промт из: {prompt_path.absolute()}")
    
    if not prompt_path.exists():
        raise FileNotFoundError(f"System prompt не найден: {agent_prompt_file}")

    with open(prompt_path, "r", encoding="utf-8") as f:
        system_prompt = f.read()
    
    logger.info(f"Промт загружен, размер: {len(system_prompt)} символов")
    logger.info(f"Первые 200 символов промта: {system_prompt[:200]}...")

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
        
        gpt_response = response.choices[0].message.content.strip()
        
        # Применяем исправления для курсов
        if agent_prompt_file == "generator.md":
            logger.info("Применяем исправления для generator.md")
            logger.info(f"Оригинальный ответ GPT: {gpt_response[:200]}...")
            original_response = gpt_response
            gpt_response = fix_course_recommendations(gpt_response, question)
            if original_response != gpt_response:
                logger.info("Ответ был исправлен!")
                logger.info(f"Исправленный ответ: {gpt_response[:200]}...")
            else:
                logger.info("Ответ не требовал исправлений")
        else:
            logger.info(f"Промт {agent_prompt_file} - исправления не применяются")
        
        return gpt_response

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
