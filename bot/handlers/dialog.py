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
from bot.handlers.course_selection import router as course_selection_router
from bot.fsm.states import CourseSearch
from bot.services.course_descriptions import search_course_by_name, format_course_info, get_course_price_info, get_course_description
from bot.services.sheets import update_user_row
from aiogram.types import InputFile
import asyncio
from typing import Dict
# Импорты для словаря курсов убраны - возвращаем к работе через GPT
# from bot.constants import find_course_by_name, get_course_tariffs


router = Router()
router.include_router(generator.router)
router.include_router(course_selection_router)

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

class TeacherDialog(StatesGroup):
    waiting_for_age = State()
    waiting_for_interest = State()
    waiting_for_experience = State()
    waiting_for_stack = State()
    waiting_for_recommendation = State()

start_keyboard = InlineKeyboardMarkup(inline_keyboard=[
    [InlineKeyboardButton(text="Подобрать курс", callback_data="start_pick")],
    [InlineKeyboardButton(text="Посмотреть демо", callback_data="start_demo")],
    [InlineKeyboardButton(text="Узнать цены", callback_data="start_price")],
    [InlineKeyboardButton(text="👨‍🏫 Я преподаватель", callback_data="start_teacher")]
])

formats_keyboard = InlineKeyboardMarkup(inline_keyboard=[
    [InlineKeyboardButton(text="🟦 Создание игр на блоках (визуальное программирование, без кода)", callback_data="teacher_games:blocks")],
    [InlineKeyboardButton(text="💻 Создание игр с помощью кода (на Python, C# и других языках)", callback_data="teacher_games:code")],
    [InlineKeyboardButton(text="👨‍💻 Изучение языков программирования", callback_data="teacher_langs")],
    [InlineKeyboardButton(text="🏠 Главное меню", callback_data="menu")]
])

formats_keyboard2 = InlineKeyboardMarkup(inline_keyboard=[
    [InlineKeyboardButton(text="🟦 Создание игр на блоках (визуальное программирование, без кода)", callback_data="teacher_games:blocks2")],
    [InlineKeyboardButton(text="💻 Создание игр с помощью кода (на Python, C# и других языках)", callback_data="teacher_games:code2")],
    [InlineKeyboardButton(text="👨‍💻 Изучение языков программирования", callback_data="teacher_langs2")],
    [InlineKeyboardButton(text="🏠 Главное меню", callback_data="menu")]
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
    # Перенаправляем на новую систему подбора курсов
    from bot.handlers.course_selection import start_course_selection
    
    # Создаем фейковый callback для совместимости
    class FakeCallback:
        def __init__(self, message):
            self.message = message
            self.data = "start_pick"
        
        async def answer(self):
            pass
    
    fake_callback = FakeCallback(message)
    await start_course_selection(fake_callback, state)

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
        
        # Используем функцию поиска курса
        search_result = search_course_by_name(course_query)
        
        if search_result["found"]:
            course_slug = search_result["course_slug"]
            course_title = search_result["course_title"]
            course_info = get_course_description(course_slug)
            
            if course_info and course_info.get("demo_link"):
                demo_link = course_info["demo_link"]
                
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
                await message.answer(
                    f"К сожалению, для курса '{course_title}' нет открытых демо-уроков. Могу рассказать подробнее о программе или подобрать другой курс — напишите, что интересно!",
                    parse_mode="Markdown"
                )
                await state.set_state(UserDialog.waiting_for_question)
                return
        else:
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
        # Используем функцию поиска курса
        search_result = search_course_by_name(course_query)
        
        if search_result["found"]:
            course_slug = search_result["course_slug"]
            course_title = search_result["course_title"]
            price_info = get_course_price_info(course_slug)
            
            await message.answer(
                f"💰 Тарифы для курса *{course_title}*:\n\n{price_info}\n\n"
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

# Обработчик кнопки "Подобрать курс" теперь находится в course_selection.py
# Этот обработчик удален, так как логика перенесена в новую систему

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
        # Используем функцию поиска курса
        search_result = search_course_by_name(course_query)
        
        if search_result["found"]:
            course_slug = search_result["course_slug"]
            course_title = search_result["course_title"]
            course_info = get_course_description(course_slug)
            
            if course_info and course_info.get("demo_link"):
                demo_link = course_info["demo_link"]
                
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
        # Используем функцию поиска курса
        search_result = search_course_by_name(course_query)
        
        if search_result["found"]:
            course_slug = search_result["course_slug"]
            course_title = search_result["course_title"]
            price_info = get_course_price_info(course_slug)
            
            await callback.message.answer(
                f"💰 Тарифы для курса *{course_title}*:\n\n{price_info}\n\n"
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
        "2. Уже пробовал(а) программировать или только начинает?"
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
        # Проверяем, что пользователь НЕ находится в состоянии поиска курса
        current_state = await state.get_state()
        if current_state == CourseSearch.waiting_for_course_name:
            logger.info("🔵 Пользователь в состоянии поиска курса, пропускаем process_question")
            return
            
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




@router.message(StateFilter(CourseSearch.waiting_for_course_name))
async def handle_course_name_input(message: Message, state: FSMContext):
    """Обработка ввода названия курса"""
    course_name = message.text.strip()
    print(f"[DEBUG] handle_course_name_input получил: '{course_name}'")
    
    # Сначала ищем по ключевым словам для получения готового описания
    course_result = find_course_by_keywords(course_name)
    print(f"[DEBUG] Результат поиска: {course_result}")
    
    if course_result["found"]:
        # Курс найден по ключевым словам, показываем готовое описание
        course_slug = course_result["course_slug"]
        course_title = course_result["course_title"]
        
        # Получаем готовое описание
        description = get_course_description_by_slug(course_slug)
        
        if description:
            # Создаем клавиатуру
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="💰 Узнать стоимость и тарифы", callback_data=f"course_prices:{course_slug}")],
                [InlineKeyboardButton(text="🏠 Главное меню", callback_data="menu")]
            ])
            
            await message.answer(description, reply_markup=keyboard)
            return
    
    # Если не найден по ключевым словам, используем старую логику поиска
    search_result = search_course_by_name(course_name)
    
    if search_result["found"]:
        # Курс найден
        course_slug = search_result["course_slug"]
        course_title = search_result["course_title"]
        
        # Курс найден, используем существующий обработчик course_info
        
        # Создаем клавиатуру с кнопкой для получения полной информации о курсе
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📚 Подробнее о курсе", callback_data=f"course_info:{course_title}")],
            [InlineKeyboardButton(text="🔙 Назад", callback_data="back")],
            [InlineKeyboardButton(text="🏠 Главное меню", callback_data="menu")]
        ])
        
        await message.answer(
            f"✅ Найден курс: <b>{course_title}</b>\n\nНажмите кнопку ниже, чтобы получить подробную информацию о курсе, демо-уроки и тарифы:",
            reply_markup=keyboard,
            parse_mode="HTML"
        )
    else:
        # Курс не найден
        suggestions = search_result["suggestions"]
        suggestions_text = "\n".join([f"• {course}" for course in suggestions[:3]])
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📝 Заполнить анкету для связи", url="https://codim.online/reg/anketa2_teacherbot")],
            [InlineKeyboardButton(text="🔙 Назад", callback_data="back")],
            [InlineKeyboardButton(text="🏠 Главное меню", callback_data="menu")]
        ])
        
        await message.answer(
            f"🤔 Спасибо за запрос!\n"
            f"Я не нашёл курс с таким названием в базе, но возможно, он есть под другим именем или у нас есть аналогичный по содержанию.\n\n"
            f"Чтобы не терять время и сразу найти то, что нужно — просто заполните короткую анкету, и наш менеджер свяжется с вами, чтобы помочь с подбором:\n\n"
            f"<b>Популярные курсы:</b>\n{suggestions_text}\n\n"
            f"Если что — я тоже рядом и всегда могу помочь 😊",
            reply_markup=keyboard,
            parse_mode="HTML"
        )

@router.callback_query(F.data.startswith("course_prices:"))
async def handle_course_prices(callback: CallbackQuery, state: FSMContext):
    """Обработка кнопки 'Узнать стоимость и тарифы'"""
    course_slug = callback.data.split(":")[1]
    
    try:
        # Получаем информацию о ценах курса
        price_info = get_course_price_info(course_slug)
        
        if price_info:
            await callback.message.answer(price_info, parse_mode="HTML")
        else:
            await callback.message.answer("❌ Информация о ценах для этого курса временно недоступна.")
            
    except Exception as e:
        print(f"[ERROR] Ошибка при получении цен курса {course_slug}: {e}")
        await callback.message.answer("❌ Произошла ошибка при получении информации о ценах.")
    
    await callback.answer()

@router.message()
async def fallback_router(message: Message, state: FSMContext):
    # Проверяем, что сообщение не пустое
    if not message.text or not message.text.strip():
        await message.answer("Пожалуйста, напишите ваш вопрос или выберите кнопку из меню.")
        return
    
    # Проверяем, что пользователь НЕ находится в состоянии поиска курса
    current_state = await state.get_state()
    if current_state == CourseSearch.waiting_for_course_name:
        print(f"[DEBUG] Пользователь в состоянии поиска курса, пропускаем fallback_router")
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

# ===== НОВАЯ ЛОГИКА ДЛЯ ПРЕПОДАВАТЕЛЕЙ =====

@router.callback_query(F.data == "start_course_search")
async def start_course_search(callback: CallbackQuery, state: FSMContext):
    """Обработка кнопки 'Хочу программу конкретного курса'"""
    await state.set_state(CourseSearch.waiting_for_course_name)
    
    message_text = """Отлично!
Пожалуйста, напишите название курса, который вас интересует — я сразу пришлю:

✔️ демо-уроки,
✔️ информацию о содержании,
✔️ тарифы и формат обучения.

Если вдруг курса с таким названием нет в базе, я помогу найти аналог или подходящую альтернативу"""
    
    await callback.message.answer(message_text)
    await callback.answer()

