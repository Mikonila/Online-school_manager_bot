
from aiogram import Router, F
from aiogram.types import Message
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.filters import StateFilter
import logging

from bot.services.gpt_engine import ask_gpt
from bot.database.models import log_interaction
from bot.services.search_engine import search_knowledge

# Подключаем агентов
from bot.handlers.agents import generator, goal_setter, presenter, objections

router = Router()
router.include_router(generator.router)
router.include_router(goal_setter.router)
router.include_router(presenter.router)
router.include_router(objections.router)

logger = logging.getLogger(__name__)

MANAGER_CHAT_ID = -1002290856432  # <-- Укажи здесь chat_id группы менеджеров

class UserDialog(StatesGroup):
    waiting_for_intro = State()
    waiting_for_question = State()
    waiting_for_demo_confirmation = State()


course_links_dict = {
    "https://codim.online/scratch_1": "https://codim.online/teach/control/stream/view/id/567829098",
    "https://codim.online/python": "https://codim.online/teach/control/stream/view/id/240471838",
    "https://codim.online/web": "https://codim.online/teach/control/stream/view/id/654038330",
    "https://codim.online/scratch_2": "https://codim.online/teach/control/stream/view/id/652143767",
    "https://codim.online/scratch_3": "https://codim.online/teach/control/stream/view/id/195941430",
    "https://codim.online/scratchHM": "https://codim.online/teach/control/stream/view/id/594957266",
    "https://codim.online/minecraft": "https://codim.online/teach/control/stream/view/id/245911461",
    "https://codim.online/roblox": "https://codim.online/teach/control/stream/view/id/245997376",
    "https://codim.online/java": "https://codim.online/teach/control/stream/view/id/680288877",
    "https://codim.online/ai": "https://codim.online/teach/control/stream/view/id/933999792",
    "https://codim.online/arduino": "https://codim.online/teach/control/stream/view/id/130440314",
    "https://codim.online/scratchjr": "https://codim.online/teach/control/stream/view/id/246490381",
    "https://codim.online/minecraftjr": "https://codim.online/teach/control/stream/view/id/35104782",
    "https://codim.online/paint": "https://codim.online/teach/control/stream/view/id/178616311",
    "https://codim.online/risovanie": "https://codim.online/teach/control/stream/view/id/360065846",
    "https://codim.online/Cospaces": "https://codim.online/teach/control/stream/view/id/160082603",
    "https://codim.online/Unity_2": "https://codim.online/teach/control/stream/view/id/415678083",
    "https://codim.online/appinventor": "https://codim.online/teach/control/stream/view/id/278739597",
    "https://codim.online/pygame": "https://codim.online/teach/control/stream/view/id/245455310",
    "https://codim.online/python2": "https://codim.online/teach/control/stream/view/id/745210336",
    "https://codim.online/pythonvm": "https://codim.online/teach/control/stream/view/id/245455310",
    "https://codim.online/colobot": "https://codim.online/teach/control/stream/view/id/410001583",
    "https://codim.online/space": "https://codim.online/teach/control/stream/view/id/311215818",
    "https://codim.online/gimp": "https://codim.online/teach/control/stream/view/id/139296514",
    "https://codim.online/helion": "https://codim.online/helion_demo",
    "https://codim.online/3d": "https://codim.online/teach/control/stream/view/id/257930249"
}

@router.message(F.text == "/getchatid")
async def get_chat_id(message: Message):
    await message.answer(f"Chat ID: `{message.chat.id}`", parse_mode="Markdown")

@router.message(F.text == "/start")
async def cmd_start(message: Message, state: FSMContext):
    await message.answer(
        "Здравствуйте, спасибо за интерес к школе программирования Codim.online. Я виртуальный помощник и помогу вам с выбором оптимального курса, расскажу о форматах обучения и тарифах. Выберите вариант:\n"
        "1. Подобрать курс\n"
        "2. Посмотреть демо-уроки\n"
        "3. Узнать стоимость и форматы обучения"
    )
    await state.set_state(UserDialog.waiting_for_intro)

