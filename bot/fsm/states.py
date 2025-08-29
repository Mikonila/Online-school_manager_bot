from aiogram.fsm.state import State, StatesGroup

class FSMGenerator(StatesGroup):
    asking = State()

class FSMGoal(StatesGroup):
    setting = State()