def find_course_by_keywords(course_name: str) -> dict:
    """Поиск курса по ключевым словам и возврат готового описания"""
    course_name_lower = course_name.lower().strip()
    print(f"[DEBUG] Поиск курса: '{course_name}' -> '{course_name_lower}'")
    
    # Словарь соответствий ключевых слов и курсов
    course_keywords = {
        "roblox": "roblox",
        "роблокс": "roblox", 
        "roblox studio": "roblox",
        "роблокс студио": "roblox",
        
        "unity": "unity_csharp",
        "юнити": "unity_csharp",
        "unity c#": "unity_csharp",
        "юнити c#": "unity_csharp",
        "unity csharp": "unity_csharp",
        "юнити csharp": "unity_csharp",
        "unity блоки": "unity_blocks",
        "юнити блоки": "unity_blocks",
        "unity blocks": "unity_blocks",
        "юнити blocks": "unity_blocks",
        
        "scratch": "scratch_1",
        "скретч": "scratch_1",
        "scratch 1": "scratch_1",
        "скретч 1": "scratch_1",
        "scratch 2": "scratch_2",
        "скретч 2": "scratch_2",
        "scratch 3": "scratch_3",
        "скретч 3": "scratch_3",
        "большое путешествие": "scratch_3",
        "scratch junior": "scratch_jr",
        "скретч джуниор": "scratch_jr",
        "scratch jr": "scratch_jr",
        "скретч jr": "scratch_jr",
        
        "minecraft": "minecraft",
        "майнкрафт": "minecraft",
        "minecraft программирование": "minecraft",
        "майнкрафт программирование": "minecraft",
        
        "python": "python_lvl_1",
        "питон": "python_lvl_1",
        "пайтон": "python_lvl_1",
        "python 1": "python_lvl_1",
        "питон 1": "python_lvl_1",
        "пайтон 1": "python_lvl_1",
        "python уровень 1": "python_lvl_1",
        "питон уровень 1": "python_lvl_1",
        "python 2": "python_lvl_2",
        "питон 2": "python_lvl_2",
        "пайтон 2": "python_lvl_2",
        "python уровень 2": "python_lvl_2",
        "питон уровень 2": "python_lvl_2",
        "python minecraft": "python_minecraft",
        "питон майнкрафт": "python_minecraft",
        "пайтон майнкрафт": "python_minecraft",
        "python в minecraft": "python_minecraft",
        "питон в майнкрафт": "python_minecraft",
        
        "cospaces": "cospaces",
        "коспейс": "cospaces",
        "co spaces": "cospaces",
        "ко спейс": "cospaces",
        
        "app inventor": "appinventor",
        "апп инвентор": "appinventor",
        "appinventor": "appinventor",
        "аппинвентор": "appinventor",
        
        "telegram": "telegram_bots",
        "телеграм": "telegram_bots",
        "телеграм бот": "telegram_bots",
        "telegram bot": "telegram_bots",
        "бот": "telegram_bots",
        "телеграм боты": "telegram_bots",
        "telegram bots": "telegram_bots",
        
        "java": "java",
        "джава": "java",
        "ява": "java",
        
        "pygame": "pygame",
        "пайгейм": "pygame",
        "python game": "pygame",
        "питон игра": "pygame",
        
        "3d": "3d_tinkercad",
        "3d моделирование": "3d_tinkercad",
        "3д": "3d_tinkercad",
        "3д моделирование": "3d_tinkercad",
        "tinkercad": "3d_tinkercad",
        "тинкеркад": "3d_tinkercad"
    }
    
    # Ищем точное совпадение
    if course_name_lower in course_keywords:
        print(f"[DEBUG] Найдено точное совпадение: '{course_name_lower}' -> {course_keywords[course_name_lower]}")
        return {
            "found": True,
            "course_slug": course_keywords[course_name_lower],
            "course_title": course_name_lower.title()
        }
    
    # Ищем частичное совпадение
    for keyword, course_slug in course_keywords.items():

        if keyword == "бот" and "колобот" in course_name_lower:
            continue

        if keyword in course_name_lower or course_name_lower in keyword:
            print(f"[DEBUG] Найдено частичное совпадение: '{keyword}' в '{course_name_lower}' -> {course_slug}")
            return {
                "found": True,
                "course_slug": course_slug,
                "course_title": keyword.title()
            }
    
    print(f"[DEBUG] Курс не найден: '{course_name_lower}'")
    return {"found": False, "course_slug": None, "course_title": None}

