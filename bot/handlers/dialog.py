from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.filters import StateFilter, Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
import logging
import re
import json
import html
import datetime
from bot.services.gpt_engine import ask_gpt, generate_summary
from bot.services.search_engine import search_knowledge
from bot.handlers.agents import generator
from bot.services.sheets import update_user_row
from aiogram.types import InputFile
import asyncio
from typing import Dict
# Импорты для словаря курсов убраны - возвращаем к работе через GPT
# from bot.constants import find_course_by_name, get_course_tariffs


router = Router()
router.include_router(generator.router)

# --- ВРЕМЕННЫЙ ОБРАБОТЧИК ДЛЯ ВЫЯВЛЕНИЯ CHAT ID ---
@router.message(Command("chatid"))
async def print_chat_id(message: Message):
    chat_id = message.chat.id
    await message.answer(f"Chat ID этого чата: {chat_id}")
    print(f"[DEBUG] Chat ID: {chat_id}")
    return  # Не даём другим обработчикам срабатывать на эту команду
# --- КОНЕЦ ВРЕМЕННОГО ОБРАБОТЧИКА ---

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

APPLICATION_CHAT_ID = -1002290856432

last_user_messages: Dict[int, float] = {}


# Удалить определение course_links_dict и все обращения к нему (например, поиск по названию курса, использование demo-ссылок из словаря и т.д.)


class UserDialog(StatesGroup):
    waiting_for_intro = State()
    waiting_for_question = State()
    waiting_for_demo_confirmation = State()

start_keyboard = InlineKeyboardMarkup(inline_keyboard=[
    [InlineKeyboardButton(text="Подобрать курс", callback_data="start_pick")],
    [InlineKeyboardButton(text="Посмотреть демо", callback_data="start_demo")],
    [InlineKeyboardButton(text="Узнать цены", callback_data="start_price")],
    [InlineKeyboardButton(text="Интересуюсь покупкой методик", callback_data="start_methods")]  # 🔥 Новая кнопка
])

def escape_markdown(text: str) -> str:
    """
    Экранирует спецсимволы Markdown V2.
    """
    if not text:
        return "-"
    escape_chars = r"_*[]()~`>#+-=|{}.!"
    return ''.join(f"\\{char}" if char in escape_chars else char for char in text)

def clean_markdown(text: str) -> str:
    """
    Убирает markdown форматирование из текста.
    """
    if not text:
        return ""
    
    # Убираем **жирный текст**
    text = re.sub(r'\*\*(.*?)\*\*', r'\1', text)
    
    # Убираем *курсив*
    text = re.sub(r'\*(.*?)\*', r'\1', text)
    
    # Убираем `код`
    text = re.sub(r'`(.*?)`', r'\1', text)
    
    # Убираем ~~зачёркнутый~~
    text = re.sub(r'~~(.*?)~~', r'\1', text)
    
    # Убираем [ссылка](url) - оставляем только текст ссылки
    text = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', text)
    
    return text

# Словарь для отслеживания отправленных follow-up сообщений
followup_sent_users: Dict[int, bool] = {}

import asyncio
import datetime

async def schedule_followup(message: Message, state: FSMContext, delay_minutes=60):
    await asyncio.sleep(delay_minutes * 60)

    data = await state.get_data()
    last_time = data.get("last_interaction")
    followup_sent = data.get("followup_sent", False)

    # Проверим, прошло ли уже 60 минут и не отправляли ли мы уже сообщение
    if not followup_sent and last_time:
        elapsed = datetime.datetime.now().timestamp() - last_time
        if elapsed >= delay_minutes * 60:
            await message.answer("Я могу вам ещё чем-то помочь или позвать менеджера? 😊")
            await state.update_data(followup_sent=True)

# --- Команда для отправки сообщений пользователям от лица бота (только для админа) ---
ADMIN_IDS = [909112901, 1339362869]  # Список Telegram user_id, которым разрешено отправлять сообщения от лица бота

@router.message(Command("sendto"))
async def send_to_user(message: Message):
    if message.from_user.id not in ADMIN_IDS:
        await message.answer("Нет доступа.")
        return
    try:
        parts = message.text.split(maxsplit=2)
        if len(parts) < 3:
            await message.answer("Используйте: /sendto <user_id> <текст>")
            return
        user_id = int(parts[1])
        text = parts[2]
        try:
            await message.bot.send_message(user_id, text)
            await message.answer(f"Сообщение отправлено пользователю {user_id}.")
        except Exception as send_err:
            import traceback
            tb = traceback.format_exc()
            await message.answer(f"Ошибка при отправке пользователю {user_id}: {send_err}\n{tb}")
    except Exception as e:
        await message.answer(f"Ошибка: {e}")

@router.message(F.text.in_(["/start", "старт", "Старт", "Start", "start"]))
async def cmd_start(message: Message, state: FSMContext):
    await message.answer(
        "👋 Здравствуйте, спасибо за интерес к школе программирования Codim.online! Я виртуальный помощник и помогу вам с выбором оптимального курса, расскажу о форматах обучения и тарифах.\n\n"
        "Выберите вариант:",
        reply_markup=start_keyboard
    )
    await state.set_state(UserDialog.waiting_for_intro)

