"""
Логика подбора курсов для бота
"""

# Правила подбора курсов
COURSE_RULES = [
    # --- Младшие возрасты (без выбора интереса) - согласно схеме ---
    {"when": {"age": "5_6"}, "recommend": ["Scratch Junior", "Логические задачи в Minecraft"], "note": "Для самых маленьких - базовые навыки логики и творчества."},
    {"when": {"age": "7_8"}, "recommend": ["Scratch Level 1", "Minecraft"], "note": "Отличный возраст для начала изучения программирования через игры."},
    
    # --- ИИ ---
    {"when": {"interest": "ai", "age": "9_11"}, "recommend": ["Python Level 1"], "note": "Для ИИ сначала Python."},
    {"when": {"interest": "ai", "age": "12_plus"}, "recommend": ["Создание телеграм-ботов"], "note": "Прикладной ИИ на проектах ботов."},

    # --- Телеграм-боты ---
    {"when": {"interest": "tg_bots", "age": "9_11"}, "recommend": ["Python Level 1"], "note": "Боты доступны с базовым Python."},
    {"when": {"interest": "tg_bots", "age": "12_plus", "exp": "no"}, "recommend": ["Python Level 1"], "note": "Для Telegram ботов нужен опыт в Python. Рекомендуем начать с Python Level 1."},
    {"when": {"interest": "tg_bots", "age": "12_plus", "exp": "yes"}, "recommend": ["Создание телеграм-ботов"], "note": "С опытом программирования можно сразу изучать создание ботов."},

    # --- Роботы ---
    {"when": {"interest": "robots", "age": "9_11", "exp": "yes"}, "recommend": ["Arduino"], "note": "Рекомендуется 10+ и базовые навыки кода."},
    {"when": {"interest": "robots", "age": "9_11", "exp": "no"}, "recommend": ["Python Level 1"], "note": "Для Arduino нужен опыт кодинга."},
    {"when": {"interest": "robots", "age": "12_plus"}, "recommend": ["Arduino"]},

    # --- Дизайн ---
    {"when": {"interest": "design", "age": "9_11"}, "recommend": ["AppInventor"]},
    {"when": {"interest": "design", "age": "12_plus"}, "recommend": ["Web-программирование", "AppInventor"], "note": "В приоритете Web-программирование."},

    # --- 3D ---
    {"when": {"interest": "3d", "age": "9_11", "exp": "yes"}, "recommend": ["3D Tinkercad", "Arduino"], "note": "Arduino — при возрасте 10+."},
    {"when": {"interest": "3d", "age": "9_11", "exp": "no"}, "recommend": ["3D Tinkercad"]},
    {"when": {"interest": "3d", "age": "12_plus"}, "recommend": ["3D Tinkercad", "Arduino"]},

    # --- Создание игр ---
    {"when": {"interest": "games", "age": "9_11"}, "recommend": ["Roblox", "Minecraft", "CoSpaces"]},
    {"when": {"interest": "games", "age": "12_plus"}, "recommend": ["Roblox", "Unity (блоки)"]},

    # --- Языки программирования ---
    {"when": {"interest": "langs", "age": "9_11", "exp": "yes", "stack": "langs"}, "recommend": ["Python Level 2", "Python в Minecraft", "Хочу начать учить Python с нуля"], "note": "С опытом в языках программирования - продвинутый уровень."},
    {"when": {"interest": "langs", "age": "9_11"}, "recommend": ["Python Level 1", "Roblox"]},
    {"when": {"interest": "langs", "age": "12_plus", "exp": "yes", "stack": "langs"}, "recommend": ["Python Level 2", "Python в Minecraft", "Хочу начать учить Python с нуля"], "note": "С опытом в языках программирования - продвинутый уровень."},
    {"when": {"interest": "langs", "age": "12_plus"}, "recommend": ["Python Level 1", "Java"]},

    # --- Сайты и приложения ---
    {"when": {"interest": "web_apps", "age": "9_11"}, "recommend": ["AppInventor"]},
    {"when": {"interest": "web_apps", "age": "12_plus"}, "recommend": ["Web-программирование", "AppInventor"]}
]

# Алиасы для возрастов (больше не нужны, так как используем точные возрастные группы)
AGE_ALIASES = {}

def find_matching_courses(user_data: dict) -> dict:
    """
    Находит подходящие курсы на основе данных пользователя
    
    Args:
        user_data: Словарь с данными пользователя (interest, age, exp, stack)
    
    Returns:
        Словарь с рекомендациями и заметками
    """
    # Нормализуем возраст
    age = user_data.get("age", "")
    if age in AGE_ALIASES:
        age = AGE_ALIASES[age]
    
    # Ищем подходящие правила
    matching_rules = []
    
    for rule in COURSE_RULES:
        when_conditions = rule.get("when", {})
        
        # Проверяем все условия
        matches = True
        for key, value in when_conditions.items():
            if user_data.get(key) != value:
                matches = False
                break
        
        if matches:
            matching_rules.append(rule)
    
    if not matching_rules:
        return {
            "courses": ["Scratch Level 1", "Minecraft"],
            "notes": "Подобрали базовые курсы для начала обучения."
        }
    
    # Берем первое подходящее правило
    best_rule = matching_rules[0]
    
    # Убираем дубли и ограничиваем количество курсов
    courses = list(set(best_rule.get("recommend", [])))
    if len(courses) > 3:
        courses = courses[:3]
    
    return {
        "courses": courses,
        "notes": best_rule.get("note", "")
    }

def format_recommendations(recommendations: dict) -> str:
    """
    Форматирует рекомендации в текст
    
    Args:
        recommendations: Словарь с курсами и заметками
    
    Returns:
        Отформатированный текст рекомендаций
    """
    # Фильтруем кнопку "Хочу начать учить Python с нуля" из текста
    text_courses = [course for course in recommendations["courses"] if course != "Хочу начать учить Python с нуля"]
    courses_text = "\n".join([f"• {course}" for course in text_courses])
    notes_text = f"\n\n💡 {recommendations['notes']}" if recommendations["notes"] else ""
    
    return f"Рекомендации:\n{courses_text}{notes_text}"