def get_course_description_by_slug(course_slug: str) -> str:
    """Получение готового описания курса по slug"""
    if course_slug == "roblox":
        return """🎮 Roblox Studio — курс по созданию 3D-игр в Roblox на языке Lua.

Отлично подходит для детей 11–13 лет, которые хотят создавать собственные игры в популярной платформе Roblox.

🎯 На курсе дети:
– Создают собственные 3D-игры в Roblox
– Программируют поведение объектов на Lua
– Изучают основы игровой логики
– Публикуют свои игры для других игроков

👨‍🏫 Курс включает:
– 32 пошаговых урока,
– методику для преподавателя,
– презентации,
– рабочие листы,
– по желанию — видеоуроки от автора.

🎬 📂 Все методические материалы (презентации, рабочие листы, планы уроков) остаются у вас навсегда — вы можете использовать их без ограничений в любое время.

🎥 Видео-уроки имеют ограниченный срок доступа, но его достаточно, чтобы изучить курс и внедрить в работу.
При необходимости доступ можно продлить — 1990₽ за месяц.

🎁 Попробуйте 3 бесплатных демо-урока:
🔗 Смотреть демо https://codim.online/teach/control/stream/view/id/245997376

💰 Тарифы и подключение:
🔗 Посмотреть тарифы https://codim.online/roblox_teacher#registration

Если возникли вопросы — пишите, с радостью помогу 😊"""
    
    elif course_slug == "unity_csharp":
        return """💻 Unity (C#) — курс по созданию игр на профессиональном движке Unity с настоящим кодом на C#.

Для детей 11–13 лет, которые готовы к серьёзному программированию и хотят создавать игры как настоящие разработчики.

🎯 На курсе дети:
– Изучают язык программирования C#
– Создают игры на движке Unity
– Понимают принципы объектно-ориентированного программирования
– Разрабатывают полноценные игровые проекты

👨‍🏫 Курс включает:
– 32 пошаговых урока,
– методику для преподавателя,
– презентации,
– рабочие листы,
– по желанию — видеоуроки от автора.

🎬 📂 Все методические материалы (презентации, рабочие листы, планы уроков) остаются у вас навсегда — вы можете использовать их без ограничений в любое время.

🎥 Видео-уроки имеют ограниченный срок доступа, но его достаточно, чтобы изучить курс и внедрить в работу.
При необходимости доступ можно продлить — 1990₽ за месяц.

🎁 Попробуйте 3 бесплатных демо-урока:
🔗 Смотреть демо https://codim.online/teach/control/stream/view/id/415678083

💰 Тарифы и подключение:
🔗 Посмотреть тарифы https://codim.online/Unity_2_teacher#registration

Если возникли вопросы — пишите, с радостью помогу 😊"""
    
    elif course_slug == "scratch_1":
        return """Scratch 1 — идеальный курс для детей 7–8 лет, которые уже умеют читать и готовы сделать свои первые шаги в мире программирования.

На курсе дети создают:
🎮 свои первые игры,
🎬 мультфильмы,
💡 интерактивные истории — всё это в простой и увлекательной среде блочного программирования Scratch.

👨‍🏫 Курс включает:
– 32 пошаговых урока,
– методику для преподавателя,
– презентации,
– рабочие листы,
– по желанию — видеоуроки от автора.

🎬 📂 Все методические материалы (презентации, рабочие листы, планы уроков) остаются у вас навсегда — вы можете использовать их без ограничений в любое время.

🎥 Видео-уроки имеют ограниченный срок доступа, но его достаточно, чтобы изучить курс и внедрить в работу.
При необходимости доступ можно продлить — 1990₽ за месяц.

🎁 Попробуйте 3 бесплатных демо-урока:
🔗 Смотреть демо https://codim.online/teach/control/stream/view/id/567829098

💰 Тарифы и подключение:
🔗 Посмотреть тарифы https://codim.online/scratch_1_teacher#registration

Если возникли вопросы — пишите, с радостью помогу 😊"""
    
    elif course_slug == "scratch_2":
        return """Scratch 2 — курс по блочному программированию для детей 9–10 лет.

Подходит:
✅ как продолжение курса Scratch 1 для тех, кто уже учился в 7–8 лет,
✅ так и для новичков этого возраста — программа выстроена с учётом старшего возраста и позволяет быстро войти в тему.

🎯 На курсе дети:
– Создают более сложные игры и проекты
– Изучают переменные, условия и циклы
– Развивают логическое мышление
– Работают в команде над проектами

👨‍🏫 Курс включает:
– 32 пошаговых урока,
– методику для преподавателя,
– презентации,
– рабочие листы,
– по желанию — видеоуроки от автора.

🎬 📂 Все методические материалы (презентации, рабочие листы, планы уроков) остаются у вас навсегда — вы можете использовать их без ограничений в любое время.

🎥 Видео-уроки имеют ограниченный срок доступа, но его достаточно, чтобы изучить курс и внедрить в работу.
При необходимости доступ можно продлить — 1990₽ за месяц.

🎁 Попробуйте 3 бесплатных демо-урока:
🔗 Смотреть демо https://codim.online/teach/control/stream/view/id/652143767

💰 Тарифы и подключение:
🔗 Посмотреть тарифы https://codim.online/scratch_2_teacher#registration

Если возникли вопросы — пишите, с радостью помогу 😊"""
    
    elif course_slug == "minecraft":
        return """⛏️ Minecraft: основы программирования — один из самых любимых курсов у детей от 7 до 13 лет!
Учимся программировать в мире Minecraft: управляем черепашкой-роботом, копаем туннели, строим дома, решаем головоломки — всё через код.

💡 Курс помогает освоить алгоритмы, команды, циклы и условия — основы, с которых начинается программирование.

🎮 Всё обучение проходит в специальной обучающей версии Minecraft, в которой:
– Нет монстров и опасностей,
– Есть специальные блоки для программирования,
– Можно создавать и сохранять свои миры.

👨‍🏫 Курс включает:
– 32 пошаговых урока,
– методику для преподавателя,
– презентации,
– рабочие листы,
– по желанию — видеоуроки от автора.

🎬 📂 Все методические материалы (презентации, рабочие листы, планы уроков) остаются у вас навсегда — вы можете использовать их без ограничений в любое время.

🎥 Видео-уроки имеют ограниченный срок доступа, но его достаточно, чтобы изучить курс и внедрить в работу.
При необходимости доступ можно продлить — 1990₽ за месяц.

🎁 Попробуйте 3 бесплатных демо-урока:
🔗 Смотреть демо https://codim.online/teach/control/stream/view/id/35104782

💰 Тарифы и подключение:
🔗 Посмотреть тарифы https://codim.online/minecraft_teacher#registration

Если возникли вопросы — пишите, с радостью помогу 😊"""
    
    elif course_slug == "cospaces":
        return """🕶 CoSpaces — это курс, в котором дети создают собственные 3D-миры и оживляют их с помощью кода!

Подходит для детей от 8 лет, особенно тем, кто уже работал в Scratch и готов к следующему уровню.
Здесь — похожий блочный язык, но в трёхмерном пространстве и с более сложной логикой.

🌍 Дети программируют 3D-сцены, добавляют анимации, озвучку, интерактивные элементы,
🎮 создают виртуальные экскурсии, игры и интерактивные истории.

👨‍🏫 Курс включает:
– 32 пошаговых урока,
– методику для преподавателя,
– презентации,
– рабочие листы,
– по желанию — видеоуроки от автора.

🎬 📂 Все методические материалы (презентации, рабочие листы, планы уроков) остаются у вас навсегда — вы можете использовать их без ограничений в любое время.

🎥 Видео-уроки имеют ограниченный срок доступа, но его достаточно, чтобы изучить курс и внедрить в работу.
При необходимости доступ можно продлить — 1990₽ за месяц.

🎁 Попробуйте 3 бесплатных демо-урока:
🔗 Смотреть демо https://codim.online/teach/control/stream/view/id/160082603

💰 Тарифы и подключение:
🔗 Посмотреть тарифы https://codim.online/cospaces_teacher#registration

Если возникли вопросы — пишите, с радостью помогу 😊"""
    
    elif course_slug == "python_lvl_1":
        return """🐍 Python для начинающих — пошаговое и понятное обучение Python с нуля.

Отлично подходит для детей 11–13 лет, которые готовы изучать настоящий язык программирования.

🎯 На курсе дети:
– Изучают основы синтаксиса Python
– Работают с переменными, условиями и циклами
– Создают простые программы и мини-проекты
– Развивают алгоритмическое мышление

👨‍🏫 Курс включает:
– 32 пошаговых урока,
– методику для преподавателя,
– презентации,
– рабочие листы,
– по желанию — видеоуроки от автора.

🎬 📂 Все методические материалы (презентации, рабочие листы, планы уроков) остаются у вас навсегда — вы можете использовать их без ограничений в любое время.

🎥 Видео-уроки имеют ограниченный срок доступа, но его достаточно, чтобы изучить курс и внедрить в работу.
При необходимости доступ можно продлить — 1990₽ за месяц.

🎁 Попробуйте 3 бесплатных демо-урока:
🔗 Смотреть демо https://codim.online/teach/control/stream/view/id/240471838

💰 Тарифы и подключение:
🔗 Посмотреть тарифы https://codim.online/python_teacher#registration

Если возникли вопросы — пишите, с радостью помогу 😊"""
    
    elif course_slug == "telegram_bots":
        return """🤖 Создание телеграм-ботов на Python — очень прикладной курс для детей 11–13 лет.

Учимся автоматизировать задачи и писать собственных ботов для Telegram — навык, который пригодится в жизни!

🎯 На курсе дети:
– Изучают API Telegram
– Создают ботов для различных задач
– Изучают работу с базами данных
– Разрабатывают полноценные проекты

👨‍🏫 Курс включает:
– 32 пошаговых урока,
– методику для преподавателя,
– презентации,
– рабочие листы,
– по желанию — видеоуроки от автора.

🎬 📂 Все методические материалы (презентации, рабочие листы, планы уроков) остаются у вас навсегда — вы можете использовать их без ограничений в любое время.

🎥 Видео-уроки имеют ограниченный срок доступа, но его достаточно, чтобы изучить курс и внедрить в работу.
При необходимости доступ можно продлить — 1990₽ за месяц.

🎁 Попробуйте 3 бесплатных демо-урока:
🔗 Смотреть демо https://codim.online/teach/control/stream/view/id/934432479

💰 Тарифы и подключение:
🔗 Посмотреть тарифы https://codim.online/tg_bot_teacher#registration

Если возникли вопросы — пишите, с радостью помогу 😊"""
    
    elif course_slug == "scratch_jr":
        return """Scratch Jr — идеальный курс для самых маленьких программистов 5–7 лет!

Это специальная версия Scratch, созданная специально для дошкольников, которые ещё не умеют читать.

🎯 На курсе дети:
– Создают свои первые анимации и игры
– Изучают основы логики программирования
– Развивают креативное мышление
– Готовятся к более сложным курсам

👨‍🏫 Курс включает:
– 32 пошаговых урока,
– методику для преподавателя,
– презентации,
– рабочие листы,
– по желанию — видеоуроки от автора.

🎬 📂 Все методические материалы (презентации, рабочие листы, планы уроков) остаются у вас навсегда — вы можете использовать их без ограничений в любое время.

🎥 Видео-уроки имеют ограниченный срок доступа, но его достаточно, чтобы изучить курс и внедрить в работу.
При необходимости доступ можно продлить — 1990₽ за месяц.

🎁 Попробуйте 3 бесплатных демо-урока:
🔗 Смотреть демо https://codim.online/teach/control/stream/view/id/246490381

💰 Тарифы и подключение:
🔗 Посмотреть тарифы https://codim.online/scratchjr_teacher#registration

Если возникли вопросы — пишите, с радостью помогу 😊"""
    
    elif course_slug == "scratch_3":
        return """🌍 "Большое путешествие" — это уникальный курс программирования и изучения мира для детей 9–13 лет.

🚀 Особенность курса — Scratch с блоками на английском языке. Но не волнуйтесь —
📚 на каждом уроке дети учат 10 новых английских слов, которые сразу используют в практике,
🧠 плюс — доступ к онлайн-тренажёру по английскому языку, чтобы закрепить лексику.

🎯 На курсе дети:
– Программируют в Scratch с английскими блоками
– Изучают страны мира через программирование
– Развивают логическое мышление
– Пополняют словарный запас английского языка

👨‍🏫 Курс включает:
– 32 пошаговых урока,
– методику для преподавателя,
– презентации,
– рабочие листы,
– по желанию — видеоуроки от автора.

🎬 📂 Все методические материалы (презентации, рабочие листы, планы уроков) остаются у вас навсегда — вы можете использовать их без ограничений в любое время.

🎥 Видео-уроки имеют ограниченный срок доступа, но его достаточно, чтобы изучить курс и внедрить в работу.
При необходимости доступ можно продлить — 1990₽ за месяц.

🎁 Попробуйте 3 бесплатных демо-урока:
🔗 Смотреть демо https://codim.online/teach/control/stream/view/id/195941430

💰 Тарифы и подключение:
🔗 Посмотреть тарифы https://codim.online/scratch_3_teacher#registration

Если возникли вопросы — пишите, с радостью помогу 😊"""
    
    elif course_slug == "3d_tinkercad":
        return """🧱 3D-моделирование в Tinkercad — курс, где дети от 7 до 14 лет учатся создавать собственные 3D-проекты с нуля!

🏗 Проектируют дома, машинки, роботов, украшения и другие объекты — фантазия ничем не ограничена!
Модели можно использовать:
🖨 для печати на 3D-принтере,
🎮 или даже импортировать в игровые движки, например, в Roblox Studio.

🎯 На курсе дети:
– Изучают основы 3D-моделирования
– Создают собственные 3D-объекты
– Развивают пространственное мышление
– Готовятся к работе с профессиональными CAD-программами

👨‍🏫 Курс включает:
– 32 пошаговых урока,
– методику для преподавателя,
– презентации,
– рабочие листы,
– по желанию — видеоуроки от автора.

🎬 📂 Все методические материалы (презентации, рабочие листы, планы уроков) остаются у вас навсегда — вы можете использовать их без ограничений в любое время.

🎥 Видео-уроки имеют ограниченный срок доступа, но его достаточно, чтобы изучить курс и внедрить в работу.
При необходимости доступ можно продлить — 1990₽ за месяц.

🎁 Попробуйте 3 бесплатных демо-урока:
🔗 Смотреть демо https://codim.online/teach/control/stream/view/id/257930249

💰 Тарифы и подключение:
🔗 Посмотреть тарифы https://codim.online/3d_tinkercad_teacher#registration

Если возникли вопросы — пишите, с радостью помогу 😊"""
    
    elif course_slug == "appinventor":
        return """📱 App Inventor — курс по созданию мобильных приложений и игр для Android на блоках.

Идеально подходит для детей 10–14 лет, которые хотят создавать настоящие мобильные приложения без сложного программирования.

🎯 На курсе дети:
– Разрабатывают интерфейс приложений
– Программируют логику на блоках
– Создают игры для Android
– Публикуют приложения в Google Play

👨‍🏫 Курс включает:
– 32 пошаговых урока,
– методику для преподавателя,
– презентации,
– рабочие листы,
– по желанию — видеоуроки от автора.

🎬 📂 Все методические материалы (презентации, рабочие листы, планы уроков) остаются у вас навсегда — вы можете использовать их без ограничений в любое время.

🎥 Видео-уроки имеют ограниченный срок доступа, но его достаточно, чтобы изучить курс и внедрить в работу.
При необходимости доступ можно продлить — 1990₽ за месяц.

🎁 Попробуйте 3 бесплатных демо-урока:
🔗 Смотреть демо https://codim.online/teach/control/stream/view/id/278739597

💰 Тарифы и подключение:
🔗 Посмотреть тарифы https://codim.online/appinventor_teacher#registration

Если возникли вопросы — пишите, с радостью помогу 😊"""
    
    elif course_slug == "unity_blocks":
        return """🧩 Unity (Блоки) — идеальный старт в мире Unity для детей 11–13 лет.

Здесь дети создают игры на профессиональном движке Unity, но используют визуальное программирование блоками — без сложного кода!

🎯 На курсе дети:
– Изучают интерфейс Unity
– Создают игры с помощью блоков
– Понимают принципы игровой разработки
– Готовятся к изучению C#

👨‍🏫 Курс включает:
– 32 пошаговых урока,
– методику для преподавателя,
– презентации,
– рабочие листы,
– по желанию — видеоуроки от автора.

🎬 📂 Все методические материалы (презентации, рабочие листы, планы уроков) остаются у вас навсегда — вы можете использовать их без ограничений в любое время.

🎥 Видео-уроки имеют ограниченный срок доступа, но его достаточно, чтобы изучить курс и внедрить в работу.
При необходимости доступ можно продлить — 1990₽ за месяц.

🎁 Попробуйте 3 бесплатных демо-урока:
🔗 Смотреть демо https://codim.online/teach/control/stream/view/id/415678083

💰 Тарифы и подключение:
🔗 Посмотреть тарифы https://codim.online/unity_1_teacher#registration

Если возникли вопросы — пишите, с радостью помогу 😊"""
    
    elif course_slug == "python_minecraft":
        return """🐢 Python в Minecraft — курс по программированию в Minecraft на языке Python.

Отлично подходит для детей 11–13 лет, которые уже начали изучать Python и хотят применить знания в увлекательной игре.

🎯 На курсе дети:
– Создают игровые сцены в Minecraft с помощью Python
– Изучают продвинутые конструкции Python
– Развивают алгоритмическое мышление
– Создают собственные модификации игры

👨‍🏫 Курс включает:
– 32 пошаговых урока,
– методику для преподавателя,
– презентации,
– рабочие листы,
– по желанию — видеоуроки от автора.

🎬 📂 Все методические материалы (презентации, рабочие листы, планы уроков) остаются у вас навсегда — вы можете использовать их без ограничений в любое время.

🎥 Видео-уроки имеют ограниченный срок доступа, но его достаточно, чтобы изучить курс и внедрить в работу.
При необходимости доступ можно продлить — 1990₽ за месяц.

🎁 Попробуйте 3 бесплатных демо-урока:
🔗 Смотреть демо https://codim.online/teach/control/stream/view/id/245455310

💰 Тарифы и подключение:
🔗 Посмотреть тарифы https://codim.online/pythonvm_teacher#registration

Если возникли вопросы — пишите, с радостью помогу 😊"""
    
    elif course_slug == "pygame":
        return """🐍 Pygame — курс по созданию 2D-игр на Python.

Для детей 11–13 лет, которые уже знают Python и хотят создавать настоящие игры с графикой, звуком и анимацией.

🎯 На курсе дети:
– Создают 2D-игры на Python с помощью библиотеки Pygame
– Изучают игровую логику и физику
– Работают с графикой и звуком
– Разрабатывают полноценные игровые проекты

👨‍🏫 Курс включает:
– 32 пошаговых урока,
– методику для преподавателя,
– презентации,
– рабочие листы,
– по желанию — видеоуроки от автора.

🎬 📂 Все методические материалы (презентации, рабочие листы, планы уроков) остаются у вас навсегда — вы можете использовать их без ограничений в любое время.

🎥 Видео-уроки имеют ограниченный срок доступа, но его достаточно, чтобы изучить курс и внедрить в работу.
При необходимости доступ можно продлить — 1990₽ за месяц.

🎁 Попробуйте 3 бесплатных демо-урока:
🔗 Смотреть демо https://codim.online/teach/control/stream/view/id/245455310

💰 Тарифы и подключение:
🔗 Посмотреть тарифы https://codim.online/pygame_teacher#registration

Если возникли вопросы — пишите, с радостью помогу 😊"""
    
    elif course_slug == "python_lvl_2":
        return """🐍 Python Уровень 2 — продолжение изучения Python для детей 11–13 лет.

Для тех, кто уже освоил основы Python и готов к более сложным темам и проектам.

🎯 На курсе дети:
– Изучают продвинутые конструкции Python
– Работают с файлами и базами данных
– Создают более сложные проекты
– Готовятся к профессиональной разработке

👨‍🏫 Курс включает:
– 32 пошаговых урока,
– методику для преподавателя,
– презентации,
– рабочие листы,
– по желанию — видеоуроки от автора.

🎬 📂 Все методические материалы (презентации, рабочие листы, планы уроков) остаются у вас навсегда — вы можете использовать их без ограничений в любое время.

🎥 Видео-уроки имеют ограниченный срок доступа, но его достаточно, чтобы изучить курс и внедрить в работу.
При необходимости доступ можно продлить — 1990₽ за месяц.

🎁 Попробуйте 3 бесплатных демо-урока:
🔗 Смотреть демо https://codim.online/teach/control/stream/view/id/745210336

💰 Тарифы и подключение:
🔗 Посмотреть тарифы https://codim.online/python2_teacher#registration

Если возникли вопросы — пишите, с радостью помогу 😊"""

    elif course_slug == "colobot":
        # Определяем роль, если она передается в data или context
        role = data.get("role") if "data" in locals() else None

        if role == "teacher":
            return """Colobot — программирование через игру!

Это курс, где дети учатся языку, похожему на C++ и Java, программируя роботов в увлекательной 3D-среде.
Каждое задание — это миссия: добыть ресурсы, построить базу, защитить колонию, изучить новую планету.

📘 Методика обучения:
теоретические объяснения и практические задания в игровой форме;
пошаговые видеоуроки (16 шт.) и готовые методические материалы;
развитие логики, алгоритмического мышления и интереса к реальному коду;
проверочные задания и шпаргалки для работы с учениками.

🎯 Что получает преподаватель:
готовый учебный курс для учеников 11+;
материалы для демонстрации и обсуждения на уроках
Видео-уроки по желанию, для того, чтобы посмотреть, как материал преподносит автор курса 

💰 Тарифы и методические материалы:
👉 codim.online/Colobot/teacher

🎓 Демо-уроки:
Попробуйте бесплатно несколько заданий и оцените структуру курса и качество методических материалов, прежде чем внедрять его в программу обучения: https://codim.online/teach/control/stream/view/id/410001583
"""
        else:
            return """🚀 Курс: Colobot — программирование и приключения!

👦 Возраст: от 11 лет  
Погрузись в мир, где роботы слушаются твоих команд!  
На курсе Colobot дети осваивают основы программирования, похожего на C++ и Java, управляют роботами, строят базы и исследуют новые планеты.

💡 Что изучаем:
• основы синтаксиса C++ и Java  
• циклы, условия, переменные и функции  
• алгоритмы управления роботами  
• применение программирования в игровой среде

🎮 Примеры миссий:
«На Тропике» — движение и добыча ресурсов  
«Битва стрелков» — стратегия и автоматизация действий  

🎓 Демо-уроки:
https://codim.online/teach/control/stream/view/id/410001583  
"""

    elif course_slug == "arduino":
        return """Программирование на Arduino
Если вы хотите проводить занятия по электронике и робототехнике — этот курс полностью готов к внедрению в учебный процесс! ⚙️

📘 Что входит в курс:
🔹 1 модуль (8 уроков) — работа в онлайн-симуляторе Tinkercad, где ученики программируют виртуальные схемы без риска ошибиться.
🔹 2 модуль — практические задания с набором электронных компонентов (можно купить у нас или собрать самостоятельно).
🔹 3 и 4 модули — сборка робота и подготовка к соревнованиям по робототехнике.

🧩 Пакет преподавателя включает:
подробные методические материалы по каждому уроку,
готовые домашние задания, тесты и презентации для проектора,


💡 Можно дополнительно приобрести видеоуроки, чтобы увидеть, как преподаватель объясняет материал и выстраивает работу с детьми.

🎓 Курс отлично подходит для учителей информатики, инженерных направлений и педагогов дополнительного образования.

🔗 Подробнее о методиках и пакетах преподавателя:
👉 codim.online/arduino_teacher

 Рассказать о тарифах или хотите посмотреть примеры методик?"""

    elif course_slug == "java":
        return """☕️ Основы Java — пошаговое введение в язык Java для детей 11–13 лет.

Подходит для школьников, кто хочет двигаться в сторону инженерных и серьёзных направлений программирования.

🎯 На курсе дети:
– Изучают базовые конструкции Java
– Понимают принципы объектно-ориентированного программирования
– Решают задачи на логику и алгоритмы
– Готовятся к серьёзной разработке

👨‍🏫 Курс включает:
– 32 пошаговых урока,
– методику для преподавателя,
– презентации,
– рабочие листы,
– по желанию — видеоуроки от автора.

🎬 📂 Все методические материалы (презентации, рабочие листы, планы уроков) остаются у вас навсегда — вы можете использовать их без ограничений в любое время.

🎥 Видео-уроки имеют ограниченный срок доступа, но его достаточно, чтобы изучить курс и внедрить в работу.
При необходимости доступ можно продлить — 1990₽ за месяц.

🎁 Попробуйте 3 бесплатных демо-урока:
🔗 Смотреть демо https://codim.online/teach/control/stream/view/id/680288877

💰 Тарифы и подключение:
🔗 Посмотреть тарифы https://codim.online/java_teacher#registration

Если возникли вопросы — пишите, с радостью помогу 😊"""
    
    # Добавим остальные курсы по мере необходимости
    return None