@router.message(StateFilter(UserDialog.waiting_for_intro))
async def handle_intro_text(message: Message, state: FSMContext):
    # Проверяем, что сообщение не пустое
    if not message.text or not message.text.strip():
        await message.answer("Пожалуйста, напишите ваш вопрос или выберите кнопку из меню.")
        return
    
    text = message.text.strip().lower()

    # Убираем скрипт с шаблонными ответами - возвращаем к работе через GPT
    print(f"[DEBUG] handle_intro_text получил сообщение: '{message.text}' - отправляем в GPT")

    if text in ["1", "подобрать курс", "подобрать"]:
        await handle_pick_callback_text(message, state)
    elif text in ["2", "посмотреть демо", "демо", "демо-уроки"]:
        await handle_demo_callback_text(message, state)
    elif text in ["3", "узнать цены", "цены", "стоимость", "форматы", "тарифы"]:
        await handle_price_callback_text(message, state)
    else:
        data = await state.get_data()
        history = data.get("history", "")
        history += f"\nПользователь: {message.text}"

        # Получаем контекст из базы знаний
        knowledge = await search_knowledge(message.text)

        # Получаем ответ от GPT
        gpt_response = await ask_gpt(
            question=message.text,
            knowledge=knowledge,
            history=history,
            agent_prompt_file="generator.md"
        )

        # Используем ответ как есть, сохраняя markdown-форматирование
        history += f"\nБот: {gpt_response}"
        await state.update_data(history=history)

        await message.answer(gpt_response, parse_mode="Markdown")

        # Можно перевести в состояние ожидания доп.вопросов
        await state.set_state(UserDialog.waiting_for_question)

# Функции для обработки текстовых команд
async def handle_pick_callback_text(message: Message, state: FSMContext):
    data = await state.get_data()
    history = data.get("history", "")
    history += f"\nПользователь написал: 'Подобрать курс'"
    await state.update_data(history=history)
    await message.answer(
        "🎯 Отлично! Ответьте, пожалуйста, на пару коротких вопросов:\n\n"
        "🔹 Сколько лет вашему ребенку?\n"
        "🔹 Уже пробовал(а) программировать или только начинает?\n"
        "🔹 Что больше интересно: игры, мультфильмы, роботы, дизайн или что-то ещё?"
    )
    await state.set_state(UserDialog.waiting_for_question)

async def handle_demo_callback_text(message: Message, state: FSMContext):
    data = await state.get_data()
    history = data.get("history", "")
    user_text = message.text.strip()
    history += f"\nПользователь написал: '{user_text}'"
    await state.update_data(history=history)

    # Пытаемся найти название курса в сообщении пользователя
    course_query = None
    
    # Ищем курс после слова "демо" или похожих (расширенный поиск)
    demo_match = re.search(r'(?:демо|демо-урок|демоурок|демо урок|демоурок)[\s:,-]*([A-Za-zА-Яа-я0-9\- ]{2,})', user_text, re.IGNORECASE)
    if demo_match and demo_match.group(1).strip():
        course_query = demo_match.group(1).strip()
    
    # Если не нашли, ищем курс в начале или конце сообщения
    if not course_query:
        # Расширенный список названий курсов для поиска
        course_names = [
            "scratch", "python", "minecraft", "roblox", "java", "ai", "arduino", "unity", 
            "веб", "web", "майнкрафт", "роблокс", "питон", "скретч", "джава", "ардуино", "юнити",
            "scratchjr", "minecraftjr", "python_2", "pygame", "appinventor", "colobot", "cospaces",
            "scratch junior", "minecraft junior", "python level 2", "веб разработка", "веб-разработка"
        ]
        for course_name in course_names:
            if course_name in user_text.lower():
                course_query = course_name
                break
    
    # Если все еще не нашли, ищем в истории
    if not course_query:
        course_names = []
        course_pattern = r"(?:Пользователь|Бот):.*?(?:курс|по|про|:)?\s*([A-Za-zА-Яа-я0-9\- ]{3,})"
        for match in re.finditer(course_pattern, history, re.IGNORECASE|re.DOTALL):
            course_names.append(match.group(1).strip())
        if course_names:
            course_query = course_names[-1]
    
    if course_query:
        print(f"[DEBUG] Найден запрос курса: '{course_query}'")
        
        # Используем новый словарь для поиска курса
        course_info = find_course_by_name(course_query)
        print(f"[DEBUG] Результат поиска: {course_info}")
        
        if course_info and course_info.get("demo"):
            demo_link = course_info["demo"]
            course_title = course_info["title"]
            
            print(f"[DEBUG] Отправляем демо-ссылку: {demo_link}")
            
            await message.answer(
                f"🎬 Демо-уроки по курсу *{course_title}* доступны по ссылке: [Открыть демо]({demo_link})\n\n"
                "Это отличная возможность увидеть, как проходят занятия и какие проекты можно создавать!\n"
                "Для просмотра потребуется регистрация на платформе.\n\n"
                "Хотите узнать подробнее о программе? Напишите название курса или задайте свой вопрос!",
                parse_mode="Markdown"
            )
            await state.set_state(UserDialog.waiting_for_question)
            return
        else:
            print(f"[DEBUG] Курс не найден или нет демо-ссылки")
            await message.answer(
                f"К сожалению, для курса '{course_query}' нет открытых демо-уроков. Могу рассказать подробнее о программе или подобрать другой курс — напишите, что интересно!",
                parse_mode="Markdown"
            )
            await state.set_state(UserDialog.waiting_for_question)
            return
    else:
        await message.answer(
            "Вот подборка самых популярных курсов:\n"
            "• Scratch Junior (5-7 лет)\n"
            "• Minecraft (7-13 лет)\n"
            "• Python (9+ лет)\n"
            "• Roblox (9+ лет)\n"
            "У нас более 30 курсов! Напишите, какой вас интересует, и я пришлю демо-урок.",
            parse_mode="Markdown"
        )
        await state.set_state(UserDialog.waiting_for_question)

