from aiogram.fsm.state import State, StatesGroup

class FSMObjection(StatesGroup):
    handling = State()

class FSMGenerator(StatesGroup):
    asking = State()

class FSMGoal(StatesGroup):
    setting = State()

class FSMPresenter(StatesGroup):
    presenting = State()

# Агент-обработчик возражений не требует отдельного состояния — он срабатывает на любое сообщение при необходимости