@router.callback_query(F.data == "start_teacher")
async def start_teacher_flow(callback: CallbackQuery, state: FSMContext):
    """Начало потока для преподавателей"""
    await state.clear()
    await state.set_state(TeacherDialog.waiting_for_age)
    
    message_text = """🎓 У нас есть готовые методики и программы, которые подойдут как для открытия кружка по программированию с нуля, так и для дополнения существующих курсов в детских центрах, школах или онлайн-проектах.

Вы можете:
🔹 Подобрать курс самостоятельно, изучив содержание и форматы.
🔹 Записаться на консультацию — наш менеджер подберёт подходящие курсы под возраст, уровень и формат обучения.
🔹 Или, если вы уже знаете, что ищете — просто получить программу курса и тарифы.

👇 Выберите удобный вариант"""
    
    markup = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Подобрать курс", callback_data="teacher_pick_course")],
        [InlineKeyboardButton(text="Консультация менеджера", callback_data="teacher_consultation")],
        [InlineKeyboardButton(text="Хочу программу конкретного курса", callback_data="start_course_search")],
        [InlineKeyboardButton(text="🏠 Главное меню", callback_data="menu")]
    ])
    
    await callback.message.answer(message_text, reply_markup=markup)
    await callback.answer()

@router.callback_query(F.data == "teacher_pick_course")
async def teacher_pick_course(callback: CallbackQuery, state: FSMContext):
    """Обработка кнопки 'Подобрать курс' для преподавателей"""
    await state.set_state(TeacherDialog.waiting_for_age)
    
    message_text = """Отлично! Давайте уточним, для какой возрастной группы вы подбираете курсы или методики 👇
Выберите интересующий возраст:"""
    
    markup = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Дошкольники (5–7 лет)", callback_data="teacher_age:preschool")],
        [InlineKeyboardButton(text="Младшие школьники (7–10 лет)", callback_data="teacher_age:elementary")],
        [InlineKeyboardButton(text="Средние классы (11–13 лет)", callback_data="teacher_age:middle")],
        [InlineKeyboardButton(text="Старшеклассники (14+ лет)", callback_data="teacher_age:high")],
        [InlineKeyboardButton(text="🏠 Главное меню", callback_data="menu")]
    ])
    
    await callback.message.answer(message_text, reply_markup=markup)
    await callback.answer()

@router.callback_query(F.data == "teacher_consultation")
async def teacher_consultation(callback: CallbackQuery, state: FSMContext):
    """Обработка кнопки 'Консультация менеджера' для преподавателей"""
    markup = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📨 Перейти на сайт для консультации", url="https://codim.online/biz")],
        [InlineKeyboardButton(text="🏠 Главное меню", callback_data="menu")]
    ])
    
    await callback.message.answer(
        "Чтобы получить консультацию со специалистом, перейдите по ссылке ниже 👇",
        reply_markup=markup
    )
    await callback.answer()