# Функция handle_contextual_response удалена - возвращаем к работе через GPT

async def handle_price_callback_text(message: Message, state: FSMContext):
    data = await state.get_data()
    history = data.get("history", "")
    user_text = message.text.strip()
    history += f"\nПользователь написал: '{user_text}'"
    await state.update_data(history=history)

    # Пытаемся найти название курса в сообщении пользователя
    course_query = None
    
    # Расширенный поиск курса после слов о ценах/тарифах
    price_match = re.search(r"(?:цены?|стоимость|тарифы?|форматы?)[\s:,-]*(.*)", user_text, re.IGNORECASE)
    if price_match and price_match.group(1).strip():
        course_query = price_match.group(1).strip()
    
    # Если не нашли, ищем курс в тексте
    if not course_query:
        # Расширенный список названий курсов для поиска
        course_names = [
            "scratch", "python", "minecraft", "roblox", "java", "ai", "arduino", "unity", 
            "веб", "web", "майнкрафт", "роблокс", "питон", "скретч", "джава", "ардуино", "юнити",
            "scratchjr", "minecraftjr", "python_2", "pygame", "appinventor", "colobot", "cospaces",
            "scratch junior", "minecraft junior", "python level 2", "веб разработка", "веб-разработка"
        ]
        for course_name in course_names:
            if course_name in user_text.lower():
                course_query = course_name
                break
    
    # Если все еще не нашли, ищем в истории
    if not course_query:
        course_names = []
        course_pattern = r"(?:Пользователь|Бот):.*?(?:курс|по|про|:)?\s*([A-Za-zА-Яа-я0-9\- ]{3,})"
        for match in re.finditer(course_pattern, history, re.IGNORECASE|re.DOTALL):
            course_names.append(match.group(1).strip())
        if course_names:
            course_query = course_names[-1]
    
    if course_query:
        # Используем новый словарь для поиска курса и тарифов
        course_info = find_course_by_name(course_query)
        tariffs = get_course_tariffs(course_query)
        
        if course_info and tariffs:
            course_title = course_info["title"]
            site_link = course_info.get("site", "")
            
            await message.answer(
                f"💰 Тарифы для курса *{course_title}*:\n\n"
                f"🔹 **Подписка** — доступ ко всем урокам курса на 30 дней\n"
                f"   💰 Стоимость: {tariffs['subscription']}\n\n"
                f"🔹 **PRO-тариф** — полный курс на 240 дней с возможностью заморозки\n"
                f"   💰 Стоимость: {tariffs['pro']}\n\n"
                f"🔹 **Индивидуальные занятия** с преподавателем в Zoom\n"
                f"   💰 Стоимость: {tariffs['individual']}\n\n"
                f"📋 Подробная программа курса: [Открыть страницу курса]({site_link})\n\n"
                f"💡 Хотите посмотреть демо-урок или у вас есть вопросы по тарифам?",
                parse_mode="Markdown"
            )
            await state.set_state(UserDialog.waiting_for_question)
            return
        else:
            await message.answer(
                f"К сожалению, для курса '{course_query}' нет информации о тарифах. Могу рассказать подробнее о программе или подобрать другой курс — напишите, что интересно!",
                parse_mode="Markdown"
            )
            await state.set_state(UserDialog.waiting_for_question)
            return
    else:
        # Общая информация о тарифах
        await message.answer(
            "💰 У нас есть:\n\n"
            "🔹 **Подписка** — доступ ко всем урокам выбранного курса на 30 дней\n"
            "   💰 Стоимость: от 6 990₽\n\n"
            "🔹 **PRO-тариф** — полный курс на 240 дней с возможностью заморозки\n"
            "   💰 Стоимость: от 19 990₽\n\n"
            "🔹 **Индивидуальные занятия** с преподавателем в Zoom\n"
            "   💰 Стоимость: от 2 500₽/занятие\n\n"
            "💡 Напишите название курса — покажу конкретные тарифы!",
            parse_mode="Markdown"
        )
        await state.set_state(UserDialog.waiting_for_question)

