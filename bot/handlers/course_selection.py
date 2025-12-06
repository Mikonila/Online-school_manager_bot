"""
Обработчики для системы подбора курсов
"""

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.filters import StateFilter
from bot.fsm.states import CourseSelection, TeacherDialog
from bot.services.course_logic import find_matching_courses, format_recommendations
from bot.services.course_descriptions import format_course_info, get_course_price_info, course_name_to_slug, get_course_description
from bot.services.gpt_engine import ask_gpt
import logging

logger = logging.getLogger(__name__)
router = Router()

# Клавиатуры для каждого состояния
def get_interest_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура для выбора интереса"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Создание игр", callback_data="interest:games")],
        [InlineKeyboardButton(text="Язык программирования", callback_data="interest:langs")],
        [InlineKeyboardButton(text="Создание телеграм-ботов", callback_data="interest:tg_bots")],
        [InlineKeyboardButton(text="Создание сайтов и приложений", callback_data="interest:web_apps")],
        [InlineKeyboardButton(text="Искусственный интеллект", callback_data="interest:ai")],
        [InlineKeyboardButton(text="Роботы", callback_data="interest:robots")],
        [InlineKeyboardButton(text="Дизайн", callback_data="interest:design")],
        [InlineKeyboardButton(text="3D", callback_data="interest:3d")],
        [InlineKeyboardButton(text="🏠 В меню", callback_data="menu")],
        [InlineKeyboardButton(text="⬅ Назад", callback_data="back")]
    ])

def get_age_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура для выбора возраста"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="5–6", callback_data="age:5_6")],
        [InlineKeyboardButton(text="7–8", callback_data="age:7_8")],
        [InlineKeyboardButton(text="9–11", callback_data="age:9_11")],
        [InlineKeyboardButton(text="12+", callback_data="age:12_plus")],
        [InlineKeyboardButton(text="🏠 В меню", callback_data="menu")],
        [InlineKeyboardButton(text="⬅ Назад", callback_data="back")]
    ])

def get_experience_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура для выбора опыта"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Да", callback_data="exp:yes")],
        [InlineKeyboardButton(text="Нет", callback_data="exp:no")],
        [InlineKeyboardButton(text="🏠 В меню", callback_data="menu")],
        [InlineKeyboardButton(text="⬅ Назад", callback_data="back")]
    ])

def get_stack_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура для выбора стека"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Блоки (Scratch/Minecraft)", callback_data="stack:blocks")],
        [InlineKeyboardButton(text="Языки (Python/Java)", callback_data="stack:langs")],
        [InlineKeyboardButton(text="Другое", callback_data="stack:other")],
        [InlineKeyboardButton(text="🏠 В меню", callback_data="menu")],
        [InlineKeyboardButton(text="⬅ Назад", callback_data="back")]
    ])

def get_recommendation_keyboard(courses: list) -> InlineKeyboardMarkup:
    """Клавиатура для рекомендаций - только названия курсов"""
    buttons = []
    
    # Кнопки для каждого курса
    for course in courses:
        if course == "Хочу начать учить Python с нуля":
            buttons.append([InlineKeyboardButton(text=f"🐍 {course}", callback_data="python_from_scratch")])
        else:
            buttons.append([InlineKeyboardButton(text=f"📚 {course}", callback_data=f"course_info:{course}")])
    
    # Если рекомендован только один курс, добавляем кнопки Демо и Тарифы
    if len(courses) == 1 and courses[0] != "Хочу начать учить Python с нуля":
        course_name = courses[0]
        # Преобразуем название курса в slug для кнопок
        course_slug = course_name.lower().replace(" ", "_").replace("level", "lvl")
        if "python" in course_slug:
            course_slug = "python_lvl_1" if "1" in course_slug else "python_lvl_2"
        elif "scratch" in course_slug:
            course_slug = "scratch_lvl_1" if "1" in course_slug else "scratch_lvl_2"
        elif "minecraft" in course_slug:
            course_slug = "minecraft"
        elif "roblox" in course_slug:
            course_slug = "roblox"
        elif "unity" in course_slug:
            course_slug = "unity_lvl_1" if "1" in course_slug else "unity_lvl_2"
        elif "appinventor" in course_slug or "app" in course_slug:
            course_slug = "appinventor"
        elif "web" in course_slug or "веб" in course_slug:
            course_slug = "web_development"
        elif "java" in course_slug:
            course_slug = "java"
        elif "ai" in course_slug or "ии" in course_slug:
            course_slug = "ai_simple"
        else:
            course_slug = "general"
        
        buttons.extend([
            [InlineKeyboardButton(text="🎬 Посмотреть демо", callback_data=f"course_info:{course_name}")],
            [InlineKeyboardButton(text="💰 Узнать тарифы", callback_data=f"course_price:{course_slug}")]
        ])
    
    # Кнопка "Посмотреть все курсы" (если есть несколько курсов)
    if len(courses) > 1:
        buttons.append([InlineKeyboardButton(text="🌐 Посмотреть все курсы", url="https://codim.online/demo1/entrance")])
    
    # Кнопки навигации
    buttons.extend([
        [InlineKeyboardButton(text="🏠 В меню", callback_data="menu")],
        [InlineKeyboardButton(text="⬅ Назад", callback_data="back")]
    ])
    
    return InlineKeyboardMarkup(inline_keyboard=buttons)

# Обработчики для каждого состояния
@router.callback_query(F.data == "start_pick")
async def start_course_selection(callback: CallbackQuery, state: FSMContext):
    """Начинаем подбор курса"""
    await callback.message.answer(
        "🎯 Отлично! Давайте подберем идеальный курс для вас.\n\n"
        "Сначала скажите, какой у вас возраст?",
        reply_markup=get_age_keyboard()
    )
    await state.set_state(CourseSelection.age)
    await callback.answer()