@router.callback_query(F.data.startswith("teacher_age:"))
async def handle_teacher_age_selection(callback: CallbackQuery, state: FSMContext):
    """Обработка выбора возраста для преподавателей"""
    age_group = callback.data.split(":")[1]
    
    # Маппинг возрастных групп
    age_mapping = {
        "preschool": "5-7 лет (дошкольники)",
        "elementary": "7-10 лет (младшие школьники)", 
        "middle": "11-13 лет (средние классы)",
        "high": "14+ лет (старшеклассники)"
    }
    
    age_text = age_mapping.get(age_group, "неизвестный возраст")
    
    await state.update_data(teacher_age_group=age_group)
    
    # Специальная обработка для дошкольников
    if age_group == "preschool":
        message_text = """Отлично! Для дошкольников у нас есть 2 готовые методики, идеально подходящие для первых шагов в программировании:

🎨 Scratch Junior — 32 увлекательных урока по блочному программированию.
Дети создают мультфильмы, анимации, интерактивные истории и учатся алгоритмическому мышлению в игровой форме.
💻 Курс можно проходить как на компьютере, так и на планшете — подойдёт даже тем, кто ещё не уверенно пользуется клавиатурой и мышкой.

⛏️ Логические задачи в Minecraft — 16 занятий, где дети программируют черепашку, решают головоломки и осваивают основы логики в увлекательной 3D-среде.
🖥 Проходит только на компьютере, в специально настроенной обучающей версии Minecraft.

👨‍🏫 Оба курса разработаны Денисом Голиковым — автором более 17 бестселлеров по обучению детей программированию. Его книги переведены на 4 языка, а методики построены так, чтобы даже самые сложные темы были понятны, интересны и давали результат уже на первых занятиях.

📦 В пакет «Учитель» входит всё необходимое для запуска занятий:
– Подробная методика проведения уроков,
– Презентации для проектора,
– Рабочие листы — чтобы ребёнок мог не только заниматься за компьютером, но и потренироваться на бумаге (например, разрезать, соединить, решить задачку вручную),
– А по желанию можно добавить видеоуроки от автора, чтобы увидеть, как именно он объясняет материал детям — отличный ориентир для начинающего преподавателя.

✨ У каждого курса есть 3 бесплатных демо-урока с методикой — вы можете:
✔️ оценить подачу материала,
✔️ провести открытое занятие,
✔️ и даже набрать первую группу ещё до покупки полного курса.

👇 Какой курс вас заинтересовал? Я пришлю ссылки на демо и расскажу про тарифы:"""
        
        markup = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📘 Выбрать Scratch Junior", callback_data="teacher_course:scratch_jr")],
            [InlineKeyboardButton(text="🧱 Выбрать Логические задачи в Minecraft", callback_data="teacher_course:minecraft_jr")],
            [InlineKeyboardButton(text="🏠 Главное меню", callback_data="menu")]
        ])
        
        await callback.message.answer(message_text, reply_markup=markup)
        await callback.answer()
        return
    
    # Специальная обработка для средних классов
    elif age_group == "middle":
        message_text = """🚀 Отлично! Для детей 11–13 лет у нас есть сильные курсы как по созданию игр, так и по изучению настоящих языков программирования.

📚 В этом возрасте ученики уже готовы к более серьёзным задачам — учатся думать как разработчики, создают первые проекты и уверенно переходят от блоков к коду.

🧩 Скажите, пожалуйста, какое направление вам интересно?

👇 Выберите вариант:"""
                
        await callback.message.answer(message_text, reply_markup=formats_keyboard)
        await callback.answer()
        return
    
    # Специальная обработка для младших школьников
    elif age_group == "elementary":
        message_text = """Для младших школьников 7–10 лет у нас есть отличные курсы, которые подойдут как для первых шагов в программировании, так и для развития креативного и логического мышления:

🔹 Scratch 1 — курс с нуля, где дети создают мультфильмы, игры и анимации. Всё через блочное программирование, весело и понятно. Отличный старт!

🔹 Scratch 2 — продолжение курса с более сложными проектами, логикой, условиями и переменными. Для тех, кто уже знаком с основами.

🔹 Большое путешествие — уникальный курс-приключение на базе Scratch, в котором ребёнок путешествует по странам, решает задачи и создаёт интерактивные истории.

🔹 Minecraft: основы программирования — курс, где дети программируют черепашку в любимой игре. Учатся логике, алгоритмам и получают удовольствие от обучения!

🔹 CoSpaces — программирование и создание собственных 3D-миров в виртуальной реальности. Подходит для творчества, презентаций и изучения технологий.

🔹 3D-моделирование в Tinkercad — дети создают свои 3D-проекты, которые можно распечатать на 3D-принтере или использовать в играх (например, в Roblox).

✨ Все курсы идут с методиками, презентациями и рабочими листами. Есть возможность добавить видеоуроки.
Каждый курс включает 3 демо-урока — вы можете протестировать материал и провести открытое занятие до покупки.

👇 Какой из курсов вас заинтересовал? Я пришлю тарифы и ссылки на демо-уроки:"""
        
        markup = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🧩 Scratch 1 для 7-8 лет", callback_data="teacher_course:scratch_1")],
            [InlineKeyboardButton(text="🔁 Scratch 2 для 9-10 лет", callback_data="teacher_course:scratch_2")],
            [InlineKeyboardButton(text="🌍 Большое путешествие для 9-13 лет", callback_data="teacher_course:scratch_3")],
            [InlineKeyboardButton(text="⛏️ Minecraft для 7-13 лет", callback_data="teacher_course:minecraft")],
            [InlineKeyboardButton(text="🕶 CoSpaces для 8-14 лет", callback_data="teacher_course:cospaces")],
            [InlineKeyboardButton(text="🧱 3D-моделирование для 7-14 лет", callback_data="teacher_course:3d_tinkercad")],
            [InlineKeyboardButton(text="🏠 Главное меню", callback_data="menu")]
        ])
        
        await callback.message.answer(message_text, reply_markup=markup)
        await callback.answer()
        return
    
    # Для остальных возрастных групп - обычная логика
        await state.set_state(TeacherDialog.waiting_for_interest)
    
    message_text = f"""🚀 Отлично! Для детей 14+ лет у нас есть сильные курсы как по созданию игр, так и по изучению настоящих языков программирования.

📚 В этом возрасте ученики уже готовы к более серьёзным задачам — учатся думать как разработчики, создают первые проекты и уверенно переходят от блоков к коду.

🧩 Скажите, пожалуйста, какое направление вам интересно?

👇 Выберите вариант:
"""
    

    await callback.message.answer(message_text, reply_markup=formats_keyboard2)
    await callback.answer()

@router.callback_query(F.data.startswith("teacher_interest:"))
async def handle_teacher_interest_selection(callback: CallbackQuery, state: FSMContext):
    """Обработка выбора интереса для преподавателей"""
    interest = callback.data.split(":")[1]
    
    await state.update_data(teacher_interest=interest)
    
    # Маппинг интересов
    interest_mapping = {
        "games": "Создание игр",
        "langs": "Язык программирования",
        "tg_bots": "Создание телеграм-ботов",
        "web_apps": "Создание сайтов и приложений",
        "ai": "Искусственный интеллект",
        "robots": "Роботы",
        "design": "Дизайн",
        "3d": "3D"
    }
    
    interest_text = interest_mapping.get(interest, "неизвестный интерес")
    
    message_text = f"""Отлично! Вы выбрали направление: {interest_text}

Теперь уточните, есть ли у ваших учеников опыт в программировании?"""
    
    markup = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Да, есть опыт", callback_data="teacher_exp:yes")],
        [InlineKeyboardButton(text="Нет, начинаем с нуля", callback_data="teacher_exp:no")],
        [InlineKeyboardButton(text="🏠 Главное меню", callback_data="menu")]
    ])
    
    await callback.message.answer(message_text, reply_markup=markup)
    await callback.answer()

@router.callback_query(F.data.startswith("teacher_exp:"))
async def handle_teacher_exp_selection(callback: CallbackQuery, state: FSMContext):
    """Обработка выбора опыта для преподавателей"""
    exp = callback.data.split(":")[1]
    
    await state.update_data(teacher_exp=exp)
    
    data = await state.get_data()
    age_group = data.get("teacher_age_group", "")
    interest = data.get("teacher_interest", "")
    
    # Маппинг возрастных групп
    age_mapping = {
        "preschool": "5-7 лет (дошкольники)",
        "elementary": "7-10 лет (младшие школьники)", 
        "middle": "11-13 лет (средние классы)",
        "high": "14+ лет (старшеклассники)"
    }
    
    # Маппинг интересов
    interest_mapping = {
        "games": "Создание игр",
        "langs": "Язык программирования",
        "tg_bots": "Создание телеграм-ботов",
        "web_apps": "Создание сайтов и приложений",
        "ai": "Искусственный интеллект",
        "robots": "Роботы",
        "design": "Дизайн",
        "3d": "3D"
    }
    
    age_text = age_mapping.get(age_group, "неизвестный возраст")
    interest_text = interest_mapping.get(interest, "неизвестный интерес")
    exp_text = "есть опыт" if exp == "yes" else "начинаем с нуля"
    
    message_text = f"""Отлично! Сейчас подберу подходящие курсы и методики для ваших учеников!"""
    
    markup = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎬 Посмотреть демо", callback_data="teacher_demo")],
        [InlineKeyboardButton(text="💰 Узнать тарифы", callback_data="teacher_tariffs")],
        [InlineKeyboardButton(text="📨 Консультация менеджера", callback_data="teacher_consultation")],
        [InlineKeyboardButton(text="🏠 Главное меню", callback_data="menu")]
    ])
    
    await callback.message.answer(message_text, reply_markup=markup)
    await callback.answer()

@router.callback_query(F.data == "teacher_demo")
async def teacher_demo(callback: CallbackQuery, state: FSMContext):
    """Обработка кнопки 'Посмотреть демо' для преподавателей"""
    markup = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🌐 Перейти к демо-урокам", url="https://codim.online/demo1/entrance")],
        [InlineKeyboardButton(text="🏠 Главное меню", callback_data="menu")]
    ])
    
    await callback.message.answer(
        "🎬 Демо-уроки помогут вам оценить качество и формат обучения.\n\nПерейдите по ссылке ниже, чтобы посмотреть примеры уроков:",
        reply_markup=markup
    )
    await callback.answer()

    
@router.callback_query(F.data == "teacher_games:blocks2")
async def teacher_games_blocks2(callback: CallbackQuery, state: FSMContext):
    markup = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🕶 CoSpaces", callback_data="teacher_course:cospaces")],  # ← исправленный callback
        [InlineKeyboardButton(text="🧩 Unity: Уровень 1 (Блоки + переход к C#)", callback_data="teacher_course:unity_blocks")],
        [InlineKeyboardButton(text="🏠 Главное меню", callback_data="menu")]
    ])
    
    await callback.message.answer(
        """🎮 Отлично! Для подростков 14+ создание игр на блоках — это не просто увлечение, а старт в мир настоящей разработки.

Вот два курса, которые идеально подойдут:

🕶 CoSpaces
Создаём 3D-миры и VR-проекты прямо в браузере. Ученики программируют поведение объектов на визуальных блоках, создают истории, симуляции и даже обучающие проекты. Отлично развивает креативность, логику и цифровую грамотность.

🧩 Unity: Уровень 1 (блоки)
Курс-переходник между блочным и текстовым программированием. Ученики создают игры в настоящем игровом движке Unity, сначала работая на визуальных блоках, а затем постепенно переходят к коду на C#. Это идеальный мост к профессиональной разработке.

👇 Какой из курсов вас заинтересовал? Я пришлю демо и подробности:
""",
        reply_markup=markup
    )
    await callback.answer()


@router.callback_query(F.data == "teacher_games:code2")
async def teacher_games_blocks2(callback: CallbackQuery, state: FSMContext):
    markup = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🐍 Python для начинающих", callback_data="teacher_course:python_lvl_1")],
        [InlineKeyboardButton(text="🐍 Python Уровень 2", callback_data="teacher_course:python_lvl_2")],
        [InlineKeyboardButton(text="🐢 Python в Minecraft", callback_data="teacher_course:python_minecraft")],
        [InlineKeyboardButton(text="🤖 Создание телеграм-ботов", callback_data="teacher_course:telegram_bots")],
        [InlineKeyboardButton(text="🎮 Pygame (создание игр на Python)", callback_data="teacher_course:pygame")],
        [InlineKeyboardButton(text="☕️ Java", callback_data="teacher_course:java")],
        [InlineKeyboardButton(text="🏠 Главное меню", callback_data="menu")]
    ])
    
    await callback.message.answer(
        """💻 Отличный выбор! В 14+ ученики уже готовы к серьёзному погружению в языки программирования — и у нас есть всё, чтобы выстроить полноценную траекторию обучения.

🐍 Python — простой в изучении и очень популярный язык. У нас есть 5 курсов по Python на разный уровень подготовки:

1. Python для начинающих — изучаем базу: переменные, циклы, списки, условия.
2. Python Level 2 — более серьёзные темы: функции, словари, файлы, проекты.
3. Python в Minecraft — программируем действия в мире Minecraft, применяя Python на практике.
4. Pygame — создаём полноценные 2D-игры на Python: спрайты, анимации, управление. Отличный способ мотивировать учеников!
5. Создание Telegram-ботов — работа с API и создание собственных ботов с полезным функционалом.

☕ Java — универсальный язык, который используется в крупных IT-проектах. В курсе — синтаксис, ООП и логика построения приложений. Подходит тем, кто хочет углубиться в системную разработку.

👇 Какой курс вас интересует? Я пришлю описание, программу и демо-уроки:
""",
        reply_markup=markup
    )
    await callback.answer()