@router.callback_query(F.data == "start_pick")
async def handle_pick_callback(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    history = data.get("history", "")
    history += f"\nПользователь нажал кнопку: 'Подобрать курс'"
    await state.update_data(history=history)
    await callback.message.answer(
        "🎯 Отлично! Ответьте, пожалуйста, на пару коротких вопросов:\n\n"
        "🔹 Сколько лет вашему ребенку?\n"
        "🔹 Уже пробовал(а) программировать или только начинает?\n"
        "🔹 Что больше интересно: игры, мультфильмы, роботы, дизайн или что-то ещё?"
    )
    await state.set_state(UserDialog.waiting_for_question)
    await callback.answer()

@router.callback_query(F.data == "start_demo")
async def handle_demo_callback(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    history = data.get("history", "")
    # Ищем последнее упоминание курса в истории
    course_names = []
    course_pattern = r"(?:Пользователь|Бот):.*?(?:курс|по|про|:)?\s*([A-Za-zА-Яа-я0-9\- ]{3,})"
    for match in re.finditer(course_pattern, history, re.IGNORECASE|re.DOTALL):
        course_names.append(match.group(1).strip())
    course_query = course_names[-1] if course_names else None
    if course_query:
        # Используем новый словарь для поиска курса
        course_info = find_course_by_name(course_query)
        if course_info and course_info.get("demo"):
            demo_link = course_info["demo"]
            course_title = course_info["title"]
            
            await callback.message.answer(
                f"🎬 Демо-уроки по курсу *{course_title}* доступны по ссылке: [Открыть демо]({demo_link})\n\n"
                "Это отличная возможность увидеть, как проходят занятия и какие проекты можно создавать!\n"
                "Для просмотра необходимо пройти небольшую регистрацию на платформе.\n\n"
                "Хотите узнать подробнее о программе? Напишите название курса или задайте свой вопрос!",
                parse_mode="Markdown"
            )
            await state.set_state(UserDialog.waiting_for_question)
            await callback.answer()
            return
    # Если не найден курс или нет demo_link — универсальная ссылка
    await callback.message.answer(
        "🎬 Демо-уроки доступны по ссылке: [Открыть демо](https://codim.online/teach/control/stream)\n\n"
        "Это отличная возможность увидеть, как проходят занятия и какие проекты можно создавать!\n"
        "Для просмотра необходимо пройти небольшую регистрацию на платформе.\n\n"
        "Хотите узнать подробнее о программе? Напишите название курса или задайте свой вопрос!",
        parse_mode="Markdown"
    )
    await state.set_state(UserDialog.waiting_for_question)
    await callback.answer()

@router.callback_query(F.data == "start_price")
async def handle_price_callback(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    history = data.get("history", "")
    history += f"\nПользователь нажал кнопку: 'Узнать цены'"
    await state.update_data(history=history)
    
    # Ищем последнее упоминание курса в истории
    course_names = []
    course_pattern = r"(?:Пользователь|Бот):.*?(?:курс|по|про|:)?\s*([A-Za-zА-Яа-я0-9\- ]{3,})"
    for match in re.finditer(course_pattern, history, re.IGNORECASE|re.DOTALL):
        course_names.append(match.group(1).strip())
    course_query = course_names[-1] if course_names else None
    
    if course_query:
        # Используем новый словарь для поиска курса и тарифов
        course_info = find_course_by_name(course_query)
        tariffs = get_course_tariffs(course_query)
        
        if course_info and tariffs:
            course_title = course_info["title"]
            site_link = course_info.get("site", "")
            
            await callback.message.answer(
                f"💰 Тарифы для курса *{course_title}*:\n\n"
                f"🔹 **Подписка** — доступ ко всем урокам курса на 30 дней\n"
                f"   💰 Стоимость: {tariffs['subscription']}\n\n"
                f"🔹 **PRO-тариф** — полный курс на 240 дней с возможностью заморозки\n"
                f"   💰 Стоимость: {tariffs['pro']}\n\n"
                f"🔹 **Индивидуальные занятия** с преподавателем в Zoom\n"
                f"   💰 Стоимость: {tariffs['individual']}\n\n"
                f"📋 Подробная программа курса: [Открыть страницу курса]({site_link})\n\n"
                f"💡 Хотите посмотреть демо-урок или у вас есть вопросы по тарифам?",
                parse_mode="Markdown"
            )
            await state.set_state(UserDialog.waiting_for_question)
            await callback.answer()
            return
    else:
        # Общая информация о тарифах
        await callback.message.answer(
            "💰 У нас есть:\n\n"
            "🔹 **Подписка** — доступ ко всем урокам выбранного курса на 30 дней\n"
            "   💰 Стоимость: от 6 990₽\n\n"
            "🔹 **PRO-тариф** — полный курс на 240 дней с возможностью заморозки\n"
            "   💰 Стоимость: от 19 990₽\n\n"
            "🔹 **Индивидуальные занятия** с преподавателем в Zoom\n"
            "   💰 Стоимость: от 2 500₽/занятие\n\n"
            "💡 Напишите название курса — покажу конкретные тарифы!",
            parse_mode="Markdown"
        )
        await state.set_state(UserDialog.waiting_for_question)
        await callback.answer()

@router.message(StateFilter(UserDialog.waiting_for_demo_confirmation))
async def handle_demo_confirmation(message: Message, state: FSMContext):
    text = message.text.lower()
    if text in ["да", "хочу", "давай", "ага", "ок", "го"]:
        await message.answer(
        "Отлично! Ответьте, пожалуйста, на пару коротких вопросов:\n"
        "1. Сколько лет вашему ребенку?\n"
        "2. Уже пробовал(а) программировать или только начинает?\n"
        "3. Что больше интересно: игры, мультфильмы, роботы, дизайн или что-то ещё?"
    )
    else:
        await message.answer("Отлично! 😊 Если захотите подобрать курс или узнать о тарифах — обращайтесь!")
    await state.clear()

@router.callback_query(F.data == "start_methods")
async def handle_methods_intro(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    history = data.get("history", "")
    # Если роль ещё не определена, добавляем явное сообщение и сохраняем роль
    if data.get("role") != "teacher":
        history += "\nПользователь: Я преподаватель, интересуюсь покупкой методик для своих учеников."
        await state.update_data(role="teacher")
    await state.update_data(history=history)
    await state.update_data(teacher=True)
    markup = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="1️⃣ Демо материалы", callback_data="methods_demo")],
        [InlineKeyboardButton(text="2️⃣ Узнать тарифы", callback_data="methods_tariffs")],
        [InlineKeyboardButton(text="3️⃣ Подобрать курс", callback_data="methods_pick_course")],
        [InlineKeyboardButton(text="4️⃣ Консультация со специалистом", callback_data="methods_consult")]
    ])
    await callback.message.answer(
        "Отлично! 😊 Мы предлагаем готовые методические материалы...\n\nВыберите, что вас интересует:",
        reply_markup=markup
    )
    # --- Запись в Google Sheets ---
    user = callback.from_user
    print("Перед вызовом update_user_row (start_methods)")
    await asyncio.get_event_loop().run_in_executor(
        None,
        update_user_row,
        {
            "ID": str(user.id),
            "Username": f"@{user.username or '—'}",
            "Интересы": "teacher",
            "История": "Пользователь: Интересуюсь покупкой методик\nБот: Показал меню методик",
            "Резюме": "",
            "Заявка менеджеру": "",
            "Преподаватель": "Преподаватель"
        }
    )
    print("После вызова update_user_row (start_methods)")
    await callback.answer()