@router.message(StateFilter(UserDialog.waiting_for_intro))
async def handle_intro_options(message: Message, state: FSMContext):
    text = message.text.strip().lower()

    if text in ["1", "подобрать курс", "подобрать"]:
        await message.answer(
            "Отлично! Ответьте, пожалуйста, на пару коротких вопросов:\n"
            "1. Сколько лет вашему ребенку?\n"
            "2. Уже пробовал(а) программировать или только начинает?\n"
            "3. Что больше интересно: игры, мультфильмы, роботы, дизайн или что-то ещё?"
        )
        await state.set_state(UserDialog.waiting_for_question)

    elif text in ["2", "посмотреть демо", "демо", "демо-уроки"]:
        await message.answer(
            "Вот подборка бесплатных демо-уроков по самым популярным курсам:\n"
            " • Scratch Junior (5–7 лет)\n"
            " • Minecraft (7–13 лет)\n"
            " • Python (9+ лет)\n"
            " • Roblox (9+ лет)\n\n"
            "У нас более 30 курсов, хотите, я помогу выбрать подходящий?"
        )
        await state.set_state(UserDialog.waiting_for_demo_confirmation)

    elif text in ["3", "узнать цены", "цены", "стоимость", "форматы", "тарифы"]:
        await message.answer(
            "У нас есть:\n"
            " • Подписка — доступ ко всем урокам на 30 дней (от 6 990₽).\n"
            " • PRO-тариф — полный курс на 240 дней с возможностью заморозки.\n"
            " • Индивидуальные занятия с преподавателем в Zoom.\n\n"
            "Напиши возраст ребенка — покажу конкретные предложения!"
        )

    else:
        data = await state.get_data()
        history = data.get("history", "")
        history += f"\nПользователь: {message.text}"
        knowledge = await search_knowledge(message.text)

        answer = await ask_gpt(
            question=message.text,
            knowledge=knowledge,
            history=history,
            agent_prompt_file="generator.md"
        )
        history += f"\nБот: {answer}"
        await state.update_data(history=history)
        await message.answer(answer)

@router.message(StateFilter(UserDialog.waiting_for_demo_confirmation))
async def handle_demo_confirmation(message: Message, state: FSMContext):
    text = message.text.lower()
    if text in ["да", "хочу", "давай", "ага"]:
        await message.answer("Для просмотра демо-уроков потребуется регистрация. Вот ссылка: https://codim.online/teach/demo")
    else:
        await message.answer("Хорошо, если появятся вопросы — я на связи!")
    await state.clear()
@router.message(StateFilter(UserDialog.waiting_for_question))
async def process_question(message: Message, state: FSMContext):
    import json
    try:
        logger.info(f"Получен ответ от пользователя: {message.text}")
        data = await state.get_data()

        text = message.text.lower()
        history = data.get("history", "")
        history += f"\nПользователь: {message.text}"

        # Получаем знания и ответ от GPT
        knowledge = await search_knowledge(message.text)
        logger.info(f"Поиск знаний прошёл успешно. Длина ответа: {len(knowledge)} символов")

        gpt_response = await ask_gpt(
            question=message.text,
            knowledge=knowledge,
            history=history,
            agent_prompt_file="generator.md"
        )

        # Пробуем распарсить JSON из ответа
        try:
            gpt_data = json.loads(gpt_response)
            age = str(gpt_data.get("age", "неизвестно"))  # 👈 преобразуем в строку
            experience = gpt_data.get("experience", "не указано")
            role = gpt_data.get("interests", "не указано")
            answer = gpt_data.get("recommendation", "")
        except Exception:
            # fallback, если ответ не JSON
            age = data.get("age", "неизвестно")
            experience = data.get("experience", "не указано")
            role = data.get("role", "не указано")
            answer = gpt_response

        await state.update_data(age=age, experience=experience, role=role)

        # Добавляем ссылку на демо, если в ответе найден курс
        for course_url, demo_url in course_links_dict.items():
            if course_url in answer and demo_url not in answer:
                answer += f"\n\n🔗 Ссылка на демо-урок: {demo_url}"

        history += f"\nБот: {answer}"
        await state.update_data(history=history)

        await log_interaction(
            user_id=message.from_user.id,
            age=age,
            experience=experience,
            question=message.text,
            answer=answer
        )

        await message.answer(answer)

        log_text = (
            f"📩 *Новая заявка*\n"
            f"👤 ID: `{message.from_user.id}`\n"
            f"👨‍🎓 Имя: {message.from_user.full_name}\n"
            f"🔗 Username: @{message.from_user.username or '—'}\n"
            f"🎂 Возраст: {age}\n"
            f"🧠 Опыт: {experience}\n"
            f"🎯 Интересы: {role}\n"
            f"❓ Вопрос:\n{message.text}\n"
            f"🤖 Ответ:\n{answer}"
        )

        await message.bot.send_message(MANAGER_CHAT_ID, log_text, parse_mode="Markdown")

    except Exception as e:
        logger.exception("Ошибка при обработке пользовательского запроса в waiting_for_question")
        await message.answer(
            "Что-то пошло не так при подборе курса 😔\nПопробуйте снова или выберите другой вариант."
        )