@router.callback_query(F.data == "teacher_langs2")
async def teacher_langs2(callback: CallbackQuery, state: FSMContext):
    markup = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎮 Roblox", callback_data="teacher_course:roblox")],
        [InlineKeyboardButton(text="🐍 Pygame", callback_data="teacher_course:pygame")],
        [InlineKeyboardButton(text="🧩 Unity на C#", callback_data="teacher_course:unity_csharp")],
        [InlineKeyboardButton(text="🤖 Colobot", callback_data="teacher_course:colobot")],
        [InlineKeyboardButton(text="🏠 Главное меню", callback_data="menu")]
    ])
    await callback.message.answer(
        """💻 Отличный выбор! В возрасте 14+ ученики уже готовы работать с настоящим кодом — и у нас есть мощные курсы, которые помогут им прокачать навыки разработки.

🎮 Roblox Studio (на Lua)
Создание 3D-игр на популярной платформе. Интересно не только детям, но и подросткам и даже взрослым!
Ученики изучают основы программирования на Lua, создают полноценные проекты, которые можно опубликовать и поделиться с другими.

🐍 Pygame (на Python)
Создаём настоящие 2D-игры на Python — со спрайтами, управлением, жизнями и счётом.
Курс отлично подходит для тех, кто уже знаком с базовым Python и хочет применять знания в игровых проектах.

🧩 Unity: Уровень 2 (на C#)
Продвинутый курс по созданию игр в Unity с полноценным кодом на языке C#.
Идеальный выбор для тех, кто хочет перейти от визуального программирования к профессиональной среде.

🤖 Colobot
Уникальный курс, где ученики управляют роботами в 3D-мире, решая задачи с помощью языка CBOT (по синтаксису похож на C/C++).
Прекрасно развивает алгоритмическое мышление и помогает понять структуру программирования через практику.

👇 Какой курс вас заинтересовал? Пришлю подробности, демо и методику:""",
        reply_markup=markup
    )
    await callback.answer()


@router.callback_query(F.data == "teacher_tariffs")
async def teacher_tariffs(callback: CallbackQuery, state: FSMContext):
    """Обработка кнопки 'Узнать тарифы' для преподавателей"""
    markup = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💳 Перейти к выбору тарифа", url="https://codim.online/biz")],
        [InlineKeyboardButton(text="🏠 Главное меню", callback_data="menu")]
    ])
    
    await callback.message.answer(
        "💰 Узнать подробную информацию о тарифах и условиях для преподавателей можно по ссылке ниже:",
        reply_markup=markup
    )
    await callback.answer()