@router.callback_query(F.data == "methods_consult")
async def handle_methods_consult(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    history = data.get("history", "")
    history += f"\nПользователь выбрал: 'Консультация со специалистом'"
    await state.update_data(history=history, teacher=True)  # Устанавливаем флаг преподавателя
    markup = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📨 Перейти на сайт для консультации", url="https://codim.online/biz")]
    ])
    await callback.message.answer(
        "Чтобы получить консультацию со специалистом, перейдите по ссылке ниже 👇",
        reply_markup=markup
    )
    # --- Запись в Google Sheets ---
    user = callback.from_user
    print("Перед вызовом update_user_row (teacher)")
    await asyncio.get_event_loop().run_in_executor(
        None,
        update_user_row,
        {
            "ID": str(user.id),
            "Username": f"@{user.username or '—'}",
            "Интересы": data.get("role", "teacher"),
            "История": "Пользователь: Интересуюсь покупкой методик\nБот: Перешёл на консультацию со специалистом",
            "Резюме": "",
            "Заявка менеджеру": "",
            "Преподаватель": "Преподаватель"
        }
    )
    print("После вызова update_user_row (teacher)")
    await callback.answer()

@router.callback_query(F.data == "methods_demo")
async def handle_methods_demo(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    history = data.get("history", "")
    history += f"\nПользователь выбрал: 'Демо материалы'"
    await state.update_data(history=history)
    await callback.message.answer(
        "📚 В каждом курсе есть 3 открытых демо урока с примерами методик:\n\n"
        "✅ Подробные методики к каждому уроку\n"
        "✅ Видео-уроки от авторов\n"
        "✅ Домашки, тесты, шпаргалки\n"
        "✅ Поддержка кураторов\n\n"
        "Напишите, пожалуйста:\n"
        "🔹 Возраст учеников\n"
        "🔹 Уровень подготовки (начинающие/продолжающие)\n"
        "🔹 Или конкретный курс"
    )
    await callback.answer()
    await state.set_state(UserDialog.waiting_for_question)


@router.callback_query(F.data == "methods_tariffs")
async def handle_methods_tariffs(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    history = data.get("history", "")
    history += f"\nПользователь выбрал: 'Узнать тарифы'"
    await state.update_data(history=history)
    markup = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➡️ Выбрать тариф Start", callback_data="tariff_start")],
        [InlineKeyboardButton(text="➡️ Выбрать тариф Pro", callback_data="tariff_pro")],
        [InlineKeyboardButton(text="➡️ Узнать про тариф Бизнес", callback_data="tariff_biz")],
        [InlineKeyboardButton(text="➡️ Хочу оформить в рассрочку", callback_data="installment_request")],
        [InlineKeyboardButton(text="⬅️ Вернуться к выбору курса", callback_data="return_to_courses")]
    ])

    
    await callback.message.answer(
        "💰 Тарифы:\n"
        "⭐️ Start — 1/2 курса — от 24 990₽\n"
        "⭐️ Pro — полный курс — от 44 990₽\n"
        "⭐️ Бизнес — 128+ уроков — от 179 960₽\n\n"
        "💬 Методики скачиваемые, видео с ограничением\n"
        "🎯 Есть рассрочки без переплат\n\n"
        "Для какого возраста подбираете курс?",
        reply_markup=markup
    )
    await callback.answer()