@router.callback_query(F.data.startswith("interest:"))
async def handle_interest_selection(callback: CallbackQuery, state: FSMContext):
    """Обработка выбора интереса"""
    interest = callback.data.split(":")[1]
    await state.update_data(interest=interest)
    
    # Отладочная информация
    logger.info(f"Выбран интерес: {interest}")
    
    # Проверяем, это преподаватель или обычный пользователь
    current_state = await state.get_state()
    is_teacher = current_state and "TeacherDialog" in str(current_state)
    
    # Для ИИ, дизайна и 3D сразу переходим к рекомендациям, минуя вопрос об опыте
    if interest in ["ai", "design", "3d"]:
        logger.info(f"Пропускаем вопрос об опыте для интереса: {interest}")
        if interest == "ai":
            message = "Отлично! Сейчас подберу идеальный курс по искусственному интеллекту!" if not is_teacher else "Отлично! Сейчас подберу идеальный курс по искусственному интеллекту для ваших учеников!"
        elif interest == "design":
            message = "Отлично! Сейчас подберу идеальные курсы по дизайну!" if not is_teacher else "Отлично! Сейчас подберу идеальные курсы по дизайну для ваших учеников!"
        else:  # 3d
            message = "Отлично! Сейчас подберу идеальные курсы по 3D-моделированию!" if not is_teacher else "Отлично! Сейчас подберу идеальные курсы по 3D-моделированию для ваших учеников!"
        
        await callback.message.answer(message)
        await generate_recommendations(callback.message, state, is_teacher=is_teacher)
    else:
        logger.info(f"Спрашиваем опыт для интереса: {interest}")
        question = "Есть ли опыт в программировании?" if not is_teacher else "Есть ли у ваших учеников опыт в программировании?"
        await callback.message.answer(
            question,
            reply_markup=get_experience_keyboard()
        )
        # Устанавливаем правильное состояние в зависимости от того, преподаватель это или нет
        if is_teacher:
            await state.set_state(TeacherDialog.waiting_for_experience)
        else:
            await state.set_state(CourseSelection.experience)
    
    await callback.answer()

@router.callback_query(F.data.startswith("age:"))
async def handle_age_selection(callback: CallbackQuery, state: FSMContext):
    """Обработка выбора возраста"""
    age = callback.data.split(":")[1]
    await state.update_data(age=age)
    
    # Проверяем, это преподаватель или обычный пользователь
    current_state = await state.get_state()
    is_teacher = current_state and "TeacherDialog" in str(current_state)
    
    # Для младших возрастов (5-6 и 7-8) сразу переходим к рекомендациям
    if age in ["5_6", "7_8"]:
        if is_teacher:
            message = "Отлично! Для возраста ваших учеников у нас есть специальные курсы. Сейчас подберу идеальные варианты!"
        else:
            message = "Отлично! Для вашего возраста у нас есть специальные курсы. Сейчас подберу идеальные варианты!"
        await callback.message.answer(message)
        await generate_recommendations(callback.message, state, is_teacher=is_teacher)
    else:
        # Для старших возрастов (9-11 и 12+) спрашиваем про интересы
        if is_teacher:
            message = "Отлично! Теперь скажите, что больше всего интересует ваших учеников?"
        else:
            message = "Отлично! Теперь скажите, что бы вы хотели изучать?"
        await callback.message.answer(
            message,
            reply_markup=get_interest_keyboard()
        )
        await state.set_state(CourseSelection.interest)
    
    await callback.answer()

@router.callback_query(F.data.startswith("exp:"))
async def handle_experience_selection(callback: CallbackQuery, state: FSMContext):
    """Обработка выбора опыта"""
    exp = callback.data.split(":")[1]
    await state.update_data(exp=exp)
    
    # Проверяем, это преподаватель или обычный пользователь
    current_state = await state.get_state()
    is_teacher = current_state and "TeacherDialog" in str(current_state)
    
    if exp == "yes":
        # Если есть опыт, спрашиваем про стек
        question = "Что изучали раньше?" if not is_teacher else "Что изучали ваши ученики раньше?"
        await callback.message.answer(
            question,
            reply_markup=get_stack_keyboard()
        )
        # Устанавливаем правильное состояние в зависимости от того, преподаватель это или нет
        if is_teacher:
            await state.set_state(TeacherDialog.waiting_for_stack)
        else:
            await state.set_state(CourseSelection.stack)
    else:
        # Если нет опыта, сразу переходим к рекомендациям
        await generate_recommendations(callback.message, state, is_teacher=is_teacher)
    
    await callback.answer()

@router.callback_query(F.data.startswith("stack:"))
async def handle_stack_selection(callback: CallbackQuery, state: FSMContext):
    """Обработка выбора стека"""
    stack = callback.data.split(":")[1]
    await state.update_data(stack=stack)
    
    # Проверяем, это преподаватель или обычный пользователь
    current_state = await state.get_state()
    is_teacher = current_state and "TeacherDialog" in str(current_state)
    
    await generate_recommendations(callback.message, state, is_teacher=is_teacher)
    await callback.answer()

@router.callback_query(F.data == "stack:other")
async def handle_stack_other(callback: CallbackQuery, state: FSMContext):
    """Обработка выбора 'Другое' в стеке"""
    await state.update_data(stack="other")
    
    # Проверяем, это преподаватель или обычный пользователь
    current_state = await state.get_state()
    is_teacher = current_state and "TeacherDialog" in str(current_state)
    
    if is_teacher:
        message = "📝 Понятно! У ваших учеников есть другой опыт в программировании.\n\nДавайте подберем курсы, которые подойдут именно им!"
    else:
        message = "📝 Понятно! У вас есть другой опыт в программировании.\n\nДавайте подберем курс, который подойдет именно вам!"
    
    await callback.message.answer(message)
    
    # Переходим к рекомендациям
    await generate_recommendations(callback.message, state, is_teacher=is_teacher)
    await callback.answer()

