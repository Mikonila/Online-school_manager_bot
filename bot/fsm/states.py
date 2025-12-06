from aiogram.fsm.state import State, StatesGroup

class FSMGenerator(StatesGroup):
    asking = State()

class FSMGoal(StatesGroup):
    setting = State()

class CourseSelection(StatesGroup):
    interest = State()
    age = State()
    experience = State()
    stack = State()
    recommend = State()

class TeacherDialog(StatesGroup):
    waiting_for_age = State()
    waiting_for_interest = State()
    waiting_for_experience = State()
    waiting_for_stack = State()
    waiting_for_recommendation = State()

class CourseSearch(StatesGroup):
    waiting_for_course_name = State()