@router.callback_query(F.data == "tariff_start")
async def handle_tariff_start(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    history = data.get("history", "")
    history += f"\nПользователь выбрал: 'Тариф Start'"
    await state.update_data(history=history)
    await callback.message.answer(
        "Вы выбрали тариф Start — 1/2 курса (16 уроков) 🎯\n\n"
        "Напишите, пожалуйста:\n"
        "🔹 Какой курс вас интересует?\n"
        "🔹 Возраст учеников?"
    )
    await callback.answer()
    await state.set_state(UserDialog.waiting_for_question)


@router.callback_query(F.data == "tariff_pro")
async def handle_tariff_pro(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    history = data.get("history", "")
    history += f"\nПользователь выбрал: 'Тариф Pro'"
    await state.update_data(history=history)
    await callback.message.answer(
        "Вы выбрали тариф Pro — полный курс (32 урока) 📘\n\n"
        "Напишите, пожалуйста:\n"
        "🔹 Какой курс вас интересует?\n"
        "🔹 Возраст учеников?"
    )
    await callback.answer()
    await state.set_state(UserDialog.waiting_for_question)

@router.callback_query(F.data == "tariff_biz")
async def handle_tariff_biz(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    history = data.get("history", "")
    history += f"\nПользователь выбрал: 'Тариф Бизнес'"
    await state.update_data(history=history)
    markup = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📨 Оставить заявку на консультацию", url="https://codim.online/biz")],
        [InlineKeyboardButton(text="🔍 Хочу подобрать курсы самостоятельно", callback_data="methods_pick_course")]
    ])
    await callback.message.answer(
        "Вы выбрали тариф Бизнес 📚\n\n"
        "✅ 128+ уроков\n"
        "✅ Материалы без водяных знаков\n"
        "✅ Доступ дольше\n"
        "✅ Размещение вашей школы на сайте\n\n"
        "📋 Заполните анкету для расчета цены 👇",
        reply_markup=markup
    )
    await callback.answer()

@router.callback_query(F.data == "installment_request")
async def handle_installment_request(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    history = data.get("history", "")
    history += f"\nПользователь выбрал: 'Хочу оформить в рассрочку'"
    await state.update_data(history=history)
    markup = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📨 Оставить заявку на оформление", callback_data="installment_form")],
        [InlineKeyboardButton(text="🔍 Подобрать курсы самостоятельно", callback_data="methods_pick_course")]
    ])
    await callback.message.answer(
        "💸 Рассрочка:\n\n"
        "🔹 2 месяца внутренняя — без переплат\n"
        "🔹 3-6 мес через банки — тоже без переплат\n\n"
        "Напишите, пожалуйста:\n"
        "🔹 Какой курс вас интересует?\n"
        "🔹 Какой тариф выбрали?\n\n"
        "Что дальше?",
        reply_markup=markup
    )
    await callback.answer()
@router.callback_query(F.data == "installment_form")
async def handle_installment_form(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    history = data.get("history", "")
    history += f"\nПользователь выбрал: 'Оставить заявку на оформление'"
    await state.update_data(history=history)
    markup = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📨 Заполнить анкету", url="https://codim.online/reg/anketa2_teacherbot")]
    ])
    await callback.message.answer(
        "Отлично! 😊 Заполните анкету, и наш менеджер свяжется с вами для оформления рассрочки!",
        reply_markup=markup
    )
    await callback.answer()