async def generate_recommendations(message: Message, state: FSMContext, is_teacher=False):
    """Генерирует рекомендации через GPT на основе данных пользователя"""
    data = await state.get_data()
    
    # Получаем рекомендации от алгоритма
    recommendations = find_matching_courses(data)
    
    # Специальная обработка для Telegram ботов
    if (data.get('interest') == 'tg_bots' and 
        data.get('age') == '12_plus' and 
        data.get('exp') == 'no'):
        
        special_message = """🤖 Отличный выбор! <b>Создание Telegram-ботов</b> — это увлекательный курс, но для него нужна подготовка.

📚 <b>Рекомендуем для начала пройти курс Python Level 1</b> — это даст вашему ребёнку необходимую базу для создания ботов. Python — это язык, на котором пишутся Telegram-боты, и без понимания основ программирования будет сложно.

🎯 <b>Требования для курса "Создание Telegram-ботов":</b>
• Возраст от 13 лет
• Опыт программирования на Python
• Базовые знания алгоритмов и логики

💡 Если вы хотите начать сразу с курса по созданию Telegram-ботов, то курс включает 16 уроков, где ребёнок научится создавать умных ботов: чат-ботов, помощников, мини-игры и даже сервисы с элементами ИИ. Но для успешного прохождения нужен опыт в Python.

📌 Что выберете: начать с Python Level 1 или сразу попробовать Telegram-боты?"""
        
        # Создаем специальную клавиатуру с обеими опциями
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📚 Python Level 1", callback_data="course_info:Python Level 1")],
            [InlineKeyboardButton(text="🎬 Посмотреть демо", callback_data="course_info:Создание телеграм-ботов")],
            [InlineKeyboardButton(text="💰 Узнать стоимость", callback_data="course_price:telegram_bots")],
            [InlineKeyboardButton(text="🌐 Посмотреть все курсы", url="https://codim.online/demo1/entrance")],
            [InlineKeyboardButton(text="🏠 В меню", callback_data="menu")],
            [InlineKeyboardButton(text="⬅ Назад", callback_data="back")]
        ])
        
        # Отправляем специальное сообщение
        await message.answer(special_message, reply_markup=keyboard, parse_mode="HTML")
        await state.set_state(CourseSelection.recommend)
        return
    
    # Специальная обработка для Telegram ботов 12+ с опытом в блоках (Scratch/Minecraft)
    if (data.get('interest') == 'tg_bots' and 
        data.get('age') == '12_plus' and 
        data.get('exp') == 'yes' and 
        data.get('stack') == 'blocks'):
        
        special_message = """Привет! Здорово, что вашему ребёнку интересно создание Telegram-ботов — это отличное направление!

Курс действительно крутой, но если он ещё не программировал на Python, рекомендую сначала пройти курс "Python для начинающих" — хотя бы 1–2 модуля. Это поможет быстро освоить основы языка и уверенно двигаться дальше к ботам.

Для старта можно взять тариф "Подписка" — он даёт доступ именно к базовому курсу по Python. Простые пошаговые уроки, поддержка и уже с первых занятий — настоящие проекты.

Освоить базу — значит легко справиться с созданием ботов и получать от этого настоящее удовольствие!

Рассказать подробнее про курс "Python для начинающих" или всё-таки про создание Telegram-ботов?"""
        
        # Создаем специальную клавиатуру с двумя кнопками
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📚 Рассказать про Python", callback_data="course_info:Python Level 1")],
            [InlineKeyboardButton(text="🤖 Рассказать про ТГ ботов", callback_data="course_info:Создание телеграм-ботов")],
            [InlineKeyboardButton(text="🌐 Посмотреть все курсы", url="https://codim.online/demo1/entrance")],
            [InlineKeyboardButton(text="🏠 В меню", callback_data="menu")],
            [InlineKeyboardButton(text="⬅ Назад", callback_data="back")]
        ])
        
        # Отправляем специальное сообщение
        await message.answer(special_message, reply_markup=keyboard, parse_mode="HTML")
        await state.set_state(CourseSelection.recommend)
        return
    
    # Специальная обработка для Telegram ботов 12+ с опытом в Python/Java
    if (data.get('interest') == 'tg_bots' and 
        data.get('age') == '12_plus' and 
        data.get('exp') == 'yes' and 
        data.get('stack') in ['langs', 'python', 'java']):
        
        special_message = """🎉 Здравствуйте! Здорово, что ваш ребёнок интересуется созданием телеграм-ботов и уже знаком с программированием — это отличный уровень для выхода на следующий этап!

🤖 <b>Курс "Создание Telegram-ботов на Python"</b> — это не просто обучение, а реальное погружение в то, как технологии работают в жизни.
Ребёнок научится создавать умных ботов, которые могут:
– автоматически отвечать на сообщения,
– вести опросы и квизы,
– присылать напоминания,
– искать информацию в интернете и даже управлять списками дел.

💡 Это настоящий шаг от обучения к созданию полезных продуктов, которые можно показать друзьям, родным или использовать в повседневной жизни.

<b>Почему стоит пройти курс:</b>

• Закрепление Python на практике.
• Развитие проектного мышления: от идеи до готового результата.
• Навык, востребованный в реальной жизни и даже в будущем обучении или карьере.

📦 В курсе — пошаговые уроки, понятные объяснения, поддержка преподавателя и готовые проекты. Учиться легко и интересно!
И да, будет сертификат, для вашего портфолио! 😊"""
        
        # Создаем специальную клавиатуру с кнопкой Telegram ботов
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🎬 Посмотреть демо", callback_data="course_info:Создание телеграм-ботов")],
            [InlineKeyboardButton(text="💰 Узнать стоимость", callback_data="course_price:telegram_bots")],
            [InlineKeyboardButton(text="🌐 Посмотреть все курсы", url="https://codim.online/demo1/entrance")],
            [InlineKeyboardButton(text="🏠 В меню", callback_data="menu")],
            [InlineKeyboardButton(text="⬅ Назад", callback_data="back")]
        ])
        
        # Отправляем специальное сообщение
        await message.answer(special_message, reply_markup=keyboard, parse_mode="HTML")
        await state.set_state(CourseSelection.recommend)
        return
    


        # Специальная обработка для детей 12+ с любым опытом и интересом к языкам программирования
    if (data.get('age') == '12_plus' and data.get('interest') in ['langs', 'programming'] and data.get('stack') in ['any', 'langs', 'python', 'java', 'none']):
        
        special_message = """🎉 Здравствуйте! Я вижу, что ваш ребёнок уже проявляет интерес к программированию и знаком с блочными языками — это отличная база для перехода на текстовые языки, где можно писать настоящий код!

🐍 <b>Python Level 1</b> — идеальный старт для начинающих программистов.
На этом курсе ребёнок освоит один из самых популярных и понятных языков — Python. Он научится работать с переменными, циклами и функциями, а также создавать свои первые программы и визуальные проекты. Python — это лёгкий и дружелюбный язык, который помогает быстро понять логику настоящего программирования.

☕️ <b>Java</b> — это следующий шаг для тех, кто хочет глубже погрузиться в код и понять, как устроены игры, приложения и веб-проекты.
Курс по Java помогает освоить объектно-ориентированное программирование, создавать графические приложения и даже игры вроде «Змейки». Этот курс подойдёт детям, готовым к более серьёзным проектам и желающим писать код на профессиональном уровне.

🤖 <b>Colobot</b> — уникальный курс, где программирование превращается в приключение!
Ребёнок изучает синтаксис, похожий на C++ и Java, и применяет знания прямо в 3D-мире, управляя роботами: добывает ресурсы, строит базы, исследует планеты и защищает колонии.
Colobot помогает не просто учить команды, а понимать, как работает искусственный интеллект и автоматизация. Это отличный переход от учебных примеров к реальной логике программирования.

📚 Каждый курс построен по принципу «от простого к сложному» — с короткими видеоуроками, домашними заданиями, тестами и поддержкой преподавателя.

Эти курсы идеально подходят для возраста и опыта вашего ребёнка. Они помогут не только освоить новые языки программирования, но и развить логическое мышление и креативность.

Какой из курсов больше всего заинтересовал вашего ребёнка? Я с удовольствием расскажу подробнее о любом из них! 😊"""
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🐍 Python Level 1", callback_data="course_info:Python Level 1")],
            [InlineKeyboardButton(text="☕️ Java", callback_data="course_info:Java")],
            [InlineKeyboardButton(text="🤖 Colobot", callback_data="course_info:colobot")],
            [InlineKeyboardButton(text="🌐 Все курсы", url="https://codim.online/demo1/entrance")],
            [InlineKeyboardButton(text="🏠 В меню", callback_data="menu")],
            [InlineKeyboardButton(text="⬅ Назад", callback_data="back")]
        ])

        await message.answer(special_message, reply_markup=keyboard, parse_mode="HTML")
        await state.set_state(CourseSelection.recommend)
        return
    
    # Специальная обработка для веб-сайтов 9-11 лет без опыта
    if (data.get('interest') == 'web_apps' and 
        data.get('age') == '9_11' and 
        data.get('exp') == 'no'):
        
        special_message = """🌐 Отличный выбор! <b>Создание сайтов и приложений</b> — это очень востребованное направление!

💻 <b>AppInventor</b> — идеальный старт для вашего возраста! Это визуальная среда разработки, где ребёнок создаёт настоящие мобильные приложения, просто перетаскивая блоки. Никакого сложного кода — только логика и творчество!

🎯 <b>Что получит ребёнок:</b>
• Создаст своё первое мобильное приложение
• Изучит основы дизайна интерфейсов
• Поймёт, как работают современные технологии
• Разовьёт логическое и креативное мышление

✨ Курс специально разработан для детей 9-11 лет без опыта программирования. Простые пошаговые уроки, поддержка преподавателя и уже с первых занятий — настоящие проекты!

📱 В итоге ребёнок сможет создать и опубликовать своё приложение в Google Play Store!"""
        
        # Создаем клавиатуру с кнопками Демо и Тарифы
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🎬 Посмотреть демо", callback_data="course_info:AppInventor")],
            [InlineKeyboardButton(text="💰 Узнать тарифы", callback_data="course_price:appinventor")],
            [InlineKeyboardButton(text="🌐 Посмотреть все курсы", url="https://codim.online/demo1/entrance")],
            [InlineKeyboardButton(text="🏠 В меню", callback_data="menu")],
            [InlineKeyboardButton(text="⬅ Назад", callback_data="back")]
        ])
        
        # Отправляем специальное сообщение
        await message.answer(special_message, reply_markup=keyboard, parse_mode="HTML")
        await state.set_state(CourseSelection.recommend)
        return
    
    # Специальная обработка для ИИ (все возрасты, с опытом и без опыта)
    if (data.get('interest') == 'ai'):
        
        special_message = """Курс "Искусственный интеллект" — это захватывающее путешествие в мир нейросетей, где ребёнок учится не просто пользоваться ИИ, а управлять им с умом!

В курсе мы:
• создаём картинки с помощью нейросетей,
• генерируем видео и делаем монтаж,
• собираем презентации "по щелчку",
• осваиваем интеллект-помощников для учёбы и жизни,
и многое другое!

Ребёнок узнает:
• какие ИИ бывают,
• как правильно с ними общаться,
• и как использовать их для учёбы, творчества и будущей карьеры.

Всего 24 урока, каждый — это новый wow-эффект, практические задания и простые объяснения.

Автор курса — Денис Голиков, признанный эксперт в обучении детей цифровым навыкам.

После курса ребёнок сможет уверенно использовать ИИ для своих проектов, заданий и идей — быть не потребителем, а создателем!

Хочешь посмотреть, как это работает? Отправлю демо-уроки или расскажу про тариф."""
        
        # Создаем клавиатуру с кнопками Демо и Тарифы
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="💰 Узнать стоимость и демо", callback_data="course_price:ai_simple")],
            [InlineKeyboardButton(text="🌐 Посмотреть все курсы", url="https://codim.online/demo1/entrance")],
            [InlineKeyboardButton(text="🏠 В меню", callback_data="menu")],
            [InlineKeyboardButton(text="⬅ Назад", callback_data="back")]
        ])
        
        # Отправляем специальное сообщение
        await message.answer(special_message, reply_markup=keyboard, parse_mode="HTML")
        await state.set_state(CourseSelection.recommend)
        return
    
    # Специальная обработка для дизайна (все возрасты, с опытом и без опыта)
    if (data.get('interest') == 'design'):
        
        special_message = """🎨 Отлично! Дизайн — это творческое направление, которое развивает креативность, чувство стиля и визуальное мышление.

У нас есть несколько классных курсов по дизайну:

🖼️ <b>GIMP</b> — бесплатный аналог Photoshop с похожими возможностями и интерфейсом. Ребёнок научится редактировать изображения, создавать коллажи, работать со слоями и эффектами.

🖌️ <b>Photoshop</b> — курс по самому популярному графическому редактору. Дети осваивают ретушь, работу с текстом, создание коллажей и оформление работ на профессиональном уровне.

🎎 <b>Рисование в стиле Аниме</b> — курс для тех, кто мечтает рисовать любимых персонажей, создавать иллюстрации и учиться аниме-стилю. Здесь раскрываются креативность, фантазия и любовь к визуальным историям.

✨ Все курсы подойдут даже тем, кто никогда не рисовал или не работал с графикой — объясняем просто, учим пошагово и вдохновляем!

❓ Не знаете, что выбрать — GIMP или Photoshop?
Пройдите короткий марафон, где выполняем одинаковые задания в обеих программах.
Попробуете обе — и поймёте, какая подойдёт именно вам! 🎯

Какой курс хотите попробовать первым? Или сразу отправить ссылку на марафон?"""
        
        # Создаем клавиатуру с кнопками курсов дизайна
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🖼️ GIMP", callback_data="course_info:GIMP")],
            [InlineKeyboardButton(text="🖌️ Photoshop", callback_data="course_info:Photoshop")],
            [InlineKeyboardButton(text="🎎 Рисование в стиле Аниме", callback_data="course_info:Рисование аниме")],
            [InlineKeyboardButton(text="🎯 Марафон Photoshop + GIMP", url="https://codim.online/ps_gimp_marafon")],
            [InlineKeyboardButton(text="🌐 Посмотреть все курсы", url="https://codim.online/demo1/entrance")],
            [InlineKeyboardButton(text="🏠 В меню", callback_data="menu")],
            [InlineKeyboardButton(text="⬅ Назад", callback_data="back")]
        ])
        
        # Отправляем специальное сообщение
        await message.answer(special_message, reply_markup=keyboard, parse_mode="HTML")
        await state.set_state(CourseSelection.recommend)
        return
    
    # Специальная обработка для 3D (все возрасты, с опытом и без опыта)
    if (data.get('interest') == '3d'):
        
        special_message = """🧱 Отлично! 3D-моделирование — это увлекательное направление, которое развивает пространственное мышление, креативность и знакомит с современными технологиями!

У нас есть отличный курс по 3D-моделированию:

🎨 <b>3D-моделирование в Tinkercad</b> — это курс, где ребёнок создаёт настоящие 3D-модели с нуля: дома, роботов, машинки, декор и многое другое!

💻 Обучение проходит на платформе Tinkercad — простой и удобной онлайн-программе, которая работает прямо в браузере. Устанавливать ничего не нужно!

💡 Уроки пошаговые и понятные: ребёнок учится работать с формами, совмещать объекты, настраивать детали — и в итоге получает проекты, готовые для 3D-печати.

🎮 А ещё созданные модели можно добавлять в свои игры, например, в Roblox Studio — и использовать как собственные игровые объекты!

📚 В курсе — 32 основных урока + 3 бесплатных демо, чтобы попробовать прямо сейчас.

✨ Развивает креативность, точность и пространственное мышление. Идеально даже для тех, кто только начинает.

👇 Нажмите на кнопку — и ваш ребёнок сделает свой первый 3D-проект уже сегодня!"""
        
        # Создаем клавиатуру с кнопками для 3D курса
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🧱 3D Tinkercad", callback_data="course_info:3D Tinkercad")],
            [InlineKeyboardButton(text="🌐 Посмотреть все курсы", url="https://codim.online/demo1/entrance")],
            [InlineKeyboardButton(text="🏠 В меню", callback_data="menu")],
            [InlineKeyboardButton(text="⬅ Назад", callback_data="back")]
        ])
        
        # Отправляем специальное сообщение
        await message.answer(special_message, reply_markup=keyboard, parse_mode="HTML")
        await state.set_state(CourseSelection.recommend)
        return
    
    # Специальная обработка для роботов 9-11 лет без опыта
    if (data.get('interest') == 'robots' and 
        data.get('age') == '9_11' and 
        data.get('exp') == 'no'):
        
        special_message = """🤖 Курс по Ардуино — очень классный, но он подойдёт тем, кто уже уверенно работает с кодом и имеет опыт программирования. Он на C++ и требует хорошей базы.

💡 А для начала я бы порекомендовала попробовать курс с блочным программированием, например, "Minecraft: робот-черепашка".
Да-да, черепашка — тоже робот! Только без проводов и пайки 😄

В нём ребёнок учится управлять "железом" в игре: копать, строить, проходить лабиринты — и всё через программирование. Это идеальный старт, чтобы понять логику, команды и алгоритмы.

✨ Начать просто, интересно и безопасно. А после — можно и на настоящих роботов переходить!

Готовы попробовать? Отправлю демо и расскажу про тариф 😊"""
        
        # Создаем клавиатуру с кнопками Демо и Тарифы
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🎬 Посмотреть демо", callback_data="course_info:Minecraft: робот-черепашка")],
            [InlineKeyboardButton(text="💰 Узнать тарифы", callback_data="course_price:logical_tasks_minecraft")],
            [InlineKeyboardButton(text="🌐 Посмотреть все курсы", url="https://codim.online/demo1/entrance")],
            [InlineKeyboardButton(text="🏠 В меню", callback_data="menu")],
            [InlineKeyboardButton(text="⬅ Назад", callback_data="back")]
        ])
        
        # Отправляем специальное сообщение
        await message.answer(special_message, reply_markup=keyboard, parse_mode="HTML")
        await state.set_state(CourseSelection.recommend)
        return
    
    # Специальная обработка для роботов 9-11 лет с опытом в блочном программировании
    if (data.get('interest') == 'robots' and 
        data.get('age') == '9_11' and 
        data.get('exp') == 'yes' and 
        data.get('stack') == 'blocks'):
        
        special_message = """🎉 Здравствуйте! Классно, что ваш ребёнок интересуется роботами — это отличное направление для развития технического мышления!

🤖 Курс по Arduino — действительно крутой, но он подойдёт ребятам 10+ лет с опытом программирования, особенно в текстовом коде (на C++). Здесь мы работаем с реальными устройствами: собираем умные лампы, датчики, управляем моторами и светодиодами.

🛠 Если опыт пока небольшой — отличным стартом станет курс "Minecraft: робот-черепашка".
Тот же робот, только в пикселях 😄 Ребёнок будет программировать виртуального помощника, учиться алгоритмам, циклам и логике — в игровой форме и с интересом.

✨ Отличная база для уверенного перехода к Arduino в будущем!

🎁 Попробовать свои силы можно на 3 открытых демо-уроках.
👉 Нажмите на кнопку ниже — и посмотрите, как проходит обучение!"""
        
        # Создаем клавиатуру с кнопками Демо Arduino, Тарифы Arduino и Курс Minecraft
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🎬 Демо Arduino", callback_data="course_info:Arduino")],
            [InlineKeyboardButton(text="💰 Тарифы Arduino", callback_data="course_price:arduino")],
            [InlineKeyboardButton(text="🎮 Курс Minecraft", callback_data="course_info:Логические задачи в Minecraft")],
            [InlineKeyboardButton(text="🌐 Посмотреть все курсы", url="https://codim.online/demo1/entrance")],
            [InlineKeyboardButton(text="🏠 В меню", callback_data="menu")],
            [InlineKeyboardButton(text="⬅ Назад", callback_data="back")]
        ])
        
        # Отправляем специальное сообщение
        await message.answer(special_message, reply_markup=keyboard, parse_mode="HTML")
        await state.set_state(CourseSelection.recommend)
        return
    
    # Специальная обработка для роботов 9-11 лет с опытом "другое"
    if (data.get('interest') == 'robots' and 
        data.get('age') == '9_11' and 
        data.get('exp') == 'yes' and 
        data.get('stack') == 'other'):
        
        special_message = """🎉 Здравствуйте! Классно, что ваш ребёнок интересуется роботами — это отличное направление для развития технического мышления!

🤖 Курс по Arduino — действительно крутой, но он подойдёт ребятам 10+ лет с опытом программирования, особенно в текстовом коде (на C++). Здесь мы работаем с реальными устройствами: собираем умные лампы, датчики, управляем моторами и светодиодами.

🛠 Если опыт пока небольшой — отличным стартом станет курс "Minecraft: робот-черепашка".
Тот же робот, только в пикселях 😄 Ребёнок будет программировать виртуального помощника, учиться алгоритмам, циклам и логике — в игровой форме и с интересом.

✨ Отличная база для уверенного перехода к Arduino в будущем!

🎁 Попробовать свои силы можно на 3 открытых демо-уроках.
👉 Нажмите на кнопку ниже — и посмотрите, как проходит обучение!"""
        
        # Создаем клавиатуру с кнопками Демо и Тарифы (без кнопки Arduino)
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🎬 Посмотреть демо", callback_data="course_info:Логические задачи в Minecraft")],
            [InlineKeyboardButton(text="💰 Узнать тарифы", callback_data="course_price:logical_tasks_minecraft")],
            [InlineKeyboardButton(text="🌐 Посмотреть все курсы", url="https://codim.online/demo1/entrance")],
            [InlineKeyboardButton(text="🏠 В меню", callback_data="menu")],
            [InlineKeyboardButton(text="⬅ Назад", callback_data="back")]
        ])
        
        # Отправляем специальное сообщение
        await message.answer(special_message, reply_markup=keyboard, parse_mode="HTML")
        await state.set_state(CourseSelection.recommend)
        return
    
    # Специальная обработка для игр 12+ без опыта
    if (data.get('interest') == 'games' and 
        data.get('age') == '12_plus' and 
        data.get('exp') == 'no'):
        
        special_message = """🎮 <b>Roblox Studio</b> — идеальная платформа для начинающих. Здесь ребёнок научится создавать собственные 3D-игры, изучит основы визуального программирования и начнёт работать с языком Lua. Простая среда и быстрый результат отлично мотивируют продолжать обучение.

🚀 <b>Unity (блочное программирование)</b> — это курс по работе в профессиональной игровой платформе Unity, на которой создаются настоящие игры для ПК, мобильных устройств и консолей.
В этом курсе ребёнок сначала программирует с помощью интуитивно понятных блоков, а затем плавно переходит к настоящему коду на языке C#. Такой подход помогает легко освоить сложные вещи и не потерять интерес на старте.

🧠 Оба курса отлично подходят детям без опыта — они развивают креативность, логическое мышление и учат доводить проект до конца. А возможность создавать свои игры с нуля вдохновляет и показывает, как работают настоящие игровые технологии.

📌 Подскажите, какой из курсов заинтересовал вашего ребёнка больше? Я с удовольствием расскажу подробнее и помогу подобрать подходящий формат обучения! 😊"""
        
        # Создаем клавиатуру с кнопками курсов
        keyboard = get_recommendation_keyboard(recommendations["courses"])
        
        # Отправляем специальное сообщение
        await message.answer(special_message, reply_markup=keyboard, parse_mode="HTML")
        await state.set_state(CourseSelection.recommend)
        return
    
    # Формируем контекст для GPT
    if is_teacher:
        user_context = f"""
Информация о учениках:
Интерес: {data.get('interest', 'не указан')}
Возраст: {data.get('age', 'не указан')}
Опыт программирования: {'есть' if data.get('exp') == 'yes' else 'нет'}
Предыдущий опыт: {data.get('stack', 'не указан') if data.get('exp') == 'yes' else 'нет опыта'}

Рекомендуемые курсы: {', '.join(recommendations['courses'])}
Дополнительная информация: {recommendations.get('note', 'нет')}
"""
        question = "Подбери и красиво представь курсы для моих учеников на основе собранной информации. Используй формулировку 'ваши ученики' вместо 'ребёнок'."
    else:
        user_context = f"""
Интерес: {data.get('interest', 'не указан')}
Возраст: {data.get('age', 'не указан')}
Опыт программирования: {'есть' if data.get('exp') == 'yes' else 'нет'}
Предыдущий опыт: {data.get('stack', 'не указан') if data.get('exp') == 'yes' else 'нет опыта'}

Рекомендуемые курсы: {', '.join(recommendations['courses'])}
Дополнительная информация: {recommendations.get('note', 'нет')}
"""
        question = "Подбери и красиво представь курсы на основе собранной информации о пользователе"
    
    try:
        # Получаем ответ от GPT
        gpt_response = await ask_gpt(
            question=question,
            knowledge="",
            agent_prompt_file="course_selection.md",
            history="",
            user_data=user_context
        )
        
        # Создаем клавиатуру с кнопками курсов
        keyboard = get_recommendation_keyboard(recommendations["courses"])
        
        # Отправляем красивый ответ от GPT с кнопками курсов
        await message.answer(gpt_response, reply_markup=keyboard, parse_mode="HTML")
        await state.set_state(CourseSelection.recommend)
        
    except Exception as e:
        logger.error(f"Ошибка при обращении к GPT: {e}")
        
        # Fallback: показываем стандартные рекомендации
        text = format_recommendations(recommendations)
        keyboard = get_recommendation_keyboard(recommendations["courses"])
        
        await message.answer(
            f"📝 {text}\n\n"
            "К сожалению, не удалось получить персонализированные рекомендации. "
            "Но вот что мы можем предложить:",
            reply_markup=keyboard
        )
        await state.set_state(CourseSelection.recommend)