# Обработчики для выбора конкретных курсов
@router.callback_query(F.data.startswith("teacher_course:"))
async def handle_teacher_course_selection(callback: CallbackQuery, state: FSMContext):
    """Обработка выбора конкретного курса для преподавателей"""
    course = callback.data.split(":")[1]
    
    if course == "scratch_jr":
        message_text = """Отличный выбор!
Курс Scratch Junior — это яркое и увлекательное введение в программирование для самых маленьких, которые ещё не умеют читать. Идеально подойдёт для кружков, детских садов и начальной школы.

👨‍🏫 В курсе:
– 32 готовых урока,
– подробные методички для преподавателя,
– презентации для проектора,
– рабочие листы,
– и возможность добавить видеоуроки от автора.

📥 Все методики, презентации и рабочие материалы можно скачать — и они остаются у вас навсегда, без ограничений.

🎬 Видеоуроки (если вы решите их добавить) предоставляются с ограниченным сроком доступа.
По завершении доступ можно продлить при необходимости — 1990₽ за месяц.

🎁 Попробуйте 3 бесплатных демо-урока — по ним можно провести открытые занятия и протестировать курс до покупки:
🔗 https://codim.online/teach/control/stream/view/id/246490381

💰 А здесь можно посмотреть описание всех тарифов:
🔗 https://codim.online/scratchjr_teacher#registration

Если будут вопросы — я на связи! 😊"""
        
        markup = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🏠 Главное меню", callback_data="menu")]
        ])
        
    elif course == "minecraft_jr":
        message_text = """Отличный выбор!
Курс "Логические задачи в Minecraft" — это увлекательное погружение в программирование через игру, которую дети обожают.

🎮 На курсе дети знакомятся с миром Minecraft и учатся программировать черепашку-робота, которая проходит 3D-лабиринты, преодолевает препятствия и решает головоломки — всё через блочные команды и алгоритмы.

👨‍🏫 В курсе:
– 16 пошаговых уроков,
– методика с готовыми сценариями занятий,
– рабочие листы для занятий без компьютера,
– по желанию — видеоуроки от автора, где показано, как доносить материал детям.

💻 Курс проводится на компьютере в специальной учебной версии Minecraft. Никаких модов и сложной установки — всё уже подготовлено.

📥 Все материалы скачиваются и остаются у вас навсегда.
🎬 Видеоуроки доступны на ограниченный срок и при необходимости продлеваются за 1990₽ в месяц.

🎁 Доступны 3 бесплатных демо-урока — вы можете попробовать курс, провести открытое занятие и набрать группу ещё до покупки:
🔗 https://codim.online/teach/control/stream/view/id/35104782

💰 Посмотреть тарифы и формат подключения:
🔗 https://codim.online/minecraftjr_teacher#registration

Готова ответить на любые вопросы 😊"""
        
        markup = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🏠 Главное меню", callback_data="menu")]
        ])
        
    elif course == "scratch_1":
        message_text = """Scratch 1 — идеальный курс для детей 7–8 лет, которые уже умеют читать и готовы сделать свои первые шаги в мире программирования.

На курсе дети создают:
🎮 свои первые игры,
🎬 мультфильмы,
💡 интерактивные истории — всё это в простой и увлекательной среде блочного программирования Scratch.

👨‍🏫 Курс записан Денисом Голиковым — автором 17+ учебников по программированию для детей, переведённых на 4 языка. Его методика делает обучение лёгким, понятным и действительно интересным.

📦 В курс входит:
– 32 пошаговых урока,
– методика для преподавателя,
– презентации для занятий,
– рабочие листы,
– по желанию — видеоуроки от автора, чтобы увидеть, как он сам объясняет материал.

🎬 Видео открываются на ограниченный срок, но при необходимости продлеваются — 1990₽ за месяц.

🎁 Доступны 3 бесплатных демо-урока — по ним можно провести открытое занятие и протестировать курс до покупки:
🔗 https://codim.online/teach/control/stream/view/id/567829098

💰 Ознакомиться с тарифами:
🔗 https://codim.online/scratch_1_teacher#registration

Если остались вопросы — с радостью помогу 😊"""
        
        markup = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🏠 Главное меню", callback_data="menu")]
        ])
        
    elif course == "scratch_2":
        message_text = """Scratch 2 — курс по блочному программированию для детей 9–10 лет.

Подходит:
✅ как продолжение курса Scratch 1 для тех, кто уже учился в 7–8 лет,
✅ так и для новичков этого возраста — программа выстроена с учётом старшего возраста и позволяет быстро войти в тему.

На курсе дети:
🎮 создают более сложные игры,
🧠 осваивают условия, переменные, циклы,
🚀 развивают логическое мышление и учатся думать, как настоящие программисты.

👨‍🏫 Курс записан Денисом Голиковым — автором бестселлеров по обучению детей программированию. Уроки выстроены так, чтобы ребёнку было понятно, интересно и результативно.

📦 Внутри:
– 32 пошаговых урока,
– методика для преподавателя,
– презентации,
– рабочие листы,
– по желанию — видеоуроки от автора.

📥 Все материалы можно скачать и использовать без ограничения по времени.
🎬 Видеоуроки — с ограниченным доступом, но их можно продлить при необходимости за 1990₽ в месяц.

🎁 Хотите попробовать? Вот 3 бесплатных демо-урока, по которым можно провести открытое занятие:
🔗 Смотреть демо https://codim.online/teach/control/stream/view/id/652143767

💰 А вот и тарифы:
🔗 https://codim.online/scratch_2_teacher#registration

Если нужны рекомендации или помощь — напишите, я помогу подобрать! 😊"""
        
        markup = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🏠 Главное меню", callback_data="menu")]
        ])
        
    elif course == "scratch_3":
        message_text = """🌍 "Большое путешествие" — это уникальный курс программирования и изучения мира для детей 9–13 лет.

🚀 Особенность курса — Scratch с блоками на английском языке. Но не волнуйтесь —
📚 на каждом уроке дети учат 10 новых английских слов, которые сразу используют в практике,
🧠 плюс — доступ к онлайн-тренажёру по английскому языку, чтобы закрепить лексику.

🎒 Вместе с черепашкой-роботом дети путешествуют по разным странам:
🇷🇺 Россия — изучаем космос,
🇪🇸 Испания — играем в футбол,
🇯🇵 Япония — роботы и технологии,
и так далее — каждый урок посвящён новой стране и тематике, с интересными фактами и логикой, связанной с культурой.

👨‍🏫 Курс записан Денисом Голиковым, и включает:
– 32 красочных урока,
– методику для преподавателя,
– презентации,
– рабочие листы,
– по желанию — видеоуроки от автора.

📥 Все материалы можно скачать и использовать навсегда,
🎬 видео — с ограниченным доступом, который можно продлить при необходимости (1990₽/мес).

🎁 Попробуйте 3 бесплатных демо-урока — и посмотрите, как проходит обучение:
🔗 Смотреть демо https://codim.online/teach/control/stream/view/id/195941430

💰 Тарифы и подключение:
🔗 Посмотреть тарифы https://codim.online/scratch_3_teacher#registration

Нажмите на кнопку Назад, чтобы выбрать новый курс 😊"""
        
        markup = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🏠 Главное меню", callback_data="menu")]
        ])
        
    elif course == "cospaces":
        message_text = """🕶 CoSpaces — это курс, в котором дети создают собственные 3D-миры и оживляют их с помощью кода!

Подходит для детей от 8 лет, особенно тем, кто уже работал в Scratch и готов к следующему уровню.
Здесь — похожий блочный язык, но в трёхмерном пространстве и с более сложной логикой.

🌍 Дети программируют 3D-сцены, добавляют анимации, озвучку, интерактивные элементы,
а готовые проекты можно просматривать:
💻 на компьютере
🕶 или в VR-очках — эффект настоящего погружения!

✅ Работает прямо в браузере, ничего устанавливать не нужно — удобно и легко начать.

👨‍🏫 Курс записан Никитой Гуртовцевым и включает:
– 32 пошаговых урока,
– методику для преподавателя,
– презентации,
– рабочие листы,
– по желанию — видеоуроки от автора.

📥 Все материалы можно скачать и использовать без ограничений по времени,
🎬 видеоуроки — с ограниченным доступом, который можно продлить при необходимости (1990₽/мес).

🎁 Попробуйте 3 бесплатных демо-урока, чтобы оценить курс в действии:
🔗 Смотреть демо https://codim.online/teach/control/stream/view/id/160082603

💰 Тарифы и форматы подключения:
🔗 Посмотреть тарифы https://codim.online/cospaces_teacher#registration

Если возникнут вопросы — напишите, я с радостью помогу 😊"""
        
        markup = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🏠 Главное меню", callback_data="menu")]
        ])
        
    elif course == "minecraft":
        message_text = """⛏️ Minecraft: основы программирования — один из самых любимых курсов у детей от 7 до 13 лет!
Учимся программировать в мире Minecraft: управляем черепашкой-роботом, копаем туннели, строим дома, решаем головоломки — всё через код.

💡 Курс помогает освоить алгоритмы, команды, циклы и условия — основы, с которых начинается программирование.

🎮 Всё обучение проходит в специальной обучающей версии Minecraft, в которой:
– нет отвлекающих элементов,
– задания — пошаговые и понятные,
– ребёнок учится в игре, но с реальной пользой.

📌 Отлично подходит как для новичков, так и для тех, кто уже пробовал Scratch.

👨‍🏫 Курс создан Денисом Голиковым и включает:
– 32 готовых урока,
– подробную методику,
– презентации,
– рабочие листы,
– по желанию — видеоуроки от автора.

💻 Устанавливается только на компьютер (поддерживаем, подскажем, если что).

📥 Все материалы можно скачать и использовать без ограничения,
🎬 Видео имеют ограниченный срок и при необходимости продлеваются — 1990₽ в месяц.

🎁 Доступно 3 бесплатных демо-урока — можно провести открытое занятие и посмотреть, как курс работает:
🔗 Смотреть демо https://codim.online/teach/control/stream/view/id/245911461

💰 Тарифы и подключение:
🔗 Посмотреть тарифы https://codim.online/minecraft_teacher#registration

Если нужно — помогу с выбором 😊"""
        
        markup = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🏠 Главное меню", callback_data="menu")]
        ])
        
    elif course == "3d_tinkercad":
        message_text = """🧱 3D-моделирование в Tinkercad — курс, где дети от 7 до 14 лет учатся создавать собственные 3D-проекты с нуля!

🏗 Проектируют дома, машинки, роботов, украшения и другие объекты — фантазия ничем не ограничена!
Модели можно использовать:
🖨 для печати на 3D-принтере,
🎮 или даже импортировать в игровые движки, например, в Roblox Studio.

💻 Занятия проходят на платформе Tinkercad — это простой и удобный онлайн-сервис, который работает прямо в браузере. Ничего устанавливать не нужно.

👨‍🏫 Курс включает:
– 32 пошаговых урока,
– методику для преподавателя,
– презентации,
– рабочие листы,
– по желанию — видеоуроки от автора, чтобы увидеть, как он объясняет материал.

📥 Все материалы можно скачать и использовать без ограничений по времени.
🎬 📂 Все методические материалы (презентации, рабочие листы, планы уроков) остаются у вас навсегда — вы можете использовать их без ограничений в любое время.

🎥 Видео-уроки имеют ограниченный срок доступа, но его достаточно, чтобы изучить курс и внедрить в работу.
При необходимости доступ можно продлить — 1990₽ за месяц.

🎁 Хотите попробовать? Доступны 3 бесплатных демо-урока — можно протестировать курс или провести открытое занятие:
🔗 Смотреть демо https://codim.online/teach/control/stream/view/id/717247449

💰 Тарифы и варианты подключения:
🔗 Посмотреть тарифы https://codim.online/3d_tinkercad_teacher#registration

Если возникли вопросы — пишите, с радостью помогу 😊"""
        
        markup = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🏠 Главное меню", callback_data="menu")]
        ])
    
    elif course == "appinventor":
        message_text = """📱 App Inventor — курс по созданию мобильных приложений и игр для Android на блоках.

Идеально подходит для детей 10–14 лет, которые хотят создавать настоящие мобильные приложения без сложного программирования.

🎯 На курсе дети:
– Разрабатывают интерфейс приложений
– Программируют логику с помощью блоков
– Создают игры для Android
– Изучают основы мобильной разработки

👨‍🏫 Курс включает:
– 32 пошаговых урока,
– методику для преподавателя,
– презентации,
– рабочие листы,
– по желанию — видеоуроки от автора.

🎬 📂 Все методические материалы (презентации, рабочие листы, планы уроков) остаются у вас навсегда — вы можете использовать их без ограничений в любое время.

🎥 Видео-уроки имеют ограниченный срок доступа, но его достаточно, чтобы изучить курс и внедрить в работу.
При необходимости доступ можно продлить — 1990₽ за месяц.

🎁 Попробуйте 3 бесплатных демо-урока:
🔗 Смотреть демо https://codim.online/teach/control/stream/view/id/278739597

💰 Тарифы и подключение:
🔗 Посмотреть тарифы https://codim.online/appinventor_teacher#registration

Если возникли вопросы — пишите, с радостью помогу 😊"""
        
        markup = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🏠 Главное меню", callback_data="menu")]
        ])
    
    elif course == "unity_blocks":
        message_text = """🧩 Unity (Блоки) — идеальный старт в мире Unity для детей 11–13 лет.

Здесь мы создаём игры с помощью визуальных блоков, но уже на базе настоящего игрового движка Unity — того самого, на котором создаются популярные игры!

🎮 На курсе дети:
– Изучают основы игрового движка Unity
– Создают игры с помощью блоков
– Понимают логику игровой разработки
– Готовятся к переходу на настоящий код

👨‍🏫 Курс включает:
– 32 пошаговых урока,
– методику для преподавателя,
– презентации,
– рабочие листы,
– по желанию — видеоуроки от автора.

🎬 📂 Все методические материалы (презентации, рабочие листы, планы уроков) остаются у вас навсегда — вы можете использовать их без ограничений в любое время.

🎥 Видео-уроки имеют ограниченный срок доступа, но его достаточно, чтобы изучить курс и внедрить в работу.
При необходимости доступ можно продлить — 1990₽ за месяц.

🎁 Попробуйте 3 бесплатных демо-урока:
🔗 Смотреть демо https://codim.online/teach/control/stream/view/id/415678083

💰 Тарифы и подключение:
🔗 Посмотреть тарифы https://codim.online/unity_1_teacher#registration

Если возникли вопросы — пишите, с радостью помогу 😊"""
        
        markup = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🏠 Главное меню", callback_data="menu")]
        ])
    
    elif course == "roblox":
        message_text = """🎮 Roblox Studio — курс по созданию 3D-игр в Roblox на языке Lua.

Отлично подходит для детей 11–13 лет, которые хотят создавать собственные игры в популярной платформе Roblox.

🎯 На курсе дети:
– Создают собственные 3D-игры в Roblox
– Программируют поведение объектов на Lua
– Изучают основы игровой логики
– Публикуют свои игры для других игроков

👨‍🏫 Курс включает:
– 32 пошаговых урока,
– методику для преподавателя,
– презентации,
– рабочие листы,
– по желанию — видеоуроки от автора.

🎬 📂 Все методические материалы (презентации, рабочие листы, планы уроков) остаются у вас навсегда — вы можете использовать их без ограничений в любое время.

🎥 Видео-уроки имеют ограниченный срок доступа, но его достаточно, чтобы изучить курс и внедрить в работу.
При необходимости доступ можно продлить — 1990₽ за месяц.

🎁 Попробуйте 3 бесплатных демо-урока:
🔗 Смотреть демо https://codim.online/teach/control/stream/view/id/245997376

💰 Тарифы и подключение:
🔗 Посмотреть тарифы https://codim.online/roblox_teacher#registration

Если возникли вопросы — пишите, с радостью помогу 😊"""
        
        markup = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🏠 Главное меню", callback_data="menu")]
        ])
    
    elif course == "unity_csharp":
        message_text = """💻 Unity (C#) — курс по созданию игр на профессиональном движке Unity с настоящим кодом на C#.

Для детей 11–13 лет, которые готовы к серьёзному программированию и хотят создавать игры как настоящие разработчики.

🎯 На курсе дети:
– Изучают язык программирования C#
– Создают игры на движке Unity
– Понимают принципы объектно-ориентированного программирования
– Разрабатывают полноценные игровые проекты

👨‍🏫 Курс включает:
– 32 пошаговых урока,
– методику для преподавателя,
– презентации,
– рабочие листы,
– по желанию — видеоуроки от автора.

🎬 📂 Все методические материалы (презентации, рабочие листы, планы уроков) остаются у вас навсегда — вы можете использовать их без ограничений в любое время.

🎥 Видео-уроки имеют ограниченный срок доступа, но его достаточно, чтобы изучить курс и внедрить в работу.
При необходимости доступ можно продлить — 1990₽ за месяц.

🎁 Попробуйте 3 бесплатных демо-урока:
🔗 Смотреть демо https://codim.online/teach/control/stream/view/id/415678083

💰 Тарифы и подключение:
🔗 Посмотреть тарифы https://codim.online/unity_2_teacher#registration

Если возникли вопросы — пишите, с радостью помогу 😊"""
        
        markup = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🏠 Главное меню", callback_data="menu")]
        ])
    
    elif course == "python_minecraft":
        message_text = """🐢 Python в Minecraft — курс по программированию в Minecraft на языке Python.

Отлично подходит для детей 11–13 лет, которые уже начали изучать Python и хотят применить знания в увлекательной игре.

🎯 На курсе дети:
– Создают игровые сцены в Minecraft с помощью Python
– Пишут скрипты для автоматизации действий
– Изучают практическое применение Python
– Развивают навыки программирования в игровой форме

⚠️ Курс подойдёт тем, кто уже начал изучать Python.

👨‍🏫 Курс включает:
– 32 пошаговых урока,
– методику для преподавателя,
– презентации,
– рабочие листы,
– по желанию — видеоуроки от автора.

🎬 📂 Все методические материалы (презентации, рабочие листы, планы уроков) остаются у вас навсегда — вы можете использовать их без ограничений в любое время.

🎥 Видео-уроки имеют ограниченный срок доступа, но его достаточно, чтобы изучить курс и внедрить в работу.
При необходимости доступ можно продлить — 1990₽ за месяц.

🎁 Попробуйте 3 бесплатных демо-урока:
🔗 Смотреть демо https://codim.online/teach/control/stream/view/id/245455310

💰 Тарифы и подключение:
🔗 Посмотреть тарифы https://codim.online/pythonvm_teacher#registration

Если возникли вопросы — пишите, с радостью помогу 😊"""
        
        markup = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🏠 Главное меню", callback_data="menu")]
        ])
    
    elif course == "pygame":
        message_text = """🐍 Pygame — курс по созданию 2D-игр на Python.

Для детей 11–13 лет, которые уже знают Python и хотят создавать настоящие игры с графикой, звуком и анимацией.

🎯 На курсе дети:
– Создают 2D-игры на Python с помощью библиотеки Pygame
– Работают со спрайтами, анимацией и звуком
– Реализуют игровую логику (жизни, счёт, управление)
– Изучают основы игровой разработки

⚠️ Важно: требует знаний Python. Рекомендуем сначала пройти базовый курс Python.

👨‍🏫 Курс включает:
– 32 пошаговых урока,
– методику для преподавателя,
– презентации,
– рабочие листы,
– по желанию — видеоуроки от автора.

🎬 📂 Все методические материалы (презентации, рабочие листы, планы уроков) остаются у вас навсегда — вы можете использовать их без ограничений в любое время.

🎥 Видео-уроки имеют ограниченный срок доступа, но его достаточно, чтобы изучить курс и внедрить в работу.
При необходимости доступ можно продлить — 1990₽ за месяц.

🎁 Попробуйте 3 бесплатных демо-урока:
🔗 Смотреть демо https://codim.online/teach/control/stream/view/id/245455310

💰 Тарифы и подключение:
🔗 Посмотреть тарифы https://codim.online/pygame_teacher#registration

Если возникли вопросы — пишите, с радостью помогу 😊"""
        
        markup = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🏠 Главное меню", callback_data="menu")]
        ])
    
    elif course == "python_lvl_1":
        message_text = """🐍 Python для начинающих — пошаговое и понятное обучение Python с нуля.

Идеально подходит для детей 11–13 лет, которые хотят изучить один из самых популярных языков программирования.

🎯 На курсе дети:
– Изучают переменные, условия, циклы, списки
– Решают задачи на примерах и мини-проектах
– Понимают основы алгоритмического мышления
– Готовятся к более сложным курсам

👨‍🏫 Курс включает:
– 32 пошаговых урока,
– методику для преподавателя,
– презентации,
– рабочие листы,
– по желанию — видеоуроки от автора.

🎬 📂 Все методические материалы (презентации, рабочие листы, планы уроков) остаются у вас навсегда — вы можете использовать их без ограничений в любое время.

🎥 Видео-уроки имеют ограниченный срок доступа, но его достаточно, чтобы изучить курс и внедрить в работу.
При необходимости доступ можно продлить — 1990₽ за месяц.

🎁 Попробуйте 3 бесплатных демо-урока:
🔗 Смотреть демо https://codim.online/teach/control/stream/view/id/240471838

💰 Тарифы и подключение:
🔗 Посмотреть тарифы https://codim.online/python_teacher#registration

Если возникли вопросы — пишите, с радостью помогу 😊"""
        
        markup = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🏠 Главное меню", callback_data="menu")]
        ])
    
    elif course == "python_lvl_2":
        message_text = """🐍 Python Уровень 2 — продолжение изучения Python для детей 11–13 лет.

Отлично подходит после базового курса Python для углубления знаний и создания более серьёзных проектов.

🎯 На курсе дети:
– Изучают функции, работу с файлами, словари
– Осваивают математику в коде
– Создают более серьёзные проекты
– Готовятся к специализированным курсам

👨‍🏫 Курс включает:
– 32 пошаговых урока,
– методику для преподавателя,
– презентации,
– рабочие листы,
– по желанию — видеоуроки от автора.

🎬 📂 Все методические материалы (презентации, рабочие листы, планы уроков) остаются у вас навсегда — вы можете использовать их без ограничений в любое время.

🎥 Видео-уроки имеют ограниченный срок доступа, но его достаточно, чтобы изучить курс и внедрить в работу.
При необходимости доступ можно продлить — 1990₽ за месяц.

🎁 Попробуйте 3 бесплатных демо-урока:
🔗 Смотреть демо https://codim.online/teach/control/stream/view/id/745210336

💰 Тарифы и подключение:
🔗 Посмотреть тарифы https://codim.online/python2_teacher#registration

Если возникли вопросы — пишите, с радостью помогу 😊"""
        
        markup = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🏠 Главное меню", callback_data="menu")]
        ])
    
    elif course == "telegram_bots":
        message_text = """🤖 Создание телеграм-ботов на Python — очень прикладной курс для детей 11–13 лет.

Учимся автоматизировать задачи и писать собственных ботов для Telegram — навык, который пригодится в жизни!

🎯 На курсе дети:
– Изучают API Telegram
– Создают ботов на Python
– Автоматизируют различные задачи
– Публикуют ботов для использования

⚠️ Подходит тем, кто уже прошёл хотя бы базовый Python.

👨‍🏫 Курс включает:
– 32 пошаговых урока,
– методику для преподавателя,
– презентации,
– рабочие листы,
– по желанию — видеоуроки от автора.

🎬 📂 Все методические материалы (презентации, рабочие листы, планы уроков) остаются у вас навсегда — вы можете использовать их без ограничений в любое время.

🎥 Видео-уроки имеют ограниченный срок доступа, но его достаточно, чтобы изучить курс и внедрить в работу.
При необходимости доступ можно продлить — 1990₽ за месяц.

🎁 Попробуйте 3 бесплатных демо-урока:
🔗 Смотреть демо https://codim.online/teach/control/stream/view/id/934432479

💰 Тарифы и подключение:
🔗 Посмотреть тарифы https://codim.online/tg_bot_teacher#registration

Если возникли вопросы — пишите, с радостью помогу 😊"""
        
        markup = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🏠 Главное меню", callback_data="menu")]
        ])
    
    elif course == "java":
        message_text = """☕️ Основы Java — пошаговое введение в язык Java для детей 11–13 лет.

Подходит для школьников, кто хочет двигаться в сторону инженерных и серьёзных направлений программирования.

🎯 На курсе дети:
– Изучают базовые конструкции Java
– Понимают принципы объектно-ориентированного программирования
– Решают задачи на логику и алгоритмы
– Готовятся к серьёзной разработке

👨‍🏫 Курс включает:
– 32 пошаговых урока,
– методику для преподавателя,
– презентации,
– рабочие листы,
– по желанию — видеоуроки от автора.

🎬 📂 Все методические материалы (презентации, рабочие листы, планы уроков) остаются у вас навсегда — вы можете использовать их без ограничений в любое время.

🎥 Видео-уроки имеют ограниченный срок доступа, но его достаточно, чтобы изучить курс и внедрить в работу.
При необходимости доступ можно продлить — 1990₽ за месяц.

🎁 Попробуйте 3 бесплатных демо-урока:
🔗 Смотреть демо https://codim.online/teach/control/stream/view/id/680288877

💰 Тарифы и подключение:
🔗 Посмотреть тарифы https://codim.online/java_teacher#registration

Если возникли вопросы — пишите, с радостью помогу 😊"""
        
        markup = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🏠 Главное меню", callback_data="menu")]
        ])
    
    await callback.message.answer(message_text, reply_markup=markup)
    await callback.answer()