@router.callback_query(F.data == "return_to_courses")
async def handle_return_to_courses(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    history = data.get("history", "")
    history += f"\nПользователь выбрал: 'Вернуться к выбору курса'"
    await state.update_data(history=history)
    await callback.message.answer(
        "Конечно! 😊 Расскажите еще раз:\n\n"
        "🔹 Возраст учеников\n"
        "🔹 Уровень подготовки (начинающие или с опытом)\n\n"
        "Подберу идеальные курсы и покажу демо!"
    )
    await callback.answer()
    await state.set_state(UserDialog.waiting_for_question)

@router.callback_query(F.data == "methods_pick_course")
async def handle_pick_course_return(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    history = data.get("history", "")
    history += f"\nПользователь выбрал: 'Подобрать курс (методики)'"
    await state.update_data(history=history)
    await callback.message.answer(
        "Конечно! 😊 Чтобы подобрать идеальный курс, расскажите:\n"
        "🔹 Возраст учеников\n"
        "🔹 Уровень подготовки\n"
        "🔹 Какие темы больше нравятся?"
    )
    await state.set_state(UserDialog.waiting_for_question)
    await callback.answer()



@router.message(StateFilter(UserDialog.waiting_for_question))
async def process_question(message: Message, state: FSMContext):
    logger.info("🔵 process_question ЗАПУЩЕН")
    try:
        data = await state.get_data()
        history = data.get("history", "")
        role = data.get("role", None)
        user_text = message.text.lower()
        # Обработка уточняющих фраз для подробного ответа
        detail_phrases = [
            "расскажите подробнее", "структура", "программа", "примеры заданий", "что внутри курса", "углубиться", "подробное описание", "подробнее о курсе", "подробнее о программе"
        ]
        if any(phrase in user_text for phrase in detail_phrases):
            history += "\nПользователь просит подробное описание курса, структуру, примеры заданий и т.д."
        # Определяем роль по тексту пользователя, если она ещё не определена
        if not role:
            if any(x in user_text for x in ["я преподаватель", "я учитель", "для учеников", "моим ученикам", "моим студентам", "для класса", "для группы"]):
                role = "teacher"
                history += "\nПользователь: Я преподаватель, интересуюсь курсами для своих учеников."
                await state.update_data(role=role)
            elif any(x in user_text for x in ["для себя", "мне", "я хочу", "ищу для себя", "мой возраст", "мне интересно", "я сам", "я сама"]):
                role = "self"
                history += "\nПользователь: Я ищу курс для себя."
                await state.update_data(role=role)
            elif any(x in user_text for x in ["мой ребенок", "моему ребенку", "для ребенка", "сыну", "дочери", "моему сыну", "моей дочери", "для сына", "для дочери", "для внука", "для внучки", "моему внуку", "моей внучке", "для ребёнка", "моему ребёнку"]):
                role = "parent"
                history += "\nПользователь: Я родитель, ищу курс для своего ребенка."
                await state.update_data(role=role)
        history += f"\nПользователь: {message.text}"

        manager_phrases = ["позвать менеджера", "связаться с менеджером", "хочу поговорить с менеджером"]
        if any(phrase in message.text.lower() for phrase in manager_phrases):
            await state.update_data(manager_request=True)  # Устанавливаем флаг запроса менеджера
            confirm_markup = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="✅ Подтвердить", callback_data="followup_manager")]
            ])
            await message.answer("Вы хотите связаться с менеджером? Подтвердите, пожалуйста 👇", reply_markup=confirm_markup)
            return

        knowledge = await search_knowledge(message.text)
        gpt_response = await ask_gpt(
            question=message.text,
            knowledge=knowledge,
            history=history,
            agent_prompt_file="generator.md"
        )

        answer = gpt_response

        await state.update_data(role=role)
        history += f"\nБот: {answer}"
        await state.update_data(history=history)
        user_id = message.from_user.id
        last_user_messages[user_id] = asyncio.get_event_loop().time()
        asyncio.create_task(schedule_follow_up(message, user_id))

        await message.answer(answer, parse_mode="Markdown")
        asyncio.create_task(schedule_followup(message, state))


        try:
            await message.bot.send_message(
            APPLICATION_CHAT_ID,
            f"ID: {message.from_user.id}\n"
            f"👨‍ Имя: {message.from_user.full_name}\n"
            f"Username: @{message.from_user.username or '—'}\n"
            f"Сообщение пользователя: {message.text}\n"
            f"🤖 Сообщение бота: {answer}",
            parse_mode=None
        )
        except Exception as e:
            logger.warning(f"Не удалось отправить лог в чат истории: {e}")

        # Если пользователь просил менеджера — отправлять заявку только в чат -1002657713491
        if role == "teacher":
            try:
                await message.bot.send_message(-1002657713491, f"Заявка менеджеру от пользователя {message.from_user.id} (@{message.from_user.username or '—'})", parse_mode="Markdown")
            except Exception as e:
                logger.warning(f"Не удалось отправить заявку менеджеру: {e}")

        # --- Генерация резюме для менеджера ---
        summary = await generate_summary(history)

        # Проверяем, просил ли пользователь менеджера
        manager_request = data.get("manager_request", False)
        manager_field = "попросил менеджера" if manager_request else ""

        teacher_flag = data.get("teacher", False)
        teacher_field = "Преподаватель" if teacher_flag else ""

        print("Перед вызовом update_user_row (summary)")
        await asyncio.get_event_loop().run_in_executor(
            None,
            update_user_row,
            {
            "ID": str(message.from_user.id),
            "Username": f"@{message.from_user.username or '—'}",
            "Интересы": role,
                "История": f"Пользователь: {message.text}\nБот: {answer}",
                "Резюме": summary,
                "Заявка менеджеру": manager_field,
                "Преподаватель": teacher_field
            }
        )
        print("После вызова update_user_row (summary)")

    except Exception as e:
        logger.exception("❗ Ошибка в process_question")

    await state.update_data(
        last_interaction=datetime.datetime.now().timestamp(),
        followup_sent=False
    )