# Обработчики навигации
@router.callback_query(F.data == "menu")
async def go_to_menu(callback: CallbackQuery, state: FSMContext):
    """Возврат в главное меню"""
    from bot.handlers.dialog import start_keyboard
    
    await callback.message.answer(
        "👋 Здравствуйте, спасибо за интерес к школе программирования Codim.online! Я виртуальный помощник и помогу вам с выбором оптимального курса, расскажу о форматах обучения и тарифах.\n\n"
        "Выберите вариант:",
        reply_markup=start_keyboard
    )
    await state.clear()
    await callback.answer()

@router.callback_query(F.data == "back")
async def go_back(callback: CallbackQuery, state: FSMContext):
    """Возврат назад"""
    current_state = await state.get_state()
    
    if current_state == CourseSelection.age:
        # Возвращаемся в главное меню (возраст - первый шаг)
        await go_to_menu(callback, state)
        return
    elif current_state == CourseSelection.interest:
        # Возвращаемся к выбору возраста
        await callback.message.answer(
            "Сначала скажите, какой у вас возраст?",
            reply_markup=get_age_keyboard()
        )
        await state.set_state(CourseSelection.age)
    elif current_state == CourseSelection.experience:
        # Возвращаемся к выбору интереса
        await callback.message.answer(
            "Отлично! Теперь скажите, что бы вы хотели изучать?",
            reply_markup=get_interest_keyboard()
        )
        await state.set_state(CourseSelection.interest)
    elif current_state == CourseSelection.stack:
        # Возвращаемся к выбору опыта
        await callback.message.answer(
            "Есть ли опыт в программировании?",
            reply_markup=get_experience_keyboard()
        )
        await state.set_state(CourseSelection.experience)
    elif current_state == CourseSelection.recommend:
        # Возвращаемся к выбору стека или опыта, или к выбору возраста для младших
        data = await state.get_data()
        age = data.get("age", "")
        interest = data.get("interest", "")
        
        # Для дизайна, ИИ и 3D возвращаемся к выбору интереса (они пропускают опыт)
        if interest in ["design", "ai", "3d"]:
            await callback.message.answer(
                "Отлично! Теперь скажите, что бы вы хотели изучать?",
                reply_markup=get_interest_keyboard()
            )
            await state.set_state(CourseSelection.interest)
        elif age in ["5_6", "7_8"]:
            # Для младших возрастов возвращаемся к выбору возраста
            await callback.message.answer(
                "Сначала скажите, какой у вас возраст?",
                reply_markup=get_age_keyboard()
            )
            await state.set_state(CourseSelection.age)
        elif data.get("exp") == "yes":
            await callback.message.answer(
                "Что изучали раньше?",
                reply_markup=get_stack_keyboard()
            )
            await state.set_state(CourseSelection.stack)
        else:
            await callback.message.answer(
                "Есть ли опыт в программировании?",
                reply_markup=get_experience_keyboard()
            )
            await state.set_state(CourseSelection.experience)
    
    await callback.answer()