# Обработчики для средних классов (11-13 лет)
@router.callback_query(F.data.startswith("teacher_games:"))
async def handle_teacher_games_selection(callback: CallbackQuery, state: FSMContext):
    """Обработка выбора типа игр для средних классов"""
    game_type = callback.data.split(":")[1]
    
    if game_type == "blocks":
        message_text = """🎨 Отлично! Вот несколько курсов по созданию игр на блоках, которые идеально подойдут для детей 11–13 лет:

🌍 Scratch: Большое путешествие (9–13 лет)
Программируем в Scratch с английскими блоками, создаём мини-игры по мотивам стран мира и изучаем базовые алгоритмы.

⛏️ Minecraft: основы программирования (7–13 лет)
Управляем черепашкой-программистом в мире Minecraft — создаём игровые сцены, решаем логические задачи, программируем поведение.

🕶 CoSpaces (8–14 лет)
Создаём собственные 3D-игры и виртуальные миры, которые можно просматривать даже в VR. Очень креативный и технологичный курс.

📱 App Inventor (10–14 лет)
Создание мобильных приложений и игр для Android на блоках. Ребёнок разрабатывает интерфейс и программирует логику без кода.

🧩 Unity (Блоки)
Идеальный старт в мире Unity. Здесь мы создаём игры с помощью визуальных блоков, но уже на базе настоящего игрового движка.

👇 Какой курс вас заинтересовал? Расскажу подробнее и пришлю ссылку на демо-уроки:"""
        
        markup = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🌍 Scratch: Большое путешествие", callback_data="teacher_course:scratch_3")],
            [InlineKeyboardButton(text="⛏️ Minecraft", callback_data="teacher_course:minecraft")],
            [InlineKeyboardButton(text="🕶 CoSpaces", callback_data="teacher_course:cospaces")],
            [InlineKeyboardButton(text="📱 App Inventor", callback_data="teacher_course:appinventor")],
            [InlineKeyboardButton(text="🧩 Unity (Блоки)", callback_data="teacher_course:unity_blocks")],
            [InlineKeyboardButton(text="🏠 Главное меню", callback_data="menu")]
        ])
        
    elif game_type == "code":
        message_text = """💻 Отлично! Вот курсы по созданию игр с помощью настоящего кода, которые подойдут для детей 11–13 лет:

🎮 Roblox Studio (на Lua)
Ученики создают свои собственные 3D-игры в Roblox, программируют поведение объектов и взаимодействие игроков. Простая и доступная среда для первых игр с кодом.

🧩 Unity (Блоки)
Идеальный старт в мире Unity. Здесь мы создаём игры с помощью визуальных блоков, но уже на базе настоящего игрового движка.
📌 После прохождения можно перейти к курсу Unity на C#, где дети начнут писать код вручную.

💻 Unity (C#)
Создание игр на профессиональном движке Unity с настоящим кодом на C#. Для тех, кто готов к серьёзному программированию.

🐢 Python в Minecraft
Создаём игровые сцены и управляем миром Minecraft с помощью настоящего кода на Python!
Работаем в обучающей версии Minecraft, пишем скрипты, автоматизируем действия. Очень наглядно и интересно!
⚠️ Курс подойдёт тем, кто уже начал изучать Python.

🐍 Pygame на Python
Создаём настоящие 2D-игры на Python — со спрайтами, жизнями, счётом и управлением.
⚠️ Важно: требует знаний Python. Рекомендуем сначала пройти базовый курс, хотя бы первые модули.

👇 О каком курсе рассказать подробнее и прислать демо-уроки?"""
        
        markup = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🎮 Roblox", callback_data="teacher_course:roblox")],
            [InlineKeyboardButton(text="🧩 Unity (Блоки)", callback_data="teacher_course:unity_blocks")],
            [InlineKeyboardButton(text="💻 Unity (C#)", callback_data="teacher_course:unity_csharp")],
            [InlineKeyboardButton(text="🐢 Python в Minecraft", callback_data="teacher_course:python_minecraft")],
            [InlineKeyboardButton(text="🐍 Pygame", callback_data="teacher_course:pygame")],
            [InlineKeyboardButton(text="🏠 Главное меню", callback_data="menu")]
        ])
    
    await callback.message.answer(message_text, reply_markup=markup)
    await callback.answer()

@router.callback_query(F.data == "teacher_langs")
async def handle_teacher_langs(callback: CallbackQuery, state: FSMContext):
    """Обработка выбора изучения языков программирования для средних классов"""
    message_text = """👨‍💻 Отличный выбор! Вот курсы по изучению языков программирования, которые подойдут для возраста 11–13 лет:

🐍 Python для начинающих
Пошаговое и понятное обучение Python с нуля. Учим переменные, условия, циклы, списки — всё на примерах и мини-проектах.

🐍 Python Уровень 2
Продолжение: изучаем функции, работу с файлами, словари, математику в коде и создаём более серьёзные проекты. Отлично подходит после базового курса.

🤖 Создание телеграм-ботов на Python
Учимся автоматизировать задачи и писать собственных ботов для Telegram. Очень прикладной курс.
⚠️ Подходит тем, кто уже прошёл хотя бы базовый Python.

☕️ Основы Java
Пошаговое введение в язык Java: базовые конструкции, логика, классы. Подходит для школьников, кто хочет двигаться в сторону инженерных и серьёзных направлений.

👇 Какой курс вас интересует? Я пришлю описание, демо и тарифы:"""
    
    markup = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🐍 Python для начинающих", callback_data="teacher_course:python_lvl_1")],
        [InlineKeyboardButton(text="🐍 Python Уровень 2", callback_data="teacher_course:python_lvl_2")],
        [InlineKeyboardButton(text="🤖 Telegram-боты", callback_data="teacher_course:telegram_bots")],
        [InlineKeyboardButton(text="☕️ Java", callback_data="teacher_course:java")],
        [InlineKeyboardButton(text="🏠 Главное меню", callback_data="menu")]
    ])
    
    await callback.message.answer(message_text, reply_markup=markup)
    await callback.answer()

