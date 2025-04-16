from aiogram import Router
from aiogram.types import Message
from aiogram.fsm.context import FSMContext
from aiogram.filters import StateFilter
from bot.services.gpt_engine import ask_gpt
from bot.fsm.states import FSMGenerator, FSMGoal
from bot.services.search_engine import search_knowledge
import logging

router = Router()

@router.message(StateFilter(FSMGenerator.asking))
async def handle_generator(message: Message, state: FSMContext):
    data = await state.get_data()

    # Формируем user_data
    user_data = f"Возраст: {data.get('age', 'не указано')}, Опыт: {data.get('experience', 'не указан')}"

    # История переписки: сразу добавим текущее сообщение
    previous_history = data.get("history", "")
    current_input = f"\nПользователь: {message.text}"
    history = previous_history + current_input

    # Загрузка знаний
    knowledge = await search_knowledge(message.text)

    # Вызов GPT
    gpt_reply = await ask_gpt(
        question=message.text,
        agent_prompt_file="generator.md",
        history=history,
        user_data=user_data,
        knowledge=knowledge
    )

    # Обновление истории
    full_history = history + f"\nБот: {gpt_reply}"
    await state.update_data(history=full_history)

    await message.answer(gpt_reply)

    # Обновляем признаки по ключевым словам
    interests_collected = data.get("interests_collected", False)
    goals_collected = data.get("goals_collected", False)

    if "интерес" in message.text.lower():
        await state.update_data(interests=message.text, interests_collected=True)
        interests_collected = True

    if "цель" in message.text.lower():
        await state.update_data(goals=message.text, goals_collected=True)
        goals_collected = True

    # Переход к следующему агенту
    if interests_collected and goals_collected:
        await state.set_state(FSMGoal.setting)
        logging.info("✅ Переход к FSMGoal.setting")