# Обработчики действий с курсами
@router.callback_query(F.data.startswith("course_info:"))
async def handle_course_info(callback: CallbackQuery, state: FSMContext):
    """Обработка выбора курса - показывает подробную информацию"""
    course_name = callback.data.split(":", 1)[1]
    
    # Преобразуем название курса в slug
    course_slug = course_name_to_slug(course_name)
    
    # Получаем отформатированную информацию о курсе
    course_info = format_course_info(course_slug)
    
    # Проверяем, является ли это Telegram-ботами из специального сообщения
    # Если да, то показываем минимальную клавиатуру без кнопки "Узнать стоимость и демо"
    if course_name == "Создание телеграм-ботов":
        # Создаем минимальную клавиатуру для Telegram ботов
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🏠 В меню", callback_data="menu")],
            [InlineKeyboardButton(text="⬅ Назад", callback_data="back")]
        ])
    else:
        # Создаем стандартную клавиатуру с кнопкой для получения стоимости и демо
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="💰 Узнать стоимость и демо", callback_data=f"course_price:{course_slug}")],
            [InlineKeyboardButton(text="🏠 В меню", callback_data="menu")],
            [InlineKeyboardButton(text="⬅ Назад", callback_data="back")]
        ])
    
    await callback.message.answer(
        course_info,
        reply_markup=keyboard,
        parse_mode="HTML"
    )
    await callback.answer()

