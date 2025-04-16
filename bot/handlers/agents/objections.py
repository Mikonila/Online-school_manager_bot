from aiogram import Router, F
from aiogram.types import Message
from aiogram.fsm.context import FSMContext
from bot.services.gpt_engine import ask_gpt
from bot.fsm.states import FSMObjection

router = Router()

@router.message(FSMObjection.handling)
async def objections_agent(message: Message, state: FSMContext):
    data = await state.get_data()
    history = data.get("history", "")

    gpt_reply = await ask_gpt(
        user_message=message.text,
        prompt_name="objections",
        history=history
    )

    full_history = history + f"\nПользователь: {message.text}\nАгент: {gpt_reply}"
    await state.update_data(history=full_history)

    await message.answer(gpt_reply)