@router.message()
async def fallback_router(message: Message, state: FSMContext):
    # Проверяем, что сообщение не пустое
    if not message.text or not message.text.strip():
        await message.answer("Пожалуйста, напишите ваш вопрос или выберите кнопку из меню.")
        return
    
    text = message.text.strip().lower()
    
    # Убираем скрипт с шаблонными ответами - возвращаем к работе через GPT
    print(f"[DEBUG] Fallback router получил сообщение: '{message.text}' - отправляем в GPT")
    
    # Проверяем, не спрашивает ли пользователь о том, как вернуться в меню
    menu_keywords = ["меню", "главное меню", "начать заново", "старт", "start", "начать", "вернуться", "главная"]
    
    if any(keyword in text for keyword in menu_keywords):
        await message.answer(
            "🔄 Чтобы вернуться в главное меню, напишите **Старт** или **Start**.\n\n"
            "Это откроет меню с основными опциями: подбор курса, демо-уроки, цены и информация о методиках.",
            parse_mode="Markdown"
        )
        return
    
    # Если ни одна из проверок не сработала, отправляем в GPT
    current_state = await state.get_state()
    if not current_state:
        await state.set_state(UserDialog.waiting_for_question)
    
    # Вызываем process_question для обработки через GPT
    await process_question(message, state)


async def schedule_follow_up(message: Message, user_id: int):
    await asyncio.sleep(3600)  # 1 час ожидания
    last_time = last_user_messages.get(user_id)
    if not last_time:
        return

    now = asyncio.get_event_loop().time()
    if now - last_time >= 3600:  # Проверяем, что прошло ровно 1 час
        try:
            # Проверяем, не отправляли ли мы уже follow-up этому пользователю
            if user_id not in followup_sent_users:
                followup_keyboard = InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="❓ Задать ещё вопрос", callback_data="followup_question")],
                    [InlineKeyboardButton(text="📨 Позвать менеджера", callback_data="followup_manager")]
                ])
                await message.answer(
                    "🕐 Я всё ещё на связи. Могу чем-то ещё помочь или позвать менеджера?",
                    reply_markup=followup_keyboard
                )
                # Отмечаем, что follow-up уже отправлен
                followup_sent_users[user_id] = True
        except Exception as e:
            logger.warning(f"Не удалось отправить follow-up сообщение: {e}")


@router.callback_query(F.data == "followup_question")
async def handle_followup_question(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    history = data.get("history", "")
    history += f"\nПользователь нажал кнопку: 'Задать ещё вопрос'"
    await state.update_data(history=history)
    await callback.message.answer("Конечно! 😊 Расскажите, что вас интересует:")
    await state.set_state(UserDialog.waiting_for_question)
    await callback.answer()

@router.callback_query(F.data == "followup_manager")
async def handle_followup_manager(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    history = data.get("history", "")
    history += f"\nПользователь нажал кнопку: 'Позвать менеджера'"
    await state.update_data(history=history)
    user = callback.from_user
    msg = (
        f"📞 Пользователь просит связаться с менеджером:\n"
        f"• ID: `{user.id}`\n"
        f"• Имя: {escape_markdown(user.full_name)}\n"
        f"• Username: @{escape_markdown(user.username) if user.username else '—'}"
    )
    await callback.message.bot.send_message(-1002657713491, msg, parse_mode="Markdown")
    await callback.message.answer("Отлично! 😊 Менеджер свяжется с вами в ближайшее время и поможет с выбором курса.")
    await state.update_data(manager_request=True)
    # --- Запись в Google Sheets ---
    print("Перед вызовом update_user_row (manager)")
    await asyncio.get_event_loop().run_in_executor(
        None,
        update_user_row,
        {
            "ID": str(user.id),
            "Username": f"@{user.username or '—'}",
            "Интересы": data.get("role", ""),
            "История": "Пользователь: Позвать менеджера\nБот: Менеджер свяжется с вами",
            "Резюме": "",
            "Заявка менеджеру": "попросил менеджера",
            "Преподаватель": "Преподаватель" if data.get("teacher") else ""
        }
    )
    print("После вызова update_user_row (manager)")
    await callback.answer()


from aiogram import types

# Удаляем лишний обработчик - он конфликтует с основной логикой
# @router.message()
# async def get_chat_id(message: types.Message):
#     print("chat_id =", message.chat.id)

# Callback для демо удален - возвращаем к работе через GPT

# Callback для тарифов удален - возвращаем к работе через GPT

# Callback для программы курса удален - возвращаем к работе через GPT