@router.callback_query(F.data == "python_from_scratch")
async def handle_python_from_scratch(callback: CallbackQuery, state: FSMContext):
    """Обработка кнопки 'Хочу начать учить Python с нуля'"""
    # Получаем информацию о Python Level 1
    course_slug = course_name_to_slug("Python Level 1")
    course_info = format_course_info(course_slug)
    
    # Создаем клавиатуру с кнопкой для получения стоимости и демо
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💰 Узнать стоимость и демо", callback_data=f"course_price:{course_slug}")],
        [InlineKeyboardButton(text="🏠 В меню", callback_data="menu")],
        [InlineKeyboardButton(text="⬅ Назад", callback_data="back")]
    ])
    
    await callback.message.answer(
        course_info,
        reply_markup=keyboard,
        parse_mode="HTML"
    )
    await callback.answer()

@router.callback_query(F.data.startswith("course_price:"))
async def handle_course_price(callback: CallbackQuery, state: FSMContext):
    """Обработка запроса стоимости и демо курса"""
    course_slug = callback.data.split(":", 1)[1]
    
    # Получаем информацию о стоимости
    price_info = get_course_price_info(course_slug)
    
    # Получаем ссылку на курс для кнопки
    course = get_course_description(course_slug)
    course_link = course.get('course_link', '') if course else ''
    registration_link = f"{course_link}#registration" if course_link else "https://codim.online"
    
    # Создаем клавиатуру с кнопками действий
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💳 Перейти к выбору тарифа", url=registration_link)],
        [InlineKeyboardButton(text="👨‍💼 Консультация менеджера", callback_data="manager")],
        [InlineKeyboardButton(text="🏠 В меню", callback_data="menu")],
        [InlineKeyboardButton(text="⬅ Назад", callback_data="back")]
    ])
    
    await callback.message.answer(
        price_info,
        reply_markup=keyboard,
        parse_mode="HTML"
    )
    await callback.answer()

@router.callback_query(F.data == "lead_signup")
async def handle_lead_signup(callback: CallbackQuery, state: FSMContext):
    """Обработка записи на курс"""
    await callback.message.answer(
        "📝 Отлично! Для записи на курс свяжитесь с нашим менеджером:\n\n"
        "📞 Телефон: +7 (XXX) XXX-XX-XX\n"
        "📧 Email: info@codim.online\n"
        "🌐 Сайт: https://codim.online\n\n"
        "Менеджер поможет с выбором тарифа и ответит на все вопросы!"
    )
    await callback.answer()

@router.callback_query(F.data == "trial")
async def handle_trial(callback: CallbackQuery, state: FSMContext):
    """Обработка пробного урока"""
    await callback.message.answer(
        "🎬 Отлично! Пробный урок поможет понять, подходит ли вам курс.\n\n"
        "📋 Запишитесь на пробный урок:\n"
        "🌐 https://codim.online/trial\n\n"
        "Или свяжитесь с менеджером для записи!"
    )
    await callback.answer()

@router.callback_query(F.data == "manager")
async def handle_manager_consultation(callback: CallbackQuery, state: FSMContext):
    """Обработка консультации с менеджером"""
    # Создаем клавиатуру с кнопкой для заполнения анкеты
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📝 Заполнить анкету", url="https://codim.online/2104")],
        [InlineKeyboardButton(text="🏠 В меню", callback_data="menu")],
        [InlineKeyboardButton(text="⬅ Назад", callback_data="back")]
    ])
    
    await callback.message.answer(
        "👨‍💼 Конечно! Наш консультант поможет подобрать вам подходящий курс.\n\n"
        "📞 Телефон: +7 (800) 4440091\n"
        "📱 Только мессенджеры: +79052091715\n\n"
        "Заполните анкету, и наш консультант свяжется с вами в ближайшее время!",
        reply_markup=keyboard
    )
    await callback.answer()
